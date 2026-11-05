#!/usr/bin/python
###########################################################################
# Description: MultiCLI Plugin for Nokia SR OS Commands
# Contributors: Giancarlo Garcia, Zeno Dhaene
# Copyright (c) 2025-2026 Nokia
###########################################################################

import os
import sys

from srlinux.mgmt.cli import CliPlugin, KeyCompleter
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


_setup_module_paths('sros_system_reports.py', ['system', 'interface', 'routing', 'service', 'bgp', 'evpn'])

from sros_system_reports import SrosSystemReports
from sros_interface_reports import SrosInterfaceReports
from sros_routing_reports import SrosRoutingReports
from sros_service_reports import SrosServiceReports
from sros_bgpsummary import BgpSummaryFilter
from evpn_report import EvpnDestinationReport


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
        # 1. System Reports
        self._add_or_override(
            target,
            Syntax('version', help='Show system version in Nokia SR OS format'),
            callback=self._print_version,
            update_location=False
        )

        sys_cmd = self._add_or_override(
            target,
            Syntax('system', help='Show system information in Nokia SR OS format'),
            update_location=False
        )
        self._add_or_override(
            sys_cmd,
            Syntax('information', help='Show system information'),
            callback=self._print_system_information,
            update_location=False
        )

        sys_lldp = self._add_or_override(
            sys_cmd,
            Syntax('lldp', help='Show LLDP information'),
            update_location=False
        )
        self._add_or_override(
            sys_lldp,
            Syntax('neighbor', help='Show LLDP neighbors in Nokia SR OS format'),
            callback=self._print_lldp_neighbor,
            update_location=False
        )

        self._add_or_override(
            target,
            Syntax('chassis', help='Show chassis information in Nokia SR OS format'),
            callback=self._print_chassis,
            update_location=False
        )

        # 2. Port & LAG Reports
        port_syntax = Syntax('port', help='Show port status in Nokia SR OS format')
        port_syntax.add_unnamed_argument(
            'port_id', default='*', suggestions=KeyCompleter(path="/interface[name=*]")
        )
        port_cmd = self._add_or_override(
            target,
            port_syntax,
            callback=self._print_port,
            update_location=False
        )
        self._add_or_override(
            port_cmd,
            Syntax('description', help='Show port descriptions in Nokia SR OS format'),
            callback=self._print_port_description,
            update_location=False
        )

        lag_syntax = Syntax('lag', help='Show LAG information in Nokia SR OS format')
        lag_syntax.add_unnamed_argument('name', default='lag*', help='LAG ID')
        self._add_or_override(
            target,
            lag_syntax,
            callback=self._print_lag,
            update_location=False
        )

        # 3. Router Reports
        router_syntax = Syntax('router', help='Show router reports in Nokia SR OS format')
        router_syntax.add_unnamed_argument(
            'netinst', default='default', help='Network instance name', suggestions=KeyCompleter('/network-instance[name=*]')
        )
        router_cmd = self._add_or_override(
            target,
            router_syntax,
            update_location=False
        )

        self._add_or_override(
            router_cmd,
            Syntax('route-table', help='Show route table in Nokia SR OS format'),
            callback=self._print_route_table,
            update_location=False
        )
        self._add_or_override(
            router_cmd,
            Syntax('interface', help='Show router interface in Nokia SR OS format'),
            callback=self._print_router_interface,
            update_location=False
        )
        self._add_or_override(
            router_cmd,
            Syntax('arp', help='Show router ARP in Nokia SR OS format'),
            callback=self._print_router_arp,
            update_location=False
        )

        router_bgp = self._add_or_override(
            router_cmd,
            Syntax('bgp', help='Show BGP information'),
            update_location=False
        )
        self._add_or_override(
            router_bgp,
            BgpSummaryFilter().get_syntax(),
            callback=BgpSummaryFilter().print,
            schema=BgpSummaryFilter().get_data_schema(),
            update_location=False
        )

        router_ospf = self._add_or_override(
            router_cmd,
            Syntax('ospf', help='Show OSPF information'),
            update_location=False
        )
        self._add_or_override(
            router_ospf,
            Syntax('neighbor', help='Show OSPF neighbors in Nokia SR OS format'),
            callback=self._print_ospf_neighbor,
            update_location=False
        )

        router_isis = self._add_or_override(
            router_cmd,
            Syntax('isis', help='Show IS-IS information'),
            update_location=False
        )
        self._add_or_override(
            router_isis,
            Syntax('adjacency', help='Show IS-IS adjacencies in Nokia SR OS format'),
            callback=self._print_isis_adjacency,
            update_location=False
        )

        # 4. Service Reports
        service_cmd = self._add_or_override(
            target,
            Syntax('service', help='Show service reports in Nokia SR OS format'),
            update_location=False
        )
        self._add_or_override(
            service_cmd,
            Syntax('service-using', help='Show configured services in Nokia SR OS format'),
            callback=self._print_service_using,
            update_location=False
        )

        service_fdb = self._add_or_override(
            service_cmd,
            Syntax('fdb', help='Show forwarding database in Nokia SR OS format'),
            update_location=False
        )
        self._add_or_override(
            service_fdb,
            Syntax('mac', help='Show MAC table in Nokia SR OS format'),
            callback=self._print_service_fdb_mac,
            update_location=False
        )

        # service id <id>
        service_id_syntax = Syntax('id', help='Show service by ID')
        service_id_syntax.add_unnamed_argument(
            'name', default='*', suggestions=KeyCompleter(path="/network-instance[name=*]")
        )
        service_id = self._add_or_override(
            service_cmd,
            service_id_syntax,
            update_location=False
        )

        service_id_fdb = self._add_or_override(
            service_id,
            Syntax('fdb', help='Show forwarding database for service'),
            update_location=False
        )
        self._add_or_override(
            service_id_fdb,
            Syntax('mac', help='Show MAC table for service'),
            callback=self._print_service_fdb_mac,
            update_location=False
        )

        self._add_or_override(
            service_id,
            Syntax('evpn-mpls', help='Show EVPN MPLS destinations'),
            callback=self._print_evpn_mpls,
            schema=EvpnDestinationReport().get_schema(),
            update_location=False
        )

        vxlan_cmd = self._add_or_override(
            service_id,
            Syntax('vxlan', help='VxLAN commands'),
            callback=self._print_evpn_vxlan,
            schema=EvpnDestinationReport().get_schema(),
            update_location=False
        )
        self._add_or_override(
            vxlan_cmd,
            Syntax('destinations', help='Show EVPN VxLAN destinations'),
            callback=self._print_evpn_vxlan,
            schema=EvpnDestinationReport().get_schema(),
            update_location=False
        )

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
        # 1. Root global command 'sros' for interactive submode and one-liners
        try:
            if hasattr(cli, 'running_mode') and cli.running_mode.has_global_command('sros'):
                sros_node = cli.get_global_command('sros')
            else:
                sros_node = cli.add_global_command(
                    Syntax('sros', help='Nokia SR OS operational mode and commands'),
                    update_location=self._enter_submode
                )
        except Exception:
            sros_node = cli.get_global_command('sros')
        sros_show = self._add_or_override(
            sros_node,
            Syntax('show', help='Nokia SR OS show reports'),
            update_location=False
        )
        self._register_all_commands(sros_show)
        self._register_srl_escape_hatch(cli)

    def on_start(self, state):
        if not self._should_register_show_mode(state, 'nokia'):
            return
        wait_for_show_reports_load(state)
        self._register_all_commands(state.command_tree.show_mode)

    # Callbacks with intermediate command guards
    def _print_version(self, state, output, **_kwargs):
        SrosSystemReports().show_version(state, output)

    def _print_system_information(self, state, output, **_kwargs):
        SrosSystemReports().show_system_information(state, output)

    def _print_chassis(self, state, output, **_kwargs):
        SrosSystemReports().show_chassis(state, output)

    def _print_lldp_neighbor(self, state, output, **_kwargs):
        SrosInterfaceReports().show_lldp_neighbor(state, output)

    def _extract_node_arg(self, state, arguments, node_name, arg_name, default=None):
        for src in (arguments, getattr(state, 'line_commands', None)):
            if not src or not hasattr(src, 'has_node'):
                continue
            try:
                if src.has_node(node_name):
                    val = src.get_value_or(node_name, arg_name, default)
                    if val is not None and val != default:
                        return val
            except Exception:
                pass
        return default

    def _print_port(self, state, output, arguments=None, **_kwargs):
        if not state.is_last_command:
            return
        port_id = self._extract_node_arg(state, arguments, 'port', 'port_id', None)
        if port_id == '*':
            port_id = None
        SrosInterfaceReports().show_port(state, output, port_id=port_id)

    def _print_port_description(self, state, output, **_kwargs):
        SrosInterfaceReports().show_port_description(state, output)

    def _print_lag(self, state, output, arguments=None, **_kwargs):
        if not state.is_last_command:
            return
        lag_id = self._extract_node_arg(state, arguments, 'lag', 'name', None)
        if not lag_id or lag_id in ('*', 'lag*'):
            lag_id = self._extract_node_arg(state, arguments, 'lag', 'lag_id', None)
        if lag_id in ('*', 'lag*'):
            lag_id = None
        SrosInterfaceReports().show_lag(state, output, lag_id=lag_id)

    def _print_route_table(self, state, output, arguments=None, **_kwargs):
        netinst = self._extract_node_arg(state, arguments, 'router', 'netinst', 'default') or 'default'
        SrosRoutingReports().show_route_table(state, output, netinst=netinst)

    def _print_router_interface(self, state, output, arguments=None, **_kwargs):
        netinst = self._extract_node_arg(state, arguments, 'router', 'netinst', 'default') or 'default'
        SrosRoutingReports().show_router_interface(state, output, netinst=netinst)

    def _print_router_arp(self, state, output, arguments=None, **_kwargs):
        netinst = self._extract_node_arg(state, arguments, 'router', 'netinst', 'default') or 'default'
        SrosRoutingReports().show_router_arp(state, output, netinst=netinst)

    def _print_ospf_neighbor(self, state, output, arguments=None, **_kwargs):
        netinst = self._extract_node_arg(state, arguments, 'router', 'netinst', 'default') or 'default'
        SrosRoutingReports().show_router_ospf_neighbor(state, output, netinst=netinst)

    def _print_isis_adjacency(self, state, output, arguments=None, **_kwargs):
        netinst = self._extract_node_arg(state, arguments, 'router', 'netinst', 'default') or 'default'
        SrosRoutingReports().show_router_isis_adjacency(state, output, netinst=netinst)

    def _print_service_using(self, state, output, **_kwargs):
        SrosServiceReports().show_service_using(state, output)

    def _print_service_fdb_mac(self, state, output, arguments=None, **_kwargs):
        service_name = self._extract_node_arg(state, arguments, 'id', 'name', None)
        if service_name == '*':
            service_name = None
        SrosServiceReports().show_service_fdb_mac(state, output, service_name=service_name)

    def _validate_service_network_instance(self, state, arguments):
        nw_name = self._extract_node_arg(state, arguments, 'id', 'name', '*') or '*'
        if '*' in nw_name:
            return
        from srlinux.location import build_path
        from srlinux.mgmt.cli.execute_error import ExecuteError
        path = build_path('/network-instance[name={name}]/type', name=nw_name)
        server_data = state.server.get_data_store(DataStore.State).get_data(path, recursive=False)
        for nw in server_data.network_instance.items():
            if not any(t in str(nw.type) for t in ('mac-vrf', 'ip-vrf')):
                raise ExecuteError('service command available for mac-vrf and ip-vrf only')

    def _print_evpn_mpls(self, state, arguments, output, **_kwargs):
        if not state.is_last_command:
            return
        self._validate_service_network_instance(state, arguments)
        EvpnDestinationReport().print_mpls(state, arguments, output, **_kwargs)

    def _print_evpn_vxlan(self, state, arguments, output, **_kwargs):
        if not state.is_last_command:
            return
        self._validate_service_network_instance(state, arguments)
        EvpnDestinationReport().print_vxlan(state, arguments, output, **_kwargs)
