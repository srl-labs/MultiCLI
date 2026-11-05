"""
CLI Plugin for Cisco-style LLDP neighbors
Author: Shashi Sharma
Email: Shashi.Sharma@nokia.com
"""

from srlinux.mgmt.cli import CliPlugin
from srlinux.syntax import Syntax
from srlinux.location import build_path
from srlinux.data import Data, ColumnFormatter, Borders
from srlinux.schema import FixedSchemaRoot
from srlinux.schema.data_store import DataStore
import logging

logger = logging.getLogger("LLDPPlugin")


class Plugin(CliPlugin):
    def load(self, cli, **_kwargs):
        """Load the LLDP plugin and define the CLI command structure."""
        lldp_cmd = cli.show_mode.add_command(Syntax('lldp', help='LLDP info'))
        lldp_cmd.add_command(
            Syntax('neighbor', help='Show LLDP neighbors Cisco-style'),
            callback=self._show_lldp_neighbor,
            schema=self._get_schema(),
        )
        lldp_cmd.add_command(
            Syntax('neighbors', help='Show LLDP neighbors Cisco-style'),
            callback=self._show_lldp_neighbor,
            schema=self._get_schema(),
        )

    def _get_schema(self):
        """Define the schema for the LLDP neighbor data."""
        root = FixedSchemaRoot()
        root.add_child(
            'neighbors',
            keys=['Local_Intf', 'Port_ID'],
            fields=['Device_ID', 'Hold_time', 'Capability'],
        )
        return root

    def _show_lldp_neighbor(self, state, arguments, output, **_kwargs):
        """Handle the 'show lldp neighbor[s]' command."""
        if state.is_intermediate_command:
            return
        lldp_data = self._get_lldp_data(state)
        if not lldp_data:
            output.print_line("No LLDP neighbors found.")
            output.print_line("\n--------------------------------------")
            output.print_line("Try SR Linux command: show system lldp neighbor")
            return

        result = Data(arguments.schema)
        self._set_formatters(result)
        total = self._populate_data(result, lldp_data, state)
        output.print_line("Capability codes: (R) Router, (B) Bridge, (W) WLAN AP, (S) Switch, (O) Other")
        output.print_line("")
        if total > 0:
            output.print_data(result)
        else:
            output.print_line("No LLDP neighbors found.")
        output.print_line(f"\nTotal entries displayed: {total}")
        output.print_line("\n--------------------------------------")
        output.print_line("Try SR Linux command: show system lldp neighbor")

    def _get_lldp_data(self, state):
        """Fetch LLDP neighbor data from the system."""
        path = build_path('/system/lldp/interface[name=*]/neighbor[id=*]')
        try:
            return state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
        except Exception as e:
            logger.debug(f"Could not fetch LLDP data: {e}")
            return None

    def _get_hold_time(self, state):
        """Calculate the hold time, using defaults if configuration attributes are missing."""
        default_hold_time = 120
        config_path = build_path('/system/lldp')
        try:
            config = state.server.get_data_store(DataStore.State).get_data(config_path, recursive=False)
            lldp_node = config.system.get().lldp.get()
            hello_timer = getattr(lldp_node, 'hello_timer', None) or 30
            hold_multiplier = getattr(lldp_node, 'hold_multiplier', None) or 4
            return str(int(hello_timer) * int(hold_multiplier))
        except Exception:
            return str(default_hold_time)

    def _get_capability(self, neighbor):
        """Determine the capability code based on neighbor's capability child node."""
        if not hasattr(neighbor, 'capability') or not neighbor.capability:
            return 'R'
        try:
            for cap in neighbor.capability.items():
                if not getattr(cap, 'enabled', False):
                    continue
                cname = str(getattr(cap, 'name', '')).lower()
                if 'router' in cname:
                    return 'R'
                if 'bridge' in cname:
                    return 'B'
                if 'wlan' in cname:
                    return 'W'
        except Exception:
            pass
        return 'S'

    def _populate_data(self, data_root, lldp_data, state):
        """Populate the LLDP neighbor data into the output structure."""
        hold_time = self._get_hold_time(state)
        interfaces = lldp_data.get_descendants('/system/lldp/interface')
        total = 0

        for iface in interfaces:
            local_intf = getattr(iface, 'name', 'Unknown')
            if not hasattr(iface, 'neighbor'):
                continue

            for neighbor in iface.neighbor.items():
                device_id = getattr(neighbor, 'system_name', 'Unknown') or 'Unknown'
                capability = self._get_capability(neighbor)
                port_id = getattr(neighbor, 'port_id', 'Unknown') or 'Unknown'

                row = data_root.neighbors.create(local_intf, port_id)
                row.device_id = device_id
                row.hold_time = hold_time
                row.capability = capability
                total += 1

        return total

    def _set_formatters(self, data):
        """Set up the table formatting for Cisco-style output."""
        data.set_formatter(
            '/neighbors',
            ColumnFormatter(
                widths={
                    'Local_Intf': 15,
                    'Port_ID': 15,
                    'Device_ID': 18,
                    'Hold_time': 10,
                    'Capability': 11,
                },
                borders=Borders.Nothing,
            ),
        )
