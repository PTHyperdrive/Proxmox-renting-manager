"""
Session Endpoints

API endpoints for viewing and managing VM sessions.
"""

from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import VMSession, get_db
from ..models.schemas import (
    VMSessionResponse, VMSessionList, SyncRequest, SyncResponse
)
from ..services.time_tracker import TimeTracker

router = APIRouter(prefix="/api/sessions", tags=["Sessions"])

# Service instance
time_tracker = TimeTracker()


@router.get("", response_model=VMSessionList)
async def list_sessions(
    vm_id: Optional[str] = Query(None, description="Filter by VM ID"),
    running_only: bool = Query(False, description="Only show running sessions"),
    start_date: Optional[datetime] = Query(None, description="Filter sessions starting after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter sessions starting before this date"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db)
):
    """
    List all VM sessions with pagination and filtering.
    """
    # Build query conditions
    conditions = []
    
    if vm_id:
        conditions.append(VMSession.vm_id == vm_id)
    
    if running_only:
        conditions.append(VMSession.is_running == True)
    
    if start_date:
        conditions.append(VMSession.start_time >= start_date)
    
    if end_date:
        conditions.append(VMSession.start_time <= end_date)
    
    # Count total
    count_query = select(VMSession.id)
    if conditions:
        count_query = count_query.where(and_(*conditions))
    
    count_result = await db.execute(count_query)
    total = len(count_result.fetchall())
    
    # Get paginated results
    query = select(VMSession)
    if conditions:
        query = query.where(and_(*conditions))
    
    query = query.order_by(desc(VMSession.start_time))
    query = query.offset((page - 1) * per_page).limit(per_page)
    
    result = await db.execute(query)
    sessions = result.scalars().all()
    
    return VMSessionList(
        sessions=[VMSessionResponse.model_validate(s) for s in sessions],
        total=total,
        page=page,
        per_page=per_page
    )


@router.get("/running")
async def get_running_sessions(db: AsyncSession = Depends(get_db)):
    """
    Get all currently running VM sessions.
    """
    result = await db.execute(
        select(VMSession)
        .where(VMSession.is_running == True)
        .order_by(VMSession.start_time)
    )
    sessions = result.scalars().all()
    
    return {
        "running_count": len(sessions),
        "sessions": [VMSessionResponse.model_validate(s) for s in sessions]
    }


@router.get("/{session_id}", response_model=VMSessionResponse)
async def get_session(session_id: int, db: AsyncSession = Depends(get_db)):
    """
    Get a specific session by ID.
    """
    result = await db.execute(
        select(VMSession).where(VMSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return VMSessionResponse.model_validate(session)


@router.post("/sync", response_model=SyncResponse)
async def sync_sessions(request: SyncRequest = None):
    """
    Sync VM sessions from Proxmox logs.
    
    This will:
    1. Connect to Proxmox (via API or SSH)
    2. Read task logs
    3. Parse start/stop events
    4. Create/update session records in the database
    """
    request = request or SyncRequest()
    
    response = await time_tracker.sync_from_logs(
        since=request.from_date,
        vm_ids=request.vm_ids,
        force=request.force
    )
    
    return response


@router.post("/manual/start")
async def manual_start_session(
    vm_id: str,
    node: str = "pve",
    user: Optional[str] = None
):
    """
    Manually start a new VM session (for testing or manual tracking).
    """
    session = await time_tracker.start_session(vm_id, node, user)
    return {
        "message": "Session started",
        "session": VMSessionResponse.model_validate(session)
    }


@router.post("/manual/stop/{session_id}")
async def manual_stop_session(session_id: int):
    """
    Manually stop a VM session.
    """
    session = await time_tracker.stop_session(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "message": "Session stopped",
        "session": VMSessionResponse.model_validate(session)
    }


@router.get("/vm/{vm_id}", response_model=VMSessionList)
async def get_vm_sessions(
    vm_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all sessions for a specific VM.
    """
    # Count total
    count_result = await db.execute(
        select(VMSession.id).where(VMSession.vm_id == vm_id)
    )
    total = len(count_result.fetchall())
    
    # Get sessions
    result = await db.execute(
        select(VMSession)
        .where(VMSession.vm_id == vm_id)
        .order_by(desc(VMSession.start_time))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    sessions = result.scalars().all()
    
    return VMSessionList(
        sessions=[VMSessionResponse.model_validate(s) for s in sessions],
        total=total,
        page=page,
        per_page=per_page
    )
