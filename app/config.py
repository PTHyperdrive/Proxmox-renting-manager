"""
Application Configuration

Loads settings from config.yaml and environment variables.
"""

import os
from pathlib import Path
from functools import lru_cache
from typing import Optional

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings


class ProxmoxSSHSettings(BaseSettings):
    """SSH settings for remote log access"""
    enabled: bool = False
    port: int = 22
    key_file: str = ""


class ProxmoxSettings(BaseSettings):
    """Proxmox connection settings"""
    host: str = "localhost"
    port: int = 8006
    user: str = "root@pam"
    password: str = ""
    token_name: Optional[str] = None
    token_value: Optional[str] = None
    verify_ssl: bool = False
    ssh: ProxmoxSSHSettings = Field(default_factory=ProxmoxSSHSettings)


class DatabaseSettings(BaseSettings):
    """Database connection settings"""
    url: str = "sqlite+aiosqlite:///./vm_tracking.db"


class ServerSettings(BaseSettings):
    """Server settings"""
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True


class LoggingSettings(BaseSettings):
    """Logging configuration"""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


class Settings(BaseSettings):
    """Main application settings"""
    proxmox: ProxmoxSettings = Field(default_factory=ProxmoxSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    
    @classmethod
    def from_yaml(cls, path: str = "config.yaml") -> "Settings":
        """Load settings from YAML file"""
        config_path = Path(path)
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f) or {}
        else:
            config_data = {}
        
        # Build nested settings
        proxmox_data = config_data.get('proxmox', {})
        ssh_data = proxmox_data.pop('ssh', {}) if 'ssh' in proxmox_data else {}
        
        return cls(
            proxmox=ProxmoxSettings(
                ssh=ProxmoxSSHSettings(**ssh_data),
                **proxmox_data
            ),
            database=DatabaseSettings(**config_data.get('database', {})),
            server=ServerSettings(**config_data.get('server', {})),
            logging=LoggingSettings(**config_data.get('logging', {}))
        )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    # Check for config file in current directory or parent
    config_paths = [
        "config.yaml",
        "../config.yaml",
        os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    ]
    
    for path in config_paths:
        if Path(path).exists():
            return Settings.from_yaml(path)
    
    # Return default settings if no config file found
    return Settings()


# Global settings instance
settings = get_settings()
