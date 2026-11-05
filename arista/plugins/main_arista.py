#!/usr/bin/python
###########################################################################
# Description: MultiCLI Plugin for Arista EOS Commands
# Contributors: Mohammad Zaman, Saju Salahudeen
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


_setup_module_paths('arista_system_reports.py', ["ip", "bgp", "interface", "system", "routing"])

try:
    from arista_ip_bgp_report import IpBgpReport as BaseBgpReport
except ImportError:
    from ip_bgp_report import IpBgpReport as BaseBgpReport
from bgp_evpn_report import IpBgpReport as EvpnBgpReport
from arista_interface_detail import InterfaceDetails
from arista_interface_status import InterfaceStatus
from arista_arp_details import ArpDetails
from arista_system_reports import AristaSystemReports
from arista_interface_reports import AristaInterfaceReports
from arista_routing_reports import AristaRoutingReports


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
        self._add_or_override(
            target,
            Syntax('version', help='Show system version in Arista EOS format'),
            callback=self._print_version,
            update_location=False
        )

        self._add_or_override(
            target,
            Syntax('hostname', help='Show system hostname'),
            callback=self._print_hostname,
            update_location=False
        )

        self._add_or_override(
            target,
            Syntax('clock', help='Show system clock in Arista EOS format'),
            callback=self._print_clock,
            update_location=False
        )

        self._add_or_override(
            target,
            Syntax('inventory', help='Show system hardware inventory'),
            callback=self._print_inventory,
            update_location=False
        )

        env_cmd = self._add_or_override(
            target,
            Syntax('environment', help='Show environment status'),
            callback=self._print_environment_all,
            update_location=False
        )
        self._add_or_override(
            env_cmd,
            Syntax('cooling', help='Show cooling status'),
            callback=self._print_environment_cooling,
            update_location=False
        )
        self._add_or_override(
            env_cmd,
            Syntax('power', help='Show power supply status'),
            callback=self._print_environment_power,
            update_location=False
        )
        self._add_or_override(
            env_cmd,
            Syntax('temperature', help='Show temperature status'),
            callback=self._print_environment_temp,
            update_location=False
        )

        self._add_or_override(
            target,
            Syntax('module', help='Show module information in Arista EOS format'),
            callback=self._print_module,
            update_location=False
        )

        proc_cmd = self._add_or_override(
            target,
            Syntax('processes', help='Show process information in Arista EOS format'),
            update_location=False
        )
        proc_top = self._add_or_override(
            proc_cmd,
            Syntax('top', help='Show top processes'),
            update_location=False
        )
        self._add_or_override(
            proc_top,
            Syntax('once', help='Show top processes once'),
            callback=self._print_processes_top_once,
            update_location=False
        )

        self._add_or_override(
            target,
            Syntax('mlag', help='Show MLAG information in Arista EOS format'),
            callback=self._print_mlag,
            update_location=False
        )

        # 2. IP Commands: show ip bgp, show ip route, show ip interface brief, show ip arp, show ip ospf
        ip = self._add_or_override(
            target,
            Syntax('ip', help='display ip protocol information'),
            update_location=False
        )

        bgp = self._add_or_override(
            ip,
            Syntax('bgp', help='show bgp information'),
            update_location=False
        )
        self._add_or_override(
            bgp,
            Syntax('summary')
            .add_named_argument('vrf', default='default', help='network instance name', suggestions=KeyCompleter('/network-instance[name=*]')),
            callback=self._print_summary,
            update_location=False
        )
        bgp_vrf = self._add_or_override(
            bgp,
            Syntax('vrf').add_unnamed_argument('vrf_name', suggestions=KeyCompleter('/network-instance[name=*]')),
            update_location=False
        )
        self._add_or_override(
            bgp_vrf,
            Syntax('summary', help='BGP summary for VRF'),
            callback=self._print_vrf_bgp_summary,
            update_location=False
        )

        # IP Route
        ip_route = self._add_or_override(
            ip,
            Syntax('route', help='IP routing table'),
            callback=self._print_ip_route,
            update_location=False
        )
        self._add_or_override(
            ip_route,
            Syntax('vrf').add_unnamed_argument('vrf_name', suggestions=KeyCompleter('/network-instance[name=*]')),
            callback=self._print_vrf_route,
            update_location=False
        )

        # IP Interface Brief
        ip_intf = self._add_or_override(
            ip,
            Syntax('interface', help='IP interface information'),
            update_location=False
        )
        self._add_or_override(
            ip_intf,
            Syntax('brief', help='IP interface brief'),
            callback=self._print_ip_interface_brief,
            update_location=False
        )

        # IP ARP
        self._add_or_override(
            ip,
            Syntax('arp', help='IP ARP table'),
            callback=self._print_ip_arp,
            update_location=False
        )

        # IP OSPF
        ip_ospf = self._add_or_override(
            ip,
            Syntax('ospf', help='IP OSPF information'),
            update_location=False
        )
        self._add_or_override(
            ip_ospf,
            Syntax('neighbor', help='OSPF neighbors'),
            callback=self._print_ospf_neighbor,
            update_location=False
        )
        ospf_intf = self._add_or_override(
            ip_ospf,
            Syntax('interface', help='OSPF interface information'),
            update_location=False
        )
        self._add_or_override(
            ospf_intf,
            Syntax('brief', help='OSPF interface brief'),
            callback=self._print_ospf_interface_brief,
            update_location=False
        )

        # 3. EVPN Commands
        bgp_root = self._add_or_override(
            target,
            Syntax('bgp', help='display bgp information'),
            update_location=False
        )

        evpn = self._add_or_override(
            bgp_root,
            Syntax('evpn', help='show EVPN information'),
            update_location=False
        )
        self._add_or_override(
            evpn,
            Syntax('summary')
            .add_named_argument('vrf', default='default', help='network instance name', suggestions=KeyCompleter('/network-instance[name=*]')),
            callback=self._print_evpn_summary,
            update_location=False
        )
        route_type = self._add_or_override(
            evpn,
            Syntax('route-type', help='specify the EVPN route type'),
            update_location=False
        )
        self._add_or_override(
            route_type,
            Syntax('auto-discovery')
            .add_named_argument('vrf', default='default', help='network instance name', suggestions=KeyCompleter('/network-instance[name=*]'))
            .add_named_argument('esi', default='*', help='ESI value'),
            callback=self._print_1,
            update_location=False
        )
        self._add_or_override(
            route_type,
            Syntax('mac-ip')
            .add_named_argument('vrf', default='default', help='network instance name', suggestions=KeyCompleter('/network-instance[name=*]'))
            .add_named_argument('mac-address', default='*', help='MAC address'),
            callback=self._print_2,
            update_location=False
        )
        self._add_or_override(
            route_type,
            Syntax('imet')
            .add_named_argument('vrf', default='default', help='network instance name', suggestions=KeyCompleter('/network-instance[name=*]'))
            .add_named_argument('origin-router', default='*', help='Originating router IPv4 or IPv6 address'),
            callback=self._print_3,
            update_location=False
        )
        self._add_or_override(
            route_type,
            Syntax('ethernet-segment')
            .add_named_argument('vrf', default='default', help='network instance name', suggestions=KeyCompleter('/network-instance[name=*]'))
            .add_named_argument('esi', default='*', help='ESI value'),
            callback=self._print_4,
            update_location=False
        )
        self._add_or_override(
            route_type,
            Syntax('ip-prefix')
            .add_named_argument('vrf', default='default', help='network instance name', suggestions=KeyCompleter('/network-instance[name=*]'))
            .add_named_argument('ip-address', default='*', help='IPv4 or IPv6 address prefix'),
            callback=self._print_5,
            update_location=False
        )

        # 4. Interfaces Commands: show interfaces status, description, detail
        intfs_syntax = Syntax('interfaces', help='Interface status and information')
        intfs_syntax.add_unnamed_argument(
            'name', default='*', suggestions=MultipleKeyCompleters(keycompleters=[KeyCompleter(path="/interface[name=*]")])
        )
        intfs = self._add_or_override(
            target,
            intfs_syntax,
            callback=self._interface_details,
            update_location=False
        )
        self._add_or_override(
            intfs,
            InterfaceStatus().get_syntax_status(),
            update_location=False,
            callback=self._interface_status,
            schema=InterfaceStatus().get_data_schema()
        )
        self._add_or_override(
            intfs,
            Syntax('description', help='Interface descriptions'),
            callback=self._print_interfaces_description,
            update_location=False
        )
        intfs_xcvr = self._add_or_override(
            intfs,
            Syntax('transceiver', help='Transceiver and DDM status in Arista EOS format'),
            callback=self._print_interfaces_transceiver,
            update_location=False
        )
        self._add_or_override(
            intfs_xcvr,
            Syntax('detail', help='Transceiver detail'),
            callback=self._print_interfaces_transceiver_detail,
            update_location=False
        )

        # 5. LLDP Commands
        lldp_node = self._add_or_override(
            target,
            Syntax('lldp', help='LLDP information'),
            update_location=False
        )
        lldp_neigh = self._add_or_override(
            lldp_node,
            Syntax('neighbors', help='LLDP neighbors in Arista format'),
            callback=self._print_lldp_neighbors,
            update_location=False
        )
        self._add_or_override(
            lldp_neigh,
            Syntax('detail', help='LLDP neighbors detail'),
            callback=self._print_lldp_neighbors_detail,
            update_location=False
        )

        # 6. MAC Table Commands
        mac_node = self._add_or_override(
            target,
            Syntax('mac', help='MAC information'),
            update_location=False
        )
        self._add_or_override(
            mac_node,
            Syntax('address-table', help='MAC address table'),
            callback=self._print_mac_address_table,
            update_location=False
        )

        # 7. VRF & VLAN Commands
        self._add_or_override(
            target,
            Syntax('vrf', help='VRF information in Arista format'),
            callback=self._print_vrf,
            update_location=False
        )
        self._add_or_override(
            target,
            Syntax('vlan', help='VLAN information in Arista format'),
            callback=self._print_vlan,
            update_location=False
        )

        # 8. Port-Channel Commands
        pc_node = self._add_or_override(
            target,
            Syntax('port-channel', help='Port-Channel information'),
            update_location=False
        )
        self._add_or_override(
            pc_node,
            Syntax('summary', help='Port-Channel summary in Arista format'),
            callback=self._print_port_channel_summary,
            update_location=False
        )

        # 9. IS-IS Commands
        isis_node = self._add_or_override(
            target,
            Syntax('isis', help='IS-IS information'),
            update_location=False
        )
        self._add_or_override(
            isis_node,
            Syntax('neighbors', help='IS-IS neighbors in Arista format'),
            callback=self._print_isis_neighbors,
            update_location=False
        )

        # 10. ARP Command (show arp / eos show arp)
        self._add_or_override(
            target,
            ArpDetails()._get_syntax_arp(),
            update_location=False,
            callback=self._arp_entries,
            schema=ArpDetails()._get_arp_schema(True)
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
        # 1. Root global command 'eos' for interactive submode and one-liners
        try:
            if hasattr(cli, 'running_mode') and cli.running_mode.has_global_command('eos'):
                eos_node = cli.get_global_command('eos')
            else:
                eos_node = cli.add_global_command(
                    Syntax('eos', help='Arista EOS operational mode and commands'),
                    update_location=self._enter_submode
                )
        except Exception:
            eos_node = cli.get_global_command('eos')
        eos_show = self._add_or_override(
            eos_node,
            Syntax('show', help='Arista EOS show reports'),
            update_location=False
        )
        self._register_all_commands(eos_show)
        self._register_srl_escape_hatch(cli)

    def on_start(self, state):
        if not self._should_register_show_mode(state, 'arista'):
            return
        # 2. Register to show_mode for persona compatibility (e.g. auser)
        wait_for_show_reports_load(state)
        self._register_all_commands(state.command_tree.show_mode)

        # 3. Legacy 'show eos ...' container preserved for compatibility
        eos_legacy = self._add_or_override(state.command_tree.show_mode, Syntax('eos', help='Show Arista EOS reports'), update_location=False)
        eos_interfaces = self._add_or_override(
            eos_legacy,
            InterfaceDetails().get_syntax_details(),
            update_location=False,
            callback=self._interface_details
        )
        self._add_or_override(
            eos_interfaces,
            InterfaceStatus().get_syntax_status(),
            update_location=False,
            callback=self._interface_status,
            schema=InterfaceStatus().get_data_schema()
        )
        self._add_or_override(
            eos_legacy,
            ArpDetails()._get_syntax_arp(),
            update_location=False,
            callback=self._arp_entries,
            schema=ArpDetails()._get_arp_schema(True)
        )

    # Callbacks
    def _print_version(self, state, output, **_kwargs):
        AristaSystemReports().show_version(state, output)

    def _print_hostname(self, state, output, **_kwargs):
        AristaSystemReports().show_hostname(state, output)

    def _print_clock(self, state, output, **_kwargs):
        AristaSystemReports().show_clock(state, output)

    def _print_inventory(self, state, output, **_kwargs):
        AristaSystemReports().show_inventory(state, output)

    def _print_environment_all(self, state, output, **_kwargs):
        if not state.is_last_command:
            return
        AristaSystemReports().show_environment(state, output, 'all')

    def _print_environment_cooling(self, state, output, **_kwargs):
        AristaSystemReports().show_environment(state, output, 'cooling')

    def _print_environment_power(self, state, output, **_kwargs):
        AristaSystemReports().show_environment(state, output, 'power')

    def _print_environment_temp(self, state, output, **_kwargs):
        AristaSystemReports().show_environment(state, output, 'temperature')

    def _print_ip_route(self, state, output, **_kwargs):
        if not state.is_last_command:
            return
        AristaRoutingReports().show_ip_route(state, output, vrf='default')

    def _extract_node_arg(self, state, arguments, node_name, arg_name, default='default'):
        for src in (arguments, getattr(state, 'line_commands', None)):
            if not src or not hasattr(src, 'has_node'):
                continue
            try:
                if src.has_node(node_name):
                    val = src.get_value_or(node_name, arg_name, default)
                    if val:
                        return val
            except Exception:
                pass
        return default

    def _print_vrf_route(self, state, arguments, output, **_kwargs):
        vrf_name = self._extract_node_arg(state, arguments, 'vrf', 'vrf_name', 'default')
        AristaRoutingReports().show_ip_route(state, output, vrf=vrf_name)

    def _print_ip_interface_brief(self, state, output, **_kwargs):
        AristaInterfaceReports().show_ip_interface_brief(state, output)

    def _print_interfaces_description(self, state, output, **_kwargs):
        AristaInterfaceReports().show_interfaces_description(state, output)

    def _print_ip_arp(self, state, output, **_kwargs):
        AristaInterfaceReports().show_ip_arp(state, output)

    def _print_ospf_neighbor(self, state, output, **_kwargs):
        AristaRoutingReports().show_ip_ospf_neighbor(state, output)

    def _print_isis_neighbors(self, state, output, **_kwargs):
        AristaRoutingReports().show_isis_neighbors(state, output)

    def _print_lldp_neighbors(self, state, output, **_kwargs):
        if not state.is_last_command:
            return
        AristaInterfaceReports().show_lldp_neighbors(state, output, detail=False)

    def _print_lldp_neighbors_detail(self, state, output, **_kwargs):
        AristaInterfaceReports().show_lldp_neighbors(state, output, detail=True)

    def _print_mac_address_table(self, state, output, **_kwargs):
        AristaRoutingReports().show_mac_address_table(state, output)

    def _print_vrf(self, state, output, **_kwargs):
        AristaRoutingReports().show_vrf(state, output)

    def _print_vlan(self, state, output, **_kwargs):
        AristaRoutingReports().show_vlan(state, output)

    def _print_port_channel_summary(self, state, output, **_kwargs):
        AristaInterfaceReports().show_port_channel_summary(state, output)

    def _print_summary(self, state, arguments, output, **_kwargs):
        netinst = self._extract_node_arg(state, arguments, 'summary', 'vrf', 'default')
        BaseBgpReport().show_bgp_summary(state, output, network_instance=netinst)
        output.print_line("-" * 100)
        output.print_line(f'Try SR Linux command: show network-instance {netinst} protocols bgp neighbor')

    def _print_vrf_bgp_summary(self, state, arguments, output, **_kwargs):
        netinst = self._extract_node_arg(state, arguments, 'vrf', 'vrf_name', 'default')
        BaseBgpReport().show_bgp_summary(state, output, network_instance=netinst)
        output.print_line("-" * 100)
        output.print_line(f'Try SR Linux command: show network-instance {netinst} protocols bgp neighbor')

    def _print_evpn_summary(self, state, arguments, output, **_kwargs):
        netinst = self._extract_node_arg(state, arguments, 'summary', 'vrf', 'default')
        EvpnBgpReport().show_bgp_summary(state, output, network_instance=netinst)
        output.print_line("-" * 100)
        output.print_line(f'Try SR Linux command: show network-instance {netinst} protocols bgp neighbor')

    def _print_1(self, state, arguments, output, **_kwargs):
        netinst = arguments.get('auto-discovery', 'vrf')
        esi_input = arguments.get('auto-discovery', 'esi')
        EvpnBgpReport().show_evpn_rt1(state, output, network_instance=netinst, esi_value=esi_input)
        output.print_line("-" * 100)
        output.print_line(f'Try SR Linux command: show network-instance {netinst} protocols bgp routes evpn route-type 1 summary')

    def _print_2(self, state, arguments, output, **_kwargs):
        netinst = arguments.get('mac-ip', 'vrf')
        mac_input = arguments.get('mac-ip', 'mac-address')
        EvpnBgpReport().show_evpn_rt2(state, output, network_instance=netinst, mac_value=mac_input)
        output.print_line("-" * 100)
        output.print_line(f'Try SR Linux command: show network-instance {netinst} protocols bgp routes evpn route-type 2 summary')

    def _print_3(self, state, arguments, output, **_kwargs):
        netinst = arguments.get('imet', 'vrf')
        originr_input = arguments.get('imet', 'origin-router')
        EvpnBgpReport().show_evpn_rt3(state, output, network_instance=netinst, originr_value=originr_input)
        output.print_line("-" * 100)
        output.print_line(f'Try SR Linux command: show network-instance {netinst} protocols bgp routes evpn route-type 3 summary')

    def _print_4(self, state, arguments, output, **_kwargs):
        netinst = arguments.get('ethernet-segment', 'vrf')
        esi4_input = arguments.get('ethernet-segment', 'esi')
        EvpnBgpReport().show_evpn_rt4(state, output, network_instance=netinst, esi4_value=esi4_input)
        output.print_line("-" * 100)
        output.print_line(f'Try SR Linux command: show network-instance {netinst} protocols bgp routes evpn route-type 4 summary')

    def _print_5(self, state, arguments, output, **_kwargs):
        netinst = arguments.get('ip-prefix', 'vrf')
        ip_input = arguments.get('ip-prefix', 'ip-address')
        EvpnBgpReport().show_evpn_rt5(state, output, network_instance=netinst, ip_value=ip_input)
        output.print_line("-" * 100)
        output.print_line(f'Try SR Linux command: show network-instance {netinst} protocols bgp routes evpn route-type 5 summary')

    def _extract_intf_arg(self, state, arguments):
        for src in (arguments, getattr(state, 'line_commands', None)):
            if not src or not hasattr(src, 'has_node'):
                continue
            try:
                if src.has_node('interfaces'):
                    val = src.get_value_or('interfaces', 'name', '*')
                    if val and val != '*':
                        return val
                if src.has_node('interface'):
                    val = src.get_value_or('interface', 'name', '*')
                    if val and val != '*':
                        return val
            except Exception:
                pass
        return '*'

    def _interface_details(self, state, arguments, output, **_kwargs):
        if not state.is_last_command:
            return
        InterfaceDetails().print(state, arguments, output, **_kwargs)
        name = self._extract_intf_arg(state, arguments)
        if name and name != '*':
            srl_name = InterfaceDetails._arista_to_srl_intf(name)
            msg = f'Try SR Linux command: show interface {srl_name} detail'
        else:
            msg = 'Try SR Linux command: show interface detail'
        output.print_line(f'\n{"-" * len(msg)}\n{msg}')

    def _interface_status(self, state, arguments, output, **_kwargs):
        if not state.is_last_command:
            return
        InterfaceStatus().print(state, arguments, output)
        name = self._extract_intf_arg(state, arguments)
        if name and name != '*':
            srl_name = InterfaceDetails._arista_to_srl_intf(name)
            msg = f'Try SR Linux command: show interface {srl_name} brief'
        else:
            msg = 'Try SR Linux command: show interface brief'
        output.print_line(f'\n{"-" * len(msg)}\n{msg}')

    def _arp_entries(self, state, arguments, output, **_kwargs):
        if not state.is_last_command:
            return
        ArpDetails().print(state, arguments, output)
        msg = 'Try SR Linux command: show arpnd arp-entries'
        output.print_line(f'\n{"-" * len(msg)}\n{msg}')

    def _print_interfaces_transceiver(self, state, output, **_kwargs):
        if not state.is_last_command:
            return
        AristaInterfaceReports().show_interfaces_transceiver(state, output, detail=False)

    def _print_interfaces_transceiver_detail(self, state, output, **_kwargs):
        AristaInterfaceReports().show_interfaces_transceiver(state, output, detail=True)

    def _print_module(self, state, output, **_kwargs):
        AristaSystemReports().show_module(state, output)

    def _print_processes_top_once(self, state, output, **_kwargs):
        AristaSystemReports().show_processes_top_once(state, output)

    def _print_ospf_interface_brief(self, state, output, **_kwargs):
        AristaRoutingReports().show_ip_ospf_interface_brief(state, output)

    def _print_mlag(self, state, output, **_kwargs):
        AristaRoutingReports().show_mlag(state, output)
