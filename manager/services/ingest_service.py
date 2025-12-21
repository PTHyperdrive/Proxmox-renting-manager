"""
Ingest Service

Handles incoming events from Proxmox client nodes.
"""

import logging
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import ProxmoxNode, VMSession, get_db_context
from ..models.schemas import (
    EventData, EventIngestRequest, EventIngestResponse,
    NodeRegisterRequest, NodeRegisterResponse
)

logger = logging.getLogger(__name__)


# Event types that represent VM starting
START_EVENTS = {'qmstart', 'vzstart'}

# Event types that represent VM stopping
STOP_EVENTS = {'qmstop', 'qmshutdown', 'qmdestroy', 'vzstop', 'vzshutdown'}


class IngestService:
    """
    Service to handle data ingestion from Proxmox client nodes.
    """
    
    async def register_node(self, request: NodeRegisterRequest) -> NodeRegisterResponse:
        """
        Register a new Proxmox node or update existing one.
        
        Args:
            request: Node registration request
            
        Returns:
            NodeRegisterResponse with registration result
        """
        async with get_db_context() as db:
            # Check if node already exists
            result = await db.execute(
                select(ProxmoxNode).where(ProxmoxNode.name == request.name)
            )
            existing_node = result.scalar_one_or_none()
            
            if existing_node:
                # Update existing node
                existing_node.hostname = request.hostname or existing_node.hostname
                existing_node.is_active = True
                existing_node.last_seen = datetime.utcnow()
                await db.flush()
                
                logger.info(f"Updated existing node: {request.name}")
                return NodeRegisterResponse(
                    success=True,
                    message=f"Node '{request.name}' updated",
                    node_id=existing_node.id
                )
            else:
                # Create new node
                new_node = ProxmoxNode(
                    name=request.name,
                    hostname=request.hostname,
                    is_active=True,
                    last_seen=datetime.utcnow()
                )
                db.add(new_node)
                await db.flush()
                await db.refresh(new_node)
                
                logger.info(f"Registered new node: {request.name}")
                return NodeRegisterResponse(
                    success=True,
                    message=f"Node '{request.name}' registered",
                    node_id=new_node.id
                )
    
    async def ingest_events(self, request: EventIngestRequest) -> EventIngestResponse:
        """
        Ingest VM events from a client node.
        
        Processes start/stop events and creates/updates sessions.
        
        Args:
            request: Event ingest request with list of events
            
        Returns:
            EventIngestResponse with processing results
        """
        response = EventIngestResponse(
            success=True,
            message="Events processed",
            events_processed=0,
            sessions_created=0,
            sessions_updated=0,
            errors=[]
        )
        
        if not request.events:
            response.message = "No events to process"
            return response
        
        async with get_db_context() as db:
            # Update node last_seen
            await self._update_node_seen(db, request.node)
            
            # Sort events by timestamp
            sorted_events = sorted(request.events, key=lambda e: e.timestamp)
            
            for event in sorted_events:
                try:
                    created, updated = await self._process_event(db, request.node, event)
                    response.events_processed += 1
                    response.sessions_created += created
                    response.sessions_updated += updated
                except Exception as e:
                    error_msg = f"Error processing event {event.upid}: {str(e)}"
                    logger.error(error_msg)
                    response.errors.append(error_msg)
            
            # Update node statistics
            await self._update_node_stats(db, request.node)
        
        if response.errors:
            response.message = f"Processed with {len(response.errors)} errors"
        else:
            response.message = (
                f"Processed {response.events_processed} events: "
                f"{response.sessions_created} sessions created, "
                f"{response.sessions_updated} updated"
            )
        
        logger.info(f"Ingested {response.events_processed} events from node {request.node}")
        return response
    
    async def _process_event(
        self,
        db: AsyncSession,
        node: str,
        event: EventData
    ) -> Tuple[int, int]:
        """
        Process a single VM event.
        
        Returns:
            Tuple of (sessions_created, sessions_updated)
        """
        created = updated = 0
        
        # Check if event already processed (by UPID)
        if event.event_type in START_EVENTS:
            existing = await db.execute(
                select(VMSession).where(VMSession.start_upid == event.upid)
            )
            if existing.scalar_one_or_none():
                return 0, 0  # Already processed
            
            # Create new session
            session = VMSession(
                vm_id=event.vm_id,
                node=node,
                start_time=event.timestamp,
                user=event.user,
                start_upid=event.upid,
                is_running=True
            )
            db.add(session)
            created = 1
            
        elif event.event_type in STOP_EVENTS:
            # Check if already used as stop event
            existing = await db.execute(
                select(VMSession).where(VMSession.stop_upid == event.upid)
            )
            if existing.scalar_one_or_none():
                return 0, 0  # Already processed
            
            # Find matching running session
            result = await db.execute(
                select(VMSession)
                .where(
                    and_(
                        VMSession.vm_id == event.vm_id,
                        VMSession.node == node,
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
                updated = 1
            else:
                logger.warning(
                    f"Stop event for VM {event.vm_id} on {node} has no matching start"
                )
        
        await db.flush()
        return created, updated
    
    async def _update_node_seen(self, db: AsyncSession, node_name: str):
        """Update node's last_seen timestamp"""
        result = await db.execute(
            select(ProxmoxNode).where(ProxmoxNode.name == node_name)
        )
        node = result.scalar_one_or_none()
        
        if node:
            node.last_seen = datetime.utcnow()
        else:
            # Auto-register unknown node
            new_node = ProxmoxNode(
                name=node_name,
                is_active=True,
                last_seen=datetime.utcnow()
            )
            db.add(new_node)
    
    async def _update_node_stats(self, db: AsyncSession, node_name: str):
        """Update node statistics"""
        result = await db.execute(
            select(ProxmoxNode).where(ProxmoxNode.name == node_name)
        )
        node = result.scalar_one_or_none()
        
        if node:
            # Count VMs for this node
            vm_count = await db.execute(
                select(VMSession.vm_id)
                .where(VMSession.node == node_name)
                .distinct()
            )
            node.total_vms = len(vm_count.fetchall())
            
            # Get last event time
            last_event = await db.execute(
                select(VMSession.start_time)
                .where(VMSession.node == node_name)
                .order_by(VMSession.start_time.desc())
                .limit(1)
            )
            last = last_event.scalar_one_or_none()
            if last:
                node.last_event_time = last
    
    async def heartbeat(self, node_name: str) -> bool:
        """
        Process heartbeat from a client node.
        
        Args:
            node_name: Name of the node sending heartbeat
            
        Returns:
            True if successful
        """
        async with get_db_context() as db:
            await self._update_node_seen(db, node_name)
            return True
    
    async def get_nodes(self) -> List[ProxmoxNode]:
        """Get all registered nodes"""
        async with get_db_context() as db:
            result = await db.execute(
                select(ProxmoxNode).order_by(ProxmoxNode.name)
            )
            return list(result.scalars().all())
