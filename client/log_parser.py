"""
Proxmox Log Parser

Parses VM start/stop events from Proxmox task logs.
"""

import re
import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Set

logger = logging.getLogger(__name__)


# Event types for VM operations
START_EVENTS = {'qmstart', 'vzstart'}
STOP_EVENTS = {'qmstop', 'qmshutdown', 'qmdestroy', 'vzstop', 'vzshutdown', 'vzdestroy'}
ALL_VM_EVENTS = START_EVENTS | STOP_EVENTS


@dataclass
class VMEvent:
    """Represents a VM start/stop event"""
    upid: str
    node: str
    pid: str
    pstart: str
    timestamp: datetime
    event_type: str
    vm_id: str
    user: str
    status: Optional[str] = None
    
    @property
    def is_start(self) -> bool:
        return self.event_type in START_EVENTS
    
    @property
    def is_stop(self) -> bool:
        return self.event_type in STOP_EVENTS
    
    @property
    def is_successful(self) -> bool:
        return self.status is None or self.status == 'OK'
    
    def to_dict(self) -> dict:
        return {
            'upid': self.upid,
            'node': self.node,
            'vm_id': self.vm_id,
            'event_type': self.event_type,
            'timestamp': self.timestamp.isoformat(),
            'user': self.user,
            'status': self.status
        }


class LogParser:
    """
    Parser for Proxmox task log files.
    
    Proxmox UPID format:
    UPID:node:PID:PSTART:TIMESTAMP:TYPE:VMID:USER:
    
    Example:
    UPID:pve1:003D2ED6:01835485:5F09980F:qmstart:100:root@pam:
    """
    
    # Regex for UPID format
    UPID_PATTERN = re.compile(
        r'UPID:([^:]+):([^:]+):([^:]+):([0-9A-Fa-f]+):([^:]+):([^:]*):([^:]*):?'
    )
    
    def __init__(self, node_name: str = ''):
        self.node_name = node_name
        self.processed_upids: Set[str] = set()
    
    def parse_upid(self, upid: str) -> Optional[VMEvent]:
        """
        Parse a UPID string into a VMEvent.
        
        Args:
            upid: Proxmox UPID string
            
        Returns:
            VMEvent if valid VM event, None otherwise
        """
        match = self.UPID_PATTERN.match(upid.strip())
        if not match:
            return None
        
        node, pid, pstart, ts_hex, event_type, vm_id, user = match.groups()
        
        # Only track VM start/stop events
        if event_type not in ALL_VM_EVENTS:
            return None
        
        # Parse hex timestamp
        try:
            timestamp = datetime.fromtimestamp(int(ts_hex, 16))
        except (ValueError, OSError):
            logger.warning(f"Invalid timestamp in UPID: {upid}")
            return None
        
        return VMEvent(
            upid=upid.strip(),
            node=node,
            pid=pid,
            pstart=pstart,
            timestamp=timestamp,
            event_type=event_type,
            vm_id=vm_id,
            user=user
        )
    
    def parse_index_line(self, line: str) -> Optional[VMEvent]:
        """
        Parse a task index file line.
        
        Format: UPID... [END_TIME] [STATUS]
        Example: UPID:pve1:...:qmstart:100:root@pam: 5F099B97 OK
        """
        parts = line.strip().split()
        if not parts:
            return None
        
        upid = parts[0]
        event = self.parse_upid(upid)
        
        if event and len(parts) >= 3:
            # Last part is status
            event.status = parts[-1]
        
        return event
    
    def parse_log_file(self, file_path: str, since: Optional[datetime] = None) -> List[VMEvent]:
        """
        Parse a Proxmox task log file.
        
        Args:
            file_path: Path to log file
            since: Only return events after this time
            
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
                    
                    # Skip already processed
                    if event.upid in self.processed_upids:
                        continue
                    
                    # Skip old events if since specified
                    if since and event.timestamp < since:
                        continue
                    
                    # Skip failed events
                    if not event.is_successful:
                        continue
                    
                    events.append(event)
        
        except FileNotFoundError:
            logger.debug(f"Log file not found: {file_path}")
        except PermissionError:
            logger.error(f"Permission denied reading: {file_path}")
        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")
        
        return sorted(events, key=lambda e: e.timestamp)
    
    def parse_multiple_files(
        self,
        file_paths: List[str],
        since: Optional[datetime] = None
    ) -> List[VMEvent]:
        """Parse multiple log files and combine events."""
        all_events = []
        seen_upids = set()
        
        for path in file_paths:
            events = self.parse_log_file(path, since)
            for event in events:
                if event.upid not in seen_upids:
                    all_events.append(event)
                    seen_upids.add(event.upid)
        
        return sorted(all_events, key=lambda e: e.timestamp)
    
    def mark_processed(self, events: List[VMEvent]):
        """Mark events as processed."""
        for event in events:
            self.processed_upids.add(event.upid)
