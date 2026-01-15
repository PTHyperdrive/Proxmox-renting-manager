"""
Pricing Models for Manager

Defines database models for pricing tiers, GPU resources, and electricity costs.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text
from sqlalchemy.orm import DeclarativeBase

from .database import Base


class ElectricityTier(Base):
    """
    Vietnam tiered electricity pricing.
    
    Stores the 6-tier electricity pricing structure for cost calculation.
    """
    __tablename__ = "electricity_tiers"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tier_number = Column(Integer, nullable=False, unique=True)  # 1-6
    min_kwh = Column(Integer, nullable=False)  # 0, 51, 101, 201, 301, 401
    max_kwh = Column(Integer, nullable=True)   # 50, 100, 200, 300, 400, None (unlimited)
    rate_per_kwh = Column(Float, nullable=False)  # VND per kWh
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        max_str = str(self.max_kwh) if self.max_kwh else "∞"
        return f"<ElectricityTier(tier={self.tier_number}, {self.min_kwh}-{max_str} kWh, {self.rate_per_kwh} VND/kWh)>"


class HardwarePool(Base):
    """
    Server hardware pool configuration.
    
    Defines the total available resources in the Proxmox cluster
    for proportional cost calculation.
    """
    __tablename__ = "hardware_pool"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)  # e.g., "StormWorking"
    
    # CPU Resources
    total_cores = Column(Integer, nullable=False)  # Physical cores
    total_threads = Column(Integer, nullable=False)  # Logical threads (with HT)
    cpu_model = Column(String(255), nullable=True)  # e.g., "Xeon 2696v4 x2 + E5-2697Av4"
    
    # Memory
    total_ram_gb = Column(Integer, nullable=False)  # Total RAM in GB
    ram_type = Column(String(100), nullable=True)  # e.g., "DDR4 ECC Buffered"
    
    # Storage
    nvme_gb = Column(Integer, default=0)  # NVMe storage in GB
    ssd_gb = Column(Integer, default=0)   # SATA SSD storage in GB
    hdd_gb = Column(Integer, default=0)   # HDD storage in GB
    backup_gb = Column(Integer, default=0)  # Backup storage in GB
    
    # Cost Configuration
    monthly_depreciation_vnd = Column(Float, default=0)  # Monthly hardware depreciation
    average_watts = Column(Integer, default=500)  # Estimated average power draw
    
    # Status
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<HardwarePool(name={self.name}, cores={self.total_cores}, ram={self.total_ram_gb}GB)>"


class PricingTier(Base):
    """
    Fixed VM pricing tiers.
    
    Defines preset configurations (Basic, Intermediate, Advanced)
    with fixed resource allocations and pricing.
    """
    __tablename__ = "pricing_tiers"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)  # "Basic", "Intermediate", "Advanced"
    description = Column(Text, nullable=True)
    
    # CPU allocation
    vcpu_min = Column(Integer, nullable=False)
    vcpu_max = Column(Integer, nullable=False)
    
    # Memory allocation (GB)
    ram_min_gb = Column(Integer, nullable=False)
    ram_max_gb = Column(Integer, nullable=False)
    
    # Storage allocation (GB)
    nvme_gb = Column(Integer, default=0)
    ssd_gb = Column(Integer, default=0)
    hdd_gb = Column(Integer, default=0)
    
    # Features
    backup_included = Column(Boolean, default=True)
    
    # Pricing (VND)
    rate_per_hour = Column(Float, nullable=False)
    rate_per_day = Column(Float, nullable=True)
    rate_per_month = Column(Float, nullable=False)
    
    # Target market
    target_market = Column(String(255), nullable=True)  # e.g., "Developers, Web hosting"
    
    # Status
    is_active = Column(Boolean, default=True)
    display_order = Column(Integer, default=0)  # For sorting in UI
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<PricingTier(name={self.name}, vCPU={self.vcpu_min}-{self.vcpu_max}, RAM={self.ram_min_gb}-{self.ram_max_gb}GB)>"


class GPUResource(Base):
    """
    GPU passthrough resources with pricing.
    
    Defines available GPUs for AI/ML workloads with
    flexible hourly pricing.
    """
    __tablename__ = "gpu_resources"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)  # "RTX 2060", "RTX 3090"
    model = Column(String(255), nullable=True)  # Full model name
    
    # Specifications
    vram_gb = Column(Integer, nullable=False)
    cuda_cores = Column(Integer, nullable=True)
    tensor_cores = Column(Integer, nullable=True)
    
    # Power consumption
    power_watts = Column(Integer, default=200)  # TDP for electricity calculation
    
    # Pricing (VND)
    rate_per_hour = Column(Float, nullable=False)
    rate_per_day = Column(Float, nullable=True)
    rate_per_month = Column(Float, nullable=True)
    
    # Availability
    total_count = Column(Integer, default=1)  # How many of this GPU we have
    available_count = Column(Integer, default=1)  # Currently available
    is_available = Column(Boolean, default=True)
    
    # Target workloads
    target_workloads = Column(String(255), nullable=True)  # "AI Training, Rendering"
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<GPUResource(name={self.name}, VRAM={self.vram_gb}GB, rate={self.rate_per_hour} VND/h)>"
