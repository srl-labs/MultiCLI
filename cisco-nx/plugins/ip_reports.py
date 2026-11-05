"""
CLI Plugin for Cisco-style IP Commands
Author: Alperen Akpinar
Email: alperen.akpinar@nokia.com
"""
from srlinux.mgmt.cli import CliPlugin, ExecuteError, KeyCompleter 
from srlinux.syntax import Syntax
import sys
import os

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
import_path = os.path.join(import_base, "ip")

# Add to Python path if not already present
if import_path not in sys.path:
    sys.path.insert(0, import_path)

from ip_route_report import IpRouteReport
from ip_interface_report import IpInterfaceReport
from ip_bgp_report import IpBgpReport

class Plugin(CliPlugin):
    """Cisco-style IP CLI plugin."""
    def load(self, cli, **_kwargs):
        # Create top-level ip command
        ip_cmd = cli.show_mode.add_command(Syntax('ip'))
        
        # Add route command
        route_cmd = ip_cmd.add_command(
            Syntax('route'),
            callback=self._show_ip_route
        )

        # Add 'vrf' subcommand with network-instance completion for route
        route_cmd.add_command(
            Syntax('vrf')
            .add_unnamed_argument('vrf_name', suggestions=KeyCompleter('/network-instance[name=*]')),
            callback=self._show_vrf_route,
            update_location=False
        )

        # Add interface command
        interface_cmd = ip_cmd.add_command(
            Syntax('interface')
        )

        # Add interface brief subcommand
        interface_cmd.add_command(
            Syntax('brief', help='IP interface status and configuration'),
            callback=self._show_ip_interface_brief,
            update_location=False
        )

        # Add BGP commands
        bgp_cmd = ip_cmd.add_command(Syntax('bgp'))
        
        # Add BGP summary command
        bgp_cmd.add_command(
            Syntax('summary', help='BGP summary information'),
            callback=self._show_ip_bgp_summary,
            update_location=False
        )

        # Add BGP VRF command
        bgp_vrf_cmd = bgp_cmd.add_command(
            Syntax('vrf')
            .add_unnamed_argument('vrf_name', suggestions=KeyCompleter('/network-instance[name=*]'))
        )
        
        # Add summary command under VRF
        bgp_vrf_cmd.add_command(
            Syntax('summary', help='BGP summary for VRF'),
            callback=self._show_ip_bgp_vrf_summary,
            update_location=False
        )

    def _show_ip_route(self, state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        IpRouteReport()._show_routes(state, output, network_instance='default')
        output.print_line('\nTry SR Linux command: show network-instance default route-table ipv4-unicast summary')
    def _show_vrf_route(self, state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        network_instance = arguments.get('vrf_name')
        IpRouteReport()._show_routes(state, output, network_instance=network_instance)
        output.print_line(f'\nTry SR Linux command: show network-instance {network_instance} route-table ipv4-unicast summary')

    def _show_ip_interface_brief(self, state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        IpInterfaceReport().show_interfaces_brief(state, output)
        output.print_line(f'\nTry SR Linux command: show interface brief')

    def _show_ip_bgp_summary(self, state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        IpBgpReport().show_bgp_summary(state, output, network_instance='default')
        output.print_line(f'\nTry SR Linux command: show network-instance default protocols bgp neighbor')

    def _show_ip_bgp_vrf_summary(self, state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        try:
            # The vrf_name is in the parent command group
            # Use the same pattern as netinst_summary_report.py
            network_instance = arguments.get('vrf', 'vrf_name')
            if not network_instance:
                network_instance = 'default'
            IpBgpReport().show_bgp_summary(state, output, network_instance=network_instance)
            output.print_line(f'\nTry SR Linux command: show network-instance {network_instance} protocols bgp neighbor')
        except Exception:
            # Silent error handling - don't print error messages for missing VRFs or no BGP config
            pass