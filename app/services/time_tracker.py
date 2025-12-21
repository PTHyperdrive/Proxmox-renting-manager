"""
Time Tracker Service

Calculates VM running time from parsed events and manages session records.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Tuple
from collections import defaultdict

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import VMSession, get_db_context
from ..models.schemas import VMUsage, SyncResponse
from .log_parser import ProxmoxLogParser, VMEvent

logger = logging.getLogger(__name__)


class TimeTracker:
    """
    Tracks VM running time by matching start/stop events
    and maintaining session records in the database.
    """
    
    def __init__(self, parser: Optional[ProxmoxLogParser] = None):
        self.parser = parser or ProxmoxLogParser()
    
    async def sync_from_logs(
        self,
        since: Optional[datetime] = None,
        vm_ids: Optional[List[str]] = None,
        force: bool = False
    ) -> SyncResponse:
        """
        Sync VM sessions from Proxmox logs to database.
        
        Args:
            since: Only sync events after this datetime
            vm_ids: Only sync these VMs
            force: Force re-sync even if already exists
            
        Returns:
            SyncResponse with statistics
        """
        response = SyncResponse(
            success=True,
            message="Sync completed",
            sessions_created=0,
            sessions_updated=0,
            sessions_skipped=0,
            errors=[]
        )
        
        # Get events from Proxmox
        events = self.parser.get_events(since=since, vm_ids=vm_ids)
        
        if not events:
            response.message = "No events found to sync"
            return response
        
        logger.info(f"Processing {len(events)} events for sync")
        
        async with get_db_context() as db:
            # Group events by VM
            vm_events: Dict[str, List[VMEvent]] = defaultdict(list)
            for event in events:
                vm_events[event.vm_id].append(event)
            
            # Process each VM's events
            for vm_id, vm_event_list in vm_events.items():
                try:
                    created, updated, skipped = await self._process_vm_events(
                        db, vm_id, vm_event_list, force
                    )
                    response.sessions_created += created
                    response.sessions_updated += updated
                    response.sessions_skipped += skipped
                except Exception as e:
                    error_msg = f"Error processing VM {vm_id}: {str(e)}"
                    logger.error(error_msg)
                    response.errors.append(error_msg)
        
        if response.errors:
            response.message = f"Sync completed with {len(response.errors)} errors"
        else:
            response.message = (
                f"Sync completed: {response.sessions_created} created, "
                f"{response.sessions_updated} updated, {response.sessions_skipped} skipped"
            )
        
        return response
    
    async def _process_vm_events(
        self,
        db: AsyncSession,
        vm_id: str,
        events: List[VMEvent],
        force: bool
    ) -> Tuple[int, int, int]:
        """
        Process events for a single VM and create/update sessions.
        
        Returns:
            Tuple of (created, updated, skipped) counts
        """
        created = updated = skipped = 0
        
        # Sort events by timestamp
        sorted_events = sorted(events, key=lambda e: e.timestamp)
        
        # Track pending start events (no matching stop yet)
        pending_starts: Dict[str, VMEvent] = {}
        
        for event in sorted_events:
            if event.is_start and event.is_successful:
                # Check if session already exists
                if not force:
                    existing = await db.execute(
                        select(VMSession).where(VMSession.start_upid == event.upid)
                    )
                    if existing.scalar_one_or_none():
                        skipped += 1
                        continue
                
                # Store as pending start
                pending_starts[event.upid] = event
                
                # Create session (initially running)
                session = VMSession(
                    vm_id=vm_id,
                    node=event.node,
                    start_time=event.timestamp,
                    user=event.user,
                    start_upid=event.upid,
                    is_running=True
                )
                db.add(session)
                created += 1
                
            elif event.is_stop and event.is_successful:
                # Find matching start session (most recent running session)
                result = await db.execute(
                    select(VMSession)
                    .where(
                        and_(
                            VMSession.vm_id == vm_id,
                            VMSession.is_running == True,
                            VMSession.start_time < event.timestamp
                        )
                    )
                    .order_by(VMSession.start_time.desc())
                    .limit(1)
                )
                session = result.scalar_one_or_none()
                
                if session:
                    session.end_time = event.timestamp
                    session.stop_upid = event.upid
                    session.is_running = False
                    session.duration_seconds = session.calculate_duration()
                    updated += 1
                else:
                    # Stop event without matching start - log warning
                    logger.warning(
                        f"Stop event for VM {vm_id} at {event.timestamp} "
                        f"has no matching start session"
                    )
        
        await db.flush()
        return created, updated, skipped
    
    async def get_vm_usage(
        self,
        vm_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        db: Optional[AsyncSession] = None
    ) -> VMUsage:
        """
        Calculate total usage for a VM within a date range.
        
        Args:
            vm_id: VM identifier
            start_date: Start of period (None = beginning of time)
            end_date: End of period (None = now)
            db: Optional database session
            
        Returns:
            VMUsage object with calculated statistics
        """
        async def _get_usage(session: AsyncSession) -> VMUsage:
            # Build query conditions
            conditions = [VMSession.vm_id == vm_id]
            
            if start_date:
                conditions.append(VMSession.start_time >= start_date)
            
            if end_date:
                conditions.append(
                    or_(
                        VMSession.end_time <= end_date,
                        VMSession.end_time.is_(None)  # Include running sessions
                    )
                )
            
            # Get sessions
            result = await session.execute(
                select(VMSession).where(and_(*conditions))
            )
            sessions = result.scalars().all()
            
            # Calculate totals
            total_seconds = 0
            session_count = len(sessions)
            
            for sess in sessions:
                if sess.duration_seconds:
                    # Completed session
                    duration = sess.duration_seconds
                else:
                    # Running session - calculate to end_date or now
                    end = end_date or datetime.utcnow()
                    if sess.start_time:
                        duration = int((end - sess.start_time).total_seconds())
                    else:
                        duration = 0
                
                # Clip duration to date range
                if start_date and sess.start_time < start_date:
                    # Session started before range, adjust
                    pre_range = int((start_date - sess.start_time).total_seconds())
                    duration = max(0, duration - pre_range)
                
                if end_date and sess.end_time and sess.end_time > end_date:
                    # Session ended after range, adjust
                    post_range = int((sess.end_time - end_date).total_seconds())
                    duration = max(0, duration - post_range)
                
                total_seconds += duration
            
            # Format duration
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            formatted = f"{hours}h {minutes}m"
            
            return VMUsage(
                vm_id=vm_id,
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
        end_date: Optional[datetime] = None
    ) -> List[VMUsage]:
        """
        Get usage for all tracked VMs.
        
        Args:
            start_date: Start of period
            end_date: End of period
            
        Returns:
            List of VMUsage objects
        """
        async with get_db_context() as db:
            # Get distinct VM IDs
            result = await db.execute(
                select(VMSession.vm_id).distinct()
            )
            vm_ids = [row[0] for row in result.fetchall()]
            
            usages = []
            for vm_id in vm_ids:
                usage = await self.get_vm_usage(vm_id, start_date, end_date, db)
                usages.append(usage)
            
            return sorted(usages, key=lambda u: u.total_seconds, reverse=True)
    
    async def get_daily_breakdown(
        self,
        vm_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, int]:
        """
        Get daily usage breakdown for a VM.
        
        Args:
            vm_id: VM identifier
            start_date: Start of period
            end_date: End of period
            
        Returns:
            Dict mapping date strings (YYYY-MM-DD) to seconds
        """
        daily = defaultdict(int)
        
        async with get_db_context() as db:
            result = await db.execute(
                select(VMSession).where(
                    and_(
                        VMSession.vm_id == vm_id,
                        VMSession.start_time >= start_date,
                        or_(
                            VMSession.end_time <= end_date,
                            VMSession.end_time.is_(None)
                        )
                    )
                )
            )
            sessions = result.scalars().all()
            
            for session in sessions:
                sess_start = max(session.start_time, start_date)
                sess_end = min(
                    session.end_time or datetime.utcnow(),
                    end_date
                )
                
                # Iterate through each day
                current = sess_start.replace(hour=0, minute=0, second=0, microsecond=0)
                while current < sess_end:
                    next_day = current + timedelta(days=1)
                    
                    # Calculate overlap with this day
                    day_start = max(sess_start, current)
                    day_end = min(sess_end, next_day)
                    
                    if day_end > day_start:
                        seconds = int((day_end - day_start).total_seconds())
                        daily[current.strftime('%Y-%m-%d')] += seconds
                    
                    current = next_day
        
        return dict(daily)
    
    async def get_current_running(self) -> List[VMSession]:
        """Get all currently running VM sessions"""
        async with get_db_context() as db:
            result = await db.execute(
                select(VMSession).where(VMSession.is_running == True)
            )
            return list(result.scalars().all())
    
    async def start_session(
        self,
        vm_id: str,
        node: str,
        user: Optional[str] = None,
        start_time: Optional[datetime] = None
    ) -> VMSession:
        """
        Manually start a new session (for testing or manual tracking).
        
        Args:
            vm_id: VM identifier
            node: Proxmox node name
            user: User who started
            start_time: Session start time (default: now)
            
        Returns:
            Created VMSession
        """
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
        """
        Manually stop a session.
        
        Args:
            session_id: Session ID to stop
            end_time: Session end time (default: now)
            
        Returns:
            Updated VMSession or None if not found
        """
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
