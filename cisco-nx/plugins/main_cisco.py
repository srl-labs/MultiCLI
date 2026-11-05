#!/usr/bin/python
###########################################################################
# Description: MultiCLI Plugin for Cisco NX-OS Commands
# Contributors: Alperen Akpinar, Shashi Sharma, Miguel Redondo (Michel)
# Copyright (c) 2025-2026 Nokia
###########################################################################

import os
import sys

from srlinux.mgmt.cli import CliPlugin, KeyCompleter, MultipleKeyCompleters
from srlinux.mgmt.cli.lazy_loader_utils import wait_for_show_reports_load
from srlinux.schema.data_store import DataStore
from srlinux.syntax import Syntax


def _setup_module_paths(marker_file, subdirs):
    plugin_file = None
    try:
        frame_file = sys._getframe(1).f_code.co_filename
        if frame_file and not frame_file.startswith('<') and not frame_file.endswith('plugin_loader.py'):
            plugin_file = frame_file
    except Exception:
        plugin_file = None
    if not plugin_file:
        raw_file = globals().get('__file__')
        if raw_file and not str(raw_file).endswith('plugin_loader.py'):
            plugin_file = raw_file

    potential_paths = [os.path.expanduser('~/cli')]
    if plugin_file:
        cand = os.path.dirname(os.path.dirname(os.path.abspath(plugin_file)))
        if cand not in potential_paths:
            potential_paths.append(cand)
    if '/etc/opt/srlinux/cli' not in potential_paths:
        potential_paths.append('/etc/opt/srlinux/cli')

    for path in potential_paths:
        if os.path.exists(path) and (
            os.path.exists(os.path.join(path, 'system', marker_file)) or
            os.path.exists(os.path.join(path, marker_file))
        ):
            if path not in sys.path:
                sys.path.insert(0, path)
            for subdir in subdirs:
                sub_path = os.path.join(path, subdir)
                if os.path.exists(sub_path) and sub_path not in sys.path:
                    sys.path.insert(0, sub_path)
            break


_setup_module_paths('cisco_system_reports.py', ["ip", "mac", "interface", "system", "routing"])

from cisco_system_reports import CiscoSystemReports
from cisco_interface_reports import CiscoInterfaceReports
from cisco_lldp_reports import CiscoLldpReports
from cisco_routing_reports import CiscoRoutingReports
from ip_route_report import IpRouteReport
from ip_interface_report import IpInterfaceReport
try:
    from cisco_ip_bgp_report import IpBgpReport
except ImportError:
    from ip_bgp_report import IpBgpReport
from mac_address_table_report import MacAddressTableReport


class _StateStoreAdapter:
    def __init__(self, state):
        self._state = state

    @property
    def server_data_store(self):
        return self._state.server.get_data_store(DataStore.State)

    @property
    def data_store(self):
        return DataStore.State

    @property
    def root_schema(self):
        return self._state.get_root_schema(DataStore.State)

    def __getattr__(self, name):
        return getattr(self._state, name)


class Plugin(CliPlugin):

    @staticmethod
    def _enter_submode(state, arguments):
        if state.is_last_command:
            state.location = arguments

    @staticmethod
    def _should_register_show_mode(state, persona_name):
        aliases = {
            'arista': ('arista', 'eos'),
            'cisco': ('cisco', 'cisco-nx', 'ciscx', 'nxos'),
            'juniper': ('juniper', 'junos'),
            'nokia': ('nokia', 'sros', 'sr-os'),
        }
        valid_prefs = aliases.get(persona_name, (persona_name, persona_name.replace('-', '')))
        target_plugin = f'main_{persona_name.split("-")[0]}.py'

        user_cli = os.path.expanduser('~/cli')
        aaa_user = getattr(state, 'aaa_username', None)
        if aaa_user and aaa_user != 'root':
            alt_cli = os.path.expanduser(f'~{aaa_user}/cli')
            if os.path.exists(alt_cli):
                user_cli = alt_cli

        if os.path.abspath(user_cli) != '/etc/opt/srlinux/cli':
            user_cfg = os.path.join(user_cli, 'default_persona')
            if os.path.exists(user_cfg):
                try:
                    with open(user_cfg) as f:
                        pref = f.read().strip().lower()
                        if pref:
                            if pref in ('none', 'all'):
                                return False
                            return pref in valid_prefs
                except Exception:
                    pass
            user_plugins_dir = os.path.join(user_cli, 'plugins')
            if os.path.exists(user_plugins_dir):
                try:
                    user_plugins = [f for f in os.listdir(user_plugins_dir) if f.startswith('main_') and f.endswith('.py')]
                    if user_plugins:
                        return len(user_plugins) == 1 and target_plugin in user_plugins
                except Exception:
                    pass

        config_file = '/etc/opt/srlinux/cli/default_persona'
        if os.path.exists(config_file):
            try:
                with open(config_file) as f:
                    pref = f.read().strip().lower()
                    if pref:
                        if pref in ('none', 'all'):
                            return False
                        return pref in valid_prefs
            except Exception:
                pass

        plugins_dir = '/etc/opt/srlinux/cli/plugins'
        if os.path.exists(plugins_dir):
            try:
                installed_plugins = [f for f in os.listdir(plugins_dir) if f.startswith('main_') and f.endswith('.py')]
                if len(installed_plugins) == 1 and target_plugin in installed_plugins:
                    return True
            except Exception:
                pass
        return False

    def _get_child(self, parent, name):
        if hasattr(parent, 'get_command_or_none'):
            return parent.get_command_or_none(name)
        elif hasattr(parent, 'root'):
            return parent.root.get_command_or_none(name)
        return None

    def _default_container_help(self, state, output, arguments, **_kwargs):
        if not state.is_last_command:
            return
        from srlinux.mgmt.cli.help_formatter import CommandHelpFormatter
        children = arguments.node.get_filtered_commands(state)
        help_text = CommandHelpFormatter(
            arguments.node, children, output_width=output.screen_width,
            state=state, help_detail=False, partial_word=''
        ).format()
        output.print_line(help_text)

    def _add_or_override(self, parent, syntax, callback=None, schema=None, update_location=False):
        node = self._get_child(parent, syntax.name)
        if node:
            if callback:
                node.set_callback(callback)
            return node
        kwargs = {'update_location': update_location}
        kwargs['callback'] = callback if callback is not None else self._default_container_help
        if schema is not None:
            kwargs['schema'] = schema
        return parent.add_command(syntax, **kwargs)

    def _register_all_commands(self, target):
        # 1. System Commands: version, hostname, clock, inventory, environment
        self._add_or_override(target, Syntax('version', help='Show system version in Cisco NX-OS format'), callback=self._print_version, update_location=False)
        self._add_or_override(target, Syntax('hostname', help='Show system hostname'), callback=self._print_hostname, update_location=False)
        self._add_or_override(target, Syntax('clock', help='Show system clock in Cisco NX-OS format'), callback=self._print_clock, update_location=False)
        self._add_or_override(target, Syntax('inventory', help='Show system hardware inventory in Cisco NX-OS format'), callback=self._print_inventory, update_location=False)

        env_cmd = self._add_or_override(target, Syntax('environment', help='Show environment status in Cisco NX-OS format'), callback=self._print_environment_all, update_location=False)
        self._add_or_override(env_cmd, Syntax('cooling', help='Show cooling status'), callback=self._print_environment_cooling, update_location=False)
        self._add_or_override(env_cmd, Syntax('power', help='Show power supply status'), callback=self._print_environment_power, update_location=False)
        self._add_or_override(env_cmd, Syntax('temperature', help='Show temperature status'), callback=self._print_environment_temp, update_location=False)

        self._add_or_override(target, Syntax('module', help='Show module information in Cisco NX-OS format'), callback=self._print_module, update_location=False)
        proc_node = self._add_or_override(target, Syntax('processes', help='Show process information in Cisco NX-OS format'), update_location=False)
        self._add_or_override(proc_node, Syntax('cpu', help='Show process CPU utilization'), callback=self._print_processes_cpu, update_location=False)

        # 2. Interface Commands: show interface [name], brief, status, description, transceiver
        intf_syntax = Syntax('interface', help='Interface status and information')
        intf_syntax.add_unnamed_argument(
            'name',
            default='*',
            suggestions=MultipleKeyCompleters(keycompleters=[KeyCompleter(path="/interface[name=*]")])
        )
        intf_node = self._add_or_override(target, intf_syntax, callback=self._print_interface_detail, update_location=False)
        self._add_or_override(intf_node, Syntax('brief', help='Interface brief in Cisco NX-OS format'), callback=self._print_interface_brief, update_location=False)
        self._add_or_override(intf_node, Syntax('status', help='Interface status in Cisco NX-OS format'), callback=self._print_interface_status, update_location=False)
        self._add_or_override(intf_node, Syntax('description', help='Interface description in Cisco NX-OS format'), callback=self._print_interface_description, update_location=False)
        xcvr = self._add_or_override(intf_node, Syntax('transceiver', help='Transceiver details in Cisco NX-OS format'), callback=self._print_interface_transceiver, update_location=False)
        self._add_or_override(xcvr, Syntax('details', help='Transceiver details'), callback=self._print_interface_transceiver_details, update_location=False)

        # IPv6 Commands: show ipv6 interface brief
        ipv6_node = self._add_or_override(target, Syntax('ipv6', help='IPv6 protocol information'), update_location=False)
        ipv6_intf = self._add_or_override(ipv6_node, Syntax('interface', help='IPv6 interface information'), update_location=False)
        self._add_or_override(ipv6_intf, Syntax('brief', help='IPv6 interface brief in Cisco NX-OS format'), callback=self._print_ipv6_interface_brief, update_location=False)

        # Port-Channel Commands
        pc_node = self._add_or_override(target, Syntax('port-channel', help='Port-Channel information'), update_location=False)
        self._add_or_override(pc_node, Syntax('summary', help='Port-Channel summary in Cisco NX-OS format'), callback=self._print_port_channel_summary, update_location=False)

        # 3. LLDP Commands: show lldp neighbors
        lldp_node = self._add_or_override(target, Syntax('lldp', help='LLDP information'), update_location=False)
        lldp_neigh = self._add_or_override(lldp_node, Syntax('neighbors', help='LLDP neighbors in Cisco NX-OS format'), callback=self._print_lldp_neighbors, update_location=False)
        self._add_or_override(lldp_neigh, Syntax('detail', help='LLDP neighbors detail in Cisco NX-OS format'), callback=self._print_lldp_neighbors_detail, update_location=False)

        # 4. IP Commands: show ip route, show ip interface brief, show ip bgp, show ip arp, show ip ospf
        ip_node = self._add_or_override(target, Syntax('ip', help='IP protocol information'), update_location=False)

        ip_route = self._add_or_override(ip_node, Syntax('route', help='IP route information'), callback=self._print_ip_route, update_location=False)
        self._add_or_override(
            ip_route,
            Syntax('vrf').add_unnamed_argument('vrf_name', suggestions=KeyCompleter('/network-instance[name=*]')),
            callback=self._print_ip_route_vrf,
            update_location=False
        )

        ip_intf = self._add_or_override(ip_node, Syntax('interface', help='IP interface information'), update_location=False)
        self._add_or_override(ip_intf, Syntax('brief', help='IP interface status in Cisco NX-OS format'), callback=self._print_ip_interface_brief, update_location=False)

        ip_bgp = self._add_or_override(ip_node, Syntax('bgp', help='IP BGP information'), update_location=False)
        self._add_or_override(ip_bgp, Syntax('summary', help='BGP summary information'), callback=self._print_ip_bgp_summary, update_location=False)

        ip_bgp_vrf = self._add_or_override(ip_bgp, Syntax('vrf').add_unnamed_argument('vrf_name', suggestions=KeyCompleter('/network-instance[name=*]')), update_location=False)
        self._add_or_override(ip_bgp_vrf, Syntax('summary', help='BGP summary for VRF'), callback=self._print_ip_bgp_vrf_summary, update_location=False)

        self._add_or_override(ip_node, Syntax('arp', help='IP ARP table in Cisco NX-OS format'), callback=self._print_ip_arp, update_location=False)

        ip_ospf = self._add_or_override(ip_node, Syntax('ospf', help='IP OSPF information'), update_location=False)
        self._add_or_override(ip_ospf, Syntax('neighbor', help='OSPF neighbors in Cisco NX-OS format'), callback=self._print_ospf_neighbor, update_location=False)
        ospf_intf = self._add_or_override(ip_ospf, Syntax('interface', help='OSPF interface information'), update_location=False)
        self._add_or_override(ospf_intf, Syntax('brief', help='OSPF interface brief in Cisco NX-OS format'), callback=self._print_ip_ospf_interface_brief, update_location=False)

        # 5. MAC Address Table
        mac_node = self._add_or_override(target, Syntax('mac', help='Show MAC commands'), update_location=False)
        mac_address_table = self._add_or_override(
            mac_node,
            Syntax('address-table', help='Show MAC Address Table in Cisco NX-OS format'),
            callback=self._print_mac_address_table,
            schema=MacAddressTableReport().get_schema_instance(),
            update_location=False
        )
        self._add_or_override(
            mac_address_table,
            Syntax('instance', help='Display information for a specified network-instance')
            .add_unnamed_argument('name', suggestions=KeyCompleter('/network-instance[name=*]')),
            callback=self._print_mac_address_table,
            update_location=False,
            schema=MacAddressTableReport().get_schema_instance()
        )
        self._add_or_override(
            mac_address_table,
            Syntax('vlan', help='Display MAC address learned on a specified VLAN')
            .add_unnamed_argument('value', suggestions=MultipleKeyCompleters(keycompleters=[KeyCompleter(path="/interface[name=*]/subinterface[index=*]/vlan/encap/single-tagged-range/low-vlan-id[range-low-vlan-id=*]"), KeyCompleter(path="/interface[name=*]/subinterface[index=*]/vlan/encap/single-tagged/vlan-id:")])),
            callback=self._print_mac_address_table,
            update_location=False,
            schema=MacAddressTableReport().get_schema_instance()
        )
        self._add_or_override(
            mac_address_table,
            Syntax('interface', help='Display MAC table for a specified interface')
            .add_unnamed_argument('name', suggestions=MultipleKeyCompleters(keycompleters=[KeyCompleter(path="/interface[name=*]"), KeyCompleter(path="/interface[name=*]/subinterface[index=*]/name:")])),
            callback=self._print_mac_address_table,
            update_location=False,
            schema=MacAddressTableReport().get_schema_instance()
        )
        self._add_or_override(
            mac_address_table,
            Syntax('vni', help='Display MAC table for a specified vni')
            .add_unnamed_argument('value', suggestions=KeyCompleter(path="/tunnel-interface[name=*]/vxlan-interface[index=*]/ingress/vni:")),
            callback=self._print_mac_address_table,
            update_location=False,
            schema=MacAddressTableReport().get_schema_instance()
        )

        # 6. Routing / Network Instance: vrf, vlan, bfd, nve, vpc
        self._add_or_override(target, Syntax('vrf', help='VRF information in Cisco NX-OS format'), callback=self._print_vrf, update_location=False)
        self._add_or_override(target, Syntax('vlan', help='VLAN information in Cisco NX-OS format'), callback=self._print_vlan, update_location=False)

        bfd_node = self._add_or_override(target, Syntax('bfd', help='BFD information'), update_location=False)
        self._add_or_override(bfd_node, Syntax('neighbors', help='BFD neighbors in Cisco NX-OS format'), callback=self._print_bfd_neighbors, update_location=False)

        nve_node = self._add_or_override(target, Syntax('nve', help='NVE information in Cisco NX-OS format'), update_location=False)
        self._add_or_override(nve_node, Syntax('vni', help='NVE VNI status in Cisco NX-OS format'), callback=self._print_nve_vni, update_location=False)
        self._add_or_override(nve_node, Syntax('peers', help='NVE peers in Cisco NX-OS format'), callback=self._print_nve_peers, update_location=False)

        self._add_or_override(target, Syntax('vpc', help='vPC information in Cisco NX-OS format'), callback=self._print_vpc, update_location=False)

    def _register_srl_escape_hatch(self, cli):
        try:
            if hasattr(cli, 'running_mode') and cli.running_mode.has_global_command('srl'):
                srl_node = cli.get_global_command('srl')
            else:
                srl_node = cli.add_global_command(
                    Syntax('srl', help='Native SR Linux operational mode and commands'),
                    update_location=self._enter_submode
                )
        except Exception:
            srl_node = cli.get_global_command('srl')

        def _srl_show_loc(state, _arguments):
            state.register_cleanup_routine(lambda st, _out: setattr(st, 'location', st.start_location))

        srl_show = self._add_or_override(
            srl_node,
            Syntax('show', help='Native SR Linux show reports'),
            update_location=_srl_show_loc
        )
        if self._get_child(srl_show, 'version') is not None:
            return

        from srlinux import strings
        from srlinux.mgmt.cli import ExecuteError

        try:
            from srlinux.mgmt.cli.plugins.reports.version import Plugin as SrlVersionPlugin
            ver_plugin = SrlVersionPlugin()

            def _srl_version(state, output, arguments, **kw):
                if not state.is_last_command:
                    return
                ver_plugin._print(_StateStoreAdapter(state), output, arguments, **kw)

            self._add_or_override(
                srl_show,
                Syntax('version', help='Show basic information of the system'),
                callback=_srl_version,
                schema=ver_plugin._get_schema(),
                update_location=False
            )
        except Exception:
            pass

        try:
            from srlinux.mgmt.cli.plugins.reports.interface_summary_report import InterfaceSummary
            from srlinux.mgmt.cli.plugins.reports.interface_brief_report import InterfaceBrief
            from srlinux.mgmt.cli.plugins.reports.interface_detail_report import InterfaceDetail

            def _validate_intf(arguments):
                ifname = arguments.get('interface', 'name')
                _, subidx = strings.extract_interface_name_subinterface_index(ifname)
                if subidx is not None:
                    raise ExecuteError('Subinterface is allowed only in summary or detail options')

            def _srl_intf_summary(state, arguments, output, **kw):
                if not state.is_last_command:
                    return
                InterfaceSummary().print_summary(_StateStoreAdapter(state), arguments, output, **kw)

            def _srl_intf_all(state, arguments, output, **kw):
                if not state.is_last_command:
                    return
                _validate_intf(arguments)
                InterfaceSummary().print_all(_StateStoreAdapter(state), arguments, output, **kw)

            def _srl_intf_brief(state, arguments, output, **kw):
                if not state.is_last_command:
                    return
                _validate_intf(arguments)
                InterfaceBrief().print(_StateStoreAdapter(state), arguments, output, **kw)

            def _srl_intf_detail(state, arguments, output, **kw):
                if not state.is_last_command:
                    return
                InterfaceDetail().print(_StateStoreAdapter(state), arguments, output, **kw)

            intf_node = self._add_or_override(
                srl_show,
                InterfaceSummary().get_syntax(),
                callback=_srl_intf_summary,
                schema=InterfaceSummary().get_data_schema(),
                update_location=True
            )
            self._add_or_override(
                intf_node,
                InterfaceSummary().get_syntax_all(),
                callback=_srl_intf_all,
                schema=InterfaceSummary().get_data_schema(),
                update_location=False
            )
            self._add_or_override(
                intf_node,
                InterfaceBrief().get_syntax(),
                callback=_srl_intf_brief,
                schema=InterfaceBrief().get_data_schema(),
                update_location=False
            )
            self._add_or_override(
                intf_node,
                InterfaceDetail().get_syntax(),
                callback=_srl_intf_detail,
                schema=InterfaceDetail().get_data_schema(),
                update_location=False
            )
        except Exception:
            pass

        try:
            from srlinux.mgmt.cli.plugins.reports.lag_summary_report import LagSummary
            from srlinux.mgmt.cli.plugins.reports.lag_brief_report import LagBrief
            from srlinux.mgmt.cli.plugins.reports.lag_detail_report import LagInterfaceDetail
            from srlinux.mgmt.cli.plugins.reports.lag_lacp_state import LagLacpState
            from srlinux.mgmt.cli.plugins.reports.lag_lacp_stats import LagLacpStats
            from srlinux.mgmt.cli.plugins.reports.lag_member_stats import LagMemberStats

            def _validate_lag(state, arguments):
                if not state.system_features.lag:
                    raise ExecuteError('LAG not supported')
                ifname = arguments.get('lag', 'name')
                if not ifname.startswith('lag') and ifname != '*':
                    raise ExecuteError(f'Failed to parse value {ifname} for Lag interface ')

            def _srl_lag_summary(state, arguments, output, **kw):
                if not state.is_last_command:
                    return
                _validate_lag(state, arguments)
                LagSummary().print_summary(_StateStoreAdapter(state), arguments, output, **kw)

            def _srl_lag_brief(state, arguments, output, **kw):
                if not state.is_last_command:
                    return
                _validate_lag(state, arguments)
                LagBrief().print(_StateStoreAdapter(state), arguments, output, **kw)

            def _srl_lag_detail(state, arguments, output, **kw):
                if not state.is_last_command:
                    return
                _validate_lag(state, arguments)
                LagInterfaceDetail().print(_StateStoreAdapter(state), arguments, output, **kw)

            def _srl_lag_lacp_state(state, arguments, output, **kw):
                if not state.is_last_command:
                    return
                _validate_lag(state, arguments)
                LagLacpState().print(_StateStoreAdapter(state), arguments, output, **kw)

            def _srl_lag_lacp_stats(state, arguments, output, **kw):
                if not state.is_last_command:
                    return
                _validate_lag(state, arguments)
                LagLacpStats().print(_StateStoreAdapter(state), arguments, output, **kw)

            def _srl_lag_member_stats(state, arguments, output, **kw):
                if not state.is_last_command:
                    return
                _validate_lag(state, arguments)
                LagMemberStats().print(_StateStoreAdapter(state), arguments, output, **kw)

            lag_node = self._add_or_override(
                srl_show,
                LagSummary().get_syntax(),
                callback=_srl_lag_summary,
                schema=LagSummary().get_data_schema(),
                update_location=True
            )
            self._add_or_override(
                lag_node,
                LagBrief().get_syntax(),
                callback=_srl_lag_brief,
                schema=LagBrief().get_data_schema(),
                update_location=False
            )
            self._add_or_override(
                lag_node,
                LagInterfaceDetail().get_syntax(),
                callback=_srl_lag_detail,
                schema=LagInterfaceDetail().get_data_schema(),
                update_location=False
            )
            self._add_or_override(
                lag_node,
                LagLacpState().get_syntax(),
                callback=_srl_lag_lacp_state,
                schema=LagLacpState().get_data_schema(),
                update_location=False
            )
            self._add_or_override(
                lag_node,
                LagLacpStats().get_syntax(),
                callback=_srl_lag_lacp_stats,
                schema=LagLacpStats().get_data_schema(),
                update_location=False
            )
            self._add_or_override(
                lag_node,
                LagMemberStats().get_syntax(),
                callback=_srl_lag_member_stats,
                schema=LagMemberStats().get_data_schema(),
                update_location=False
            )
        except Exception:
            pass

        try:
            from srlinux.mgmt.cli.plugins.reports.system_lldp_reports import Plugin as SrlLldpPlugin
            lldp_plugin = SrlLldpPlugin()

            def _srl_lldp_neighbor(state, arguments, output, **kw):
                if not state.is_last_command:
                    return
                lldp_plugin.print(_StateStoreAdapter(state), arguments, output, **kw)

            sys_node = self._add_or_override(
                srl_show,
                Syntax('system', help='Show system reports'),
                update_location=False
            )
            lldp_node = self._add_or_override(
                sys_node,
                lldp_plugin.get_lldp_syntax(),
                update_location=False
            )
            self._add_or_override(
                lldp_node,
                lldp_plugin.get_lldp_neighbor_syntax(),
                callback=_srl_lldp_neighbor,
                schema=lldp_plugin.get_schema(),
                update_location=False
            )
        except Exception:
            pass

    def load(self, cli, **_kwargs):
        self._cli = cli
        # 1. Root global command 'nxos' for interactive submode and one-liners
        try:
            if hasattr(cli, 'running_mode') and cli.running_mode.has_global_command('nxos'):
                nxos_node = cli.get_global_command('nxos')
            else:
                nxos_node = cli.add_global_command(
                    Syntax('nxos', help='Cisco NX-OS operational mode and commands'),
                    update_location=self._enter_submode
                )
        except Exception:
            nxos_node = cli.get_global_command('nxos')
        nx_show = self._add_or_override(
            nxos_node,
            Syntax('show', help='Cisco NX-OS show reports'),
            update_location=False
        )
        self._register_all_commands(nx_show)
        self._register_srl_escape_hatch(cli)

    def on_start(self, state):
        if not self._should_register_show_mode(state, 'cisco'):
            return
        # 2. Register to show_mode for persona compatibility (e.g. cnxuser)
        wait_for_show_reports_load(state)
        self._register_all_commands(state.command_tree.show_mode)

    # Callbacks
    def _print_interface_detail(self, state, output, arguments=None, **_kwargs):
        if not state.is_last_command:
            return
        CiscoInterfaceReports().show_interface_detail(state, output, arguments=arguments)

    def _print_version(self, state, output, **_kwargs):
        CiscoSystemReports().show_version(state, output)

    def _print_hostname(self, state, output, **_kwargs):
        CiscoSystemReports().show_hostname(state, output)

    def _print_clock(self, state, output, **_kwargs):
        CiscoSystemReports().show_clock(state, output)

    def _print_inventory(self, state, output, **_kwargs):
        CiscoSystemReports().show_inventory(state, output)

    def _print_environment_all(self, state, output, **_kwargs):
        if not state.is_last_command:
            return
        CiscoSystemReports().show_environment(state, output, 'all')

    def _print_environment_cooling(self, state, output, **_kwargs):
        CiscoSystemReports().show_environment(state, output, 'cooling')

    def _print_environment_power(self, state, output, **_kwargs):
        CiscoSystemReports().show_environment(state, output, 'power')

    def _print_environment_temp(self, state, output, **_kwargs):
        CiscoSystemReports().show_environment(state, output, 'temperature')

    def _print_interface_brief(self, state, output, **_kwargs):
        CiscoInterfaceReports().show_interface_brief(state, output)

    def _print_interface_status(self, state, output, **_kwargs):
        CiscoInterfaceReports().show_interface_status(state, output)

    def _print_interface_description(self, state, output, **_kwargs):
        CiscoInterfaceReports().show_interface_description(state, output)

    def _print_port_channel_summary(self, state, output, **_kwargs):
        CiscoInterfaceReports().show_port_channel_summary(state, output)

    def _print_lldp_neighbors(self, state, output, **_kwargs):
        if not state.is_last_command:
            return
        CiscoLldpReports().show_lldp_neighbors(state, output, detail=False)

    def _print_lldp_neighbors_detail(self, state, output, **_kwargs):
        CiscoLldpReports().show_lldp_neighbors(state, output, detail=True)

    def _print_ip_route(self, state, output, **_kwargs):
        if not state.is_last_command:
            return
        IpRouteReport()._show_routes(state, output, network_instance='default')
        output.print_line('\nTry SR Linux command: show network-instance default route-table ipv4-unicast summary')

    def _extract_vrf_arg(self, state, arguments):
        for src in (arguments, getattr(state, 'line_commands', None)):
            if not src or not hasattr(src, 'has_node'):
                continue
            try:
                if src.has_node('vrf'):
                    val = src.get_value_or('vrf', 'vrf_name', 'default')
                    if val:
                        return val
            except Exception:
                pass
        return 'default'

    def _print_ip_route_vrf(self, state, arguments, output, **_kwargs):
        vrf_name = self._extract_vrf_arg(state, arguments)
        IpRouteReport()._show_routes(state, output, network_instance=vrf_name)
        output.print_line(f'\nTry SR Linux command: show network-instance {vrf_name} route-table ipv4-unicast summary')

    def _print_ip_interface_brief(self, state, output, **_kwargs):
        IpInterfaceReport().show_ip_interface_brief(state, output, vrf='default')

    def _print_ip_bgp_summary(self, state, output, **_kwargs):
        IpBgpReport().show_bgp_summary(state, output, network_instance='default')
        output.print_line('\nTry SR Linux command: show network-instance default protocols bgp neighbor')

    def _print_ip_bgp_vrf_summary(self, state, arguments, output, **_kwargs):
        vrf_name = self._extract_vrf_arg(state, arguments)
        IpBgpReport().show_bgp_summary(state, output, network_instance=vrf_name)
        output.print_line(f'\nTry SR Linux command: show network-instance {vrf_name} protocols bgp neighbor')

    def _print_ip_arp(self, state, output, **_kwargs):
        CiscoRoutingReports().show_ip_arp(state, output)

    def _print_ospf_neighbor(self, state, output, **_kwargs):
        CiscoRoutingReports().show_ip_ospf_neighbor(state, output)

    def _print_mac_address_table(self, state, arguments, output, **kwargs):
        if not state.is_last_command:
            return
        MacAddressTableReport()._show_table_instance(state, output, arguments, **kwargs)

    def _print_vrf(self, state, output, **_kwargs):
        CiscoRoutingReports().show_vrf(state, output)

    def _print_vlan(self, state, output, **_kwargs):
        CiscoRoutingReports().show_vlan(state, output)

    def _print_bfd_neighbors(self, state, output, **_kwargs):
        CiscoRoutingReports().show_bfd_neighbors(state, output)

    def _print_module(self, state, output, **_kwargs):
        CiscoSystemReports().show_module(state, output)

    def _print_processes_cpu(self, state, output, **_kwargs):
        CiscoSystemReports().show_processes_cpu(state, output)

    def _print_interface_transceiver(self, state, output, **_kwargs):
        if not state.is_last_command:
            return
        CiscoInterfaceReports().show_interface_transceiver(state, output, details=False)

    def _print_interface_transceiver_details(self, state, output, **_kwargs):
        CiscoInterfaceReports().show_interface_transceiver(state, output, details=True)

    def _print_ipv6_interface_brief(self, state, output, **_kwargs):
        CiscoInterfaceReports().show_ipv6_interface_brief(state, output)

    def _print_ip_ospf_interface_brief(self, state, output, **_kwargs):
        CiscoRoutingReports().show_ip_ospf_interface_brief(state, output)

    def _print_nve_vni(self, state, output, **_kwargs):
        CiscoRoutingReports().show_nve_vni(state, output)

    def _print_nve_peers(self, state, output, **_kwargs):
        CiscoRoutingReports().show_nve_peers(state, output)

    def _print_vpc(self, state, output, **_kwargs):
        CiscoRoutingReports().show_vpc(state, output)
