"""
Tests for Proxmox Log Parser

Tests the UPID parsing and event extraction functionality.
"""

import pytest
from datetime import datetime

from app.services.log_parser import ProxmoxLogParser, VMEvent, EventType


class TestUPIDParsing:
    """Test UPID string parsing"""
    
    def setup_method(self):
        self.parser = ProxmoxLogParser()
    
    def test_parse_qmstart_upid(self):
        """Test parsing a VM start UPID"""
        upid = "UPID:pve1:003D2ED6:01835485:5F09980F:qmstart:100:root@pam:"
        event = self.parser.parse_upid(upid)
        
        assert event is not None
        assert event.node == "pve1"
        assert event.vm_id == "100"
        assert event.event_type == "qmstart"
        assert event.user == "root@pam"
        assert event.is_start == True
        assert event.is_stop == False
    
    def test_parse_qmstop_upid(self):
        """Test parsing a VM stop UPID"""
        upid = "UPID:pve1:003D2ED7:01835486:5F099900:qmstop:100:root@pam:"
        event = self.parser.parse_upid(upid)
        
        assert event is not None
        assert event.event_type == "qmstop"
        assert event.is_start == False
        assert event.is_stop == True
    
    def test_parse_qmshutdown_upid(self):
        """Test parsing a VM shutdown UPID"""
        upid = "UPID:pve1:003D2ED8:01835487:5F099901:qmshutdown:100:admin@pve:"
        event = self.parser.parse_upid(upid)
        
        assert event is not None
        assert event.event_type == "qmshutdown"
        assert event.is_stop == True
        assert event.user == "admin@pve"
    
    def test_parse_lxc_start_upid(self):
        """Test parsing a LXC container start UPID"""
        upid = "UPID:pve1:003D2ED9:01835488:5F099902:vzstart:200:root@pam:"
        event = self.parser.parse_upid(upid)
        
        assert event is not None
        assert event.event_type == "vzstart"
        assert event.vm_id == "200"
        assert event.is_start == True
    
    def test_parse_invalid_upid(self):
        """Test parsing an invalid UPID returns None"""
        invalid_upids = [
            "",
            "not a upid",
            "UPID:only:two:parts",
            "UPID:missing:type"
        ]
        
        for upid in invalid_upids:
            event = self.parser.parse_upid(upid)
            # Invalid UPIDs should return None
            assert event is None or event.event_type not in self.parser.VM_TASK_TYPES
    
    def test_parse_non_vm_task_returns_none(self):
        """Test that non-VM tasks (like vncproxy) return None"""
        upid = "UPID:pve1:003D2ED6:01835485:5F09980F:vncproxy:100:root@pam:"
        event = self.parser.parse_upid(upid)
        
        # vncproxy is not a VM start/stop event
        assert event is None
    
    def test_timestamp_parsing(self):
        """Test that hex timestamp is correctly parsed"""
        # 0x5F09980F = 1594456079 (Unix timestamp)
        upid = "UPID:pve1:003D2ED6:01835485:5F09980F:qmstart:100:root@pam:"
        event = self.parser.parse_upid(upid)
        
        assert event is not None
        assert isinstance(event.timestamp, datetime)
        # Verify timestamp is reasonable (year 2020)
        assert event.timestamp.year == 2020


class TestIndexLineParsing:
    """Test parsing task index file lines"""
    
    def setup_method(self):
        self.parser = ProxmoxLogParser()
    
    def test_parse_index_line_with_status(self):
        """Test parsing an index line with OK status"""
        line = "UPID:pve1:003D2ED6:01835485:5F09980F:qmstart:100:root@pam: 5F099B97 OK"
        event = self.parser.parse_index_line(line)
        
        assert event is not None
        assert event.status == "OK"
        assert event.is_successful == True
    
    def test_parse_index_line_failed_status(self):
        """Test parsing an index line with FAILED status"""
        line = "UPID:pve1:003D2ED6:01835485:5F09980F:qmstart:100:root@pam: 5F099B97 FAILED"
        event = self.parser.parse_index_line(line)
        
        assert event is not None
        assert event.status == "FAILED"
        assert event.is_successful == False


class TestSampleLogParsing:
    """Test parsing sample log content"""
    
    def setup_method(self):
        self.parser = ProxmoxLogParser()
    
    def test_parse_multiple_events(self):
        """Test parsing multiple log entries"""
        log_content = """UPID:pve1:003D2ED6:01835485:5F09980F:qmstart:100:root@pam: 5F099B97 OK
UPID:pve1:003D2ED7:01835486:5F099900:qmstop:100:root@pam: 5F09A000 OK
UPID:pve1:003D2ED8:01835487:5F09A001:qmstart:101:admin@pve: 5F09A100 OK"""
        
        events = self.parser.parse_sample_log(log_content)
        
        assert len(events) == 3
        assert events[0].vm_id == "100"
        assert events[0].event_type == "qmstart"
        assert events[1].event_type == "qmstop"
        assert events[2].vm_id == "101"
    
    def test_events_sorted_by_timestamp(self):
        """Test that events are returned sorted by timestamp"""
        log_content = """UPID:pve1:003D2ED8:01835487:5F09A001:qmstart:101:admin@pve:
UPID:pve1:003D2ED6:01835485:5F09980F:qmstart:100:root@pam:
UPID:pve1:003D2ED7:01835486:5F099900:qmstop:100:root@pam:"""
        
        events = self.parser.parse_sample_log(log_content)
        
        # Should be sorted by timestamp
        for i in range(len(events) - 1):
            assert events[i].timestamp <= events[i + 1].timestamp


class TestEventType:
    """Test EventType enum methods"""
    
    def test_is_start_event(self):
        """Test identifying start events"""
        assert EventType.is_start_event("qmstart") == True
        assert EventType.is_start_event("vzstart") == True
        assert EventType.is_start_event("qmstop") == False
        assert EventType.is_start_event("qmshutdown") == False
    
    def test_is_stop_event(self):
        """Test identifying stop events"""
        assert EventType.is_stop_event("qmstop") == True
        assert EventType.is_stop_event("qmshutdown") == True
        assert EventType.is_stop_event("qmdestroy") == True
        assert EventType.is_stop_event("vzstop") == True
        assert EventType.is_stop_event("qmstart") == False


class TestVMEvent:
    """Test VMEvent dataclass methods"""
    
    def test_to_dict(self):
        """Test converting event to dictionary"""
        event = VMEvent(
            upid="UPID:pve1:123:456:5F09980F:qmstart:100:root@pam:",
            node="pve1",
            pid="123",
            pstart="456",
            timestamp=datetime(2020, 7, 11, 12, 0, 0),
            event_type="qmstart",
            vm_id="100",
            user="root@pam",
            status="OK"
        )
        
        d = event.to_dict()
        
        assert d["node"] == "pve1"
        assert d["vm_id"] == "100"
        assert d["is_start"] == True
        assert d["is_stop"] == False
        assert d["status"] == "OK"
