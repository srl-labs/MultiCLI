import os
import sys

from srlinux.location import build_path
from srlinux.mgmt.cli import CliPlugin, KeyCompleter
from srlinux.mgmt.cli.execute_error import ExecuteError
from srlinux.schema.data_store import DataStore
from srlinux.syntax import Syntax

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
import_path = os.path.join(import_base, "evpn")

# Add to Python path if not already present
if import_path not in sys.path:
    sys.path.insert(0, import_path)

from evpn_report import EvpnDestinationReport


class Plugin(CliPlugin):
    def load(self, cli, **kwargs):
        # root command: `/show service`
        syntax = Syntax(
            name="service",
            short_help="SROS MultiCLI service commands",
            help="SROS compability commands for services on SRLinux (project MultiCLI)",
        )

        service = cli.show_mode.add_command(
            syntax
        )

        # subcommand: `/show service id <network-instance>`
        service_id_syntax = Syntax(
            name="id",
            short_help="Service ID",
            help="ID of the network-instance",
        )

        service_id_syntax.add_unnamed_argument(
            'name', 
            default='*', 
            suggestions=KeyCompleter(
                path="/network-instance[name=*]"
            )
        )

        service_id = service.add_command(
            service_id_syntax
        )

        # service_id subcommands:
        service_id.add_command(
            Syntax(
                name="evpn-mpls",
                short_help="EVPN MPLS destinations",
                help="Information about EVPN MPLS tunnel destinations for a particular service",
            ),
            update_location=False,
            callback=self._evpn_mpls,
            schema=EvpnDestinationReport().get_schema()
        )

        vxlan = service_id.add_command(
            Syntax(
                name="vxlan",
                short_help="VxLAN commands",
                help="Various show commands for VxLAN-enabled services",
            )
        )

        vxlan.add_command(
            Syntax(
                name="destinations",
                short_help="EVPN VxLAN destinations",
                help="Information about EVPN VXLAN tunnel destinations for a particular service",
            ),
            update_location=False,
            callback=self._evpn_vxlan,
            schema=EvpnDestinationReport().get_schema()
        )
    
    def _evpn_mpls(self, state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        self._validate_network_instance(state, arguments)
        EvpnDestinationReport().print_mpls(state, arguments, output, **_kwargs)
    
    def _evpn_vxlan(self, state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        self._validate_network_instance(state, arguments)
        EvpnDestinationReport().print_vxlan(state, arguments, output, **_kwargs)
    
    def _validate_network_instance(self, state, arguments):
        nw_name = arguments.get('id', 'name')
        if '*' in nw_name:
            return
        path = build_path('/network-instance[name={name}]/type', name=nw_name)
        server_data = state.server.get_data_store(DataStore.State).get_data(path, recursive=False)
        for nw in server_data.network_instance.items():
            if not any(t in str(nw.type) for t in ('mac-vrf', 'ip-vrf')):
                raise ExecuteError('service command available for mac-vrf and ip-vrf only')
