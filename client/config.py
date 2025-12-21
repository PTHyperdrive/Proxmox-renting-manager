"""
Client Configuration

Loads settings from client_config.yaml for the Proxmox client.
"""

import os
from pathlib import Path
from typing import List, Optional

import yaml


class ManagerSettings:
    """Manager server connection settings"""
    def __init__(self, data: dict):
        self.url = data.get('url', 'http://localhost:8000')
        self.api_key = data.get('api_key', '')
        self.timeout = data.get('timeout', 30)


class SyncSettings:
    """Sync behavior settings"""
    def __init__(self, data: dict):
        self.interval_seconds = data.get('interval_seconds', 30)
        self.batch_size = data.get('batch_size', 100)
        self.max_retries = data.get('max_retries', 3)
        self.retry_delay = data.get('retry_delay', 10)


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
        self.log_paths: List[str] = []
        self.state_file = '/var/lib/proxmox-tracker/state.json'
        self.manager = ManagerSettings({})
        self.sync = SyncSettings({})
        self.logging = LoggingSettings({})
        
        self._load(config_path)
    
    def _load(self, config_path: str):
        """Load settings from YAML file"""
        path = Path(config_path)
        
        if not path.exists():
            # Try alternative paths
            alt_paths = [
                '/etc/proxmox-tracker/client_config.yaml',
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
        self.node_name = node_data.get('name', os.uname().nodename if hasattr(os, 'uname') else 'pve')
        self.hostname = node_data.get('hostname', '')
        
        # Log paths
        self.log_paths = data.get('log_paths', [
            '/var/log/pve/tasks/index',
            '/var/log/pve/tasks/active'
        ])
        
        # State file
        self.state_file = data.get('state_file', '/var/lib/proxmox-tracker/state.json')
        
        # Manager settings
        self.manager = ManagerSettings(data.get('manager', {}))
        
        # Sync settings
        self.sync = SyncSettings(data.get('sync', {}))
        
        # Logging settings
        self.logging = LoggingSettings(data.get('logging', {}))


def get_settings() -> ClientSettings:
    """Get settings instance"""
    return ClientSettings()


# Global instance
settings = get_settings()
