"""
Proxmox VM Time Tracking Service - Manager Server

FastAPI application that tracks VM running time from Proxmox clients.
Receives events from distributed client nodes and stores in MySQL.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .models.database import init_db, ProxmoxNode, get_db_context
from .routes import vms_router, sessions_router, rentals_router, ingest_router, nodes_router, pricing_router

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.logging.level),
    format=settings.logging.format
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup
    logger.info("Starting Proxmox VM Time Tracking Manager...")
    await init_db()
    logger.info("Database initialized (MySQL)")
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")


# Create FastAPI application
app = FastAPI(
    title="Proxmox VM Time Tracking - Manager",
    description="""
    Central manager for tracking VM running time from distributed Proxmox nodes.
    
    Features:
    - Receive events from Proxmox client nodes
    - Track all VMs across multiple Proxmox clusters
    - Calculate total running time per VM
    - Manage rental periods with configurable start months
    - Generate usage reports for billing
    """,
    version="2.0.0",
    lifespan=lifespan
)

# CORS middleware for web dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(ingest_router)  # Client data ingestion
app.include_router(nodes_router)   # Node management
app.include_router(vms_router)
app.include_router(sessions_router)
app.include_router(rentals_router)
app.include_router(pricing_router)  # Pricing calculator


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint with node count"""
    try:
        async with get_db_context() as db:
            from sqlalchemy import select, func
            result = await db.execute(
                select(func.count(ProxmoxNode.id)).where(ProxmoxNode.is_active == True)
            )
            active_nodes = result.scalar() or 0
    except Exception:
        active_nodes = 0
    
    return {
        "status": "healthy",
        "version": "2.0.0",
        "database": "mysql",
        "active_nodes": active_nodes,
        "timestamp": datetime.utcnow().isoformat()
    }


# Serve the web dashboard
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """
    Serve the web dashboard.
    
    The dashboard provides:
    - Real-time overview of all VMs
    - Session logs with filtering
    - Usage statistics and charts
    - Rental management interface
    """
    return get_dashboard_html()


def get_dashboard_html() -> str:
    """Generate the dashboard HTML"""
    return '''<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Proxmox VM Time Tracking</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        /* Dark theme (default) */
        :root, [data-theme="dark"] {
            --bs-body-bg: #0d1117;
            --bs-body-color: #c9d1d9;
            --card-bg: #161b22;
            --border-color: #30363d;
            --accent-color: #58a6ff;
            --success-color: #3fb950;
            --warning-color: #d29922;
            --navbar-bg: linear-gradient(135deg, #1a1f2e 0%, #0d1117 100%);
            --stat-card-bg: linear-gradient(135deg, #1a1f2e 0%, #161b22 100%);
            --input-bg: #0d1117;
            --muted-color: #8b949e;
            --table-hover-bg: rgba(255,255,255,0.05);
        }
        
        /* Light theme */
        [data-theme="light"] {
            --bs-body-bg: #f6f8fa;
            --bs-body-color: #24292f;
            --card-bg: #ffffff;
            --border-color: #d0d7de;
            --accent-color: #0969da;
            --success-color: #1a7f37;
            --warning-color: #9a6700;
            --navbar-bg: linear-gradient(135deg, #ffffff 0%, #f6f8fa 100%);
            --stat-card-bg: linear-gradient(135deg, #ffffff 0%, #f6f8fa 100%);
            --input-bg: #ffffff;
            --muted-color: #57606a;
            --table-hover-bg: rgba(0,0,0,0.03);
        }
        
        /* Smooth theme transition */
        *, *::before, *::after {
            transition: background-color 0.3s ease, color 0.3s ease, border-color 0.3s ease;
        }
        
        body {
            background: var(--bs-body-bg);
            color: var(--bs-body-color);
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
        }
        
        .navbar {
            background: var(--navbar-bg);
            border-bottom: 1px solid var(--border-color);
        }
        
        [data-theme="light"] .navbar {
            box-shadow: 0 1px 2px rgba(0,0,0,0.05);
        }
        
        .card {
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
        }
        
        .card-header {
            background: transparent;
            border-bottom: 1px solid var(--border-color);
            font-weight: 600;
        }
        
        .stat-card {
            background: var(--stat-card-bg);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.5rem;
            transition: transform 0.2s, box-shadow 0.2s, background-color 0.3s;
        }
        
        .stat-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 30px rgba(0,0,0,0.15);
        }
        
        .stat-value {
            font-size: 2.5rem;
            font-weight: 700;
            background: linear-gradient(135deg, var(--accent-color), #a371f7);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        
        .stat-label {
            color: var(--muted-color);
            font-size: 0.875rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .table {
            color: var(--bs-body-color);
        }
        
        .table thead th {
            border-color: var(--border-color);
            color: var(--muted-color);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.75rem;
            letter-spacing: 0.5px;
        }
        
        .table tbody td {
            border-color: var(--border-color);
            vertical-align: middle;
        }
        
        .table-hover tbody tr:hover {
            background-color: var(--table-hover-bg);
        }
        
        .badge-running {
            background: rgba(63, 185, 80, 0.2);
            color: var(--success-color);
            border: 1px solid var(--success-color);
        }
        
        .badge-stopped {
            background: rgba(139, 148, 158, 0.2);
            color: var(--muted-color);
            border: 1px solid var(--muted-color);
        }
        
        .btn-primary {
            background: var(--accent-color);
            border: none;
            border-radius: 8px;
            padding: 0.5rem 1.5rem;
        }
        
        .btn-primary:hover {
            background: var(--accent-color);
            filter: brightness(1.2);
        }
        
        .btn-outline-secondary {
            color: var(--muted-color);
            border-color: var(--border-color);
        }
        
        .btn-outline-secondary:hover {
            background: var(--border-color);
            color: var(--bs-body-color);
        }
        
        .form-control, .form-select {
            background: var(--input-bg);
            border: 1px solid var(--border-color);
            color: var(--bs-body-color);
            border-radius: 8px;
        }
        
        .form-control:focus, .form-select:focus {
            background: var(--input-bg);
            border-color: var(--accent-color);
            color: var(--bs-body-color);
            box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.2);
        }
        
        .modal-content {
            background: var(--card-bg);
            border: 1px solid var(--border-color);
        }
        
        .modal-header, .modal-footer {
            border-color: var(--border-color);
        }
        
        .nav-tabs {
            border-bottom: 1px solid var(--border-color);
        }
        
        .nav-tabs .nav-link {
            color: var(--muted-color);
            border: none;
            border-bottom: 2px solid transparent;
            border-radius: 0;
        }
        
        .nav-tabs .nav-link:hover {
            color: var(--bs-body-color);
            border-color: transparent;
        }
        
        .nav-tabs .nav-link.active {
            color: var(--accent-color);
            background: transparent;
            border-bottom-color: var(--accent-color);
        }
        
        .duration-display {
            font-family: 'SF Mono', 'Consolas', monospace;
            font-size: 1.1rem;
        }
        
        .log-entry {
            font-family: 'SF Mono', 'Consolas', monospace;
            font-size: 0.85rem;
            padding: 0.5rem;
            background: var(--input-bg);
            border-radius: 4px;
            margin-bottom: 0.25rem;
        }
        
        .log-entry.start {
            border-left: 3px solid var(--success-color);
        }
        
        .log-entry.stop {
            border-left: 3px solid var(--warning-color);
        }
        
        .empty-state {
            text-align: center;
            padding: 3rem;
            color: var(--muted-color);
        }
        
        .empty-state i {
            font-size: 4rem;
            margin-bottom: 1rem;
            opacity: 0.5;
        }
        
        .loading-spinner {
            display: flex;
            justify-content: center;
            padding: 2rem;
        }
        
        .month-selector {
            display: flex;
            gap: 0.5rem;
            align-items: center;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .running-indicator {
            animation: pulse 2s infinite;
        }
        
        /* Theme toggle button */
        .theme-toggle {
            background: transparent;
            border: 1px solid var(--border-color);
            border-radius: 50%;
            width: 40px;
            height: 40px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            color: var(--bs-body-color);
            transition: all 0.3s ease;
        }
        
        .theme-toggle:hover {
            background: var(--border-color);
            transform: rotate(15deg);
        }
        
        .theme-toggle .bi-sun { display: none; }
        .theme-toggle .bi-moon { display: block; }
        
        [data-theme="light"] .theme-toggle .bi-sun { display: block; }
        [data-theme="light"] .theme-toggle .bi-moon { display: none; }
        
        /* Close button fix for light mode */
        [data-theme="light"] .btn-close {
            filter: none;
        }
        
        [data-theme="dark"] .btn-close {
            filter: invert(1) grayscale(100%) brightness(200%);
        }
    </style>
</head>
<body>
    <!-- Navbar -->
    <nav class="navbar py-3">
        <div class="container">
            <a class="navbar-brand d-flex align-items-center gap-2" href="#">
                <i class="bi bi-hdd-rack fs-4"></i>
                <span class="fw-bold">Proxmox VM Tracker</span>
            </a>
            <div class="d-flex align-items-center gap-3">
                <button class="btn btn-primary btn-sm" onclick="forceSync()" id="forceSyncBtn">
                    <i class="bi bi-arrow-clockwise"></i> Force Sync
                </button>
                <span class="text-muted small" id="lastUpdated">Last updated: --</span>
                <button class="theme-toggle" onclick="toggleTheme()" title="Toggle dark/light mode">
                    <i class="bi bi-moon fs-5"></i>
                    <i class="bi bi-sun fs-5"></i>
                </button>
            </div>
        </div>
    </nav>

    <div class="container py-4">
        <!-- Stats Row -->
        <div class="row g-4 mb-4" id="statsRow">
            <div class="col-md-3">
                <div class="stat-card">
                    <div class="stat-value" id="statTotalVMs">--</div>
                    <div class="stat-label">Total VMs Tracked</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="stat-card">
                    <div class="stat-value" id="statRunning">--</div>
                    <div class="stat-label">Currently Running</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="stat-card">
                    <div class="stat-value" id="statTotalTime">--</div>
                    <div class="stat-label">Total Runtime (All VMs)</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="stat-card">
                    <div class="stat-value" id="statMonthTime">--</div>
                    <div class="stat-label">This Month</div>
                </div>
            </div>
        </div>

        <!-- Tabs -->
        <ul class="nav nav-tabs mb-4" role="tablist">
            <li class="nav-item">
                <button class="nav-link active" data-bs-toggle="tab" data-bs-target="#vmsTab">
                    <i class="bi bi-pc-display me-1"></i> VMs
                </button>
            </li>
            <li class="nav-item">
                <button class="nav-link" data-bs-toggle="tab" data-bs-target="#sessionsTab">
                    <i class="bi bi-clock-history me-1"></i> Session Logs
                </button>
            </li>
            <li class="nav-item">
                <button class="nav-link" data-bs-toggle="tab" data-bs-target="#rentalsTab">
                    <i class="bi bi-calendar-check me-1"></i> Rentals
                </button>
            </li>
            <li class="nav-item">
                <button class="nav-link" data-bs-toggle="tab" data-bs-target="#customersTab">
                    <i class="bi bi-people me-1"></i> Customers
                </button>
            </li>
            <li class="nav-item">
                <button class="nav-link" data-bs-toggle="tab" data-bs-target="#pricingTab">
                    <i class="bi bi-calculator me-1"></i> Pricing
                </button>
            </li>
        </ul>

        <div class="tab-content">
            <!-- VMs Tab -->
            <div class="tab-pane fade show active" id="vmsTab">
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <span><i class="bi bi-pc-display me-2"></i>Virtual Machines</span>
                    </div>
                    <div class="card-body p-0">
                        <div class="table-responsive">
                            <table class="table table-hover mb-0">
                                <thead>
                                    <tr>
                                        <th>VM ID</th>
                                        <th>Node</th>
                                        <th>Status</th>
                                        <th>Total Runtime</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody id="vmsTableBody">
                                    <tr>
                                        <td colspan="5" class="text-center py-4 text-muted">Loading...</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Sessions Tab -->
            <div class="tab-pane fade" id="sessionsTab">
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <span><i class="bi bi-clock-history me-2"></i>Session Logs</span>
                        <div class="d-flex gap-2">
                            <select class="form-select form-select-sm" id="sessionVmFilter" style="width: auto;">
                                <option value="">All VMs</option>
                            </select>
                            <input type="date" class="form-control form-control-sm" id="sessionDateFilter" style="width: auto;">
                        </div>
                    </div>
                    <div class="card-body p-0">
                        <div class="table-responsive">
                            <table class="table table-hover mb-0">
                                <thead>
                                    <tr>
                                        <th>VM ID</th>
                                        <th>Start Time</th>
                                        <th>End Time</th>
                                        <th>Duration</th>
                                        <th>User</th>
                                        <th>Status</th>
                                    </tr>
                                </thead>
                                <tbody id="sessionsTableBody">
                                    <tr>
                                        <td colspan="6" class="text-center py-4 text-muted">Loading...</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Rentals Tab -->
            <div class="tab-pane fade" id="rentalsTab">
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <span><i class="bi bi-calendar-check me-2"></i>Rental Periods</span>
                        <button class="btn btn-primary btn-sm" data-bs-toggle="modal" data-bs-target="#rentalModal">
                            <i class="bi bi-plus"></i> New Rental
                        </button>
                    </div>
                    <div class="card-body p-0">
                        <div class="table-responsive">
                            <table class="table table-hover mb-0">
                                <thead>
                                    <tr>
                                        <th>VM ID</th>
                                        <th>Customer</th>
                                        <th>Start Date</th>
                                        <th>End Date</th>
                                        <th>Usage This Month</th>
                                        <th>Total Usage</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody id="rentalsTableBody">
                                    <tr>
                                        <td colspan="7" class="text-center py-4 text-muted">Loading...</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Customers Tab -->
            <div class="tab-pane fade" id="customersTab">
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <span><i class="bi bi-people me-2"></i>Customer Billing Summary</span>
                        <button class="btn btn-sm btn-outline-secondary" onclick="loadCustomers()">
                            <i class="bi bi-arrow-repeat"></i> Refresh
                        </button>
                    </div>
                    <div class="card-body">
                        <!-- Summary Cards -->
                        <div class="row g-3 mb-4" id="customerSummaryCards">
                            <div class="col-md-3">
                                <div class="stat-card">
                                    <div class="stat-value" id="totalCustomers">--</div>
                                    <div class="stat-label">Total Customers</div>
                                </div>
                            </div>
                            <div class="col-md-3">
                                <div class="stat-card">
                                    <div class="stat-value" id="totalRentedVMs">--</div>
                                    <div class="stat-label">Rented VMs</div>
                                </div>
                            </div>
                            <div class="col-md-3">
                                <div class="stat-card">
                                    <div class="stat-value" id="totalBilledRuntime">--</div>
                                    <div class="stat-label">Total Billed Runtime</div>
                                </div>
                            </div>
                            <div class="col-md-3">
                                <div class="stat-card" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%);">
                                    <div class="stat-value" id="totalRevenue">$--</div>
                                    <div class="stat-label">Total Revenue</div>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Customer Table -->
                        <div class="table-responsive">
                            <table class="table table-hover mb-0">
                                <thead>
                                    <tr>
                                        <th>Customer</th>
                                        <th>Email</th>
                                        <th>VMs</th>
                                        <th>Total Runtime</th>
                                        <th>Total Cost</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody id="customersTableBody">
                                    <tr>
                                        <td colspan="6" class="text-center py-4 text-muted">Loading...</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Pricing Tab -->
            <div class="tab-pane fade" id="pricingTab">
                <div class="row g-4">
                    <!-- Pricing Tiers Card -->
                    <div class="col-lg-6">
                        <div class="card">
                            <div class="card-header d-flex justify-content-between align-items-center">
                                <span><i class="bi bi-layers me-2"></i>Pricing Tiers</span>
                                <div class="btn-group">
                                    <button class="btn btn-sm btn-outline-secondary" onclick="loadPricingTiers()">
                                        <i class="bi bi-arrow-repeat"></i>
                                    </button>
                                    <button class="btn btn-sm btn-primary" data-bs-toggle="modal" data-bs-target="#tierModal">
                                        <i class="bi bi-plus"></i> Add Tier
                                    </button>
                                </div>
                            </div>
                            <div class="card-body p-0">
                                <div class="table-responsive">
                                    <table class="table table-hover mb-0">
                                        <thead>
                                            <tr>
                                                <th>Tier</th>
                                                <th>vCPU</th>
                                                <th>RAM</th>
                                                <th>Storage</th>
                                                <th>Rate/Hour</th>
                                                <th>Rate/Month</th>
                                                <th>Actions</th>
                                            </tr>
                                        </thead>
                                        <tbody id="pricingTiersTableBody">
                                            <tr>
                                                <td colspan="7" class="text-center py-4 text-muted">Loading...</td>
                                            </tr>
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- GPU Resources Card -->
                    <div class="col-lg-6">
                        <div class="card">
                            <div class="card-header d-flex justify-content-between align-items-center">
                                <span><i class="bi bi-gpu-card me-2"></i>GPU Resources</span>
                                <div class="btn-group">
                                    <button class="btn btn-sm btn-outline-secondary" onclick="loadGPUResources()">
                                        <i class="bi bi-arrow-repeat"></i>
                                    </button>
                                    <button class="btn btn-sm btn-primary" data-bs-toggle="modal" data-bs-target="#gpuModal">
                                        <i class="bi bi-plus"></i> Add GPU
                                    </button>
                                </div>
                            </div>
                            <div class="card-body p-0">
                                <div class="table-responsive">
                                    <table class="table table-hover mb-0">
                                        <thead>
                                            <tr>
                                                <th>GPU</th>
                                                <th>VRAM</th>
                                                <th>Rate/Hour</th>
                                                <th>Workloads</th>
                                                <th>Actions</th>
                                            </tr>
                                        </thead>
                                        <tbody id="gpuResourcesTableBody">
                                            <tr>
                                                <td colspan="5" class="text-center py-4 text-muted">Loading...</td>
                                            </tr>
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Pricing Calculator Card -->
                    <div class="col-12">
                        <div class="card">
                            <div class="card-header">
                                <i class="bi bi-calculator me-2"></i>Pricing Calculator
                            </div>
                            <div class="card-body">
                                <div class="row g-4">
                                    <div class="col-md-4">
                                        <h6 class="text-muted mb-3">VM Configuration</h6>
                                        <div class="mb-3">
                                            <label class="form-label">vCPU</label>
                                            <input type="number" class="form-control" id="calcVcpu" value="4" min="1" max="64">
                                        </div>
                                        <div class="mb-3">
                                            <label class="form-label">RAM (GB)</label>
                                            <input type="number" class="form-control" id="calcRam" value="16" min="1" max="512">
                                        </div>
                                        <div class="mb-3">
                                            <label class="form-label">NVMe Storage (GB)</label>
                                            <input type="number" class="form-control" id="calcNvme" value="100" min="0" max="2048">
                                        </div>
                                        <div class="mb-3">
                                            <label class="form-label">GPU (Optional)</label>
                                            <select class="form-select" id="calcGpu">
                                                <option value="">No GPU</option>
                                            </select>
                                        </div>
                                        <div class="mb-3">
                                            <label class="form-label">Profit Margin: <span id="marginValue">30</span>%</label>
                                            <input type="range" class="form-range" id="calcMargin" min="0" max="100" value="30" oninput="document.getElementById('marginValue').textContent = this.value">
                                        </div>
                                        <button class="btn btn-primary w-100" onclick="calculatePricing()">
                                            <i class="bi bi-calculator me-2"></i>Calculate
                                        </button>
                                    </div>
                                    <div class="col-md-8">
                                        <h6 class="text-muted mb-3">Cost Breakdown</h6>
                                        <div id="pricingResult" class="p-3 rounded" style="background: var(--stat-card-bg); min-height: 300px;">
                                            <div class="text-center py-5 text-muted">
                                                <i class="bi bi-calculator fs-1 mb-3 d-block"></i>
                                                Configure VM specs and click Calculate
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Seed Data Button -->
                    <div class="col-12">
                        <button class="btn btn-outline-secondary" onclick="seedPricingData()">
                            <i class="bi bi-database-add me-2"></i>Seed Default Pricing Data
                        </button>
                        <small class="text-muted ms-2">Click to populate default tiers, GPUs, and electricity rates</small>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Rental Modal -->
    <div class="modal fade" id="rentalModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Create/Edit Rental</h5>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <form id="rentalForm">
                        <input type="hidden" id="rentalId">
                        <div class="mb-3">
                            <label class="form-label">VM ID</label>
                            <input type="text" class="form-control" id="rentalVmId" required>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Customer Name</label>
                            <input type="text" class="form-control" id="rentalCustomer">
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Customer Email</label>
                            <input type="email" class="form-control" id="rentalEmail">
                        </div>
                        <div class="row mb-3">
                            <div class="col">
                                <label class="form-label">Start Month</label>
                                <div class="month-selector">
                                    <select class="form-select" id="rentalStartYear">
                                        <!-- Populated by JS -->
                                    </select>
                                    <select class="form-select" id="rentalStartMonth">
                                        <option value="1">January</option>
                                        <option value="2">February</option>
                                        <option value="3">March</option>
                                        <option value="4">April</option>
                                        <option value="5">May</option>
                                        <option value="6">June</option>
                                        <option value="7">July</option>
                                        <option value="8">August</option>
                                        <option value="9">September</option>
                                        <option value="10">October</option>
                                        <option value="11">November</option>
                                        <option value="12">December</option>
                                    </select>
                                </div>
                            </div>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Billing Cycle</label>
                            <select class="form-select" id="rentalBillingCycle" onchange="updateRateFields()">
                                <option value="hourly">Hourly</option>
                                <option value="weekly">Weekly</option>
                                <option value="monthly" selected>Monthly</option>
                            </select>
                        </div>
                        <div class="mb-3" id="rateHourlyDiv" style="display:none;">
                            <label class="form-label">Rate per Hour (VND)</label>
                            <input type="number" step="1000" class="form-control" id="rentalRateHourly" placeholder="e.g. 10000">
                            <small class="text-muted">Suggested: 10,000 VND/hr</small>
                        </div>
                        <div class="mb-3" id="rateWeeklyDiv" style="display:none;">
                            <label class="form-label">Rate per Week (VND)</label>
                            <input type="number" step="10000" class="form-control" id="rentalRateWeekly" placeholder="e.g. 250000">
                            <small class="text-muted">Suggested: 250,000 VND/week (~30% off hourly)</small>
                        </div>
                        <div class="mb-3" id="rateMonthlyDiv">
                            <label class="form-label">Rate per Month (VND)</label>
                            <input type="number" step="50000" class="form-control" id="rentalRateMonthly" placeholder="e.g. 700000">
                            <small class="text-muted">Suggested: 700,000 VND/month (~50% off hourly)</small>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Notes</label>
                            <textarea class="form-control" id="rentalNotes" rows="2"></textarea>
                        </div>
                    </form>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Cancel</button>
                    <button type="button" class="btn btn-primary" onclick="saveRental()">Save Rental</button>
                </div>
            </div>
        </div>
    </div>

    <!-- Usage Report Modal -->
    <div class="modal fade" id="usageModal" tabindex="-1">
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Usage Report</h5>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body" id="usageModalBody">
                    <!-- Populated by JS -->
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // API Base URL
        const API_BASE = '';
        
        // State
        let vmsData = [];
        let sessionsData = [];
        let rentalsData = [];
        
        // Theme toggle function
        function toggleTheme() {
            const html = document.documentElement;
            const currentTheme = html.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            
            html.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
        }
        
        // Load saved theme on page load
        function initTheme() {
            const savedTheme = localStorage.getItem('theme');
            if (savedTheme) {
                document.documentElement.setAttribute('data-theme', savedTheme);
            } else {
                // Check system preference
                const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
                document.documentElement.setAttribute('data-theme', prefersDark ? 'dark' : 'light');
            }
        }
        
        // Initialize theme immediately
        initTheme();
        
        // Initialize
        document.addEventListener('DOMContentLoaded', () => {
            populateYearSelector();
            loadAllData();
            
            // Set up filters
            document.getElementById('sessionVmFilter').addEventListener('change', loadSessions);
            document.getElementById('sessionDateFilter').addEventListener('change', loadSessions);
        });
        
        function populateYearSelector() {
            const select = document.getElementById('rentalStartYear');
            const currentYear = new Date().getFullYear();
            for (let y = currentYear - 2; y <= currentYear + 1; y++) {
                const option = document.createElement('option');
                option.value = y;
                option.textContent = y;
                if (y === currentYear) option.selected = true;
                select.appendChild(option);
            }
        }
        
        async function loadAllData() {
            await Promise.all([loadVMs(), loadSessions(), loadRentals()]);
            updateStats();
            document.getElementById('lastUpdated').textContent = 
                'Last updated: ' + new Date().toLocaleTimeString();
        }
        
        async function forceSync() {
            const btn = document.getElementById('forceSyncBtn');
            const originalHTML = btn.innerHTML;
            
            try {
                btn.disabled = true;
                btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Syncing...';
                
                const response = await fetch(`${API_BASE}/api/ingest/force-sync`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                
                const result = await response.json();
                
                if (result.success) {
                    // Show success message
                    btn.innerHTML = '<i class="bi bi-check-lg"></i> Sync Requested';
                    btn.classList.remove('btn-primary');
                    btn.classList.add('btn-success');
                    
                    // Wait a moment then reload data
                    setTimeout(async () => {
                        await loadAllData();
                        btn.innerHTML = originalHTML;
                        btn.classList.remove('btn-success');
                        btn.classList.add('btn-primary');
                        btn.disabled = false;
                    }, 2000);
                } else {
                    throw new Error(result.message || 'Sync failed');
                }
            } catch (err) {
                console.error('Force sync failed:', err);
                btn.innerHTML = '<i class="bi bi-exclamation-triangle"></i> Error';
                btn.classList.remove('btn-primary');
                btn.classList.add('btn-danger');
                
                setTimeout(() => {
                    btn.innerHTML = originalHTML;
                    btn.classList.remove('btn-danger');
                    btn.classList.add('btn-primary');
                    btn.disabled = false;
                }, 3000);
            }
        }
        
        async function loadVMs() {
            try {
                const response = await fetch(`${API_BASE}/api/vms`);
                const data = await response.json();
                vmsData = data.vms || [];
                renderVMs();
                updateVmFilter();
            } catch (err) {
                console.error('Failed to load VMs:', err);
            }
        }
        
        function renderVMs() {
            const tbody = document.getElementById('vmsTableBody');
            
            if (vmsData.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="5" class="empty-state">
                            <i class="bi bi-inbox"></i>
                            <p>No VMs tracked yet</p>
                            <button class="btn btn-primary btn-sm" onclick="syncSessions()">
                                Sync from Proxmox
                            </button>
                        </td>
                    </tr>`;
                return;
            }
            
            tbody.innerHTML = vmsData.map(vm => `
                <tr>
                    <td><strong>VM ${vm.vm_id}</strong>${vm.name ? `<br><small class="text-muted">${vm.name}</small>` : ''}</td>
                    <td>${vm.node}</td>
                    <td>
                        <span class="badge ${vm.status === 'running' ? 'badge-running' : 'badge-stopped'}">
                            ${vm.status === 'running' ? '<i class="bi bi-circle-fill me-1 running-indicator"></i>' : ''}
                            ${vm.status}
                        </span>
                    </td>
                    <td class="duration-display">${vm.formatted_runtime}</td>
                    <td>
                        <button class="btn btn-sm btn-outline-secondary me-1" onclick="viewVmUsage('${vm.vm_id}')">
                            <i class="bi bi-graph-up"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger" onclick="removeVM('${vm.vm_id}', '${vm.node}')" title="Remove from tracking">
                            <i class="bi bi-trash"></i>
                        </button>
                    </td>
                </tr>
            `).join('');
        }
        
        async function removeVM(vmId, node) {
            if (!confirm(`Delete VM ${vmId} from database?\n\nThis will permanently delete:\n• Current tracking state\n• All session history\n\nThis action cannot be undone.`)) {
                return;
            }
            
            try {
                const response = await fetch(`${API_BASE}/api/vms/${vmId}?node=${node}`, {
                    method: 'DELETE'
                });
                
                if (response.ok) {
                    await loadVMs();
                    updateStats();
                } else {
                    const error = await response.json();
                    alert('Failed to delete VM: ' + (error.detail || 'Unknown error'));
                }
            } catch (err) {
                console.error('Failed to delete VM:', err);
                alert('Failed to delete VM');
            }
        }
        
        async function loadSessions() {
            try {
                const vmFilter = document.getElementById('sessionVmFilter').value;
                const dateFilter = document.getElementById('sessionDateFilter').value;
                
                let url = `${API_BASE}/api/sessions?per_page=100`;
                if (vmFilter) url += `&vm_id=${vmFilter}`;
                if (dateFilter) url += `&start_date=${dateFilter}T00:00:00`;
                
                const response = await fetch(url);
                const data = await response.json();
                sessionsData = data.sessions || [];
                renderSessions();
            } catch (err) {
                console.error('Failed to load sessions:', err);
            }
        }
        
        function renderSessions() {
            const tbody = document.getElementById('sessionsTableBody');
            
            if (sessionsData.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="6" class="empty-state">
                            <i class="bi bi-clock"></i>
                            <p>No sessions found</p>
                        </td>
                    </tr>`;
                return;
            }
            
            tbody.innerHTML = sessionsData.map(s => `
                <tr>
                    <td><strong>VM ${s.vm_id}</strong></td>
                    <td>${formatDateTime(s.start_time)}</td>
                    <td>${s.end_time ? formatDateTime(s.end_time) : '<span class="text-success">Running...</span>'}</td>
                    <td class="duration-display">${formatDuration(s.duration_seconds)}</td>
                    <td>${s.user || '-'}</td>
                    <td>
                        <span class="badge ${s.is_running ? 'badge-running' : 'badge-stopped'}">
                            ${s.is_running ? 'Running' : 'Completed'}
                        </span>
                    </td>
                </tr>
            `).join('');
        }
        
        async function loadRentals() {
            try {
                const response = await fetch(`${API_BASE}/api/rentals`);
                rentalsData = await response.json() || [];
                await enrichRentalsWithUsage();
                renderRentals();
            } catch (err) {
                console.error('Failed to load rentals:', err);
            }
        }
        
        async function enrichRentalsWithUsage() {
            for (let rental of rentalsData) {
                try {
                    const reportRes = await fetch(`${API_BASE}/api/rentals/${rental.id}/report`);
                    const report = await reportRes.json();
                    rental.totalUsage = report.formatted_duration;
                    rental.totalSeconds = report.total_seconds;
                    
                    // Get this month's usage
                    const now = new Date();
                    const monthRes = await fetch(
                        `${API_BASE}/api/rentals/${rental.id}/monthly/${now.getFullYear()}/${now.getMonth() + 1}`
                    );
                    const monthReport = await monthRes.json();
                    rental.monthUsage = monthReport.formatted_duration;
                } catch (err) {
                    rental.totalUsage = '--';
                    rental.monthUsage = '--';
                }
            }
        }
        
        function renderRentals() {
            const tbody = document.getElementById('rentalsTableBody');
            
            if (rentalsData.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="7" class="empty-state">
                            <i class="bi bi-calendar-x"></i>
                            <p>No rentals configured</p>
                            <button class="btn btn-primary btn-sm" data-bs-toggle="modal" data-bs-target="#rentalModal">
                                Create First Rental
                            </button>
                        </td>
                    </tr>`;
                return;
            }
            
            tbody.innerHTML = rentalsData.map(r => `
                <tr>
                    <td><strong>VM ${r.vm_id}</strong></td>
                    <td>${r.customer_name || '-'}</td>
                    <td>${formatDate(r.rental_start)}</td>
                    <td>${r.rental_end ? formatDate(r.rental_end) : '<span class="text-success">Ongoing</span>'}</td>
                    <td class="duration-display">${r.monthUsage || '--'}</td>
                    <td class="duration-display">${r.totalUsage || '--'}</td>
                    <td>
                        <div class="btn-group btn-group-sm">
                            <button class="btn btn-outline-secondary" onclick="viewUsageReport(${r.id})" title="Usage Report">
                                <i class="bi bi-file-text"></i>
                            </button>
                            <button class="btn btn-outline-secondary" onclick="editRental(${r.id})" title="Edit">
                                <i class="bi bi-pencil"></i>
                            </button>
                            <button class="btn btn-outline-secondary" onclick="deleteRental(${r.id})" title="Delete">
                                <i class="bi bi-trash"></i>
                            </button>
                        </div>
                    </td>
                </tr>
            `).join('');
        }
        
        function updateVmFilter() {
            const select = document.getElementById('sessionVmFilter');
            const current = select.value;
            select.innerHTML = '<option value="">All VMs</option>';
            vmsData.forEach(vm => {
                const option = document.createElement('option');
                option.value = vm.vm_id;
                option.textContent = `VM ${vm.vm_id}`;
                if (vm.vm_id === current) option.selected = true;
                select.appendChild(option);
            });
        }
        
        function updateStats() {
            document.getElementById('statTotalVMs').textContent = vmsData.length;
            document.getElementById('statRunning').textContent = 
                vmsData.filter(v => v.status === 'running').length;
            
            // Calculate total runtime
            const totalSeconds = vmsData.reduce((sum, v) => sum + (v.total_runtime_seconds || 0), 0);
            document.getElementById('statTotalTime').textContent = formatDurationShort(totalSeconds);
            
            // This month total (from rentals)
            const monthSeconds = rentalsData.reduce((sum, r) => sum + (r.totalSeconds || 0), 0);
            document.getElementById('statMonthTime').textContent = formatDurationShort(monthSeconds);
        }
        
        async function syncSessions() {
            try {
                const btn = event.target.closest('button');
                btn.disabled = true;
                btn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Syncing...';
                
                const response = await fetch(`${API_BASE}/api/sessions/sync`, { method: 'POST' });
                const result = await response.json();
                
                alert(`Sync complete!\\n${result.message}`);
                await loadAllData();
            } catch (err) {
                alert('Sync failed: ' + err.message);
            } finally {
                const btn = document.querySelector('[onclick="syncSessions()"]');
                btn.disabled = false;
                btn.innerHTML = '<i class="bi bi-arrow-repeat"></i> Sync from Proxmox';
            }
        }
        
        function updateRateFields() {
            const cycle = document.getElementById('rentalBillingCycle').value;
            document.getElementById('rateHourlyDiv').style.display = cycle === 'hourly' ? 'block' : 'none';
            document.getElementById('rateWeeklyDiv').style.display = cycle === 'weekly' ? 'block' : 'none';
            document.getElementById('rateMonthlyDiv').style.display = cycle === 'monthly' ? 'block' : 'none';
        }
        
        async function saveRental() {
            const id = document.getElementById('rentalId').value;
            const year = document.getElementById('rentalStartYear').value;
            const month = document.getElementById('rentalStartMonth').value;
            const billingCycle = document.getElementById('rentalBillingCycle').value;
            
            const data = {
                vm_id: document.getElementById('rentalVmId').value,
                customer_name: document.getElementById('rentalCustomer').value || null,
                customer_email: document.getElementById('rentalEmail').value || null,
                rental_start: `${year}-${month.padStart(2, '0')}-01T00:00:00`,
                billing_cycle: billingCycle,
                rate_per_hour: parseFloat(document.getElementById('rentalRateHourly').value) || null,
                rate_per_week: parseFloat(document.getElementById('rentalRateWeekly').value) || null,
                rate_per_month: parseFloat(document.getElementById('rentalRateMonthly').value) || null,
                notes: document.getElementById('rentalNotes').value || null
            };
            
            try {
                const url = id ? `${API_BASE}/api/rentals/${id}` : `${API_BASE}/api/rentals`;
                const method = id ? 'PUT' : 'POST';
                
                const response = await fetch(url, {
                    method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                
                if (response.ok) {
                    bootstrap.Modal.getInstance(document.getElementById('rentalModal')).hide();
                    await loadRentals();
                } else {
                    const err = await response.json();
                    alert('Error: ' + (err.detail || 'Failed to save'));
                }
            } catch (err) {
                alert('Error: ' + err.message);
            }
        }
        
        function editRental(id) {
            const rental = rentalsData.find(r => r.id === id);
            if (!rental) return;
            
            document.getElementById('rentalId').value = id;
            document.getElementById('rentalVmId').value = rental.vm_id;
            document.getElementById('rentalCustomer').value = rental.customer_name || '';
            document.getElementById('rentalEmail').value = rental.customer_email || '';
            document.getElementById('rentalBillingCycle').value = rental.billing_cycle || 'monthly';
            document.getElementById('rentalRateHourly').value = rental.rate_per_hour || '';
            document.getElementById('rentalRateWeekly').value = rental.rate_per_week || '';
            document.getElementById('rentalRateMonthly').value = rental.rate_per_month || '';
            document.getElementById('rentalNotes').value = rental.notes || '';
            
            const startDate = new Date(rental.rental_start);
            document.getElementById('rentalStartYear').value = startDate.getFullYear();
            document.getElementById('rentalStartMonth').value = startDate.getMonth() + 1;
            
            updateRateFields();
            new bootstrap.Modal(document.getElementById('rentalModal')).show();
        }
        
        async function deleteRental(id) {
            if (!confirm('Delete this rental?')) return;
            
            try {
                await fetch(`${API_BASE}/api/rentals/${id}`, { method: 'DELETE' });
                await loadRentals();
            } catch (err) {
                alert('Error: ' + err.message);
            }
        }
        
        async function viewUsageReport(rentalId) {
            try {
                const response = await fetch(`${API_BASE}/api/rentals/${rentalId}/report`);
                const report = await response.json();
                
                document.getElementById('usageModalBody').innerHTML = `
                    <div class="row mb-4">
                        <div class="col-md-4">
                            <div class="stat-card text-center">
                                <div class="stat-value">${report.formatted_duration}</div>
                                <div class="stat-label">Total Runtime</div>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="stat-card text-center">
                                <div class="stat-value">${report.session_count}</div>
                                <div class="stat-label">Sessions</div>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="stat-card text-center">
                                <div class="stat-value">${report.total_cost ? '$' + report.total_cost.toFixed(2) : 'N/A'}</div>
                                <div class="stat-label">Estimated Cost</div>
                            </div>
                        </div>
                    </div>
                    <h6 class="mb-3">Sessions in Period</h6>
                    <div class="table-responsive">
                        <table class="table table-sm">
                            <thead>
                                <tr>
                                    <th>Start</th>
                                    <th>End</th>
                                    <th>Duration</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${report.sessions.map(s => `
                                    <tr>
                                        <td>${formatDateTime(s.start_time)}</td>
                                        <td>${s.end_time ? formatDateTime(s.end_time) : 'Running'}</td>
                                        <td>${formatDuration(s.duration_seconds)}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                `;
                
                new bootstrap.Modal(document.getElementById('usageModal')).show();
            } catch (err) {
                alert('Error loading report: ' + err.message);
            }
        }
        
        async function viewVmUsage(vmId) {
            try {
                const response = await fetch(`${API_BASE}/api/vms/${vmId}/usage`);
                const usage = await response.json();
                
                document.getElementById('usageModalBody').innerHTML = `
                    <h5>VM ${vmId} Usage</h5>
                    <div class="row mt-4">
                        <div class="col-md-6">
                            <div class="stat-card text-center">
                                <div class="stat-value">${usage.formatted_duration}</div>
                                <div class="stat-label">Total Runtime</div>
                            </div>
                        </div>
                        <div class="col-md-6">
                            <div class="stat-card text-center">
                                <div class="stat-value">${usage.session_count}</div>
                                <div class="stat-label">Total Sessions</div>
                            </div>
                        </div>
                    </div>
                `;
                
                new bootstrap.Modal(document.getElementById('usageModal')).show();
            } catch (err) {
                alert('Error loading usage: ' + err.message);
            }
        }
        
        // Utility functions
        function formatDateTime(dateStr) {
            if (!dateStr) return '-';
            const date = new Date(dateStr);
            return date.toLocaleString();
        }
        
        function formatDate(dateStr) {
            if (!dateStr) return '-';
            const date = new Date(dateStr);
            return date.toLocaleDateString();
        }
        
        function formatDuration(seconds) {
            if (!seconds) return '0m';
            const h = Math.floor(seconds / 3600);
            const m = Math.floor((seconds % 3600) / 60);
            const s = seconds % 60;
            if (h > 0) return `${h}h ${m}m`;
            if (m > 0) return `${m}m ${s}s`;
            return `${s}s`;
        }
        
        function formatDurationShort(seconds) {
            if (!seconds) return '0h';
            const h = Math.floor(seconds / 3600);
            const m = Math.floor((seconds % 3600) / 60);
            if (h > 0) return `${h}h ${m}m`;
            return `${m}m`;
        }
        
        // Customer functions
        let customersData = { customers: [], totals: {} };
        
        async function loadCustomers() {
            try {
                const response = await fetch(`${API_BASE}/api/rentals/customers/summary`);
                if (response.ok) {
                    customersData = await response.json();
                    renderCustomers();
                    updateCustomerSummary();
                }
            } catch (err) {
                console.error('Failed to load customers:', err);
            }
        }
        
        function renderCustomers() {
            const tbody = document.getElementById('customersTableBody');
            
            if (!customersData.customers || customersData.customers.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="6" class="empty-state">
                            <i class="bi bi-people"></i>
                            <p>No customers found</p>
                            <small class="text-muted">Create rentals with customer information to see billing summaries</small>
                        </td>
                    </tr>`;
                return;
            }
            
            tbody.innerHTML = customersData.customers.map(customer => `
                <tr>
                    <td><strong>${customer.customer_name || 'Unknown'}</strong></td>
                    <td>${customer.customer_email || '-'}</td>
                    <td><span class="badge bg-primary">${customer.total_vms} VMs</span></td>
                    <td class="duration-display">${customer.total_runtime_formatted}</td>
                    <td><strong class="text-success">${formatVND(customer.total_cost)}</strong></td>
                    <td>
                        <button class="btn btn-sm btn-outline-secondary me-1" onclick="viewCustomerDetails('${customer.customer_name}')">
                            <i class="bi bi-eye"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger" onclick="deleteCustomer('${customer.customer_name}')" title="Delete customer">
                            <i class="bi bi-trash"></i>
                        </button>
                    </td>
                </tr>
            `).join('');
        }
        
        function formatVND(amount) {
            return new Intl.NumberFormat('vi-VN').format(amount) + ' VND';
        }
        
        async function deleteCustomer(customerName) {
            if (!confirm(`Delete customer "${customerName}"?\n\nThis will delete ALL rentals for this customer.\nThis action cannot be undone.`)) {
                return;
            }
            
            try {
                const response = await fetch(`${API_BASE}/api/rentals/customers/${encodeURIComponent(customerName)}`, {
                    method: 'DELETE'
                });
                
                if (response.ok) {
                    await loadCustomers();
                } else {
                    const error = await response.json();
                    alert('Failed to delete customer: ' + (error.detail || 'Unknown error'));
                }
            } catch (err) {
                console.error('Failed to delete customer:', err);
                alert('Failed to delete customer');
            }
        }
        
        function updateCustomerSummary() {
            const totals = customersData.totals || {};
            document.getElementById('totalCustomers').textContent = totals.total_customers || 0;
            document.getElementById('totalRentedVMs').textContent = totals.total_vms || 0;
            document.getElementById('totalBilledRuntime').textContent = totals.total_runtime_formatted || '0h';
            document.getElementById('totalRevenue').textContent = formatVND(totals.total_cost || 0);
        }
        
        function viewCustomerDetails(customerName) {
            const customer = customersData.customers.find(c => c.customer_name === customerName);
            if (!customer) return;
            
            const modalBody = document.getElementById('usageModalBody');
            const modal = new bootstrap.Modal(document.getElementById('usageModal'));
            
            let rentalsHtml = customer.rentals.map(r => {
                const rateDisplay = r.rate ? `${formatVND(r.rate)}/${r.rate_unit || 'month'}` : '-';
                const cycleDisplay = r.billing_cycle ? `<span class="badge bg-secondary">${r.billing_cycle}</span>` : '';
                const capBadge = r.used_monthly_cap ? `<span class="badge bg-info ms-1" title="Monthly cap applied">capped</span>` : '';
                return `
                    <tr>
                        <td>VM ${r.vm_id} ${cycleDisplay}${capBadge}</td>
                        <td>${r.node || '-'}</td>
                        <td>${r.runtime_formatted}</td>
                        <td>${rateDisplay}</td>
                        <td class="text-success"><strong>${formatVND(r.cost)}</strong></td>
                    </tr>
                `;
            }).join('');
            
            modalBody.innerHTML = `
                <div class="mb-3">
                    <h5>${customer.customer_name}</h5>
                    <p class="text-muted mb-1">${customer.customer_email || 'No email'}</p>
                </div>
                <div class="row g-3 mb-4">
                    <div class="col-md-4">
                        <div class="p-3 bg-light rounded text-center">
                            <div class="h4 mb-0">${customer.total_vms}</div>
                            <small class="text-muted">VMs</small>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="p-3 bg-light rounded text-center">
                            <div class="h4 mb-0">${customer.total_runtime_formatted}</div>
                            <small class="text-muted">Total Runtime</small>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="p-3 bg-success text-white rounded text-center">
                            <div class="h5 mb-0">${formatVND(customer.total_cost)}</div>
                            <small>Total Cost</small>
                        </div>
                    </div>
                </div>
                <h6>VM Rentals</h6>
                <table class="table table-sm">
                    <thead>
                        <tr>
                            <th>VM</th>
                            <th>Node</th>
                            <th>Runtime</th>
                            <th>Rate</th>
                            <th>Cost</th>
                        </tr>
                    </thead>
                    <tbody>${rentalsHtml}</tbody>
                    <tfoot class="table-light">
                        <tr>
                            <th colspan="4">Total</th>
                            <th class="text-success">${formatVND(customer.total_cost)}</th>
                        </tr>
                    </tfoot>
                </table>
            `;
            
            document.querySelector('#usageModal .modal-title').textContent = 'Customer Details';
            modal.show();
        }
        
        // Load customers when tab is clicked
        document.querySelector('button[data-bs-target="#customersTab"]')?.addEventListener('shown.bs.tab', loadCustomers);
        
        // ============================================
        // PRICING TAB FUNCTIONS
        // ============================================
        
        let pricingTiers = [];
        let gpuResources = [];
        
        async function loadPricingTiers() {
            try {
                const response = await fetch(`${API_BASE}/api/pricing/tiers`);
                pricingTiers = await response.json();
                
                const tbody = document.getElementById('pricingTiersTableBody');
                if (pricingTiers.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4 text-muted">
                        No pricing tiers. Click "Seed Default Pricing Data" to get started.
                    </td></tr>`;
                    return;
                }
                
                tbody.innerHTML = pricingTiers.map(tier => `
                    <tr>
                        <td><strong>${tier.name}</strong><br><small class="text-muted">${tier.target_market || ''}</small></td>
                        <td>${tier.vcpu_min}-${tier.vcpu_max}</td>
                        <td>${tier.ram_min_gb}-${tier.ram_max_gb}GB</td>
                        <td>${tier.nvme_gb}GB NVMe</td>
                        <td>${formatVND(tier.rate_per_hour)}</td>
                        <td>${formatVND(tier.rate_per_month)}</td>
                        <td>
                            <button class="btn btn-sm btn-outline-danger" onclick="deletePricingTier(${tier.id})">
                                <i class="bi bi-trash"></i>
                            </button>
                        </td>
                    </tr>
                `).join('');
            } catch (err) {
                console.error('Failed to load pricing tiers:', err);
            }
        }
        
        async function loadGPUResources() {
            try {
                const response = await fetch(`${API_BASE}/api/pricing/gpus`);
                gpuResources = await response.json();
                
                const tbody = document.getElementById('gpuResourcesTableBody');
                const gpuSelect = document.getElementById('calcGpu');
                
                if (gpuResources.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-muted">
                        No GPU resources. Click "Seed Default Pricing Data" to get started.
                    </td></tr>`;
                    return;
                }
                
                tbody.innerHTML = gpuResources.map(gpu => `
                    <tr>
                        <td><strong>${gpu.name}</strong><br><small class="text-muted">${gpu.model || ''}</small></td>
                        <td>${gpu.vram_gb}GB</td>
                        <td>${formatVND(gpu.rate_per_hour)}</td>
                        <td><small>${gpu.target_workloads || '-'}</small></td>
                        <td>
                            <button class="btn btn-sm btn-outline-danger" onclick="deleteGPUResource(${gpu.id})">
                                <i class="bi bi-trash"></i>
                            </button>
                        </td>
                    </tr>
                `).join('');
                
                // Update GPU select in calculator
                gpuSelect.innerHTML = `<option value="">No GPU</option>` + 
                    gpuResources.map(gpu => `<option value="${gpu.id}">${gpu.name} (${gpu.vram_gb}GB) - ${formatVND(gpu.rate_per_hour)}/h</option>`).join('');
            } catch (err) {
                console.error('Failed to load GPU resources:', err);
            }
        }
        
        async function calculatePricing() {
            const resultDiv = document.getElementById('pricingResult');
            resultDiv.innerHTML = `<div class="text-center py-5"><div class="spinner-border text-primary"></div></div>`;
            
            try {
                const request = {
                    vcpu: parseInt(document.getElementById('calcVcpu').value),
                    ram_gb: parseInt(document.getElementById('calcRam').value),
                    nvme_gb: parseInt(document.getElementById('calcNvme').value),
                    gpu_id: document.getElementById('calcGpu').value || null,
                    profit_margin_percent: parseFloat(document.getElementById('calcMargin').value)
                };
                
                const response = await fetch(`${API_BASE}/api/pricing/calculate`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(request)
                });
                
                if (!response.ok) throw new Error('Calculation failed');
                const result = await response.json();
                const b = result.breakdown;
                
                resultDiv.innerHTML = `
                    <div class="row g-3">
                        <div class="col-md-6">
                            <div class="p-3 rounded mb-3" style="background: rgba(var(--bs-primary-rgb), 0.1);">
                                <h5 class="mb-3"><i class="bi bi-cash-stack me-2"></i>Recommended Pricing</h5>
                                <div class="d-flex justify-content-between mb-2">
                                    <span>Per Hour:</span>
                                    <strong class="text-primary">${formatVND(b.total_price_per_hour)}</strong>
                                </div>
                                <div class="d-flex justify-content-between mb-2">
                                    <span>Per Day:</span>
                                    <strong class="text-primary">${formatVND(b.total_price_per_day)}</strong>
                                </div>
                                <div class="d-flex justify-content-between">
                                    <span>Per Month:</span>
                                    <strong class="text-primary fs-5">${formatVND(b.total_price_per_month)}</strong>
                                </div>
                            </div>
                        </div>
                        <div class="col-md-6">
                            <div class="p-3 rounded" style="background: rgba(var(--bs-warning-rgb), 0.1);">
                                <h6 class="mb-3"><i class="bi bi-pie-chart me-2"></i>Cost Breakdown (per hour)</h6>
                                <div class="d-flex justify-content-between mb-2">
                                    <span>Hardware:</span>
                                    <span>${formatVND(b.hardware_cost_per_hour)}</span>
                                </div>
                                <div class="d-flex justify-content-between mb-2">
                                    <span>Electricity:</span>
                                    <span>${formatVND(b.electricity_cost_per_hour)}</span>
                                </div>
                                ${b.gpu_cost_per_hour > 0 ? `
                                <div class="d-flex justify-content-between mb-2">
                                    <span>GPU:</span>
                                    <span>${formatVND(b.gpu_cost_per_hour)}</span>
                                </div>
                                ` : ''}
                                <hr>
                                <div class="d-flex justify-content-between mb-2">
                                    <span>Base Cost:</span>
                                    <span>${formatVND(b.base_cost_per_hour)}</span>
                                </div>
                                <div class="d-flex justify-content-between text-success">
                                    <span>Profit (${b.profit_margin_applied}%):</span>
                                    <span>+${formatVND(b.profit_per_hour)}</span>
                                </div>
                            </div>
                        </div>
                        <div class="col-12">
                            <small class="text-muted">
                                <i class="bi bi-info-circle me-1"></i>
                                Hardware pool: ${result.hardware_pool} | ${result.electricity_tier_info}
                            </small>
                        </div>
                    </div>
                `;
            } catch (err) {
                resultDiv.innerHTML = `<div class="text-center py-5 text-danger">
                    <i class="bi bi-exclamation-triangle fs-1 mb-3 d-block"></i>
                    Failed to calculate. Make sure pricing data is seeded.
                </div>`;
            }
        }
        
        async function seedPricingData() {
            if (!confirm('This will seed default pricing tiers, GPU resources, and electricity rates. Continue?')) return;
            
            try {
                const response = await fetch(`${API_BASE}/api/pricing/seed`, { method: 'POST' });
                const result = await response.json();
                alert(`Seeded: ${result.data.pricing_tiers} tiers, ${result.data.gpu_resources} GPUs, ${result.data.electricity_tiers} electricity tiers`);
                loadPricingTiers();
                loadGPUResources();
            } catch (err) {
                alert('Failed to seed data: ' + err.message);
            }
        }
        
        async function deletePricingTier(id) {
            if (!confirm('Delete this pricing tier?')) return;
            try {
                await fetch(`${API_BASE}/api/pricing/tiers/${id}`, { method: 'DELETE' });
                loadPricingTiers();
            } catch (err) {
                alert('Failed to delete tier');
            }
        }
        
        async function deleteGPUResource(id) {
            if (!confirm('Delete this GPU resource?')) return;
            try {
                await fetch(`${API_BASE}/api/pricing/gpus/${id}`, { method: 'DELETE' });
                loadGPUResources();
            } catch (err) {
                alert('Failed to delete GPU');
            }
        }
        
        // Load pricing data when tab is clicked
        document.querySelector('button[data-bs-target="#pricingTab"]')?.addEventListener('shown.bs.tab', () => {
            loadPricingTiers();
            loadGPUResources();
        });
    </script>
    
    <style>
        .spin { animation: spin 1s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
    </style>
</body>
</html>'''


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.debug
    )
