"""
Proxmox VM Tracker Client - Main Entry Point

Runs on Proxmox machines to watch log files and send events to the Manager.
"""

import os
import sys
import json
import asyncio
import logging
import signal
from pathlib import Path
from datetime import datetime
from typing import Optional, Set

from .config import settings, ClientSettings
from .log_parser import LogParser, VMEvent
from .api_client import APIClient

# Set up logging
logging.basicConfig(
    level=getattr(logging, settings.logging.level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ProxmoxClient:
    """
    Main client class that watches Proxmox logs and sends events to Manager.
    """
    
    def __init__(self, config: Optional[ClientSettings] = None):
        self.settings = config or settings
        self.parser = LogParser(self.settings.node_name)
        self.api_client = APIClient()
        self.running = False
        self.last_sync: Optional[datetime] = None
        self.processed_upids: Set[str] = set()
    
    def _load_state(self):
        """Load state from previous run"""
        state_path = Path(self.settings.state_file)
        
        if state_path.exists():
            try:
                with open(state_path, 'r') as f:
                    state = json.load(f)
                    self.last_sync = datetime.fromisoformat(state.get('last_sync', ''))
                    self.processed_upids = set(state.get('processed_upids', []))
                    logger.info(f"Loaded state: {len(self.processed_upids)} previous events")
            except Exception as e:
                logger.warning(f"Failed to load state: {e}")
    
    def _save_state(self):
        """Save state for next run"""
        state_path = Path(self.settings.state_file)
        
        # Ensure directory exists
        state_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Keep only recent UPIDs (last 10000)
        recent_upids = list(self.processed_upids)[-10000:]
        
        try:
            with open(state_path, 'w') as f:
                json.dump({
                    'last_sync': datetime.utcnow().isoformat(),
                    'processed_upids': recent_upids
                }, f)
        except Exception as e:
            logger.warning(f"Failed to save state: {e}")
    
    async def register_with_manager(self) -> bool:
        """Register this node with the manager"""
        try:
            result = await self.api_client.register_node(
                self.settings.node_name,
                self.settings.hostname
            )
            if result.get('success'):
                logger.info(f"Registered with manager as '{self.settings.node_name}'")
                return True
            else:
                logger.error(f"Registration failed: {result.get('message')}")
                return False
        except Exception as e:
            logger.error(f"Failed to register with manager: {e}")
            return False
    
    async def sync_events(self) -> int:
        """
        Parse logs and send new events to manager.
        
        Returns:
            Number of events sent
        """
        # Parse log files
        events = self.parser.parse_multiple_files(
            self.settings.log_paths,
            since=self.last_sync
        )
        
        # Filter already processed
        new_events = [
            e for e in events
            if e.upid not in self.processed_upids
        ]
        
        if not new_events:
            logger.debug("No new events to sync")
            return 0
        
        logger.info(f"Found {len(new_events)} new events to sync")
        
        # Send in batches
        batch_size = self.settings.sync.batch_size
        sent_count = 0
        
        for i in range(0, len(new_events), batch_size):
            batch = new_events[i:i + batch_size]
            
            try:
                result = await self.api_client.send_events(
                    self.settings.node_name,
                    batch
                )
                
                if result.get('success', True):
                    # Mark as processed
                    for event in batch:
                        self.processed_upids.add(event.upid)
                    sent_count += len(batch)
                    
            except Exception as e:
                logger.error(f"Failed to send batch: {e}")
                # Will retry on next sync
                break
        
        self.last_sync = datetime.utcnow()
        self._save_state()
        
        return sent_count
    
    async def run_once(self):
        """Run a single sync cycle"""
        self._load_state()
        
        # Check connection
        if not await self.api_client.check_connection():
            logger.error(f"Cannot connect to manager at {self.settings.manager.url}")
            return
        
        # Register
        await self.register_with_manager()
        
        # Sync
        count = await self.sync_events()
        logger.info(f"Sync complete: {count} events sent")
    
    async def run_daemon(self):
        """Run as a daemon, syncing periodically"""
        self._load_state()
        self.running = True
        
        logger.info(f"Starting Proxmox Tracker Client for node '{self.settings.node_name}'")
        logger.info(f"Manager: {self.settings.manager.url}")
        logger.info(f"Sync interval: {self.settings.sync.interval_seconds}s")
        
        # Check initial connection
        if not await self.api_client.check_connection():
            logger.warning(f"Cannot connect to manager, will retry...")
        else:
            await self.register_with_manager()
        
        while self.running:
            try:
                await self.sync_events()
                await self.api_client.heartbeat(self.settings.node_name)
                
            except Exception as e:
                logger.error(f"Sync error: {e}")
            
            # Wait for next sync
            await asyncio.sleep(self.settings.sync.interval_seconds)
        
        logger.info("Client stopped")
    
    def stop(self):
        """Stop the daemon"""
        self.running = False


def main():
    """CLI entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Proxmox VM Tracker Client'
    )
    parser.add_argument(
        '--config', '-c',
        default='client_config.yaml',
        help='Path to configuration file'
    )
    parser.add_argument(
        '--once', '-1',
        action='store_true',
        help='Run once and exit (instead of daemon mode)'
    )
    parser.add_argument(
        '--daemon', '-d',
        action='store_true',
        help='Run as daemon'
    )
    
    args = parser.parse_args()
    
    # Load config
    config = ClientSettings(args.config)
    client = ProxmoxClient(config)
    
    # Set up signal handlers
    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        client.stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run
    if args.once:
        asyncio.run(client.run_once())
    else:
        asyncio.run(client.run_daemon())


if __name__ == '__main__':
    main()
