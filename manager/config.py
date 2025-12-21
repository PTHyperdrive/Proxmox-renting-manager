"""
Manager Configuration

Loads settings from config.yaml for the Manager server.
Supports MySQL database configuration.
"""

import os
from pathlib import Path
from functools import lru_cache
from typing import Optional, List

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings


class DatabaseSettings(BaseSettings):
    """MySQL Database settings"""
    type: str = "mysql"
    host: str = "localhost"
    port: int = 3306
    user: str = "vm_tracker"
    password: str = ""
    database: str = "vm_tracking"
    pool_size: int = 5
    max_overflow: int = 10
    
    @property
    def url(self) -> str:
        """Generate SQLAlchemy database URL"""
        if self.type == "mysql":
            return f"mysql+aiomysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
        else:
            # Fallback to SQLite for development
            return "sqlite+aiosqlite:///./vm_tracking.db"


class ServerSettings(BaseSettings):
    """Server settings"""
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True


class SecuritySettings(BaseSettings):
    """Security settings"""
    api_key: str = ""
    trusted_ips: List[str] = []
    
    def validate_api_key(self, key: str) -> bool:
        """Check if API key is valid"""
        if not self.api_key:
            return True  # No key required if not set
        return key == self.api_key
    
    def is_trusted_ip(self, ip: str) -> bool:
        """Check if IP is in trusted list"""
        return ip in self.trusted_ips


class LoggingSettings(BaseSettings):
    """Logging configuration"""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


class Settings(BaseSettings):
    """Main application settings"""
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
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
        
        return cls(
            database=DatabaseSettings(**config_data.get('database', {})),
            server=ServerSettings(**config_data.get('server', {})),
            security=SecuritySettings(**config_data.get('security', {})),
            logging=LoggingSettings(**config_data.get('logging', {}))
        )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    config_paths = [
        "config.yaml",
        "../config.yaml",
        os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    ]
    
    for path in config_paths:
        if Path(path).exists():
            return Settings.from_yaml(path)
    
    return Settings()


# Global settings instance
settings = get_settings()
