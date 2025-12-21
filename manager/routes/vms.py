"""
VM Endpoints

API endpoints for viewing VMs and their usage statistics.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import VMSession, TrackedVM, get_db
from ..models.schemas import VMInfo, VMListResponse, VMUsage
from ..services.time_tracker import TimeTracker

router = APIRouter(prefix="/api/vms", tags=["VMs"])

time_tracker = TimeTracker()


@router.get("", response_model=VMListResponse)
async def list_vms(
    node: Optional[str] = Query(None, description="Filter by node"),
    db: AsyncSession = Depends(get_db)
):
    """
    List all tracked VMs with their usage statistics.
    
    Combines data from:
    - TrackedVM: Real-time VM status from Proxmox
    - VMSession: Historical session data for runtime calculation
    """
    # First, get all tracked VMs (real-time status)
    tracked_query = select(TrackedVM)
    if node:
        tracked_query = tracked_query.where(TrackedVM.node == node)
    tracked_query = tracked_query.order_by(TrackedVM.vm_id)
    
    tracked_result = await db.execute(tracked_query)
    tracked_vms = {(vm.vm_id, vm.node): vm for vm in tracked_result.scalars().all()}
    
    # Also get VMs from sessions (in case there are VMs with history but not currently tracked)
    session_query = select(VMSession.vm_id, VMSession.node).distinct()
    if node:
        session_query = session_query.where(VMSession.node == node)
    
    session_result = await db.execute(session_query)
    session_vms = set((row.vm_id, row.node) for row in session_result.fetchall())
    
    # Combine all VM IDs
    all_vm_keys = set(tracked_vms.keys()) | session_vms
    
    vms = []
    for vm_id, vm_node in sorted(all_vm_keys, key=lambda x: (x[1], x[0])):
        tracked = tracked_vms.get((vm_id, vm_node))
        
        # Get stats from sessions
        stats_result = await db.execute(
            select(
                func.coalesce(func.sum(VMSession.duration_seconds), 0).label('total_seconds'),
                func.count(VMSession.id).label('session_count')
            )
            .where(VMSession.vm_id == vm_id, VMSession.node == vm_node)
        )
        stats = stats_result.fetchone()
        total_seconds = int(stats.total_seconds) if stats.total_seconds else 0
        
        # If VM is currently running, add time since session started
        active_result = await db.execute(
            select(VMSession)
            .where(VMSession.vm_id == vm_id, VMSession.node == vm_node, VMSession.is_running == True)
            .limit(1)
        )
        active_session = active_result.scalar_one_or_none()
        
        if active_session:
            # Add running time to total
            running_seconds = int((datetime.utcnow() - active_session.start_time).total_seconds())
            total_seconds += running_seconds
        
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        
        # Determine status from TrackedVM or active session
        if tracked:
            status = tracked.current_status
            name = tracked.name
        else:
            status = "running" if active_session else "stopped"
            name = None
        
        vms.append(VMInfo(
            vm_id=vm_id,
            name=name,
            node=vm_node,
            status=status,
            is_tracked=True,
            total_runtime_seconds=total_seconds,
            formatted_runtime=f"{hours}h {minutes}m",
            active_session_id=active_session.id if active_session else None
        ))
    
    return VMListResponse(vms=vms, total=len(vms))


@router.get("/{vm_id}", response_model=VMInfo)
async def get_vm(
    vm_id: str,
    node: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Get details for a specific VM."""
    # Try to get from TrackedVM first
    tracked_query = select(TrackedVM).where(TrackedVM.vm_id == vm_id)
    if node:
        tracked_query = tracked_query.where(TrackedVM.node == node)
    
    tracked_result = await db.execute(tracked_query.limit(1))
    tracked = tracked_result.scalar_one_or_none()
    
    # If not found in TrackedVM, check sessions
    if not tracked:
        conditions = [VMSession.vm_id == vm_id]
        if node:
            conditions.append(VMSession.node == node)
        
        session_result = await db.execute(
            select(VMSession.vm_id, VMSession.node)
            .where(*conditions)
            .limit(1)
        )
        row = session_result.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail=f"VM {vm_id} not found")
        
        vm_node = row.node
    else:
        vm_node = tracked.node
    
    # Get stats
    stats_result = await db.execute(
        select(
            func.coalesce(func.sum(VMSession.duration_seconds), 0).label('total_seconds'),
            func.count(VMSession.id).label('session_count')
        )
        .where(VMSession.vm_id == vm_id, VMSession.node == vm_node)
    )
    stats = stats_result.fetchone()
    total_seconds = int(stats.total_seconds) if stats.total_seconds else 0
    
    # Check for active session
    active_result = await db.execute(
        select(VMSession)
        .where(VMSession.vm_id == vm_id, VMSession.node == vm_node, VMSession.is_running == True)
        .limit(1)
    )
    active_session = active_result.scalar_one_or_none()
    
    if active_session:
        running_seconds = int((datetime.utcnow() - active_session.start_time).total_seconds())
        total_seconds += running_seconds
    
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    
    if tracked:
        status = tracked.current_status
        name = tracked.name
    else:
        status = "running" if active_session else "stopped"
        name = None
    
    return VMInfo(
        vm_id=vm_id,
        name=name,
        node=vm_node,
        status=status,
        is_tracked=True,
        total_runtime_seconds=total_seconds,
        formatted_runtime=f"{hours}h {minutes}m",
        active_session_id=active_session.id if active_session else None
    )


@router.get("/{vm_id}/usage", response_model=VMUsage)
async def get_vm_usage(
    vm_id: str,
    node: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Get usage statistics for a VM within a date range."""
    usage = await time_tracker.get_vm_usage(vm_id, start_date, end_date, node, db)
    return usage


@router.get("/{vm_id}/daily")
async def get_vm_daily_usage(
    vm_id: str,
    start_date: datetime = Query(...),
    end_date: datetime = Query(...),
    node: Optional[str] = Query(None)
):
    """Get daily usage breakdown for a VM."""
    daily = await time_tracker.get_daily_breakdown(vm_id, start_date, end_date, node)
    
    result = []
    for date_str, seconds in sorted(daily.items()):
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        result.append({
            "date": date_str,
            "total_seconds": seconds,
            "formatted_duration": f"{hours}h {minutes}m"
        })
    
    return {"vm_id": vm_id, "daily_usage": result}


@router.delete("/{vm_id}")
async def remove_vm(
    vm_id: str,
    node: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Remove a VM from the database completely.
    
    This deletes:
    - TrackedVM record (current state)
    - All VMSession records (history)
    
    Args:
        vm_id: VM ID to remove
        node: Optional node filter (if not specified, removes from all nodes)
    """
    from sqlalchemy import delete
    
    deleted_tracked = 0
    deleted_sessions = 0
    
    # Delete from TrackedVM
    tracked_query = delete(TrackedVM).where(TrackedVM.vm_id == vm_id)
    if node:
        tracked_query = tracked_query.where(TrackedVM.node == node)
    
    result = await db.execute(tracked_query)
    deleted_tracked = result.rowcount
    
    # Delete all sessions
    session_query = delete(VMSession).where(VMSession.vm_id == vm_id)
    if node:
        session_query = session_query.where(VMSession.node == node)
    
    result = await db.execute(session_query)
    deleted_sessions = result.rowcount
    
    if deleted_tracked == 0 and deleted_sessions == 0:
        raise HTTPException(status_code=404, detail=f"VM {vm_id} not found")
    
    return {
        "success": True,
        "message": f"VM {vm_id} removed from database",
        "deleted_tracked": deleted_tracked,
        "deleted_sessions": deleted_sessions
    }


