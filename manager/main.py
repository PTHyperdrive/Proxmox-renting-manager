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
from .routes import vms_router, sessions_router, rentals_router, ingest_router, nodes_router

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
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Proxmox VM Time Tracking</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        :root {
            --bs-body-bg: #0d1117;
            --bs-body-color: #c9d1d9;
            --card-bg: #161b22;
            --border-color: #30363d;
            --accent-color: #58a6ff;
            --success-color: #3fb950;
            --warning-color: #d29922;
        }
        
        body {
            background: var(--bs-body-bg);
            color: var(--bs-body-color);
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
        }
        
        .navbar {
            background: linear-gradient(135deg, #1a1f2e 0%, #0d1117 100%);
            border-bottom: 1px solid var(--border-color);
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
            background: linear-gradient(135deg, #1a1f2e 0%, #161b22 100%);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.5rem;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        
        .stat-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 30px rgba(0,0,0,0.3);
        }
        
        .stat-value {
            font-size: 2.5rem;
            font-weight: 700;
            background: linear-gradient(135deg, var(--accent-color), #a371f7);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .stat-label {
            color: #8b949e;
            font-size: 0.875rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .table {
            color: var(--bs-body-color);
        }
        
        .table thead th {
            border-color: var(--border-color);
            color: #8b949e;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.75rem;
            letter-spacing: 0.5px;
        }
        
        .table tbody td {
            border-color: var(--border-color);
            vertical-align: middle;
        }
        
        .badge-running {
            background: rgba(63, 185, 80, 0.2);
            color: var(--success-color);
            border: 1px solid var(--success-color);
        }
        
        .badge-stopped {
            background: rgba(139, 148, 158, 0.2);
            color: #8b949e;
            border: 1px solid #8b949e;
        }
        
        .btn-primary {
            background: var(--accent-color);
            border: none;
            border-radius: 8px;
            padding: 0.5rem 1.5rem;
        }
        
        .btn-primary:hover {
            background: #79b8ff;
        }
        
        .btn-outline-secondary {
            color: #8b949e;
            border-color: var(--border-color);
        }
        
        .btn-outline-secondary:hover {
            background: var(--border-color);
            color: var(--bs-body-color);
        }
        
        .form-control, .form-select {
            background: #0d1117;
            border: 1px solid var(--border-color);
            color: var(--bs-body-color);
            border-radius: 8px;
        }
        
        .form-control:focus, .form-select:focus {
            background: #0d1117;
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
            color: #8b949e;
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
            background: #0d1117;
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
            color: #8b949e;
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
    </style>
</head>
<body>
    <!-- Navbar -->
    <nav class="navbar navbar-dark py-3">
        <div class="container">
            <a class="navbar-brand d-flex align-items-center gap-2" href="#">
                <i class="bi bi-hdd-rack fs-4"></i>
                <span class="fw-bold">Proxmox VM Tracker</span>
            </a>
            <div class="d-flex align-items-center gap-3">
                <button class="btn btn-outline-secondary btn-sm" onclick="syncSessions()">
                    <i class="bi bi-arrow-repeat"></i> Sync from Proxmox
                </button>
                <span class="text-muted small" id="lastUpdated">Last updated: --</span>
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
                            <label class="form-label">Rate per Hour ($)</label>
                            <input type="number" step="0.01" class="form-control" id="rentalRate">
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
                    <td><strong>VM ${vm.vm_id}</strong></td>
                    <td>${vm.node}</td>
                    <td>
                        <span class="badge ${vm.status === 'running' ? 'badge-running' : 'badge-stopped'}">
                            ${vm.status === 'running' ? '<i class="bi bi-circle-fill me-1 running-indicator"></i>' : ''}
                            ${vm.status}
                        </span>
                    </td>
                    <td class="duration-display">${vm.formatted_runtime}</td>
                    <td>
                        <button class="btn btn-sm btn-outline-secondary" onclick="viewVmUsage('${vm.vm_id}')">
                            <i class="bi bi-graph-up"></i> Usage
                        </button>
                    </td>
                </tr>
            `).join('');
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
        
        async function saveRental() {
            const id = document.getElementById('rentalId').value;
            const year = document.getElementById('rentalStartYear').value;
            const month = document.getElementById('rentalStartMonth').value;
            
            const data = {
                vm_id: document.getElementById('rentalVmId').value,
                customer_name: document.getElementById('rentalCustomer').value || null,
                customer_email: document.getElementById('rentalEmail').value || null,
                rental_start: `${year}-${month.padStart(2, '0')}-01T00:00:00`,
                rate_per_hour: parseFloat(document.getElementById('rentalRate').value) || null,
                notes: document.getElementById('rentalNotes').value || null,
                billing_cycle: 'monthly'
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
            document.getElementById('rentalRate').value = rental.rate_per_hour || '';
            document.getElementById('rentalNotes').value = rental.notes || '';
            
            const startDate = new Date(rental.rental_start);
            document.getElementById('rentalStartYear').value = startDate.getFullYear();
            document.getElementById('rentalStartMonth').value = startDate.getMonth() + 1;
            
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
