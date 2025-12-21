"""
Pydantic Schemas for Manager API

Request/Response models for the Manager server.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


# ============================================
# Node & Ingest Schemas (for Client communication)
# ============================================

class NodeRegisterRequest(BaseModel):
    """Request to register a new Proxmox node"""
    name: str = Field(..., description="Unique node identifier")
    hostname: Optional[str] = Field(None, description="Node hostname")


class NodeRegisterResponse(BaseModel):
    """Response after node registration"""
    success: bool
    message: str
    node_id: Optional[int] = None


class EventData(BaseModel):
    """Single VM event from client"""
    upid: str = Field(..., description="Proxmox UPID string")
    vm_id: str = Field(..., description="VM identifier")
    event_type: str = Field(..., description="Event type: qmstart, qmstop, etc.")
    timestamp: datetime = Field(..., description="Event timestamp")
    user: Optional[str] = Field(None, description="User who triggered the event")
    status: Optional[str] = Field(None, description="Event status: OK, FAILED")


class EventIngestRequest(BaseModel):
    """Request to ingest events from a client"""
    node: str = Field(..., description="Node name sending the events")
    events: List[EventData] = Field(..., description="List of events to ingest")


class EventIngestResponse(BaseModel):
    """Response after ingesting events"""
    success: bool
    message: str
    events_processed: int = 0
    sessions_created: int = 0
    sessions_updated: int = 0
    errors: List[str] = []


class HeartbeatRequest(BaseModel):
    """Client heartbeat request"""
    node: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    stats: Optional[dict] = None


class HeartbeatResponse(BaseModel):
    """Heartbeat response"""
    success: bool
    server_time: datetime = Field(default_factory=datetime.utcnow)


# ============================================
# VM Session Schemas
# ============================================

class VMSessionBase(BaseModel):
    """Base schema for VM session"""
    vm_id: str
    node: str
    start_time: datetime
    user: Optional[str] = None


class VMSessionCreate(VMSessionBase):
    """Schema for creating a new VM session"""
    start_upid: Optional[str] = None


class VMSessionUpdate(BaseModel):
    """Schema for updating a VM session"""
    end_time: datetime
    stop_upid: Optional[str] = None


class VMSessionResponse(VMSessionBase):
    """Schema for VM session in API responses"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    end_time: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    is_running: bool = True
    start_upid: Optional[str] = None
    stop_upid: Optional[str] = None
    created_at: datetime


class VMSessionList(BaseModel):
    """Paginated list of VM sessions"""
    sessions: List[VMSessionResponse]
    total: int
    page: int = 1
    per_page: int = 50


# ============================================
# Rental Schemas
# ============================================

class RentalBase(BaseModel):
    """Base schema for rental"""
    vm_id: str
    node: Optional[str] = None
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    rental_start: datetime
    rental_end: Optional[datetime] = None
    billing_cycle: str = "monthly"
    rate_per_hour: Optional[float] = None
    notes: Optional[str] = None


class RentalCreate(RentalBase):
    """Schema for creating a new rental"""
    pass


class RentalUpdate(BaseModel):
    """Schema for updating a rental"""
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    rental_start: Optional[datetime] = None
    rental_end: Optional[datetime] = None
    billing_cycle: Optional[str] = None
    rate_per_hour: Optional[float] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class RentalResponse(RentalBase):
    """Schema for rental in API responses"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


# ============================================
# Usage & Reporting Schemas
# ============================================

class VMUsage(BaseModel):
    """Usage statistics for a single VM"""
    vm_id: str
    node: Optional[str] = None
    total_seconds: int = 0
    total_hours: float = 0.0
    session_count: int = 0
    formatted_duration: str = "0h 0m"
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    estimated_cost: Optional[float] = None


class UsageReport(BaseModel):
    """Usage report for a rental period"""
    rental_id: int
    vm_id: str
    customer_name: Optional[str] = None
    report_start: datetime
    report_end: datetime
    total_seconds: int = 0
    total_hours: float = 0.0
    session_count: int = 0
    formatted_duration: str = "0h 0m"
    sessions: List[VMSessionResponse] = []
    rate_per_hour: Optional[float] = None
    total_cost: Optional[float] = None


class DailyUsage(BaseModel):
    """Daily usage breakdown"""
    date: datetime
    total_seconds: int
    session_count: int
    formatted_duration: str


class MonthlyUsage(BaseModel):
    """Monthly usage breakdown"""
    year: int
    month: int
    total_seconds: int
    session_count: int
    formatted_duration: str
    daily_breakdown: List[DailyUsage] = []


# ============================================
# Sync & Status Schemas
# ============================================

class SyncResponse(BaseModel):
    """Response from sync operation"""
    success: bool
    message: str
    sessions_created: int = 0
    sessions_updated: int = 0
    sessions_skipped: int = 0
    errors: List[str] = []


class VMInfo(BaseModel):
    """Basic VM information"""
    vm_id: str
    name: Optional[str] = None
    node: str
    status: str
    is_tracked: bool = False
    total_runtime_seconds: int = 0
    formatted_runtime: str = "0h 0m"
    active_session_id: Optional[int] = None


class VMListResponse(BaseModel):
    """List of VMs with tracking info"""
    vms: List[VMInfo]
    total: int


class NodeInfo(BaseModel):
    """Proxmox node information"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    name: str
    hostname: Optional[str] = None
    is_active: bool
    last_seen: Optional[datetime] = None
    total_events: int = 0
    total_vms: int = 0


class NodeListResponse(BaseModel):
    """List of registered nodes"""
    nodes: List[NodeInfo]
    total: int


# ============================================
# Health & Status
# ============================================

class HealthStatus(BaseModel):
    """API health status"""
    status: str = "healthy"
    version: str = "2.0.0"
    database: str = "connected"
    nodes_active: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
