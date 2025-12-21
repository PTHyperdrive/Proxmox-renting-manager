"""
Pydantic Schemas for API Request/Response Models

These schemas define the structure of data sent to and from the API.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


# ============================================
# VM Session Schemas
# ============================================

class VMSessionBase(BaseModel):
    """Base schema for VM session"""
    vm_id: str = Field(..., description="VM identifier (e.g., '100', '101')")
    node: str = Field(..., description="Proxmox node name")
    start_time: datetime = Field(..., description="Session start time")
    user: Optional[str] = Field(None, description="User who started the VM")


class VMSessionCreate(VMSessionBase):
    """Schema for creating a new VM session"""
    start_upid: Optional[str] = Field(None, description="Proxmox UPID for start event")


class VMSessionUpdate(BaseModel):
    """Schema for updating a VM session (when VM stops)"""
    end_time: datetime = Field(..., description="Session end time")
    stop_upid: Optional[str] = Field(None, description="Proxmox UPID for stop event")


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
    
    @property
    def formatted_duration(self) -> str:
        """Get human-readable duration"""
        if self.duration_seconds is None:
            return "Running..."
        hours = self.duration_seconds // 3600
        minutes = (self.duration_seconds % 3600) // 60
        seconds = self.duration_seconds % 60
        return f"{hours}h {minutes}m {seconds}s"


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
    vm_id: str = Field(..., description="VM identifier")
    customer_name: Optional[str] = Field(None, description="Customer name")
    customer_email: Optional[str] = Field(None, description="Customer email")
    rental_start: datetime = Field(..., description="Rental start date/time")
    rental_end: Optional[datetime] = Field(None, description="Rental end date (None for ongoing)")
    billing_cycle: str = Field("monthly", description="Billing cycle: monthly, weekly, daily, hourly")
    rate_per_hour: Optional[float] = Field(None, description="Hourly rate for cost calculation")
    notes: Optional[str] = Field(None, description="Additional notes")


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
    total_seconds: int = 0
    total_hours: float = 0.0
    session_count: int = 0
    formatted_duration: str = "0h 0m"
    
    # Period info
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    
    # Cost calculation (if rate is set)
    estimated_cost: Optional[float] = None


class UsageReport(BaseModel):
    """Usage report for a rental period"""
    rental_id: int
    vm_id: str
    customer_name: Optional[str] = None
    
    # Period
    report_start: datetime
    report_end: datetime
    
    # Usage stats
    total_seconds: int = 0
    total_hours: float = 0.0
    session_count: int = 0
    formatted_duration: str = "0h 0m"
    
    # Sessions in this period
    sessions: List[VMSessionResponse] = []
    
    # Cost
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

class SyncRequest(BaseModel):
    """Request to sync sessions from Proxmox"""
    from_date: Optional[datetime] = Field(None, description="Start syncing from this date")
    vm_ids: Optional[List[str]] = Field(None, description="Only sync these VMs (None = all)")
    force: bool = Field(False, description="Force re-sync existing sessions")


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
    status: str  # running, stopped, etc.
    is_tracked: bool = False
    total_runtime_seconds: int = 0
    formatted_runtime: str = "0h 0m"
    active_session_id: Optional[int] = None


class VMListResponse(BaseModel):
    """List of VMs with tracking info"""
    vms: List[VMInfo]
    total: int


# ============================================
# Health & Status
# ============================================

class HealthStatus(BaseModel):
    """API health status"""
    status: str = "healthy"
    version: str = "1.0.0"
    database: str = "connected"
    proxmox: str = "unknown"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
