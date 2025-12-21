"""
Ingest Endpoints

API endpoints for receiving data from Proxmox client nodes.
"""

from datetime import datetime
from fastapi import APIRouter, Header, HTTPException, Request

from ..config import settings
from ..models.schemas import (
    NodeRegisterRequest, NodeRegisterResponse,
    EventIngestRequest, EventIngestResponse,
    HeartbeatRequest, HeartbeatResponse
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


@router.post("/events", response_model=EventIngestResponse)
async def ingest_events(
    request: EventIngestRequest,
    api_key: str = Header(None, alias="X-API-Key")
):
    """
    Ingest VM events from a client node.
    
    Clients should send batches of events periodically.
    Events are deduplicated by UPID.
    """
    verify_api_key(api_key)
    return await ingest_service.ingest_events(request)


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(
    request: HeartbeatRequest,
    api_key: str = Header(None, alias="X-API-Key")
):
    """
    Heartbeat from a client node.
    
    Used to track node availability.
    """
    verify_api_key(api_key)
    await ingest_service.heartbeat(request.node)
    return HeartbeatResponse(
        success=True,
        server_time=datetime.utcnow()
    )
