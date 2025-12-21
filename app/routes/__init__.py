"""API Routes package"""

from .vms import router as vms_router
from .sessions import router as sessions_router
from .rentals import router as rentals_router

__all__ = ["vms_router", "sessions_router", "rentals_router"]
