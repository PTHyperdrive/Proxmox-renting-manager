# Proxmox VM Time Tracking Service

A distributed system for tracking VM running time across multiple Proxmox nodes.

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
          │   HTTP/API     │                │
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
│  │          (Sessions, Rentals, Nodes)                     │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Components

| Component | Location | Description |
|-----------|----------|-------------|
| **Manager** | Ubuntu 24.04 server | Central API server with MySQL, web dashboard |
| **Client** | Each Proxmox machine | Watches logs, sends events to Manager |

## Quick Start

### 1. Set Up Manager (Ubuntu 24.04)

```bash
# Clone repository
git clone <repo-url> /opt/proxmox-tracker
cd /opt/proxmox-tracker

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
nano config.yaml  # Edit MySQL credentials

# Run manually
python -m uvicorn manager.main:app --host 0.0.0.0 --port 8000

# Or install as service
sudo cp deploy/proxmox-tracker-manager.service /etc/systemd/system/
sudo systemctl enable proxmox-tracker-manager
sudo systemctl start proxmox-tracker-manager
```

### 2. Set Up Client (Each Proxmox Machine)

```bash
# Copy client files to Proxmox
scp -r client/ requirements-client.txt client_config.yaml root@pve-node:/opt/proxmox-tracker/

# SSH to Proxmox node
ssh root@pve-node

# Install dependencies
cd /opt/proxmox-tracker
pip install -r requirements-client.txt

# Configure
nano client_config.yaml  # Set manager URL and API key

# Run manually
python -m client.main --once  # Test single sync

# Or install as service
cp deploy/proxmox-tracker-client.service /etc/systemd/system/
systemctl enable proxmox-tracker-client
systemctl start proxmox-tracker-client
```

### 3. Access Dashboard

Open: `http://your-manager-ip:8000`

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

manager:
  url: "http://manager-ip:8000"
  api_key: "shared-secret-key"

sync:
  interval_seconds: 30
```

## API Endpoints

### Ingest API (for Clients)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/ingest/register` | Register a new node |
| POST | `/api/ingest/events` | Send VM events |
| POST | `/api/ingest/heartbeat` | Node heartbeat |

### Management API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/nodes` | List registered nodes |
| GET | `/api/vms` | List all VMs |
| GET | `/api/sessions` | List sessions |
| GET/POST/PUT/DELETE | `/api/rentals` | Manage rentals |
| GET | `/api/rentals/{id}/report` | Usage report |

## Project Structure

```
proxmox-tracker/
├── manager/                 # Manager server (Ubuntu)
│   ├── main.py              # FastAPI app + dashboard
│   ├── config.py            # MySQL configuration
│   ├── models/              # SQLAlchemy models
│   ├── services/            # Business logic
│   └── routes/              # API endpoints
│
├── client/                  # Client (Proxmox machines)
│   ├── main.py              # Client daemon
│   ├── config.py            # Client configuration
│   ├── log_parser.py        # Proxmox log parser
│   └── api_client.py        # HTTP client
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

## Features

- 📊 **Multi-Node Tracking** - Track VMs across multiple Proxmox clusters
- ⏱️ **Real-Time Sync** - Events sent every 30 seconds (configurable)
- 📅 **Rental Management** - Set billing start months, generate usage reports
- 🔒 **API Key Auth** - Secure client-manager communication
- 🌐 **Web Dashboard** - Beautiful dark-themed dashboard
- 📈 **MySQL Storage** - Production-ready database

## Troubleshooting

### Client not connecting
```bash
# Check client logs
journalctl -u proxmox-tracker-client -f

# Test connection manually
curl http://manager-ip:8000/health
```

### Events not syncing
```bash
# Check log files exist
ls -la /var/log/pve/tasks/

# Run client once with debug
python -m client.main --once
```
