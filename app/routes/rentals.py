"""
Rental Endpoints

API endpoints for managing rentals and generating usage reports.
"""

from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import get_db
from ..models.schemas import (
    RentalCreate, RentalUpdate, RentalResponse,
    UsageReport, MonthlyUsage
)
from ..services.rental_manager import RentalManager

router = APIRouter(prefix="/api/rentals", tags=["Rentals"])

# Service instance
rental_manager = RentalManager()


@router.get("", response_model=List[RentalResponse])
async def list_rentals(
    vm_id: Optional[str] = Query(None, description="Filter by VM ID"),
    active_only: bool = Query(False, description="Only show active rentals")
):
    """
    List all rentals with optional filtering.
    """
    rentals = await rental_manager.get_rentals(vm_id=vm_id, active_only=active_only)
    return [RentalResponse.model_validate(r) for r in rentals]


@router.post("", response_model=RentalResponse)
async def create_rental(rental_data: RentalCreate):
    """
    Create a new rental period.
    
    Set the rental start date to begin tracking billable usage from that point.
    This is typically the first day of the month when the customer starts renting.
    """
    rental = await rental_manager.create_rental(rental_data)
    return RentalResponse.model_validate(rental)


@router.get("/{rental_id}", response_model=RentalResponse)
async def get_rental(rental_id: int):
    """
    Get a specific rental by ID.
    """
    rental = await rental_manager.get_rental(rental_id)
    
    if not rental:
        raise HTTPException(status_code=404, detail="Rental not found")
    
    return RentalResponse.model_validate(rental)


@router.put("/{rental_id}", response_model=RentalResponse)
async def update_rental(rental_id: int, update_data: RentalUpdate):
    """
    Update a rental period.
    
    Use this to:
    - Change the rental start month
    - Update customer information
    - Modify billing settings
    - End the rental (set rental_end or is_active=false)
    """
    rental = await rental_manager.update_rental(rental_id, update_data)
    
    if not rental:
        raise HTTPException(status_code=404, detail="Rental not found")
    
    return RentalResponse.model_validate(rental)


@router.delete("/{rental_id}")
async def delete_rental(rental_id: int):
    """
    Delete a rental period.
    """
    deleted = await rental_manager.delete_rental(rental_id)
    
    if not deleted:
        raise HTTPException(status_code=404, detail="Rental not found")
    
    return {"message": "Rental deleted successfully"}


@router.post("/{rental_id}/set-start-month")
async def set_rental_start_month(
    rental_id: int,
    year: int = Query(..., description="Year (e.g., 2024)"),
    month: int = Query(..., ge=1, le=12, description="Month (1-12)")
):
    """
    Set the rental start to the first day of a specific month.
    
    This is useful for cloud VPS billing where you want to track usage
    starting from a specific month.
    """
    rental = await rental_manager.set_rental_start_month(rental_id, year, month)
    
    if not rental:
        raise HTTPException(status_code=404, detail="Rental not found")
    
    return {
        "message": f"Rental start set to {year}-{month:02d}-01",
        "rental": RentalResponse.model_validate(rental)
    }


@router.get("/{rental_id}/report", response_model=UsageReport)
async def get_usage_report(
    rental_id: int,
    start_date: Optional[datetime] = Query(None, description="Report start (default: rental start)"),
    end_date: Optional[datetime] = Query(None, description="Report end (default: now)")
):
    """
    Generate a usage report for a rental period.
    
    Returns:
    - Total running time
    - Session count
    - Individual session details
    - Cost calculation (if rate is set)
    """
    report = await rental_manager.generate_usage_report(
        rental_id,
        report_start=start_date,
        report_end=end_date
    )
    
    if not report:
        raise HTTPException(status_code=404, detail="Rental not found")
    
    return report


@router.get("/{rental_id}/monthly/{year}/{month}", response_model=MonthlyUsage)
async def get_monthly_report(
    rental_id: int,
    year: int,
    month: int = Path(..., ge=1, le=12)
):
    """
    Generate a monthly usage report with daily breakdown.
    
    Shows usage for a specific month with daily statistics.
    """
    report = await rental_manager.generate_monthly_report(rental_id, year, month)
    
    if not report:
        raise HTTPException(status_code=404, detail="Rental not found")
    
    return report


@router.get("/vm/{vm_id}/active", response_model=Optional[RentalResponse])
async def get_active_rental_for_vm(vm_id: str):
    """
    Get the currently active rental for a specific VM.
    """
    rental = await rental_manager.get_active_rental_for_vm(vm_id)
    
    if not rental:
        return None
    
    return RentalResponse.model_validate(rental)
