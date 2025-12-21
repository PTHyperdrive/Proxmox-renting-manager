# Proxmox VM Time Tracking Service

A distributed system for tracking VM running time across multiple Proxmox nodes using **real-time state monitoring**.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Proxmox Machines (Clients)                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   pve-01    │  │   pve-02    │  │   pve-03    │             │
│  │  (Client)   │  │  (Client)   │  │  (Client)   │             │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │
└─────────┼────────────────┼────────────────┼─────────────────────┘
          │                │                │
          │   Proxmox API  │   HTTP/API     │
          └────────────────┼────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Manager Server (Ubuntu 24.04)                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Manager API                           │   │
│  │              (FastAPI + Web Dashboard)                   │   │
│  └────────────────────────┬────────────────────────────────┘   │
│                           │                                     │
│  ┌────────────────────────▼────────────────────────────────┐   │
│  │                   MySQL Database                         │   │
│  │          (Sessions, Rentals, Nodes, VMs)                │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## How It Works

1. **Client polls Proxmox API** every 30 seconds for VM status
2. **Detects state changes** (VM started/stopped)
3. **Reports to Manager** immediately via HTTP API
4. **Manager tracks sessions** with start/end times and duration
5. **Force Sync** button reconciles all VM states on demand

## Quick Start

### 1. Create Proxmox API Token

On each Proxmox node, create an API token for the client:

#### Via Web UI:
1. Go to **Datacenter** → **Permissions** → **API Tokens**
2. Click **Add**
3. **User**: `root@pam`
4. **Token ID**: `tracker`
5. **Privilege Separation**: ❌ Uncheck (or add VM.Audit permission)
6. Click **Add** and **copy the token value**

#### Via CLI:
```bash
pveum user token add root@pam tracker --privsep=0
```

Output:
```
┌──────────────┬──────────────────────────────────────┐
│ key          │ value                                │
├──────────────┼──────────────────────────────────────┤
│ full-tokenid │ root@pam!tracker                     │
│ info         │ {"privsep":"0"}                      │
│ value        │ xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx │
└──────────────┴──────────────────────────────────────┘
```

**Save the token value** - you'll need it for `client_config.yaml`.

---

### 2. Set Up Manager (Ubuntu 24.04)

```bash
# Clone repository
git clone <repo-url> /opt/proxmox-tracker
cd /opt/proxmox-tracker

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements-manager.txt

# Set up MySQL
mysql -u root -p << 'EOF'
CREATE DATABASE vm_tracking CHARACTER SET utf8mb4;
CREATE USER 'vm_tracker'@'localhost' IDENTIFIED BY 'your-secure-password';
GRANT ALL PRIVILEGES ON vm_tracking.* TO 'vm_tracker'@'localhost';
FLUSH PRIVILEGES;
EOF

# Configure
nano config.yaml  # Edit MySQL credentials and API key

# Test run (HTTP)
python -m uvicorn manager.main:app --host 0.0.0.0 --port 8000

# Install as service
sudo cp deploy/proxmox-tracker-manager.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable proxmox-tracker-manager
sudo systemctl start proxmox-tracker-manager
```

#### Enable HTTPS (Recommended)

```bash
# Create SSL directory
mkdir -p /opt/proxmox-tracker/ssl
cd /opt/proxmox-tracker/ssl

# Generate self-signed certificate (valid for 365 days)
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes \
  -subj "/C=US/ST=State/L=City/O=Organization/CN=pve-tracker"

# Set permissions
chmod 600 key.pem
chmod 644 cert.pem

# Update service file to use HTTPS (already configured in deploy/proxmox-tracker-manager.service)
sudo systemctl daemon-reload
sudo systemctl restart proxmox-tracker-manager
```

---

### 3. Set Up Client (Each Proxmox Machine)

```bash
# Copy client files to Proxmox
scp -r client/ requirements-client.txt client_config.yaml root@pve-node:/opt/proxmox-tracker/

# SSH to Proxmox node
ssh root@pve-node

# Install dependencies
cd /opt/proxmox-tracker
pip3 install -r requirements-client.txt

# Configure - ADD YOUR API TOKEN HERE
nano client_config.yaml
```

**client_config.yaml:**
```yaml
node:
  name: "StormWorking"  # Your node name

proxmox:
  host: "127.0.0.1"
  port: 8006
  user: "root@pam"
  token_name: "tracker"
  token_value: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"  # Your token
  verify_ssl: false

manager:
  url: "https://YOUR-MANAGER-IP:8000"  # Use https:// for secure connection
  api_key: "shared-secret-key"
  verify_ssl: false  # Set to false for self-signed certificates

polling:
  interval_seconds: 30
  track_qemu: true
  track_lxc: true
```

```bash
# Test Proxmox API connection
python3 -m client.main --test

# Test single sync
python3 -m client.main --once

# Install as service
cp deploy/proxmox-tracker-client.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable proxmox-tracker-client
systemctl start proxmox-tracker-client
```

---

### 4. Access Dashboard

Open: `http://your-manager-ip:8000`

Features:
- 🌙/☀️ Dark/Light mode toggle
- 📊 VM status overview
- ⏱️ Running time tracking
- 🔄 Force Sync button
- 📅 Rental management

---

## Configuration

### Manager (config.yaml)

```yaml
database:
  type: mysql
  host: localhost
  port: 3306
  user: vm_tracker
  password: "your-password"
  database: vm_tracking

security:
  api_key: "shared-secret-key"  # Must match clients

server:
  host: "0.0.0.0"
  port: 8000
```

### Client (client_config.yaml)

```yaml
node:
  name: "pve-01"  # Unique per node

proxmox:
  host: "127.0.0.1"
  port: 8006
  user: "root@pam"
  token_name: "tracker"
  token_value: "your-api-token"
  verify_ssl: false

manager:
  url: "http://manager-ip:8000"
  api_key: "shared-secret-key"

polling:
  interval_seconds: 30
  track_qemu: true   # Track QEMU VMs
  track_lxc: true    # Track LXC containers
```

---

## API Endpoints

### Ingest API (for Clients)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/ingest/register` | Register a new node |
| POST | `/api/ingest/vm-start` | Report VM started |
| POST | `/api/ingest/vm-stop` | Report VM stopped |
| POST | `/api/ingest/vm-states` | Send full state snapshot |
| POST | `/api/ingest/heartbeat` | Node heartbeat |
| POST | `/api/ingest/force-sync` | Request sync from all nodes |

### Management API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/nodes` | List registered nodes |
| GET | `/api/vms` | List all VMs |
| GET | `/api/sessions` | List sessions |
| GET/POST/PUT/DELETE | `/api/rentals` | Manage rentals |
| GET | `/api/rentals/{id}/report` | Usage report |

---

## Project Structure

```
proxmox-tracker/
├── manager/                 # Manager server (Ubuntu)
│   ├── main.py              # FastAPI app + dashboard
│   ├── config.py            # MySQL configuration
│   ├── models/              # SQLAlchemy models
│   │   ├── database.py      # VMSession, TrackedVM, Rental, ProxmoxNode
│   │   └── schemas.py       # Pydantic models
│   ├── services/            # Business logic
│   │   └── ingest_service.py
│   └── routes/              # API endpoints
│       ├── ingest.py        # Client data ingestion
│       └── vms.py, sessions.py, rentals.py, nodes.py
│
├── client/                  # Client (Proxmox machines)
│   ├── main.py              # State polling daemon
│   ├── config.py            # Client configuration
│   ├── proxmox_api.py       # Proxmox API client
│   └── api_client.py        # Manager HTTP client
│
├── deploy/                  # Deployment files
│   ├── proxmox-tracker-manager.service
│   └── proxmox-tracker-client.service
│
├── config.yaml              # Manager config
├── client_config.yaml       # Client config
├── requirements-manager.txt # Manager dependencies
└── requirements-client.txt  # Client dependencies
```

---

## Features

- 📊 **Multi-Node Tracking** - Track VMs across multiple Proxmox clusters
- ⏱️ **Real-Time State Monitoring** - Uses Proxmox API, not logs
- 🔄 **Force Sync** - Reconcile all VM states on demand
- 📅 **Rental Management** - Set billing start months, generate usage reports
- 🔒 **API Key Auth** - Secure client-manager communication
- 🌐 **Web Dashboard** - Beautiful dark/light mode dashboard
- 📈 **MySQL Storage** - Production-ready database

---

## Troubleshooting

### Test Proxmox API connection
```bash
python3 -m client.main --test
```

Expected output:
```
✓ Proxmox API connection successful
  Node: StormWorking
  VMs found: 5
    - 104: vGPU-1 (running)
    - 105: vGPU-2 (stopped)
```

### Client not connecting to Manager
```bash
# Check client logs
journalctl -u proxmox-tracker-client -f

# Test manager is reachable
curl http://manager-ip:8000/health
```

### API Token permission denied
```bash
# Add VM.Audit permission to token
pveum aclmod / -user root@pam -token tracker -role PVEVMUser
```

### VMs not showing up
1. Check `track_qemu` and `track_lxc` settings in client_config.yaml
2. Run `python3 -m client.main --once` to force sync
3. Click "Force Sync" button in dashboard

---

## License

MIT
