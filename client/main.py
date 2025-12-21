"""
Proxmox VM Tracker Client - Main Entry Point

Runs on Proxmox machines to monitor VM states and send events to the Manager.
Uses Proxmox API for real-time state detection instead of log parsing.
"""

import os
import sys
import json
import asyncio
import logging
import signal
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict

from .config import settings, ClientSettings
from .proxmox_api import ProxmoxAPI, VMState, VMStatus
from .api_client import APIClient

# Set up logging
logging.basicConfig(
    level=getattr(logging, settings.logging.level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ProxmoxClient:
    """
    Main client class that monitors VM states and sends events to Manager.
    
    Uses Proxmox API to poll VM status and detect start/stop events.
    """
    
    def __init__(self, config: Optional[ClientSettings] = None):
        self.settings = config or settings
        
        # Proxmox API client
        self.proxmox = ProxmoxAPI(
            host=self.settings.proxmox.host,
            port=self.settings.proxmox.port,
            user=self.settings.proxmox.user,
            token_name=self.settings.proxmox.token_name,
            token_value=self.settings.proxmox.token_value,
            verify_ssl=self.settings.proxmox.verify_ssl,
            node_name=self.settings.node_name
        )
        
        # Manager API client
        self.api_client = APIClient()
        
        # State tracking
        self.running = False
        self.previous_states: Dict[str, VMState] = {}  # vm_id -> last known state
        self.node_name = self.settings.node_name
    
    def _load_state(self):
        """Load previous VM states from disk"""
        state_path = Path(self.settings.state_file)
        
        if state_path.exists():
            try:
                with open(state_path, 'r') as f:
                    data = json.load(f)
                    # Reconstruct previous states
                    for vm_id, state_dict in data.get('vm_states', {}).items():
                        self.previous_states[vm_id] = VMState(
                            vm_id=state_dict['vm_id'],
                            vm_type=state_dict.get('vm_type', 'qemu'),
                            name=state_dict.get('name', ''),
                            status=VMStatus(state_dict.get('status', 'unknown')),
                            node=state_dict.get('node', self.node_name),
                            uptime=state_dict.get('uptime', 0)
                        )
                    logger.info(f"Loaded state: {len(self.previous_states)} VMs tracked")
            except Exception as e:
                logger.warning(f"Failed to load state: {e}")
    
    def _save_state(self):
        """Save current VM states to disk"""
        state_path = Path(self.settings.state_file)
        
        # Ensure directory exists
        state_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            states_dict = {
                vm_id: {
                    'vm_id': state.vm_id,
                    'vm_type': state.vm_type.value if hasattr(state.vm_type, 'value') else state.vm_type,
                    'name': state.name,
                    'status': state.status.value if hasattr(state.status, 'value') else state.status,
                    'node': state.node,
                    'uptime': state.uptime
                }
                for vm_id, state in self.previous_states.items()
            }
            
            with open(state_path, 'w') as f:
                json.dump({
                    'last_update': datetime.utcnow().isoformat(),
                    'node': self.node_name,
                    'vm_states': states_dict
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save state: {e}")
    
    async def register_with_manager(self) -> bool:
        """Register this node with the manager"""
        try:
            result = await self.api_client.register_node(
                self.node_name,
                self.settings.hostname
            )
            if result.get('success'):
                logger.info(f"Registered with manager as '{self.node_name}'")
                return True
            else:
                logger.error(f"Registration failed: {result.get('message')}")
                return False
        except Exception as e:
            logger.error(f"Failed to register with manager: {e}")
            return False
    
    async def poll_vm_states(self) -> int:
        """
        Poll current VM states and detect changes.
        
        Returns:
            Number of state changes detected
        """
        try:
            # Get current VMs from Proxmox
            current_vms = await self.proxmox.get_all_vms(
                include_qemu=self.settings.polling.track_qemu,
                include_lxc=self.settings.polling.track_lxc
            )
        except Exception as e:
            logger.error(f"Failed to get VM states from Proxmox: {e}")
            return 0
        
        changes = 0
        current_vm_ids = set()
        
        for vm in current_vms:
            current_vm_ids.add(vm.vm_id)
            previous = self.previous_states.get(vm.vm_id)
            
            if previous is None:
                # New VM - if running, report start
                if vm.status == VMStatus.RUNNING:
                    logger.info(f"New VM {vm.vm_id} ({vm.name}) detected as running")
                    try:
                        await self.api_client.send_vm_start(
                            node=self.node_name,
                            vm_id=vm.vm_id,
                            vm_name=vm.name,
                            vm_type=vm.vm_type.value if hasattr(vm.vm_type, 'value') else str(vm.vm_type)
                        )
                        changes += 1
                    except Exception as e:
                        logger.error(f"Failed to report VM start: {e}")
            
            elif previous.status != vm.status:
                # Status changed
                if vm.status == VMStatus.RUNNING and previous.status != VMStatus.RUNNING:
                    # VM started
                    logger.info(f"VM {vm.vm_id} ({vm.name}) started")
                    try:
                        await self.api_client.send_vm_start(
                            node=self.node_name,
                            vm_id=vm.vm_id,
                            vm_name=vm.name,
                            vm_type=vm.vm_type.value if hasattr(vm.vm_type, 'value') else str(vm.vm_type)
                        )
                        changes += 1
                    except Exception as e:
                        logger.error(f"Failed to report VM start: {e}")
                
                elif vm.status == VMStatus.STOPPED and previous.status == VMStatus.RUNNING:
                    # VM stopped
                    logger.info(f"VM {vm.vm_id} ({vm.name}) stopped")
                    try:
                        await self.api_client.send_vm_stop(
                            node=self.node_name,
                            vm_id=vm.vm_id
                        )
                        changes += 1
                    except Exception as e:
                        logger.error(f"Failed to report VM stop: {e}")
            
            # Update previous state
            self.previous_states[vm.vm_id] = vm
        
        # Check for removed VMs (VMs that existed before but not anymore)
        removed_vms = set(self.previous_states.keys()) - current_vm_ids
        for vm_id in removed_vms:
            previous = self.previous_states[vm_id]
            if previous.status == VMStatus.RUNNING:
                # VM was running but is now gone (deleted?)
                logger.info(f"VM {vm_id} removed while running")
                try:
                    await self.api_client.send_vm_stop(
                        node=self.node_name,
                        vm_id=vm_id
                    )
                    changes += 1
                except Exception as e:
                    logger.error(f"Failed to report VM stop: {e}")
            del self.previous_states[vm_id]
        
        if changes > 0:
            self._save_state()
            logger.info(f"Detected {changes} state change(s)")
        
        return changes
    
    async def send_full_snapshot(self):
        """Send complete VM state snapshot to manager"""
        try:
            current_vms = await self.proxmox.get_all_vms(
                include_qemu=self.settings.polling.track_qemu,
                include_lxc=self.settings.polling.track_lxc
            )
            
            await self.api_client.send_vm_states(
                node=self.node_name,
                vms=current_vms
            )
            
            # Update local state
            for vm in current_vms:
                self.previous_states[vm.vm_id] = vm
            self._save_state()
            
            logger.info(f"Sent full snapshot: {len(current_vms)} VMs")
            
        except Exception as e:
            logger.error(f"Failed to send snapshot: {e}")
    
    async def run_once(self):
        """Run a single poll cycle"""
        self._load_state()
        
        # Test Proxmox connection
        logger.info("Testing Proxmox API connection...")
        if not await self.proxmox.test_connection():
            logger.error("Cannot connect to Proxmox API. Check credentials.")
            return
        
        # Get node name from Proxmox
        self.node_name = await self.proxmox.get_node_name()
        logger.info(f"Connected to Proxmox node: {self.node_name}")
        
        # Check manager connection
        if not await self.api_client.check_connection():
            logger.error(f"Cannot connect to manager at {self.settings.manager.url}")
            return
        
        # Register
        await self.register_with_manager()
        
        # Send full snapshot
        await self.send_full_snapshot()
        
        logger.info("Single run complete")
    
    async def run_daemon(self):
        """Run as a daemon, polling periodically"""
        self._load_state()
        self.running = True
        
        logger.info(f"Starting Proxmox Tracker Client")
        logger.info(f"Node: {self.settings.node_name}")
        logger.info(f"Manager: {self.settings.manager.url}")
        logger.info(f"Poll interval: {self.settings.polling.interval_seconds}s")
        
        # Test Proxmox connection
        logger.info("Testing Proxmox API connection...")
        if not await self.proxmox.test_connection():
            logger.error("Cannot connect to Proxmox API. Check credentials in config.")
            return
        
        # Get actual node name from Proxmox
        self.node_name = await self.proxmox.get_node_name()
        logger.info(f"Connected to Proxmox node: {self.node_name}")
        
        # Initial manager connection check
        if not await self.api_client.check_connection():
            logger.warning(f"Cannot connect to manager, will retry...")
        else:
            await self.register_with_manager()
            # Send initial full snapshot
            await self.send_full_snapshot()
        
        poll_count = 0
        
        while self.running:
            try:
                # Poll for state changes
                await self.poll_vm_states()
                
                # Send heartbeat and check for force sync
                hb_result = await self.api_client.heartbeat(self.node_name)
                
                # Handle force sync request
                if self.api_client.is_force_sync_pending():
                    logger.info("Processing force sync request...")
                    await self.send_full_snapshot()
                    self.api_client.clear_force_sync()
                
                poll_count += 1
                
                # Periodic full sync (every 100 polls ~ 50 minutes at 30s interval)
                if poll_count % 100 == 0:
                    logger.info("Sending periodic full sync...")
                    await self.send_full_snapshot()
                
            except Exception as e:
                logger.error(f"Poll error: {e}")
            
            # Wait for next poll
            await asyncio.sleep(self.settings.polling.interval_seconds)
        
        logger.info("Client stopped")
    
    def stop(self):
        """Stop the daemon"""
        self.running = False
        self._save_state()


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
        help='Run once and exit (send full snapshot)'
    )
    parser.add_argument(
        '--daemon', '-d',
        action='store_true',
        help='Run as daemon (default)'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Test Proxmox API connection only'
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
    if args.test:
        async def test():
            api = ProxmoxAPI(
                host=config.proxmox.host,
                port=config.proxmox.port,
                user=config.proxmox.user,
                token_name=config.proxmox.token_name,
                token_value=config.proxmox.token_value,
                verify_ssl=config.proxmox.verify_ssl
            )
            if await api.test_connection():
                print("✓ Proxmox API connection successful")
                node = await api.get_node_name()
                print(f"  Node: {node}")
                vms = await api.get_all_vms()
                print(f"  VMs found: {len(vms)}")
                for vm in vms:
                    print(f"    - {vm.vm_id}: {vm.name} ({vm.status.value})")
            else:
                print("✗ Failed to connect to Proxmox API")
                print("  Check host, port, and API token credentials")
        
        asyncio.run(test())
    elif args.once:
        asyncio.run(client.run_once())
    else:
        asyncio.run(client.run_daemon())


if __name__ == '__main__':
    main()
