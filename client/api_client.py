"""
API Client

HTTP client for sending VM events to the Manager server.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

import httpx

from .config import settings
from .proxmox_api import VMState

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
        self._force_sync_pending = False
    
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
        """Register this node with the manager."""
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
                logger.error(f"Registration failed: {e.response.status_code}")
                raise
            except httpx.RequestError as e:
                logger.error(f"Request failed: {e}")
                raise
    
    async def send_vm_start(
        self,
        node: str,
        vm_id: str,
        vm_name: str = '',
        vm_type: str = 'qemu',
        start_time: Optional[datetime] = None
    ) -> dict:
        """
        Report that a VM has started.
        
        Args:
            node: Node name
            vm_id: VM ID
            vm_name: VM name
            vm_type: qemu or lxc
            start_time: When VM started (default: now)
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/ingest/vm-start",
                    json={
                        'node': node,
                        'vm_id': vm_id,
                        'vm_name': vm_name,
                        'vm_type': vm_type,
                        'start_time': (start_time or datetime.utcnow()).isoformat()
                    },
                    headers=self._get_headers()
                )
                response.raise_for_status()
                result = response.json()
                logger.info(f"Reported VM {vm_id} started on {node}")
                return result
            except Exception as e:
                logger.error(f"Failed to report VM start: {e}")
                raise
    
    async def send_vm_stop(
        self,
        node: str,
        vm_id: str,
        stop_time: Optional[datetime] = None
    ) -> dict:
        """
        Report that a VM has stopped.
        
        Args:
            node: Node name
            vm_id: VM ID
            stop_time: When VM stopped (default: now)
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/ingest/vm-stop",
                    json={
                        'node': node,
                        'vm_id': vm_id,
                        'stop_time': (stop_time or datetime.utcnow()).isoformat()
                    },
                    headers=self._get_headers()
                )
                response.raise_for_status()
                result = response.json()
                logger.info(f"Reported VM {vm_id} stopped on {node}")
                return result
            except Exception as e:
                logger.error(f"Failed to report VM stop: {e}")
                raise
    
    async def send_vm_states(
        self,
        node: str,
        vms: List[VMState]
    ) -> dict:
        """
        Send full VM state snapshot.
        
        Used for initial sync and force sync operations.
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/ingest/vm-states",
                    json={
                        'node': node,
                        'timestamp': datetime.utcnow().isoformat(),
                        'vms': [vm.to_dict() for vm in vms]
                    },
                    headers=self._get_headers()
                )
                response.raise_for_status()
                result = response.json()
                logger.info(f"Sent full state snapshot: {len(vms)} VMs")
                return result
            except Exception as e:
                logger.error(f"Failed to send VM states: {e}")
                raise
    
    async def heartbeat(self, node_name: str) -> dict:
        """
        Send heartbeat and check for force sync request.
        
        Returns:
            Response dict with 'force_sync' flag if sync requested
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
                result = response.json()
                
                # Check for force sync request
                if result.get('force_sync'):
                    self._force_sync_pending = True
                    logger.info("Force sync requested by manager")
                
                return result
            except httpx.RequestError as e:
                logger.debug(f"Heartbeat failed: {e}")
                return {'success': False}
    
    def is_force_sync_pending(self) -> bool:
        """Check if force sync was requested"""
        return self._force_sync_pending
    
    def clear_force_sync(self):
        """Clear force sync flag after completing sync"""
        self._force_sync_pending = False
    
    async def check_connection(self) -> bool:
        """Check if manager is reachable."""
        async with httpx.AsyncClient(timeout=5) as client:
            try:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
            except Exception:
                return False
