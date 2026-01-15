"""
Pricing API Routes

Endpoints for managing pricing tiers, GPU resources, and calculating optimal pricing.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional

from ..services.pricing_calculator import PricingCalculator
from ..models.schemas import (
    PricingTierCreate, PricingTierUpdate, PricingTierResponse,
    GPUResourceCreate, GPUResourceUpdate, GPUResourceResponse,
    HardwarePoolCreate, HardwarePoolResponse,
    ElectricityTierResponse,
    PricingCalculateRequest, PricingCalculateResponse,
    PricingRecommendationsResponse
)

router = APIRouter(prefix="/api/pricing", tags=["Pricing"])

# Service instance
pricing_calculator = PricingCalculator()


# =========================================
# Initialization
# =========================================

@router.post("/seed", response_model=dict)
async def seed_default_data():
    """
    Seed the database with default pricing data.
    
    This includes:
    - Vietnam electricity tiers (6 tiers)
    - Default hardware pool configuration
    - Default pricing tiers (Basic, Intermediate, Advanced)
    - Default GPU resources (RTX 2060, 3060, 3090, 4090)
    """
    result = await pricing_calculator.seed_default_data()
    return {
        "success": True,
        "message": "Default pricing data seeded",
        "data": result
    }


# =========================================
# Pricing Tiers CRUD
# =========================================

@router.get("/tiers", response_model=List[PricingTierResponse])
async def list_pricing_tiers(
    active_only: bool = Query(True, description="Only show active tiers")
):
    """
    List all pricing tiers.
    
    Returns tiers sorted by display order (Basic, Intermediate, Advanced).
    """
    tiers = await pricing_calculator.get_pricing_tiers(active_only=active_only)
    return tiers


@router.get("/tiers/{tier_id}", response_model=PricingTierResponse)
async def get_pricing_tier(tier_id: int):
    """Get a specific pricing tier by ID."""
    tier = await pricing_calculator.get_pricing_tier(tier_id)
    if not tier:
        raise HTTPException(status_code=404, detail="Pricing tier not found")
    return tier


@router.post("/tiers", response_model=PricingTierResponse)
async def create_pricing_tier(data: PricingTierCreate):
    """
    Create a new pricing tier.
    
    Example:
    ```json
    {
        "name": "Basic",
        "vcpu_min": 2, "vcpu_max": 4,
        "ram_min_gb": 4, "ram_max_gb": 8,
        "nvme_gb": 50,
        "backup_included": true,
        "rate_per_hour": 2000,
        "rate_per_month": 500000,
        "target_market": "Developers, Web hosting"
    }
    ```
    """
    tier = await pricing_calculator.create_pricing_tier(data)
    return tier


@router.put("/tiers/{tier_id}", response_model=PricingTierResponse)
async def update_pricing_tier(tier_id: int, data: PricingTierUpdate):
    """Update an existing pricing tier."""
    tier = await pricing_calculator.update_pricing_tier(tier_id, data)
    if not tier:
        raise HTTPException(status_code=404, detail="Pricing tier not found")
    return tier


@router.delete("/tiers/{tier_id}")
async def delete_pricing_tier(tier_id: int):
    """Delete a pricing tier."""
    success = await pricing_calculator.delete_pricing_tier(tier_id)
    if not success:
        raise HTTPException(status_code=404, detail="Pricing tier not found")
    return {"success": True, "message": f"Pricing tier {tier_id} deleted"}


# =========================================
# GPU Resources CRUD
# =========================================

@router.get("/gpus", response_model=List[GPUResourceResponse])
async def list_gpu_resources():
    """
    List all GPU resources.
    
    Returns GPUs sorted by VRAM size.
    """
    gpus = await pricing_calculator.get_gpu_resources()
    return gpus


@router.get("/gpus/{gpu_id}", response_model=GPUResourceResponse)
async def get_gpu_resource(gpu_id: int):
    """Get a specific GPU resource by ID."""
    gpu = await pricing_calculator.get_gpu_by_id(gpu_id)
    if not gpu:
        raise HTTPException(status_code=404, detail="GPU resource not found")
    return gpu


@router.post("/gpus", response_model=GPUResourceResponse)
async def create_gpu_resource(data: GPUResourceCreate):
    """
    Create a new GPU resource.
    
    Example:
    ```json
    {
        "name": "RTX 2060",
        "model": "NVIDIA GeForce RTX 2060 6GB",
        "vram_gb": 6,
        "cuda_cores": 1920,
        "power_watts": 160,
        "rate_per_hour": 4000,
        "target_workloads": "Light AI/ML, Inference"
    }
    ```
    """
    gpu = await pricing_calculator.create_gpu_resource(data)
    return gpu


@router.put("/gpus/{gpu_id}", response_model=GPUResourceResponse)
async def update_gpu_resource(gpu_id: int, data: GPUResourceUpdate):
    """Update an existing GPU resource."""
    gpu = await pricing_calculator.update_gpu_resource(gpu_id, data)
    if not gpu:
        raise HTTPException(status_code=404, detail="GPU resource not found")
    return gpu


@router.delete("/gpus/{gpu_id}")
async def delete_gpu_resource(gpu_id: int):
    """Delete a GPU resource."""
    success = await pricing_calculator.delete_gpu_resource(gpu_id)
    if not success:
        raise HTTPException(status_code=404, detail="GPU resource not found")
    return {"success": True, "message": f"GPU resource {gpu_id} deleted"}


# =========================================
# Electricity & Hardware Pool
# =========================================

@router.get("/electricity", response_model=List[ElectricityTierResponse])
async def list_electricity_tiers():
    """
    List Vietnam electricity tier pricing.
    
    Returns 6 tiers with their kWh ranges and rates in VND.
    """
    tiers = await pricing_calculator.get_electricity_tiers()
    return tiers


@router.get("/hardware-pool", response_model=HardwarePoolResponse)
async def get_hardware_pool():
    """
    Get the current hardware pool configuration.
    
    Shows total available resources and depreciation settings.
    """
    pool = await pricing_calculator.get_hardware_pool()
    if not pool:
        raise HTTPException(status_code=404, detail="Hardware pool not configured")
    return pool


@router.put("/hardware-pool/{pool_id}", response_model=HardwarePoolResponse)
async def update_hardware_pool(pool_id: int, data: HardwarePoolCreate):
    """Update hardware pool configuration."""
    pool = await pricing_calculator.update_hardware_pool(pool_id, data)
    if not pool:
        raise HTTPException(status_code=404, detail="Hardware pool not found")
    return pool


# =========================================
# Pricing Calculator
# =========================================

@router.post("/calculate", response_model=PricingCalculateResponse)
async def calculate_pricing(request: PricingCalculateRequest):
    """
    Calculate optimal pricing for a custom VM configuration.
    
    Returns a breakdown of:
    - Hardware depreciation cost
    - Electricity cost
    - GPU cost (if applicable)
    - Recommended price with profit margin
    
    Example request:
    ```json
    {
        "vcpu": 4,
        "ram_gb": 16,
        "nvme_gb": 100,
        "gpu_id": null,
        "hours_per_day": 24,
        "days_per_month": 30,
        "profit_margin_percent": 30
    }
    ```
    """
    response = await pricing_calculator.calculate_pricing(request)
    return response


@router.get("/recommendations", response_model=PricingRecommendationsResponse)
async def get_pricing_recommendations(
    profit_margin: float = Query(30, ge=0, le=100, description="Profit margin percentage")
):
    """
    Get recommended pricing for all defined tiers.
    
    Compares current pricing with calculated optimal pricing
    based on hardware costs, electricity, and desired margin.
    """
    recommendations = await pricing_calculator.get_tier_recommendations(profit_margin)
    return recommendations


@router.get("/quick-estimate")
async def quick_price_estimate(
    vcpu: int = Query(..., ge=1, description="Number of vCPUs"),
    ram_gb: int = Query(..., ge=1, description="RAM in GB"),
    nvme_gb: int = Query(0, ge=0, description="NVMe storage in GB"),
    gpu_id: Optional[int] = Query(None, description="GPU resource ID"),
    margin: float = Query(30, ge=0, le=100, description="Profit margin %")
):
    """
    Quick price estimate without full calculation details.
    
    Returns simple hourly and monthly prices.
    """
    request = PricingCalculateRequest(
        vcpu=vcpu,
        ram_gb=ram_gb,
        nvme_gb=nvme_gb,
        gpu_id=gpu_id,
        profit_margin_percent=margin
    )
    
    response = await pricing_calculator.calculate_pricing(request)
    
    return {
        "config": {
            "vcpu": vcpu,
            "ram_gb": ram_gb,
            "nvme_gb": nvme_gb,
            "gpu_id": gpu_id
        },
        "price_per_hour": response.breakdown.total_price_per_hour,
        "price_per_day": response.breakdown.total_price_per_day,
        "price_per_month": response.breakdown.total_price_per_month,
        "profit_margin": margin,
        "currency": "VND"
    }
