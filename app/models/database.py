"""
SQLAlchemy Database Models

Defines the database schema for VM sessions, rentals, and usage summaries.
"""

from datetime import datetime
from typing import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, ForeignKey, Index
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship

from ..config import settings


class Base(DeclarativeBase):
    """SQLAlchemy declarative base"""
    pass


class VMSession(Base):
    """
    Records individual VM running sessions (start/stop pairs).
    
    Each session represents one continuous period where a VM was running.
    """
    __tablename__ = "vm_sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    vm_id = Column(String(50), nullable=False, index=True)
    node = Column(String(100), nullable=False)
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=True)  # NULL if VM is still running
    duration_seconds = Column(Integer, nullable=True)  # Calculated on session end
    user = Column(String(100), nullable=True)  # User who started the VM
    
    # Proxmox-specific identifiers
    start_upid = Column(String(255), nullable=True, unique=True)  # UPID of start event
    stop_upid = Column(String(255), nullable=True)  # UPID of stop event
    
    # Status tracking
    is_running = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Composite index for efficient queries
    __table_args__ = (
        Index('idx_vm_session_lookup', 'vm_id', 'start_time'),
        Index('idx_vm_running', 'vm_id', 'is_running'),
    )
    
    def calculate_duration(self) -> int:
        """Calculate duration in seconds"""
        if self.end_time and self.start_time:
            delta = self.end_time - self.start_time
            return int(delta.total_seconds())
        elif self.start_time:
            # VM still running - calculate from start to now
            delta = datetime.utcnow() - self.start_time
            return int(delta.total_seconds())
        return 0
    
    def __repr__(self):
        status = "running" if self.is_running else "stopped"
        return f"<VMSession(vm_id={self.vm_id}, status={status}, start={self.start_time})>"


class Rental(Base):
    """
    Rental period configuration for VMs.
    
    Tracks when a VM rental started, allowing usage calculation
    within the rental period.
    """
    __tablename__ = "rentals"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    vm_id = Column(String(50), nullable=False, index=True)
    customer_name = Column(String(255), nullable=True)
    customer_email = Column(String(255), nullable=True)
    
    # Rental period
    rental_start = Column(DateTime, nullable=False)
    rental_end = Column(DateTime, nullable=True)  # NULL for ongoing rentals
    
    # Billing configuration
    billing_cycle = Column(String(20), default="monthly")  # monthly, weekly, daily, hourly
    rate_per_hour = Column(Float, nullable=True)  # Optional: for cost calculation
    
    # Status
    is_active = Column(Boolean, default=True)
    
    # Notes
    notes = Column(String(1000), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_rental_active', 'vm_id', 'is_active'),
    )
    
    def __repr__(self):
        return f"<Rental(vm_id={self.vm_id}, customer={self.customer_name}, start={self.rental_start})>"


class UsageSummary(Base):
    """
    Aggregated usage statistics for reporting.
    
    Pre-calculated summaries for efficient reporting.
    """
    __tablename__ = "usage_summaries"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    vm_id = Column(String(50), nullable=False, index=True)
    
    # Period definition
    period_type = Column(String(20), nullable=False)  # daily, weekly, monthly
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    
    # Aggregated stats
    total_seconds = Column(Integer, default=0)
    session_count = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_usage_period', 'vm_id', 'period_type', 'period_start'),
    )
    
    @property
    def total_hours(self) -> float:
        """Get total hours as decimal"""
        return self.total_seconds / 3600.0
    
    @property
    def formatted_duration(self) -> str:
        """Get human-readable duration string"""
        hours = self.total_seconds // 3600
        minutes = (self.total_seconds % 3600) // 60
        return f"{hours}h {minutes}m"
    
    def __repr__(self):
        return f"<UsageSummary(vm_id={self.vm_id}, period={self.period_type}, total={self.formatted_duration})>"


# Database engine and session factory
engine = create_async_engine(
    settings.database.url,
    echo=settings.server.debug,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def init_db():
    """Initialize the database - create all tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database session"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for database session"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
