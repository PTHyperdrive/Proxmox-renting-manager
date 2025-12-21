"""
Node Endpoints

API endpoints for viewing registered Proxmox nodes.
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from ..models.database import ProxmoxNode, get_db_context
from ..models.schemas import NodeInfo, NodeListResponse
from ..services.ingest_service import IngestService

router = APIRouter(prefix="/api/nodes", tags=["Nodes"])

ingest_service = IngestService()


@router.get("", response_model=NodeListResponse)
async def list_nodes():
    """
    List all registered Proxmox nodes.
    """
    nodes = await ingest_service.get_nodes()
    return NodeListResponse(
        nodes=[NodeInfo.model_validate(n) for n in nodes],
        total=len(nodes)
    )


@router.get("/{node_name}", response_model=NodeInfo)
async def get_node(node_name: str):
    """
    Get details for a specific node.
    """
    async with get_db_context() as db:
        result = await db.execute(
            select(ProxmoxNode).where(ProxmoxNode.name == node_name)
        )
        node = result.scalar_one_or_none()
        
        if not node:
            raise HTTPException(status_code=404, detail="Node not found")
        
        return NodeInfo.model_validate(node)


@router.delete("/{node_name}")
async def delete_node(node_name: str):
    """
    Remove a node from tracking.
    """
    async with get_db_context() as db:
        result = await db.execute(
            select(ProxmoxNode).where(ProxmoxNode.name == node_name)
        )
        node = result.scalar_one_or_none()
        
        if not node:
            raise HTTPException(status_code=404, detail="Node not found")
        
        await db.delete(node)
        return {"message": f"Node '{node_name}' deleted"}
