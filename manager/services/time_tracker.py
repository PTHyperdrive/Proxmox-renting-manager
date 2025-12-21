"""
Time Tracker Service

Calculates VM running time and manages session records.
Manager version - receives data from client nodes.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from collections import defaultdict

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import VMSession, get_db_context
from ..models.schemas import VMUsage

logger = logging.getLogger(__name__)


class TimeTracker:
    """
    Tracks VM running time from session records in the database.
    """
    
    async def get_vm_usage(
        self,
        vm_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        node: Optional[str] = None,
        db: Optional[AsyncSession] = None
    ) -> VMUsage:
        """
        Calculate total usage for a VM within a date range.
        
        Args:
            vm_id: VM identifier
            start_date: Start of period (None = beginning of time)
            end_date: End of period (None = now)
            node: Optional: filter by specific node
            db: Optional database session
            
        Returns:
            VMUsage object with calculated statistics
        """
        async def _get_usage(session: AsyncSession) -> VMUsage:
            conditions = [VMSession.vm_id == vm_id]
            
            if node:
                conditions.append(VMSession.node == node)
            
            if start_date:
                conditions.append(VMSession.start_time >= start_date)
            
            if end_date:
                conditions.append(
                    or_(
                        VMSession.end_time <= end_date,
                        VMSession.end_time.is_(None)
                    )
                )
            
            result = await session.execute(
                select(VMSession).where(and_(*conditions))
            )
            sessions = result.scalars().all()
            
            total_seconds = 0
            session_count = len(sessions)
            
            for sess in sessions:
                if sess.duration_seconds:
                    duration = sess.duration_seconds
                else:
                    end = end_date or datetime.utcnow()
                    if sess.start_time:
                        duration = int((end - sess.start_time).total_seconds())
                    else:
                        duration = 0
                
                if start_date and sess.start_time < start_date:
                    pre_range = int((start_date - sess.start_time).total_seconds())
                    duration = max(0, duration - pre_range)
                
                if end_date and sess.end_time and sess.end_time > end_date:
                    post_range = int((sess.end_time - end_date).total_seconds())
                    duration = max(0, duration - post_range)
                
                total_seconds += duration
            
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            formatted = f"{hours}h {minutes}m"
            
            return VMUsage(
                vm_id=vm_id,
                node=node,
                total_seconds=total_seconds,
                total_hours=total_seconds / 3600.0,
                session_count=session_count,
                formatted_duration=formatted,
                period_start=start_date,
                period_end=end_date
            )
        
        if db:
            return await _get_usage(db)
        else:
            async with get_db_context() as session:
                return await _get_usage(session)
    
    async def get_all_vms_usage(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        node: Optional[str] = None
    ) -> List[VMUsage]:
        """Get usage for all tracked VMs."""
        async with get_db_context() as db:
            query = select(VMSession.vm_id, VMSession.node).distinct()
            if node:
                query = query.where(VMSession.node == node)
            
            result = await db.execute(query)
            rows = result.fetchall()
            
            usages = []
            for row in rows:
                usage = await self.get_vm_usage(row.vm_id, start_date, end_date, row.node, db)
                usages.append(usage)
            
            return sorted(usages, key=lambda u: u.total_seconds, reverse=True)
    
    async def get_daily_breakdown(
        self,
        vm_id: str,
        start_date: datetime,
        end_date: datetime,
        node: Optional[str] = None
    ) -> Dict[str, int]:
        """Get daily usage breakdown for a VM."""
        daily = defaultdict(int)
        
        async with get_db_context() as db:
            conditions = [
                VMSession.vm_id == vm_id,
                VMSession.start_time >= start_date,
                or_(
                    VMSession.end_time <= end_date,
                    VMSession.end_time.is_(None)
                )
            ]
            if node:
                conditions.append(VMSession.node == node)
            
            result = await db.execute(
                select(VMSession).where(and_(*conditions))
            )
            sessions = result.scalars().all()
            
            for session in sessions:
                sess_start = max(session.start_time, start_date)
                sess_end = min(
                    session.end_time or datetime.utcnow(),
                    end_date
                )
                
                current = sess_start.replace(hour=0, minute=0, second=0, microsecond=0)
                while current < sess_end:
                    next_day = current + timedelta(days=1)
                    
                    day_start = max(sess_start, current)
                    day_end = min(sess_end, next_day)
                    
                    if day_end > day_start:
                        seconds = int((day_end - day_start).total_seconds())
                        daily[current.strftime('%Y-%m-%d')] += seconds
                    
                    current = next_day
        
        return dict(daily)
    
    async def get_current_running(self, node: Optional[str] = None) -> List[VMSession]:
        """Get all currently running VM sessions."""
        async with get_db_context() as db:
            query = select(VMSession).where(VMSession.is_running == True)
            if node:
                query = query.where(VMSession.node == node)
            
            result = await db.execute(query)
            return list(result.scalars().all())
    
    async def start_session(
        self,
        vm_id: str,
        node: str,
        user: Optional[str] = None,
        start_time: Optional[datetime] = None
    ) -> VMSession:
        """Manually start a new session."""
        async with get_db_context() as db:
            session = VMSession(
                vm_id=vm_id,
                node=node,
                start_time=start_time or datetime.utcnow(),
                user=user,
                is_running=True
            )
            db.add(session)
            await db.flush()
            await db.refresh(session)
            return session
    
    async def stop_session(
        self,
        session_id: int,
        end_time: Optional[datetime] = None
    ) -> Optional[VMSession]:
        """Manually stop a session."""
        async with get_db_context() as db:
            result = await db.execute(
                select(VMSession).where(VMSession.id == session_id)
            )
            session = result.scalar_one_or_none()
            
            if session:
                session.end_time = end_time or datetime.utcnow()
                session.is_running = False
                session.duration_seconds = session.calculate_duration()
                await db.flush()
                await db.refresh(session)
            
            return session
