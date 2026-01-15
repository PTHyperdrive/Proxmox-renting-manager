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
    """Heartbeat response with optional force sync flag"""
    success: bool
    server_time: datetime = Field(default_factory=datetime.utcnow)
    force_sync: bool = False  # If True, client should send full snapshot


# ============================================
# Real-time VM State Schemas
# ============================================

class VMStartEvent(BaseModel):
    """Event when a VM starts"""
    node: str = Field(..., description="Proxmox node name")
    vm_id: str = Field(..., description="VM ID")
    vm_name: Optional[str] = Field(None, description="VM name")
    vm_type: str = Field("qemu", description="VM type: qemu or lxc")
    start_time: datetime = Field(default_factory=datetime.utcnow)


class VMStartResponse(BaseModel):
    """Response after VM start event"""
    success: bool
    message: str
    session_id: Optional[int] = None


class VMStopEvent(BaseModel):
    """Event when a VM stops"""
    node: str = Field(..., description="Proxmox node name")
    vm_id: str = Field(..., description="VM ID")
    stop_time: datetime = Field(default_factory=datetime.utcnow)


class VMStopResponse(BaseModel):
    """Response after VM stop event"""
    success: bool
    message: str
    session_id: Optional[int] = None
    duration_seconds: Optional[int] = None


class VMStateData(BaseModel):
    """Current state of a single VM"""
    vm_id: str
    vm_type: str = "qemu"
    name: Optional[str] = None
    status: str  # running, stopped, paused
    node: str
    uptime: int = 0
    cpu: float = 0.0
    memory: int = 0
    maxmem: int = 0


class VMStatesSnapshot(BaseModel):
    """Full snapshot of all VM states from a node"""
    node: str = Field(..., description="Node sending the snapshot")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    vms: List[VMStateData] = Field(..., description="List of VM states")


class VMStatesResponse(BaseModel):
    """Response after processing VM states snapshot"""
    success: bool
    message: str
    vms_processed: int = 0
    sessions_started: int = 0
    sessions_stopped: int = 0


class ForceSyncRequest(BaseModel):
    """Request to trigger force sync on all clients"""
    target_node: Optional[str] = None  # None = all nodes


class ForceSyncResponse(BaseModel):
    """Response after triggering force sync"""
    success: bool
    message: str
    nodes_notified: int = 0


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

from enum import Enum

class BillingCycle(str, Enum):
    """Billing cycle options for rentals"""
    HOURLY = "hourly"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class RentalBase(BaseModel):
    """Base schema for rental"""
    vm_id: str
    node: Optional[str] = None
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    rental_start: datetime
    rental_end: Optional[datetime] = None
    billing_cycle: BillingCycle = BillingCycle.MONTHLY
    
    # Pricing - set based on billing cycle
    rate_per_hour: Optional[float] = None      # For hourly billing
    rate_per_week: Optional[float] = None      # For weekly billing  
    rate_per_month: Optional[float] = None     # For monthly billing
    
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
    billing_cycle: Optional[BillingCycle] = None
    rate_per_hour: Optional[float] = None
    rate_per_week: Optional[float] = None
    rate_per_month: Optional[float] = None
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


# ============================================
# Pricing Schemas
# ============================================

class ElectricityTierBase(BaseModel):
    """Base schema for electricity tier"""
    tier_number: int = Field(..., ge=1, le=6, description="Tier number (1-6)")
    min_kwh: int = Field(..., ge=0, description="Minimum kWh for this tier")
    max_kwh: Optional[int] = Field(None, description="Maximum kWh (None for unlimited)")
    rate_per_kwh: float = Field(..., gt=0, description="Rate in VND per kWh")


class ElectricityTierResponse(ElectricityTierBase):
    """Response schema for electricity tier"""
    model_config = ConfigDict(from_attributes=True)
    id: int


class HardwarePoolBase(BaseModel):
    """Base schema for hardware pool"""
    name: str = Field(..., description="Pool name (e.g., 'StormWorking')")
    total_cores: int = Field(..., gt=0, description="Total physical cores")
    total_threads: int = Field(..., gt=0, description="Total logical threads")
    cpu_model: Optional[str] = Field(None, description="CPU model description")
    total_ram_gb: int = Field(..., gt=0, description="Total RAM in GB")
    ram_type: Optional[str] = Field(None, description="RAM type (e.g., 'DDR4 ECC')")
    nvme_gb: int = Field(0, ge=0, description="NVMe storage in GB")
    ssd_gb: int = Field(0, ge=0, description="SATA SSD storage in GB")
    hdd_gb: int = Field(0, ge=0, description="HDD storage in GB")
    backup_gb: int = Field(0, ge=0, description="Backup storage in GB")
    monthly_depreciation_vnd: float = Field(0, ge=0, description="Monthly hardware depreciation cost")
    average_watts: int = Field(500, gt=0, description="Average power consumption in watts")


class HardwarePoolCreate(HardwarePoolBase):
    """Schema for creating hardware pool"""
    pass


class HardwarePoolResponse(HardwarePoolBase):
    """Response schema for hardware pool"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class PricingTierBase(BaseModel):
    """Base schema for pricing tier"""
    name: str = Field(..., description="Tier name (Basic, Intermediate, Advanced)")
    description: Optional[str] = None
    vcpu_min: int = Field(..., ge=1, description="Minimum vCPU allocation")
    vcpu_max: int = Field(..., ge=1, description="Maximum vCPU allocation")
    ram_min_gb: int = Field(..., ge=1, description="Minimum RAM in GB")
    ram_max_gb: int = Field(..., ge=1, description="Maximum RAM in GB")
    nvme_gb: int = Field(0, ge=0, description="NVMe storage in GB")
    ssd_gb: int = Field(0, ge=0, description="SATA SSD storage in GB")
    hdd_gb: int = Field(0, ge=0, description="HDD storage in GB")
    backup_included: bool = Field(True, description="Whether backup is included")
    rate_per_hour: float = Field(..., gt=0, description="Hourly rate in VND")
    rate_per_day: Optional[float] = Field(None, description="Daily rate in VND")
    rate_per_month: float = Field(..., gt=0, description="Monthly rate in VND")
    target_market: Optional[str] = Field(None, description="Target market description")


class PricingTierCreate(PricingTierBase):
    """Schema for creating pricing tier"""
    pass


class PricingTierUpdate(BaseModel):
    """Schema for updating pricing tier"""
    name: Optional[str] = None
    description: Optional[str] = None
    vcpu_min: Optional[int] = Field(None, ge=1)
    vcpu_max: Optional[int] = Field(None, ge=1)
    ram_min_gb: Optional[int] = Field(None, ge=1)
    ram_max_gb: Optional[int] = Field(None, ge=1)
    nvme_gb: Optional[int] = Field(None, ge=0)
    ssd_gb: Optional[int] = Field(None, ge=0)
    hdd_gb: Optional[int] = Field(None, ge=0)
    backup_included: Optional[bool] = None
    rate_per_hour: Optional[float] = Field(None, gt=0)
    rate_per_day: Optional[float] = None
    rate_per_month: Optional[float] = Field(None, gt=0)
    target_market: Optional[str] = None
    is_active: Optional[bool] = None


class PricingTierResponse(PricingTierBase):
    """Response schema for pricing tier"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_active: bool = True
    display_order: int = 0
    created_at: datetime
    updated_at: datetime


class GPUResourceBase(BaseModel):
    """Base schema for GPU resource"""
    name: str = Field(..., description="GPU name (e.g., 'RTX 2060')")
    model: Optional[str] = Field(None, description="Full model name")
    vram_gb: int = Field(..., gt=0, description="VRAM in GB")
    cuda_cores: Optional[int] = Field(None, description="Number of CUDA cores")
    tensor_cores: Optional[int] = Field(None, description="Number of Tensor cores")
    power_watts: int = Field(200, gt=0, description="TDP in watts")
    rate_per_hour: float = Field(..., gt=0, description="Hourly rate in VND")
    rate_per_day: Optional[float] = Field(None, description="Daily rate in VND")
    rate_per_month: Optional[float] = Field(None, description="Monthly rate in VND")
    total_count: int = Field(1, ge=1, description="Total units available")
    target_workloads: Optional[str] = Field(None, description="Target workloads description")


class GPUResourceCreate(GPUResourceBase):
    """Schema for creating GPU resource"""
    pass


class GPUResourceUpdate(BaseModel):
    """Schema for updating GPU resource"""
    name: Optional[str] = None
    model: Optional[str] = None
    vram_gb: Optional[int] = Field(None, gt=0)
    cuda_cores: Optional[int] = None
    tensor_cores: Optional[int] = None
    power_watts: Optional[int] = Field(None, gt=0)
    rate_per_hour: Optional[float] = Field(None, gt=0)
    rate_per_day: Optional[float] = None
    rate_per_month: Optional[float] = None
    total_count: Optional[int] = Field(None, ge=1)
    available_count: Optional[int] = Field(None, ge=0)
    is_available: Optional[bool] = None
    target_workloads: Optional[str] = None


class GPUResourceResponse(GPUResourceBase):
    """Response schema for GPU resource"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    available_count: int = 1
    is_available: bool = True
    created_at: datetime
    updated_at: datetime


class PricingCalculateRequest(BaseModel):
    """Request to calculate optimal pricing"""
    vcpu: int = Field(..., ge=1, description="Number of vCPUs")
    ram_gb: int = Field(..., ge=1, description="RAM in GB")
    nvme_gb: int = Field(0, ge=0, description="NVMe storage in GB")
    ssd_gb: int = Field(0, ge=0, description="SSD storage in GB")
    hdd_gb: int = Field(0, ge=0, description="HDD storage in GB")
    gpu_id: Optional[int] = Field(None, description="GPU resource ID if using GPU")
    hours_per_day: float = Field(24, gt=0, le=24, description="Expected usage hours per day")
    days_per_month: int = Field(30, ge=1, le=31, description="Expected usage days per month")
    profit_margin_percent: float = Field(30, ge=0, le=100, description="Desired profit margin percentage")


class PricingCostBreakdown(BaseModel):
    """Breakdown of costs for pricing calculation"""
    hardware_cost_per_hour: float = Field(..., description="Hardware depreciation cost per hour in VND")
    electricity_cost_per_hour: float = Field(..., description="Electricity cost per hour in VND")
    gpu_cost_per_hour: float = Field(0, description="GPU cost per hour in VND")
    base_cost_per_hour: float = Field(..., description="Total base cost per hour in VND")
    profit_per_hour: float = Field(..., description="Profit per hour in VND")
    total_price_per_hour: float = Field(..., description="Recommended price per hour in VND")
    total_price_per_day: float = Field(..., description="Recommended price per day in VND")
    total_price_per_month: float = Field(..., description="Recommended price per month in VND")
    profit_margin_applied: float = Field(..., description="Profit margin applied (percentage)")


class PricingCalculateResponse(BaseModel):
    """Response from pricing calculation"""
    request: PricingCalculateRequest
    breakdown: PricingCostBreakdown
    hardware_pool: Optional[str] = Field(None, description="Hardware pool name used for calculation")
    electricity_tier_info: str = Field("Vietnam tiered pricing", description="Electricity pricing structure used")


class PricingRecommendation(BaseModel):
    """Pricing recommendation for a tier"""
    tier_name: str
    vcpu_range: str
    ram_range: str
    storage_included: str
    recommended_hourly_rate: float
    recommended_monthly_rate: float
    current_hourly_rate: Optional[float] = None
    current_monthly_rate: Optional[float] = None
    cost_analysis: PricingCostBreakdown


class PricingRecommendationsResponse(BaseModel):
    """Response with pricing recommendations for all tiers"""
    recommendations: List[PricingRecommendation]
    hardware_pool: str
    profit_margin_used: float
    generated_at: datetime = Field(default_factory=datetime.utcnow)

