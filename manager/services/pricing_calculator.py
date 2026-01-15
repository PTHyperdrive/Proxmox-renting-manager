"""
Pricing Calculator Service

Calculates optimal VM pricing based on:
- Hardware depreciation costs
- Electricity costs (Vietnam tiered pricing)
- GPU passthrough costs
- Desired profit margin
"""

import logging
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import get_db_context
from ..models.pricing import ElectricityTier, HardwarePool, PricingTier, GPUResource
from ..models.schemas import (
    PricingCalculateRequest, PricingCalculateResponse, PricingCostBreakdown,
    PricingRecommendation, PricingRecommendationsResponse,
    PricingTierCreate, PricingTierUpdate, PricingTierResponse,
    GPUResourceCreate, GPUResourceUpdate, GPUResourceResponse,
    HardwarePoolCreate, HardwarePoolResponse,
    ElectricityTierResponse
)

logger = logging.getLogger(__name__)


# Vietnam tiered electricity pricing (VND per kWh)
DEFAULT_ELECTRICITY_TIERS = [
    {"tier_number": 1, "min_kwh": 0, "max_kwh": 50, "rate_per_kwh": 1984},
    {"tier_number": 2, "min_kwh": 51, "max_kwh": 100, "rate_per_kwh": 2050},
    {"tier_number": 3, "min_kwh": 101, "max_kwh": 200, "rate_per_kwh": 2380},
    {"tier_number": 4, "min_kwh": 201, "max_kwh": 300, "rate_per_kwh": 2998},
    {"tier_number": 5, "min_kwh": 301, "max_kwh": 400, "rate_per_kwh": 3350},
    {"tier_number": 6, "min_kwh": 401, "max_kwh": None, "rate_per_kwh": 3460},
]

# Default hardware pool configuration based on user's specs
DEFAULT_HARDWARE_POOL = {
    "name": "StormWorking",
    "total_cores": 60,  # 44 + 16 from 2x Xeon 2696v4 + 1x E5-2697Av4
    "total_threads": 120,  # 88 + 32
    "cpu_model": "Xeon 2696v4 x2 + E5-2697Av4 x1",
    "total_ram_gb": 320,
    "ram_type": "DDR4 ECC Buffered",
    "nvme_gb": 2048,  # 2TB
    "ssd_gb": 4096,   # 4TB
    "hdd_gb": 8192,   # 8TB
    "backup_gb": 3072,  # 3TB backup server
    "monthly_depreciation_vnd": 5_000_000,  # Estimated monthly depreciation
    "average_watts": 800,  # Dual socket server + storage
}

# Default pricing tiers
DEFAULT_PRICING_TIERS = [
    {
        "name": "Basic",
        "description": "Light development, web hosting",
        "vcpu_min": 2, "vcpu_max": 4,
        "ram_min_gb": 4, "ram_max_gb": 8,
        "nvme_gb": 50,
        "backup_included": True,
        "rate_per_hour": 2000,
        "rate_per_month": 500_000,
        "target_market": "Developers, Web hosting",
        "display_order": 1,
    },
    {
        "name": "Intermediate",
        "description": "Full-stack development, gaming",
        "vcpu_min": 6, "vcpu_max": 8,
        "ram_min_gb": 16, "ram_max_gb": 32,
        "nvme_gb": 100,
        "backup_included": True,
        "rate_per_hour": 5000,
        "rate_per_month": 1_200_000,
        "target_market": "Full-stack dev, Gaming",
        "display_order": 2,
    },
    {
        "name": "Advanced",
        "description": "Heavy workloads, servers",
        "vcpu_min": 12, "vcpu_max": 16,
        "ram_min_gb": 64, "ram_max_gb": 128,
        "nvme_gb": 250,
        "backup_included": True,
        "rate_per_hour": 12000,
        "rate_per_month": 3_000_000,
        "target_market": "Heavy workloads, Servers",
        "display_order": 3,
    },
]

# Default GPU resources
DEFAULT_GPU_RESOURCES = [
    {
        "name": "RTX 2060",
        "model": "NVIDIA GeForce RTX 2060 6GB",
        "vram_gb": 6,
        "cuda_cores": 1920,
        "power_watts": 160,
        "rate_per_hour": 4000,
        "target_workloads": "Light AI/ML, Inference",
    },
    {
        "name": "RTX 3060",
        "model": "NVIDIA GeForce RTX 3060 12GB",
        "vram_gb": 12,
        "cuda_cores": 3584,
        "power_watts": 170,
        "rate_per_hour": 6000,
        "target_workloads": "Training, Rendering",
    },
    {
        "name": "RTX 3090",
        "model": "NVIDIA GeForce RTX 3090 24GB",
        "vram_gb": 24,
        "cuda_cores": 10496,
        "power_watts": 350,
        "rate_per_hour": 12000,
        "target_workloads": "Heavy Training, 3D Rendering",
    },
    {
        "name": "RTX 4090",
        "model": "NVIDIA GeForce RTX 4090 24GB",
        "vram_gb": 24,
        "cuda_cores": 16384,
        "power_watts": 450,
        "rate_per_hour": 20000,
        "target_workloads": "Professional AI/ML, Research",
    },
]


class PricingCalculator:
    """
    Calculates optimal VM pricing based on hardware costs, electricity, and margins.
    """
    
    def __init__(self):
        self._electricity_tiers_cache: Optional[List[dict]] = None
        self._hardware_pool_cache: Optional[dict] = None
    
    # =========================================
    # Initialization & Seeding
    # =========================================
    
    async def seed_default_data(self) -> dict:
        """
        Seed the database with default electricity tiers, hardware pool,
        pricing tiers, and GPU resources.
        """
        results = {
            "electricity_tiers": 0,
            "hardware_pool": False,
            "pricing_tiers": 0,
            "gpu_resources": 0,
        }
        
        async with get_db_context() as db:
            # Seed electricity tiers
            existing_tiers = await db.execute(select(ElectricityTier))
            if not existing_tiers.scalars().first():
                for tier_data in DEFAULT_ELECTRICITY_TIERS:
                    tier = ElectricityTier(**tier_data)
                    db.add(tier)
                    results["electricity_tiers"] += 1
            
            # Seed hardware pool
            existing_pool = await db.execute(select(HardwarePool))
            if not existing_pool.scalars().first():
                pool = HardwarePool(**DEFAULT_HARDWARE_POOL)
                db.add(pool)
                results["hardware_pool"] = True
            
            # Seed pricing tiers
            existing_pricing = await db.execute(select(PricingTier))
            if not existing_pricing.scalars().first():
                for tier_data in DEFAULT_PRICING_TIERS:
                    tier = PricingTier(**tier_data)
                    db.add(tier)
                    results["pricing_tiers"] += 1
            
            # Seed GPU resources
            existing_gpus = await db.execute(select(GPUResource))
            if not existing_gpus.scalars().first():
                for gpu_data in DEFAULT_GPU_RESOURCES:
                    gpu = GPUResource(**gpu_data)
                    db.add(gpu)
                    results["gpu_resources"] += 1
        
        logger.info(f"Seeded pricing data: {results}")
        return results
    
    # =========================================
    # Electricity Cost Calculation
    # =========================================
    
    async def get_electricity_tiers(self) -> List[ElectricityTier]:
        """Get all electricity tiers from database."""
        async with get_db_context() as db:
            result = await db.execute(
                select(ElectricityTier).order_by(ElectricityTier.tier_number)
            )
            return result.scalars().all()
    
    def calculate_electricity_cost_kwh(
        self,
        kwh: float,
        tiers: List[dict]
    ) -> float:
        """
        Calculate electricity cost using Vietnam tiered pricing.
        
        Args:
            kwh: Total kWh consumed
            tiers: List of tier dicts with min_kwh, max_kwh, rate_per_kwh
            
        Returns:
            Total cost in VND
        """
        if not tiers:
            tiers = DEFAULT_ELECTRICITY_TIERS
        
        total_cost = 0.0
        remaining_kwh = kwh
        
        for tier in sorted(tiers, key=lambda t: t.get("tier_number", t.get("min_kwh", 0))):
            min_kwh = tier.get("min_kwh", 0)
            max_kwh = tier.get("max_kwh")
            rate = tier.get("rate_per_kwh", 0)
            
            if remaining_kwh <= 0:
                break
            
            # Calculate kWh in this tier
            if max_kwh is None:
                # Last tier - all remaining
                tier_kwh = remaining_kwh
            else:
                tier_range = max_kwh - min_kwh + 1
                tier_kwh = min(remaining_kwh, tier_range)
            
            total_cost += tier_kwh * rate
            remaining_kwh -= tier_kwh
        
        return total_cost
    
    def calculate_electricity_cost_per_hour(
        self,
        watts: float,
        tiers: List[dict] = None
    ) -> float:
        """
        Calculate electricity cost per hour for given wattage.
        
        Uses tier 6 rate as an approximation for datacenter-level usage.
        
        Args:
            watts: Power consumption in watts
            tiers: Electricity tiers (uses default if None)
            
        Returns:
            Cost per hour in VND
        """
        if tiers is None:
            tiers = DEFAULT_ELECTRICITY_TIERS
        
        # kWh per hour = watts / 1000
        kwh_per_hour = watts / 1000
        
        # For servers running 24/7, we're likely in the highest tier
        # Use tier 6 rate
        tier_6_rate = tiers[-1].get("rate_per_kwh", 3460)
        
        return kwh_per_hour * tier_6_rate
    
    # =========================================
    # Hardware Cost Calculation
    # =========================================
    
    async def get_hardware_pool(self) -> Optional[HardwarePool]:
        """Get the active hardware pool from database."""
        async with get_db_context() as db:
            result = await db.execute(
                select(HardwarePool).where(HardwarePool.is_active == True)
            )
            return result.scalars().first()
    
    def calculate_hardware_cost_per_hour(
        self,
        vcpu: int,
        ram_gb: int,
        nvme_gb: int = 0,
        ssd_gb: int = 0,
        hdd_gb: int = 0,
        pool: dict = None
    ) -> float:
        """
        Calculate proportional hardware depreciation cost per hour.
        
        Args:
            vcpu: Number of virtual CPUs requested
            ram_gb: RAM in GB requested
            nvme_gb: NVMe storage in GB requested
            ssd_gb: SSD storage in GB requested
            hdd_gb: HDD storage in GB requested
            pool: Hardware pool config (uses default if None)
            
        Returns:
            Hardware cost per hour in VND
        """
        if pool is None:
            pool = DEFAULT_HARDWARE_POOL
        
        monthly_depreciation = pool.get("monthly_depreciation_vnd", 5_000_000)
        hours_per_month = 24 * 30  # 720 hours
        
        # Calculate resource utilization percentages
        vcpu_percent = vcpu / pool.get("total_threads", 120)
        ram_percent = ram_gb / pool.get("total_ram_gb", 320)
        
        # Storage utilization (weighted by type importance)
        total_nvme = pool.get("nvme_gb", 2048)
        total_ssd = pool.get("ssd_gb", 4096)
        total_hdd = pool.get("hdd_gb", 8192)
        
        nvme_percent = nvme_gb / total_nvme if total_nvme > 0 else 0
        ssd_percent = ssd_gb / total_ssd if total_ssd > 0 else 0
        hdd_percent = hdd_gb / total_hdd if total_hdd > 0 else 0
        
        # Weight resources: CPU and RAM are most important
        # Weights: CPU 35%, RAM 35%, Storage 30%
        storage_percent = (nvme_percent * 0.6 + ssd_percent * 0.3 + hdd_percent * 0.1)
        total_utilization = (vcpu_percent * 0.35 + ram_percent * 0.35 + storage_percent * 0.30)
        
        # Calculate hourly cost
        monthly_cost = monthly_depreciation * total_utilization
        hourly_cost = monthly_cost / hours_per_month
        
        return hourly_cost
    
    # =========================================
    # GPU Cost Calculation
    # =========================================
    
    async def get_gpu_resources(self) -> List[GPUResource]:
        """Get all GPU resources from database."""
        async with get_db_context() as db:
            result = await db.execute(
                select(GPUResource).order_by(GPUResource.vram_gb)
            )
            return result.scalars().all()
    
    async def get_gpu_by_id(self, gpu_id: int) -> Optional[GPUResource]:
        """Get a specific GPU resource by ID."""
        async with get_db_context() as db:
            result = await db.execute(
                select(GPUResource).where(GPUResource.id == gpu_id)
            )
            return result.scalars().first()
    
    # =========================================
    # Pricing Calculation
    # =========================================
    
    async def calculate_pricing(
        self,
        request: PricingCalculateRequest
    ) -> PricingCalculateResponse:
        """
        Calculate recommended pricing for a VM configuration.
        
        Args:
            request: Pricing calculation request with VM specs
            
        Returns:
            Complete pricing breakdown with recommendations
        """
        # Get hardware pool
        pool = await self.get_hardware_pool()
        pool_dict = {
            "total_threads": pool.total_threads if pool else DEFAULT_HARDWARE_POOL["total_threads"],
            "total_ram_gb": pool.total_ram_gb if pool else DEFAULT_HARDWARE_POOL["total_ram_gb"],
            "nvme_gb": pool.nvme_gb if pool else DEFAULT_HARDWARE_POOL["nvme_gb"],
            "ssd_gb": pool.ssd_gb if pool else DEFAULT_HARDWARE_POOL["ssd_gb"],
            "hdd_gb": pool.hdd_gb if pool else DEFAULT_HARDWARE_POOL["hdd_gb"],
            "monthly_depreciation_vnd": pool.monthly_depreciation_vnd if pool else DEFAULT_HARDWARE_POOL["monthly_depreciation_vnd"],
            "average_watts": pool.average_watts if pool else DEFAULT_HARDWARE_POOL["average_watts"],
        }
        pool_name = pool.name if pool else DEFAULT_HARDWARE_POOL["name"]
        
        # Calculate hardware cost
        hardware_cost = self.calculate_hardware_cost_per_hour(
            vcpu=request.vcpu,
            ram_gb=request.ram_gb,
            nvme_gb=request.nvme_gb,
            ssd_gb=request.ssd_gb,
            hdd_gb=request.hdd_gb,
            pool=pool_dict
        )
        
        # Calculate electricity cost (proportional to resource usage)
        # Estimate watts based on resource utilization
        base_watts = pool_dict["average_watts"]
        vcpu_ratio = request.vcpu / pool_dict["total_threads"]
        ram_ratio = request.ram_gb / pool_dict["total_ram_gb"]
        avg_ratio = (vcpu_ratio + ram_ratio) / 2
        estimated_watts = base_watts * avg_ratio
        
        electricity_cost = self.calculate_electricity_cost_per_hour(estimated_watts)
        
        # Calculate GPU cost if applicable
        gpu_cost = 0.0
        if request.gpu_id:
            gpu = await self.get_gpu_by_id(request.gpu_id)
            if gpu:
                gpu_cost = gpu.rate_per_hour
                # Add GPU electricity cost
                gpu_electricity = self.calculate_electricity_cost_per_hour(gpu.power_watts)
                electricity_cost += gpu_electricity
        
        # Total base cost
        base_cost = hardware_cost + electricity_cost + gpu_cost
        
        # Apply profit margin
        profit_margin = request.profit_margin_percent / 100
        profit = base_cost * profit_margin
        total_price_per_hour = base_cost + profit
        
        # Calculate daily and monthly prices
        hours_per_day = request.hours_per_day
        days_per_month = request.days_per_month
        total_price_per_day = total_price_per_hour * hours_per_day
        total_price_per_month = total_price_per_day * days_per_month
        
        breakdown = PricingCostBreakdown(
            hardware_cost_per_hour=round(hardware_cost, 2),
            electricity_cost_per_hour=round(electricity_cost, 2),
            gpu_cost_per_hour=round(gpu_cost, 2),
            base_cost_per_hour=round(base_cost, 2),
            profit_per_hour=round(profit, 2),
            total_price_per_hour=round(total_price_per_hour, 2),
            total_price_per_day=round(total_price_per_day, 2),
            total_price_per_month=round(total_price_per_month, 2),
            profit_margin_applied=request.profit_margin_percent
        )
        
        return PricingCalculateResponse(
            request=request,
            breakdown=breakdown,
            hardware_pool=pool_name,
            electricity_tier_info="Vietnam tiered pricing (Tier 6: 3,460 VND/kWh)"
        )
    
    async def get_tier_recommendations(
        self,
        profit_margin_percent: float = 30
    ) -> PricingRecommendationsResponse:
        """
        Get pricing recommendations for all defined tiers.
        
        Args:
            profit_margin_percent: Desired profit margin
            
        Returns:
            Recommendations for each tier with cost analysis
        """
        recommendations = []
        
        # Get current pricing tiers
        async with get_db_context() as db:
            result = await db.execute(
                select(PricingTier)
                .where(PricingTier.is_active == True)
                .order_by(PricingTier.display_order)
            )
            tiers = result.scalars().all()
        
        pool = await self.get_hardware_pool()
        pool_name = pool.name if pool else DEFAULT_HARDWARE_POOL["name"]
        
        for tier in tiers:
            # Use average of min/max for calculation
            avg_vcpu = (tier.vcpu_min + tier.vcpu_max) // 2
            avg_ram = (tier.ram_min_gb + tier.ram_max_gb) // 2
            
            # Calculate recommended pricing
            request = PricingCalculateRequest(
                vcpu=avg_vcpu,
                ram_gb=avg_ram,
                nvme_gb=tier.nvme_gb,
                ssd_gb=tier.ssd_gb or 0,
                hdd_gb=tier.hdd_gb or 0,
                profit_margin_percent=profit_margin_percent
            )
            
            calc_response = await self.calculate_pricing(request)
            
            recommendation = PricingRecommendation(
                tier_name=tier.name,
                vcpu_range=f"{tier.vcpu_min}-{tier.vcpu_max}",
                ram_range=f"{tier.ram_min_gb}-{tier.ram_max_gb}GB",
                storage_included=f"{tier.nvme_gb}GB NVMe",
                recommended_hourly_rate=calc_response.breakdown.total_price_per_hour,
                recommended_monthly_rate=calc_response.breakdown.total_price_per_month,
                current_hourly_rate=tier.rate_per_hour,
                current_monthly_rate=tier.rate_per_month,
                cost_analysis=calc_response.breakdown
            )
            recommendations.append(recommendation)
        
        return PricingRecommendationsResponse(
            recommendations=recommendations,
            hardware_pool=pool_name,
            profit_margin_used=profit_margin_percent,
            generated_at=datetime.utcnow()
        )
    
    # =========================================
    # CRUD Operations
    # =========================================
    
    async def get_pricing_tiers(self, active_only: bool = True) -> List[PricingTier]:
        """Get all pricing tiers."""
        async with get_db_context() as db:
            query = select(PricingTier).order_by(PricingTier.display_order)
            if active_only:
                query = query.where(PricingTier.is_active == True)
            result = await db.execute(query)
            return result.scalars().all()
    
    async def get_pricing_tier(self, tier_id: int) -> Optional[PricingTier]:
        """Get a specific pricing tier."""
        async with get_db_context() as db:
            result = await db.execute(
                select(PricingTier).where(PricingTier.id == tier_id)
            )
            return result.scalars().first()
    
    async def create_pricing_tier(self, data: PricingTierCreate) -> PricingTier:
        """Create a new pricing tier."""
        async with get_db_context() as db:
            tier = PricingTier(**data.model_dump())
            db.add(tier)
            await db.flush()
            await db.refresh(tier)
            return tier
    
    async def update_pricing_tier(
        self,
        tier_id: int,
        data: PricingTierUpdate
    ) -> Optional[PricingTier]:
        """Update a pricing tier."""
        async with get_db_context() as db:
            result = await db.execute(
                select(PricingTier).where(PricingTier.id == tier_id)
            )
            tier = result.scalars().first()
            if not tier:
                return None
            
            update_data = data.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                setattr(tier, key, value)
            
            await db.flush()
            await db.refresh(tier)
            return tier
    
    async def delete_pricing_tier(self, tier_id: int) -> bool:
        """Delete a pricing tier."""
        async with get_db_context() as db:
            result = await db.execute(
                select(PricingTier).where(PricingTier.id == tier_id)
            )
            tier = result.scalars().first()
            if not tier:
                return False
            await db.delete(tier)
            return True
    
    async def create_gpu_resource(self, data: GPUResourceCreate) -> GPUResource:
        """Create a new GPU resource."""
        async with get_db_context() as db:
            gpu = GPUResource(**data.model_dump())
            gpu.available_count = gpu.total_count
            db.add(gpu)
            await db.flush()
            await db.refresh(gpu)
            return gpu
    
    async def update_gpu_resource(
        self,
        gpu_id: int,
        data: GPUResourceUpdate
    ) -> Optional[GPUResource]:
        """Update a GPU resource."""
        async with get_db_context() as db:
            result = await db.execute(
                select(GPUResource).where(GPUResource.id == gpu_id)
            )
            gpu = result.scalars().first()
            if not gpu:
                return None
            
            update_data = data.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                setattr(gpu, key, value)
            
            await db.flush()
            await db.refresh(gpu)
            return gpu
    
    async def delete_gpu_resource(self, gpu_id: int) -> bool:
        """Delete a GPU resource."""
        async with get_db_context() as db:
            result = await db.execute(
                select(GPUResource).where(GPUResource.id == gpu_id)
            )
            gpu = result.scalars().first()
            if not gpu:
                return False
            await db.delete(gpu)
            return True
    
    async def update_hardware_pool(
        self,
        pool_id: int,
        data: HardwarePoolCreate
    ) -> Optional[HardwarePool]:
        """Update hardware pool configuration."""
        async with get_db_context() as db:
            result = await db.execute(
                select(HardwarePool).where(HardwarePool.id == pool_id)
            )
            pool = result.scalars().first()
            if not pool:
                return None
            
            update_data = data.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                setattr(pool, key, value)
            
            await db.flush()
            await db.refresh(pool)
            return pool
