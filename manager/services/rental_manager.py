"""
Rental Manager Service

Manages rental periods and generates usage reports.
"""

import logging
from datetime import datetime
from typing import List, Optional
from calendar import monthrange

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import Rental, VMSession, get_db_context
from ..models.schemas import (
    RentalCreate, RentalUpdate,
    UsageReport, VMSessionResponse, DailyUsage, MonthlyUsage
)
from .time_tracker import TimeTracker

logger = logging.getLogger(__name__)


class RentalManager:
    """Manages VM rental periods and generates usage reports."""
    
    def __init__(self, time_tracker: Optional[TimeTracker] = None):
        self.time_tracker = time_tracker or TimeTracker()
    
    async def create_rental(self, rental_data: RentalCreate) -> Rental:
        """Create a new rental period."""
        async with get_db_context() as db:
            rental = Rental(
                vm_id=rental_data.vm_id,
                node=rental_data.node,
                customer_name=rental_data.customer_name,
                customer_email=rental_data.customer_email,
                rental_start=rental_data.rental_start,
                rental_end=rental_data.rental_end,
                billing_cycle=rental_data.billing_cycle,
                rate_per_hour=rental_data.rate_per_hour,
                notes=rental_data.notes,
                is_active=True
            )
            db.add(rental)
            await db.flush()
            await db.refresh(rental)
            
            logger.info(f"Created rental {rental.id} for VM {rental.vm_id}")
            return rental
    
    async def update_rental(
        self,
        rental_id: int,
        update_data: RentalUpdate
    ) -> Optional[Rental]:
        """Update a rental period."""
        async with get_db_context() as db:
            result = await db.execute(
                select(Rental).where(Rental.id == rental_id)
            )
            rental = result.scalar_one_or_none()
            
            if not rental:
                return None
            
            update_dict = update_data.model_dump(exclude_unset=True)
            for field, value in update_dict.items():
                setattr(rental, field, value)
            
            await db.flush()
            await db.refresh(rental)
            
            logger.info(f"Updated rental {rental_id}")
            return rental
    
    async def delete_rental(self, rental_id: int) -> bool:
        """Delete a rental period."""
        async with get_db_context() as db:
            result = await db.execute(
                select(Rental).where(Rental.id == rental_id)
            )
            rental = result.scalar_one_or_none()
            
            if not rental:
                return False
            
            await db.delete(rental)
            logger.info(f"Deleted rental {rental_id}")
            return True
    
    async def get_rental(self, rental_id: int) -> Optional[Rental]:
        """Get a rental by ID."""
        async with get_db_context() as db:
            result = await db.execute(
                select(Rental).where(Rental.id == rental_id)
            )
            return result.scalar_one_or_none()
    
    async def get_rentals(
        self,
        vm_id: Optional[str] = None,
        node: Optional[str] = None,
        active_only: bool = False
    ) -> List[Rental]:
        """Get rentals with optional filtering."""
        async with get_db_context() as db:
            conditions = []
            
            if vm_id:
                conditions.append(Rental.vm_id == vm_id)
            
            if node:
                conditions.append(Rental.node == node)
            
            if active_only:
                conditions.append(Rental.is_active == True)
            
            query = select(Rental)
            if conditions:
                query = query.where(and_(*conditions))
            
            query = query.order_by(Rental.rental_start.desc())
            
            result = await db.execute(query)
            return list(result.scalars().all())
    
    async def get_active_rental_for_vm(self, vm_id: str) -> Optional[Rental]:
        """Get the current active rental for a VM."""
        async with get_db_context() as db:
            result = await db.execute(
                select(Rental).where(
                    and_(
                        Rental.vm_id == vm_id,
                        Rental.is_active == True
                    )
                ).order_by(Rental.rental_start.desc()).limit(1)
            )
            return result.scalar_one_or_none()
    
    async def generate_usage_report(
        self,
        rental_id: int,
        report_start: Optional[datetime] = None,
        report_end: Optional[datetime] = None
    ) -> Optional[UsageReport]:
        """Generate a usage report for a rental period."""
        rental = await self.get_rental(rental_id)
        if not rental:
            return None
        
        start = report_start or rental.rental_start
        end = report_end or rental.rental_end or datetime.utcnow()
        
        async with get_db_context() as db:
            conditions = [
                VMSession.vm_id == rental.vm_id,
                VMSession.start_time >= start,
                VMSession.start_time <= end
            ]
            if rental.node:
                conditions.append(VMSession.node == rental.node)
            
            result = await db.execute(
                select(VMSession).where(and_(*conditions))
                .order_by(VMSession.start_time)
            )
            sessions = list(result.scalars().all())
        
        usage = await self.time_tracker.get_vm_usage(
            rental.vm_id,
            start_date=start,
            end_date=end,
            node=rental.node
        )
        
        total_cost = None
        if rental.rate_per_hour:
            total_cost = usage.total_hours * rental.rate_per_hour
        
        session_responses = [
            VMSessionResponse.model_validate(s) for s in sessions
        ]
        
        return UsageReport(
            rental_id=rental_id,
            vm_id=rental.vm_id,
            customer_name=rental.customer_name,
            report_start=start,
            report_end=end,
            total_seconds=usage.total_seconds,
            total_hours=usage.total_hours,
            session_count=usage.session_count,
            formatted_duration=usage.formatted_duration,
            sessions=session_responses,
            rate_per_hour=rental.rate_per_hour,
            total_cost=total_cost
        )
    
    async def generate_monthly_report(
        self,
        rental_id: int,
        year: int,
        month: int
    ) -> Optional[MonthlyUsage]:
        """Generate a monthly usage report with daily breakdown."""
        rental = await self.get_rental(rental_id)
        if not rental:
            return None
        
        _, last_day = monthrange(year, month)
        month_start = datetime(year, month, 1)
        month_end = datetime(year, month, last_day, 23, 59, 59)
        
        start = max(month_start, rental.rental_start)
        end = min(month_end, rental.rental_end or datetime.utcnow())
        
        if start > end:
            return MonthlyUsage(
                year=year,
                month=month,
                total_seconds=0,
                session_count=0,
                formatted_duration="0h 0m",
                daily_breakdown=[]
            )
        
        daily_data = await self.time_tracker.get_daily_breakdown(
            rental.vm_id, start, end, rental.node
        )
        
        daily_breakdown = []
        for date_str, seconds in sorted(daily_data.items()):
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            daily_breakdown.append(DailyUsage(
                date=datetime.strptime(date_str, '%Y-%m-%d'),
                total_seconds=seconds,
                session_count=0,
                formatted_duration=f"{hours}h {minutes}m"
            ))
        
        total_seconds = sum(daily_data.values())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        
        usage = await self.time_tracker.get_vm_usage(
            rental.vm_id, start, end, rental.node
        )
        
        return MonthlyUsage(
            year=year,
            month=month,
            total_seconds=total_seconds,
            session_count=usage.session_count,
            formatted_duration=f"{hours}h {minutes}m",
            daily_breakdown=daily_breakdown
        )
    
    async def set_rental_start_month(
        self,
        rental_id: int,
        year: int,
        month: int
    ) -> Optional[Rental]:
        """Set the rental start to the first day of a specific month."""
        new_start = datetime(year, month, 1, 0, 0, 0)
        
        return await self.update_rental(
            rental_id,
            RentalUpdate(rental_start=new_start)
        )
