"""
CLI Plugin for Junos-like show "ethernet-switching" commands
Author: Miguel Redondo (Michel)
Email: miguel.redondo_ferrero@nokia.com

Provides the following commands:
- show ethernet-switching table
- show ethernet-switching table instance <instance_name>
- show ethernet-switching table vlan <vlan_id>
- show ethernet-switching table interface <interface_name>

"""
from srlinux.mgmt.cli import CliPlugin, ExecuteError, KeyCompleter, MultipleKeyCompleters
from srlinux.syntax import Syntax
from srlinux.schema import FixedSchemaRoot
from srlinux.mgmt.cli.cli_loader import CliLoader

import sys
import os
import argparse

# Try potential base directories
potential_paths = [
    os.path.expanduser('~/cli'),
    '/etc/opt/srlinux/cli'
]

# Find the first valid path
import_base = None
for path in potential_paths:
    if os.path.exists(path):
        import_base = path
        break

if import_base is None:
    raise ImportError("Could not find a valid CLI plugin base directory")

# Construct the import path
import_path = os.path.join(import_base, "plugins")

# Add to Python path if not already present
if import_path not in sys.path:
    sys.path.insert(0, import_path)

from ethernet_switching_table_report import EthernetSwitchingReport 

class Plugin(CliPlugin):
    """Junos-like ethernet-switching CLI plugin."""
    def load(self, cli: CliLoader, arguments: argparse.Namespace) -> None:
        ethernet_switching = cli.show_mode.add_command(Syntax('ethernet-switching', help='Show ethernet switching information'))
        
        # Add table command as a subcommand
        ethernet_switching_table = ethernet_switching.add_command(
            Syntax('table', help='Show media access control table'),
            callback=self._show_ethernet_switching_table,
            schema=EthernetSwitchingReport().get_schema_instance()
        )

        # Add 'table' subcommand with network-instance completion
        ethernet_switching_table_instance = ethernet_switching_table.add_command(
            Syntax('instance', help='Display information for a specified network-instance')
            .add_unnamed_argument('name', suggestions=KeyCompleter('/network-instance[name=*]')),
            callback=self._show_ethernet_switching_table_instance,
            update_location=False,
            schema=EthernetSwitchingReport().get_schema_instance()
        )
        
        # Add 'vlan-id' subcommand with vlans completion
        ethernet_switching_table_vlanid = ethernet_switching_table.add_command(
            Syntax('vlan', help='Display MAC address learned on a specified VLAN')
            .add_unnamed_argument('value', suggestions=MultipleKeyCompleters(keycompleters=[KeyCompleter(path="/interface[name=*]/subinterface[index=*]/vlan/encap/single-tagged-range/low-vlan-id[range-low-vlan-id=*]"), KeyCompleter(path="/interface[name=*]/subinterface[index=*]/vlan/encap/single-tagged/vlan-id:")])),
            callback=self._show_ethernet_switching_table_vlanid,
            update_location=False,
            schema=EthernetSwitchingReport().get_schema_instance()
        )

        # Add 'interface' subcommand with interface completion
        ethernet_switching_table_interface = ethernet_switching_table.add_command(
            Syntax('interface', help='Display MAC table for a specified interface')
            .add_unnamed_argument('name', suggestions=MultipleKeyCompleters(keycompleters=[KeyCompleter(path="/interface[name=*]"), KeyCompleter(path="/interface[name=*]/subinterface[index=*]/name:")])),
            callback=self._show_ethernet_switching_table_interface,
            update_location=False,
            schema=EthernetSwitchingReport().get_schema_instance()
        )
    
    def _show_ethernet_switching_table(self, state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        EthernetSwitchingReport()._show_table_instance(state, output, arguments, **_kwargs)

    def _show_ethernet_switching_table_instance(self, state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        EthernetSwitchingReport()._show_table_instance(state, output, arguments, **_kwargs)

    def _show_ethernet_switching_table_vlanid(self, state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        EthernetSwitchingReport()._show_table_instance(state, output, arguments, **_kwargs)
    
    def _show_ethernet_switching_table_interface(self, state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        EthernetSwitchingReport()._show_table_instance(state, output, arguments, **_kwargs)

