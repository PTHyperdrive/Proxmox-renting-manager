"""
Ingest Service

Handles incoming data from Proxmox client nodes.
Processes VM start/stop events and manages sessions.
"""

import logging
from datetime import datetime
from typing import Optional, Tuple, List

from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import ProxmoxNode, VMSession, TrackedVM, get_db_context
from ..models.schemas import (
    NodeRegisterRequest, NodeRegisterResponse,
    VMStartEvent, VMStartResponse,
    VMStopEvent, VMStopResponse,
    VMStatesSnapshot, VMStatesResponse, VMStateData
)

logger = logging.getLogger(__name__)

# In-memory force sync flags per node
_force_sync_pending = {}  # node_name -> bool


class IngestService:
    """Service for ingesting data from Proxmox clients."""
    
    async def register_node(self, request: NodeRegisterRequest) -> NodeRegisterResponse:
        """Register a new Proxmox node or update existing."""
        async with get_db_context() as db:
            # Check if node exists
            result = await db.execute(
                select(ProxmoxNode).where(ProxmoxNode.name == request.name)
            )
            node = result.scalar_one_or_none()
            
            if node:
                # Update existing
                node.hostname = request.hostname or node.hostname
                node.is_active = True
                node.last_seen = datetime.utcnow()
                await db.flush()
                
                return NodeRegisterResponse(
                    success=True,
                    message=f"Node '{request.name}' updated",
                    node_id=node.id
                )
            else:
                # Create new
                node = ProxmoxNode(
                    name=request.name,
                    hostname=request.hostname,
                    is_active=True,
                    last_seen=datetime.utcnow()
                )
                db.add(node)
                await db.flush()
                await db.refresh(node)
                
                logger.info(f"Registered new node: {request.name}")
                
                return NodeRegisterResponse(
                    success=True,
                    message=f"Node '{request.name}' registered",
                    node_id=node.id
                )
    
    async def handle_vm_start(self, event: VMStartEvent) -> VMStartResponse:
        """
        Handle VM start event.
        Creates a new session for the VM.
        """
        async with get_db_context() as db:
            # Update node last seen
            await self._update_node_seen(db, event.node)
            
            # Update or create tracked VM
            await self._update_tracked_vm(
                db, event.vm_id, event.node, 
                status='running', 
                name=event.vm_name,
                vm_type=event.vm_type
            )
            
            # Check if there's already a running session for this VM
            result = await db.execute(
                select(VMSession).where(
                    and_(
                        VMSession.vm_id == event.vm_id,
                        VMSession.node == event.node,
                        VMSession.is_running == True
                    )
                )
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                # Already running - update start time if this is earlier
                if event.start_time < existing.start_time:
                    existing.start_time = event.start_time
                    await db.flush()
                
                return VMStartResponse(
                    success=True,
                    message=f"VM {event.vm_id} already running",
                    session_id=existing.id
                )
            
            # Create new session
            session = VMSession(
                vm_id=event.vm_id,
                node=event.node,
                start_time=event.start_time,
                user=None,
                is_running=True,
                vm_type=event.vm_type
            )
            db.add(session)
            await db.flush()
            await db.refresh(session)
            
            logger.info(f"VM {event.vm_id} started on {event.node}, session {session.id}")
            
            return VMStartResponse(
                success=True,
                message=f"Session started for VM {event.vm_id}",
                session_id=session.id
            )
    
    async def handle_vm_stop(self, event: VMStopEvent) -> VMStopResponse:
        """
        Handle VM stop event.
        Closes the running session and calculates duration.
        """
        async with get_db_context() as db:
            # Update node last seen
            await self._update_node_seen(db, event.node)
            
            # Update tracked VM status
            await self._update_tracked_vm(db, event.vm_id, event.node, status='stopped')
            
            # Find running session
            result = await db.execute(
                select(VMSession).where(
                    and_(
                        VMSession.vm_id == event.vm_id,
                        VMSession.node == event.node,
                        VMSession.is_running == True
                    )
                ).order_by(VMSession.start_time.desc()).limit(1)
            )
            session = result.scalar_one_or_none()
            
            if not session:
                return VMStopResponse(
                    success=True,
                    message=f"No running session found for VM {event.vm_id}",
                    session_id=None,
                    duration_seconds=None
                )
            
            # Close session
            session.end_time = event.stop_time
            session.is_running = False
            session.duration_seconds = session.calculate_duration()
            await db.flush()
            
            logger.info(
                f"VM {event.vm_id} stopped on {event.node}, "
                f"duration: {session.duration_seconds}s"
            )
            
            return VMStopResponse(
                success=True,
                message=f"Session closed for VM {event.vm_id}",
                session_id=session.id,
                duration_seconds=session.duration_seconds
            )
    
    async def handle_vm_states(self, snapshot: VMStatesSnapshot) -> VMStatesResponse:
        """
        Handle full VM states snapshot.
        Reconciles current VM states with database.
        """
        response = VMStatesResponse(
            success=True,
            message="States processed",
            vms_processed=0,
            sessions_started=0,
            sessions_stopped=0
        )
        
        async with get_db_context() as db:
            # Update node last seen
            await self._update_node_seen(db, snapshot.node)
            
            # Get currently running sessions for this node
            result = await db.execute(
                select(VMSession).where(
                    and_(
                        VMSession.node == snapshot.node,
                        VMSession.is_running == True
                    )
                )
            )
            running_sessions = {s.vm_id: s for s in result.scalars().all()}
            
            # Process each VM in snapshot
            snapshot_vm_ids = set()
            
            for vm in snapshot.vms:
                snapshot_vm_ids.add(vm.vm_id)
                response.vms_processed += 1
                
                # Update tracked VM
                await self._update_tracked_vm(
                    db, vm.vm_id, snapshot.node,
                    status=vm.status,
                    name=vm.name,
                    vm_type=vm.vm_type
                )
                
                is_running = vm.status == 'running'
                has_session = vm.vm_id in running_sessions
                
                if is_running and not has_session:
                    # VM is running but no session - start one
                    # Calculate start time from uptime
                    if vm.uptime > 0:
                        start_time = datetime.utcnow() - __import__('datetime').timedelta(seconds=vm.uptime)
                    else:
                        start_time = snapshot.timestamp
                    
                    session = VMSession(
                        vm_id=vm.vm_id,
                        node=snapshot.node,
                        start_time=start_time,
                        is_running=True,
                        vm_type=vm.vm_type
                    )
                    db.add(session)
                    response.sessions_started += 1
                    logger.info(f"Started missing session for running VM {vm.vm_id}")
                
                elif not is_running and has_session:
                    # VM is stopped but has running session - close it
                    session = running_sessions[vm.vm_id]
                    session.end_time = snapshot.timestamp
                    session.is_running = False
                    session.duration_seconds = session.calculate_duration()
                    response.sessions_stopped += 1
                    logger.info(f"Closed orphan session for stopped VM {vm.vm_id}")
            
            # Check for VMs with running sessions that weren't in snapshot
            for vm_id, session in running_sessions.items():
                if vm_id not in snapshot_vm_ids:
                    # VM no longer exists - close session
                    session.end_time = snapshot.timestamp
                    session.is_running = False
                    session.duration_seconds = session.calculate_duration()
                    response.sessions_stopped += 1
                    logger.info(f"Closed session for removed VM {vm_id}")
            
            await db.flush()
            
            # Update node VM count
            await db.execute(
                update(ProxmoxNode)
                .where(ProxmoxNode.name == snapshot.node)
                .values(total_vms=len(snapshot.vms))
            )
        
        response.message = (
            f"Processed {response.vms_processed} VMs, "
            f"{response.sessions_started} started, "
            f"{response.sessions_stopped} stopped"
        )
        
        return response
    
    async def heartbeat(self, node: str) -> bool:
        """
        Process heartbeat and return force_sync flag.
        """
        await self._update_node_seen_simple(node)
        
        # Check and clear force sync flag
        force_sync = _force_sync_pending.get(node, False)
        if force_sync:
            _force_sync_pending[node] = False
        
        return force_sync
    
    def request_force_sync(self, node: Optional[str] = None) -> int:
        """
        Request force sync from nodes.
        Returns number of nodes that will be notified.
        """
        if node:
            _force_sync_pending[node] = True
            return 1
        else:
            # Request from all known nodes
            # This is a simple in-memory approach
            # For production, you'd want persistent storage
            _force_sync_pending['*'] = True  # Wildcard for all
            return -1  # Unknown count
    
    async def check_force_sync(self, node: str) -> bool:
        """Check if force sync is pending for a node."""
        # Check specific node or wildcard
        return _force_sync_pending.get(node, False) or _force_sync_pending.get('*', False)
    
    async def get_nodes(self) -> List[ProxmoxNode]:
        """Get all registered nodes."""
        async with get_db_context() as db:
            result = await db.execute(
                select(ProxmoxNode).order_by(ProxmoxNode.name)
            )
            return list(result.scalars().all())
    
    async def _update_node_seen(self, db: AsyncSession, node_name: str):
        """Update node's last_seen timestamp."""
        await db.execute(
            update(ProxmoxNode)
            .where(ProxmoxNode.name == node_name)
            .values(last_seen=datetime.utcnow())
        )
    
    async def _update_node_seen_simple(self, node_name: str):
        """Update node's last_seen timestamp (standalone)."""
        async with get_db_context() as db:
            await db.execute(
                update(ProxmoxNode)
                .where(ProxmoxNode.name == node_name)
                .values(last_seen=datetime.utcnow())
            )
    
    async def _update_tracked_vm(
        self, 
        db: AsyncSession, 
        vm_id: str, 
        node: str,
        status: str = None,
        name: str = None,
        vm_type: str = None
    ):
        """Update or create tracked VM record."""
        result = await db.execute(
            select(TrackedVM).where(
                and_(TrackedVM.vm_id == vm_id, TrackedVM.node == node)
            )
        )
        vm = result.scalar_one_or_none()
        
        if vm:
            if status:
                vm.current_status = status
            if name:
                vm.name = name
            vm.last_seen = datetime.utcnow()
        else:
            vm = TrackedVM(
                vm_id=vm_id,
                node=node,
                name=name or f"VM {vm_id}",
                vm_type=vm_type or 'qemu',
                current_status=status or 'unknown',
                last_seen=datetime.utcnow()
            )
            db.add(vm)
