"""
VM Endpoints

API endpoints for viewing VMs and their usage statistics.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import VMSession, get_db
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
    """
    query = select(VMSession.vm_id, VMSession.node).distinct()
    if node:
        query = query.where(VMSession.node == node)
    query = query.order_by(VMSession.vm_id)
    
    result = await db.execute(query)
    rows = result.fetchall()
    
    vms = []
    for row in rows:
        # Get stats
        stats_result = await db.execute(
            select(
                func.coalesce(func.sum(VMSession.duration_seconds), 0).label('total_seconds'),
                func.count(VMSession.id).label('session_count')
            )
            .where(VMSession.vm_id == row.vm_id, VMSession.node == row.node)
        )
        stats = stats_result.fetchone()
        total_seconds = int(stats.total_seconds) if stats.total_seconds else 0
        
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        
        # Check for active session
        active_result = await db.execute(
            select(VMSession.id)
            .where(VMSession.vm_id == row.vm_id, VMSession.node == row.node, VMSession.is_running == True)
            .limit(1)
        )
        active_session = active_result.scalar_one_or_none()
        
        vms.append(VMInfo(
            vm_id=row.vm_id,
            node=row.node,
            status="running" if active_session else "stopped",
            is_tracked=True,
            total_runtime_seconds=total_seconds,
            formatted_runtime=f"{hours}h {minutes}m",
            active_session_id=active_session
        ))
    
    return VMListResponse(vms=vms, total=len(vms))


@router.get("/{vm_id}", response_model=VMInfo)
async def get_vm(
    vm_id: str,
    node: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Get details for a specific VM."""
    conditions = [VMSession.vm_id == vm_id]
    if node:
        conditions.append(VMSession.node == node)
    
    result = await db.execute(
        select(VMSession.vm_id, VMSession.node)
        .where(*conditions)
        .limit(1)
    )
    row = result.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail=f"VM {vm_id} not found")
    
    stats_result = await db.execute(
        select(
            func.coalesce(func.sum(VMSession.duration_seconds), 0).label('total_seconds'),
            func.count(VMSession.id).label('session_count')
        )
        .where(VMSession.vm_id == row.vm_id, VMSession.node == row.node)
    )
    stats = stats_result.fetchone()
    total_seconds = int(stats.total_seconds) if stats.total_seconds else 0
    
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    
    active_result = await db.execute(
        select(VMSession.id)
        .where(VMSession.vm_id == vm_id, VMSession.is_running == True)
        .limit(1)
    )
    active_session = active_result.scalar_one_or_none()
    
    return VMInfo(
        vm_id=row.vm_id,
        node=row.node,
        status="running" if active_session else "stopped",
        is_tracked=True,
        total_runtime_seconds=total_seconds,
        formatted_runtime=f"{hours}h {minutes}m",
        active_session_id=active_session
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
