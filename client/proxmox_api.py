"""
Proxmox API Client

Queries the Proxmox VE API to get real-time VM status.
"""

import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from enum import Enum

import httpx

logger = logging.getLogger(__name__)


class VMType(Enum):
    QEMU = "qemu"
    LXC = "lxc"


class VMStatus(Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    PAUSED = "paused"
    UNKNOWN = "unknown"


@dataclass
class VMState:
    """Current state of a VM"""
    vm_id: str
    vm_type: VMType
    name: str
    status: VMStatus
    node: str
    uptime: int = 0  # seconds
    cpu: float = 0.0
    memory: int = 0  # bytes
    maxmem: int = 0  # bytes
    
    def to_dict(self) -> dict:
        return {
            "vm_id": self.vm_id,
            "vm_type": self.vm_type.value,
            "name": self.name,
            "status": self.status.value,
            "node": self.node,
            "uptime": self.uptime,
            "cpu": self.cpu,
            "memory": self.memory,
            "maxmem": self.maxmem
        }


class ProxmoxAPI:
    """
    Client for Proxmox VE API.
    
    Uses API token authentication for security.
    """
    
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8006,
        user: str = "root@pam",
        token_name: str = "tracker",
        token_value: str = "",
        verify_ssl: bool = False,
        node_name: str = ""
    ):
        self.host = host
        self.port = port
        self.user = user
        self.token_name = token_name
        self.token_value = token_value
        self.verify_ssl = verify_ssl
        self.node_name = node_name
        
        self.base_url = f"https://{host}:{port}/api2/json"
        self._auth_header = f"PVEAPIToken={user}!{token_name}={token_value}"
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with API token auth"""
        return {
            "Authorization": self._auth_header,
            "Content-Type": "application/json"
        }
    
    async def _request(self, method: str, endpoint: str, **kwargs) -> Optional[Any]:
        """Make an API request"""
        url = f"{self.base_url}{endpoint}"
        
        async with httpx.AsyncClient(verify=self.verify_ssl, timeout=10) as client:
            try:
                response = await client.request(
                    method,
                    url,
                    headers=self._get_headers(),
                    **kwargs
                )
                response.raise_for_status()
                data = response.json()
                return data.get("data")
            except httpx.HTTPStatusError as e:
                logger.error(f"API error: {e.response.status_code} - {endpoint}")
                return None
            except httpx.RequestError as e:
                logger.error(f"Request failed: {e}")
                return None
    
    async def get_node_name(self) -> str:
        """Get this node's name from Proxmox"""
        if self.node_name:
            return self.node_name
        
        nodes = await self._request("GET", "/nodes")
        if nodes and len(nodes) > 0:
            # Find local node (status = online, local = 1)
            for node in nodes:
                if node.get("local") == 1:
                    self.node_name = node.get("node", "pve")
                    return self.node_name
            # Fallback to first node
            self.node_name = nodes[0].get("node", "pve")
        else:
            self.node_name = "pve"
        
        return self.node_name
    
    async def get_qemu_vms(self) -> List[VMState]:
        """Get all QEMU VMs on this node"""
        node = await self.get_node_name()
        vms_data = await self._request("GET", f"/nodes/{node}/qemu")
        
        if not vms_data:
            return []
        
        vms = []
        for vm in vms_data:
            status_str = vm.get("status", "unknown")
            try:
                status = VMStatus(status_str)
            except ValueError:
                status = VMStatus.UNKNOWN
            
            vms.append(VMState(
                vm_id=str(vm.get("vmid", "")),
                vm_type=VMType.QEMU,
                name=vm.get("name", f"VM {vm.get('vmid')}"),
                status=status,
                node=node,
                uptime=vm.get("uptime", 0),
                cpu=vm.get("cpu", 0.0),
                memory=vm.get("mem", 0),
                maxmem=vm.get("maxmem", 0)
            ))
        
        return vms
    
    async def get_lxc_containers(self) -> List[VMState]:
        """Get all LXC containers on this node"""
        node = await self.get_node_name()
        cts_data = await self._request("GET", f"/nodes/{node}/lxc")
        
        if not cts_data:
            return []
        
        containers = []
        for ct in cts_data:
            status_str = ct.get("status", "unknown")
            try:
                status = VMStatus(status_str)
            except ValueError:
                status = VMStatus.UNKNOWN
            
            containers.append(VMState(
                vm_id=str(ct.get("vmid", "")),
                vm_type=VMType.LXC,
                name=ct.get("name", f"CT {ct.get('vmid')}"),
                status=status,
                node=node,
                uptime=ct.get("uptime", 0),
                cpu=ct.get("cpu", 0.0),
                memory=ct.get("mem", 0),
                maxmem=ct.get("maxmem", 0)
            ))
        
        return containers
    
    async def get_all_vms(
        self,
        include_qemu: bool = True,
        include_lxc: bool = True
    ) -> List[VMState]:
        """Get all VMs and containers"""
        vms = []
        
        if include_qemu:
            qemu_vms = await self.get_qemu_vms()
            vms.extend(qemu_vms)
        
        if include_lxc:
            lxc_cts = await self.get_lxc_containers()
            vms.extend(lxc_cts)
        
        return sorted(vms, key=lambda v: int(v.vm_id) if v.vm_id.isdigit() else 0)
    
    async def get_vm_status(self, vm_id: str, vm_type: VMType = VMType.QEMU) -> Optional[VMState]:
        """Get status of a specific VM"""
        node = await self.get_node_name()
        type_path = "qemu" if vm_type == VMType.QEMU else "lxc"
        
        data = await self._request("GET", f"/nodes/{node}/{type_path}/{vm_id}/status/current")
        
        if not data:
            return None
        
        status_str = data.get("status", "unknown")
        try:
            status = VMStatus(status_str)
        except ValueError:
            status = VMStatus.UNKNOWN
        
        return VMState(
            vm_id=vm_id,
            vm_type=vm_type,
            name=data.get("name", f"VM {vm_id}"),
            status=status,
            node=node,
            uptime=data.get("uptime", 0),
            cpu=data.get("cpu", 0.0),
            memory=data.get("mem", 0),
            maxmem=data.get("maxmem", 0)
        )
    
    async def test_connection(self) -> bool:
        """Test if API connection works"""
        try:
            nodes = await self._request("GET", "/nodes")
            return nodes is not None
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
