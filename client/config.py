"""
Client Configuration

Loads settings from client_config.yaml for the Proxmox client.
"""

import os
import socket
from pathlib import Path
from typing import List, Optional

import yaml


class ProxmoxSettings:
    """Proxmox API connection settings"""
    def __init__(self, data: dict):
        self.host = data.get('host', '127.0.0.1')
        self.port = data.get('port', 8006)
        self.user = data.get('user', 'root@pam')
        self.token_name = data.get('token_name', 'tracker')
        self.token_value = data.get('token_value', '')
        self.verify_ssl = data.get('verify_ssl', False)


class ManagerSettings:
    """Manager server connection settings"""
    def __init__(self, data: dict):
        self.url = data.get('url', 'http://localhost:8000')
        self.api_key = data.get('api_key', '')
        self.timeout = data.get('timeout', 30)
        self.verify_ssl = data.get('verify_ssl', False)  # False to allow self-signed certs


class PollingSettings:
    """VM state polling settings"""
    def __init__(self, data: dict):
        self.interval_seconds = data.get('interval_seconds', 30)
        self.report_unchanged = data.get('report_unchanged', False)
        self.track_qemu = data.get('track_qemu', True)
        self.track_lxc = data.get('track_lxc', True)


class LoggingSettings:
    """Logging configuration"""
    def __init__(self, data: dict):
        self.level = data.get('level', 'INFO')
        self.file = data.get('file', '')


class ClientSettings:
    """Main client settings"""
    
    def __init__(self, config_path: str = 'client_config.yaml'):
        self.node_name = ''
        self.hostname = ''
        self.state_file = '/var/lib/proxmox-tracker/state.json'
        self.proxmox = ProxmoxSettings({})
        self.manager = ManagerSettings({})
        self.polling = PollingSettings({})
        self.logging = LoggingSettings({})
        
        self._load(config_path)
    
    def _load(self, config_path: str):
        """Load settings from YAML file"""
        path = Path(config_path)
        
        if not path.exists():
            # Try alternative paths
            alt_paths = [
                '/etc/proxmox-tracker/client_config.yaml',
                '/opt/proxmox-tracker/client_config.yaml',
                os.path.join(os.path.dirname(__file__), '..', 'client_config.yaml')
            ]
            for alt in alt_paths:
                if Path(alt).exists():
                    path = Path(alt)
                    break
        
        if path.exists():
            with open(path, 'r') as f:
                data = yaml.safe_load(f) or {}
        else:
            data = {}
        
        # Node settings
        node_data = data.get('node', {})
        self.node_name = node_data.get('name', '')
        self.hostname = node_data.get('hostname', '')
        
        # Auto-detect node name if not set
        if not self.node_name:
            try:
                self.node_name = socket.gethostname()
            except Exception:
                self.node_name = 'pve'
        
        # State file
        self.state_file = data.get('state_file', '/var/lib/proxmox-tracker/state.json')
        
        # Proxmox settings
        self.proxmox = ProxmoxSettings(data.get('proxmox', {}))
        
        # Manager settings
        self.manager = ManagerSettings(data.get('manager', {}))
        
        # Polling settings
        self.polling = PollingSettings(data.get('polling', {}))
        
        # Logging settings
        self.logging = LoggingSettings(data.get('logging', {}))


def get_settings(config_path: str = 'client_config.yaml') -> ClientSettings:
    """Get settings instance"""
    return ClientSettings(config_path)


# Global instance
settings = get_settings()
