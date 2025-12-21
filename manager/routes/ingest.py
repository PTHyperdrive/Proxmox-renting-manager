"""
Ingest Endpoints

API endpoints for receiving data from Proxmox client nodes.
"""

from datetime import datetime
from fastapi import APIRouter, Header, HTTPException

from ..config import settings
from ..models.schemas import (
    NodeRegisterRequest, NodeRegisterResponse,
    HeartbeatRequest, HeartbeatResponse,
    VMStartEvent, VMStartResponse,
    VMStopEvent, VMStopResponse,
    VMStatesSnapshot, VMStatesResponse,
    ForceSyncRequest, ForceSyncResponse
)
from ..services.ingest_service import IngestService

router = APIRouter(prefix="/api/ingest", tags=["Ingest"])

# Service instance
ingest_service = IngestService()


def verify_api_key(api_key: str = Header(None, alias="X-API-Key")):
    """Verify the API key from client"""
    if not settings.security.validate_api_key(api_key or ""):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key"
        )


@router.post("/register", response_model=NodeRegisterResponse)
async def register_node(
    request: NodeRegisterRequest,
    api_key: str = Header(None, alias="X-API-Key")
):
    """
    Register a new Proxmox node with the manager.
    
    Nodes should call this on startup to register themselves.
    """
    verify_api_key(api_key)
    return await ingest_service.register_node(request)


@router.post("/vm-start", response_model=VMStartResponse)
async def vm_start(
    request: VMStartEvent,
    api_key: str = Header(None, alias="X-API-Key")
):
    """
    Report that a VM has started.
    
    Creates a new session for the VM.
    """
    verify_api_key(api_key)
    return await ingest_service.handle_vm_start(request)


@router.post("/vm-stop", response_model=VMStopResponse)
async def vm_stop(
    request: VMStopEvent,
    api_key: str = Header(None, alias="X-API-Key")
):
    """
    Report that a VM has stopped.
    
    Closes the running session and calculates duration.
    """
    verify_api_key(api_key)
    return await ingest_service.handle_vm_stop(request)


@router.post("/vm-states", response_model=VMStatesResponse)
async def vm_states(
    request: VMStatesSnapshot,
    api_key: str = Header(None, alias="X-API-Key")
):
    """
    Send full VM states snapshot.
    
    Used for initial sync, force sync, and periodic reconciliation.
    The manager will:
    - Start sessions for VMs that are running but don't have sessions
    - Stop sessions for VMs that are stopped but have running sessions
    """
    verify_api_key(api_key)
    return await ingest_service.handle_vm_states(request)


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(
    request: HeartbeatRequest,
    api_key: str = Header(None, alias="X-API-Key")
):
    """
    Heartbeat from a client node.
    
    Used to track node availability and communicate force sync requests.
    Check the 'force_sync' field in response - if True, send a full VM states snapshot.
    """
    verify_api_key(api_key)
    
    # Check if force sync is pending
    force_sync = await ingest_service.check_force_sync(request.node)
    
    # Update node last seen
    await ingest_service.heartbeat(request.node)
    
    return HeartbeatResponse(
        success=True,
        server_time=datetime.utcnow(),
        force_sync=force_sync
    )


@router.post("/force-sync", response_model=ForceSyncResponse)
async def force_sync(
    request: ForceSyncRequest = None,
    api_key: str = Header(None, alias="X-API-Key")
):
    """
    Request force sync from all or specific nodes.
    
    This sets a flag that clients will see in their next heartbeat response.
    When they see force_sync=True, they should send a full VM states snapshot.
    
    Args:
        target_node: If specified, only request sync from this node.
                    If not specified, request from all nodes.
    """
    verify_api_key(api_key)
    
    target = request.target_node if request else None
    count = ingest_service.request_force_sync(target)
    
    if target:
        message = f"Force sync requested for node '{target}'"
    else:
        message = "Force sync requested for all nodes"
    
    return ForceSyncResponse(
        success=True,
        message=message,
        nodes_notified=count if count > 0 else 0
    )
