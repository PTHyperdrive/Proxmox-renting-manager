"""
API Client

HTTP client for sending events to the Manager server.
"""

import logging
from typing import List, Optional
from datetime import datetime

import httpx

from .log_parser import VMEvent
from .config import settings

logger = logging.getLogger(__name__)


class APIClient:
    """Client for communicating with the Manager server."""
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 30
    ):
        self.base_url = (base_url or settings.manager.url).rstrip('/')
        self.api_key = api_key or settings.manager.api_key
        self.timeout = timeout or settings.manager.timeout
    
    def _get_headers(self) -> dict:
        """Get request headers including API key"""
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'proxmox-tracker-client/2.0'
        }
        if self.api_key:
            headers['X-API-Key'] = self.api_key
        return headers
    
    async def register_node(self, node_name: str, hostname: str = '') -> dict:
        """
        Register this node with the manager.
        
        Args:
            node_name: Unique node identifier
            hostname: Optional hostname
            
        Returns:
            Response from manager
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/ingest/register",
                    json={
                        'name': node_name,
                        'hostname': hostname
                    },
                    headers=self._get_headers()
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Registration failed: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.RequestError as e:
                logger.error(f"Request failed: {e}")
                raise
    
    async def send_events(self, node_name: str, events: List[VMEvent]) -> dict:
        """
        Send VM events to the manager.
        
        Args:
            node_name: Node sending the events
            events: List of VM events to send
            
        Returns:
            Response from manager
        """
        if not events:
            return {'success': True, 'message': 'No events to send'}
        
        # Convert events to dict format
        events_data = [
            {
                'upid': e.upid,
                'vm_id': e.vm_id,
                'event_type': e.event_type,
                'timestamp': e.timestamp.isoformat(),
                'user': e.user,
                'status': e.status
            }
            for e in events
        ]
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/ingest/events",
                    json={
                        'node': node_name,
                        'events': events_data
                    },
                    headers=self._get_headers()
                )
                response.raise_for_status()
                result = response.json()
                
                logger.info(
                    f"Sent {len(events)} events to manager: "
                    f"{result.get('sessions_created', 0)} created, "
                    f"{result.get('sessions_updated', 0)} updated"
                )
                return result
                
            except httpx.HTTPStatusError as e:
                logger.error(f"Failed to send events: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.RequestError as e:
                logger.error(f"Request failed: {e}")
                raise
    
    async def heartbeat(self, node_name: str) -> dict:
        """
        Send heartbeat to manager.
        
        Args:
            node_name: Node sending heartbeat
            
        Returns:
            Response from manager
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/ingest/heartbeat",
                    json={
                        'node': node_name,
                        'timestamp': datetime.utcnow().isoformat()
                    },
                    headers=self._get_headers()
                )
                response.raise_for_status()
                return response.json()
            except httpx.RequestError as e:
                logger.debug(f"Heartbeat failed: {e}")
                return {'success': False}
    
    async def check_connection(self) -> bool:
        """
        Check if manager is reachable.
        
        Returns:
            True if connection successful
        """
        async with httpx.AsyncClient(timeout=5) as client:
            try:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
            except Exception:
                return False
