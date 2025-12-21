"""
Proxmox Log Parser

Parses Proxmox task logs to extract VM start/stop events.
Supports both local file access and remote access via SSH/API.
"""

import re
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum

try:
    from proxmoxer import ProxmoxAPI
    HAS_PROXMOXER = True
except ImportError:
    HAS_PROXMOXER = False

try:
    import paramiko
    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False

from ..config import settings

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """VM event types from Proxmox logs"""
    START = "qmstart"      # VM start
    STOP = "qmstop"        # VM stop (graceful)
    SHUTDOWN = "qmshutdown"  # VM shutdown
    RESET = "qmreset"      # VM reset
    DESTROY = "qmdestroy"  # VM destroy
    CREATE = "qmcreate"    # VM create
    MIGRATE = "qmigrate"   # VM migration
    
    # LXC container events
    LXC_START = "vzstart"
    LXC_STOP = "vzstop"
    LXC_SHUTDOWN = "vzshutdown"
    
    @classmethod
    def is_start_event(cls, event_type: str) -> bool:
        """Check if event type represents a VM starting"""
        return event_type in [cls.START.value, cls.LXC_START.value]
    
    @classmethod
    def is_stop_event(cls, event_type: str) -> bool:
        """Check if event type represents a VM stopping"""
        return event_type in [
            cls.STOP.value, cls.SHUTDOWN.value, cls.DESTROY.value,
            cls.LXC_STOP.value, cls.LXC_SHUTDOWN.value
        ]


@dataclass
class VMEvent:
    """Represents a VM start/stop event parsed from logs"""
    upid: str
    node: str
    pid: str
    pstart: str
    timestamp: datetime
    event_type: str  # qmstart, qmstop, etc.
    vm_id: str
    user: str
    status: Optional[str] = None  # OK, FAILED, etc.
    
    @property
    def is_start(self) -> bool:
        return EventType.is_start_event(self.event_type)
    
    @property
    def is_stop(self) -> bool:
        return EventType.is_stop_event(self.event_type)
    
    @property
    def is_successful(self) -> bool:
        return self.status is None or self.status.upper() == "OK"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "upid": self.upid,
            "node": self.node,
            "pid": self.pid,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "vm_id": self.vm_id,
            "user": self.user,
            "status": self.status,
            "is_start": self.is_start,
            "is_stop": self.is_stop,
        }


class ProxmoxLogParser:
    """
    Parser for Proxmox task logs.
    
    UPID Format:
    UPID:NODE:PID:PSTART:STARTTIME:TYPE:VMID:USER:
    
    Example:
    UPID:pve1:003D2ED6:01835485:5F09980F:qmstart:100:root@pam:
    
    Where:
    - NODE: Proxmox node name
    - PID: Process ID (hex)
    - PSTART: Process start time (hex)
    - STARTTIME: Unix timestamp (hex)
    - TYPE: Task type (qmstart, qmstop, etc.)
    - VMID: Virtual machine ID
    - USER: User who initiated the action
    """
    
    # Regex pattern for UPID parsing
    UPID_PATTERN = re.compile(
        r'^UPID:(?P<node>[^:]+):(?P<pid>[^:]+):(?P<pstart>[^:]+):'
        r'(?P<starttime>[^:]+):(?P<type>[^:]+):(?P<vmid>[^:]*):(?P<user>[^:]*):?'
        r'(?:\s*(?P<extra>.*))?$'
    )
    
    # Pattern for index file entries (UPID followed by status)
    INDEX_PATTERN = re.compile(
        r'^(?P<upid>UPID:[^\s]+)\s+(?P<endtime>[^\s]+)\s+(?P<status>\w+)'
    )
    
    # VM-related task types to track
    VM_TASK_TYPES = {
        'qmstart', 'qmstop', 'qmshutdown', 'qmreset', 'qmdestroy',
        'vzstart', 'vzstop', 'vzshutdown'
    }
    
    def __init__(self):
        self.proxmox_api: Optional[Any] = None
        self.ssh_client: Optional[Any] = None
    
    def connect_api(self) -> bool:
        """Connect to Proxmox API"""
        if not HAS_PROXMOXER:
            logger.warning("proxmoxer not installed, API connection unavailable")
            return False
        
        try:
            if settings.proxmox.token_name and settings.proxmox.token_value:
                self.proxmox_api = ProxmoxAPI(
                    settings.proxmox.host,
                    port=settings.proxmox.port,
                    user=settings.proxmox.user,
                    token_name=settings.proxmox.token_name,
                    token_value=settings.proxmox.token_value,
                    verify_ssl=settings.proxmox.verify_ssl
                )
            else:
                self.proxmox_api = ProxmoxAPI(
                    settings.proxmox.host,
                    port=settings.proxmox.port,
                    user=settings.proxmox.user,
                    password=settings.proxmox.password,
                    verify_ssl=settings.proxmox.verify_ssl
                )
            logger.info(f"Connected to Proxmox API at {settings.proxmox.host}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Proxmox API: {e}")
            return False
    
    def connect_ssh(self) -> bool:
        """Connect to Proxmox via SSH for log file access"""
        if not HAS_PARAMIKO:
            logger.warning("paramiko not installed, SSH connection unavailable")
            return False
        
        if not settings.proxmox.ssh.enabled:
            return False
        
        try:
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            connect_kwargs = {
                'hostname': settings.proxmox.host,
                'port': settings.proxmox.ssh.port,
                'username': settings.proxmox.user.split('@')[0],  # Extract username
            }
            
            if settings.proxmox.ssh.key_file:
                connect_kwargs['key_filename'] = settings.proxmox.ssh.key_file
            else:
                connect_kwargs['password'] = settings.proxmox.password
            
            self.ssh_client.connect(**connect_kwargs)
            logger.info(f"Connected to Proxmox via SSH at {settings.proxmox.host}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect via SSH: {e}")
            return False
    
    def parse_upid(self, upid_string: str) -> Optional[VMEvent]:
        """
        Parse a UPID string into a VMEvent object.
        
        Args:
            upid_string: Full UPID string from Proxmox logs
            
        Returns:
            VMEvent object or None if parsing fails
        """
        match = self.UPID_PATTERN.match(upid_string.strip())
        if not match:
            logger.debug(f"Failed to parse UPID: {upid_string}")
            return None
        
        groups = match.groupdict()
        
        # Parse hex timestamp to datetime
        try:
            unix_timestamp = int(groups['starttime'], 16)
            timestamp = datetime.fromtimestamp(unix_timestamp)
        except (ValueError, OSError) as e:
            logger.warning(f"Failed to parse timestamp from UPID: {e}")
            return None
        
        event_type = groups['type']
        
        # Only process VM-related events
        if event_type not in self.VM_TASK_TYPES:
            return None
        
        # Parse extra info (may contain status)
        extra = groups.get('extra', '')
        status = None
        if extra:
            parts = extra.strip().split()
            if parts and parts[-1].upper() in ['OK', 'FAILED', 'ERROR']:
                status = parts[-1].upper()
        
        return VMEvent(
            upid=upid_string.strip(),
            node=groups['node'],
            pid=groups['pid'],
            pstart=groups['pstart'],
            timestamp=timestamp,
            event_type=event_type,
            vm_id=groups['vmid'],
            user=groups['user'],
            status=status
        )
    
    def parse_index_line(self, line: str) -> Optional[VMEvent]:
        """
        Parse a line from the task index file.
        
        Format: UPID:... ENDTIME STATUS
        """
        match = self.INDEX_PATTERN.match(line.strip())
        if not match:
            return self.parse_upid(line)
        
        groups = match.groupdict()
        event = self.parse_upid(groups['upid'])
        
        if event:
            event.status = groups['status']
        
        return event
    
    def get_events_from_api(
        self, 
        since: Optional[datetime] = None,
        vm_ids: Optional[List[str]] = None,
        limit: int = 1000
    ) -> List[VMEvent]:
        """
        Get VM events from Proxmox API.
        
        Args:
            since: Only get events after this datetime
            vm_ids: Filter to specific VM IDs
            limit: Maximum number of events to retrieve
            
        Returns:
            List of VMEvent objects
        """
        if not self.proxmox_api:
            if not self.connect_api():
                return []
        
        events = []
        
        try:
            # Get all nodes
            nodes = self.proxmox_api.nodes.get()
            
            for node_info in nodes:
                node_name = node_info['node']
                
                # Get tasks for this node
                try:
                    tasks = self.proxmox_api.nodes(node_name).tasks.get(
                        limit=limit,
                        typefilter='qm|vz'  # VM and container tasks
                    )
                except Exception as e:
                    logger.warning(f"Failed to get tasks for node {node_name}: {e}")
                    continue
                
                for task in tasks:
                    upid = task.get('upid', '')
                    event = self.parse_upid(upid)
                    
                    if event is None:
                        continue
                    
                    # Apply filters
                    if since and event.timestamp < since:
                        continue
                    
                    if vm_ids and event.vm_id not in vm_ids:
                        continue
                    
                    # Get status from task info
                    event.status = task.get('status', 'OK')
                    
                    events.append(event)
            
            logger.info(f"Retrieved {len(events)} VM events from Proxmox API")
            return sorted(events, key=lambda e: e.timestamp)
            
        except Exception as e:
            logger.error(f"Failed to get events from Proxmox API: {e}")
            return []
    
    def get_events_from_ssh(
        self,
        since: Optional[datetime] = None,
        vm_ids: Optional[List[str]] = None
    ) -> List[VMEvent]:
        """
        Get VM events by reading log files via SSH.
        
        Args:
            since: Only get events after this datetime
            vm_ids: Filter to specific VM IDs
            
        Returns:
            List of VMEvent objects
        """
        if not self.ssh_client:
            if not self.connect_ssh():
                return []
        
        events = []
        log_paths = [
            '/var/log/pve/tasks/index',
            '/var/log/pve/tasks/active'
        ]
        
        try:
            for log_path in log_paths:
                # Read log file via SSH
                stdin, stdout, stderr = self.ssh_client.exec_command(f'cat {log_path} 2>/dev/null')
                content = stdout.read().decode('utf-8', errors='ignore')
                
                for line in content.splitlines():
                    event = self.parse_index_line(line)
                    
                    if event is None:
                        continue
                    
                    # Apply filters
                    if since and event.timestamp < since:
                        continue
                    
                    if vm_ids and event.vm_id not in vm_ids:
                        continue
                    
                    events.append(event)
            
            logger.info(f"Retrieved {len(events)} VM events via SSH")
            return sorted(events, key=lambda e: e.timestamp)
            
        except Exception as e:
            logger.error(f"Failed to get events via SSH: {e}")
            return []
    
    def get_events_from_file(
        self,
        file_path: str,
        since: Optional[datetime] = None,
        vm_ids: Optional[List[str]] = None
    ) -> List[VMEvent]:
        """
        Parse events from a local log file (for testing or local deployment).
        
        Args:
            file_path: Path to the log file
            since: Only get events after this datetime
            vm_ids: Filter to specific VM IDs
            
        Returns:
            List of VMEvent objects
        """
        events = []
        
        try:
            with open(file_path, 'r') as f:
                for line in f:
                    event = self.parse_index_line(line)
                    
                    if event is None:
                        continue
                    
                    if since and event.timestamp < since:
                        continue
                    
                    if vm_ids and event.vm_id not in vm_ids:
                        continue
                    
                    events.append(event)
            
            logger.info(f"Parsed {len(events)} VM events from {file_path}")
            return sorted(events, key=lambda e: e.timestamp)
            
        except FileNotFoundError:
            logger.error(f"Log file not found: {file_path}")
            return []
        except Exception as e:
            logger.error(f"Failed to parse log file: {e}")
            return []
    
    def get_events(
        self,
        since: Optional[datetime] = None,
        vm_ids: Optional[List[str]] = None,
        method: str = "auto"
    ) -> List[VMEvent]:
        """
        Get VM events using the best available method.
        
        Args:
            since: Only get events after this datetime
            vm_ids: Filter to specific VM IDs
            method: "api", "ssh", or "auto" (try API first, then SSH)
            
        Returns:
            List of VMEvent objects
        """
        if method == "api" or method == "auto":
            events = self.get_events_from_api(since=since, vm_ids=vm_ids)
            if events or method == "api":
                return events
        
        if method == "ssh" or method == "auto":
            events = self.get_events_from_ssh(since=since, vm_ids=vm_ids)
            if events:
                return events
        
        logger.warning("No events retrieved from any source")
        return []
    
    def parse_sample_log(self, log_content: str) -> List[VMEvent]:
        """
        Parse a sample log content string (for testing).
        
        Args:
            log_content: Multi-line string of log entries
            
        Returns:
            List of VMEvent objects
        """
        events = []
        for line in log_content.strip().splitlines():
            event = self.parse_index_line(line)
            if event:
                events.append(event)
        return sorted(events, key=lambda e: e.timestamp)
    
    def close(self):
        """Close all connections"""
        if self.ssh_client:
            self.ssh_client.close()
            self.ssh_client = None
        self.proxmox_api = None
