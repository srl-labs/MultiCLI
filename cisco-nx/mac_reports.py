"""
CLI Plugin for Cisco-like show "mac" commands
Author: Miguel Redondo (Michel)
Email: miguel.redondo_ferrero@nokia.com

Provides the following commands:
- show mac address-table
- show mac address-table instance <instance_name>
- show mac address-table vlan <vlan_id>
- show mac address-table interface <interface_name>
- show mac address-table vni <vni_id>

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

from mac_address_table_report import MacAddressTableReport

class Plugin(CliPlugin):
    """NXOS-like mac address-table CLI plugin."""
    def load(self, cli: CliLoader, arguments: argparse.Namespace) -> None:
        mac = cli.show_mode.add_command(Syntax('mac', help='Show MAC commands'))

        # Add address-table command as a subcommand
        mac_address_table = mac.add_command(
            Syntax('address-table', help='Show MAC Address Table'),
            callback=self._show_mac_address_table,
            schema=MacAddressTableReport().get_schema_instance()
        )

        # Add 'instance' subcommand with network-instance completion
        mac_address_table_instance = mac_address_table.add_command(
            Syntax('instance', help='Display information for a specified network-instance')
            .add_unnamed_argument('name', suggestions=KeyCompleter('/network-instance[name=*]')),
            callback=self._show_mac_address_table_instance,
            update_location=False,
            schema=MacAddressTableReport().get_schema_instance()
        )

        # Add 'vlan-id' subcommand with vlans completion
        mac_address_table_vlanid = mac_address_table.add_command(
            Syntax('vlan', help='Display MAC address learned on a specified VLAN')
            .add_unnamed_argument('value', suggestions=MultipleKeyCompleters(keycompleters=[KeyCompleter(path="/interface[name=*]/subinterface[index=*]/vlan/encap/single-tagged-range/low-vlan-id[range-low-vlan-id=*]"), KeyCompleter(path="/interface[name=*]/subinterface[index=*]/vlan/encap/single-tagged/vlan-id:")])),
            callback=self._show_mac_address_table_vlanid,
            update_location=False,
            schema=MacAddressTableReport().get_schema_instance()
        )

        # Add 'interface' subcommand with interface completion
        mac_address_table_interface = mac_address_table.add_command(
            Syntax('interface', help='Display MAC table for a specified interface')
            .add_unnamed_argument('name', suggestions=MultipleKeyCompleters(keycompleters=[KeyCompleter(path="/interface[name=*]"), KeyCompleter(path="/interface[name=*]/subinterface[index=*]/name:")])),
            callback=self._show_mac_address_table_interface,
            update_location=False,
            schema=MacAddressTableReport().get_schema_instance()
        )

        # Add 'vni' subcommand with interface completion
        mac_address_table_vni = mac_address_table.add_command(
            Syntax('vni', help='Display MAC table for a specified vni')
            .add_unnamed_argument('value', suggestions=KeyCompleter(path="/tunnel-interface[name=*]/vxlan-interface[index=*]/ingress/vni:")),
            callback=self._show_mac_address_table_vni,
            update_location=False,
            schema=MacAddressTableReport().get_schema_instance()
        )

    def _show_mac_address_table(self, state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        MacAddressTableReport()._show_table_instance(state, output, arguments, **_kwargs)

    def _show_mac_address_table_instance(self, state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        MacAddressTableReport()._show_table_instance(state, output, arguments, **_kwargs)

    def _show_mac_address_table_vlanid(self, state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        MacAddressTableReport()._show_table_instance(state, output, arguments, **_kwargs)

    def _show_mac_address_table_interface(self, state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        MacAddressTableReport()._show_table_instance(state, output, arguments, **_kwargs)

    def _show_mac_address_table_vni(self, state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        MacAddressTableReport()._show_table_instance(state, output, arguments, **_kwargs)

