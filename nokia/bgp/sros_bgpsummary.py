#!/usr/bin/python
###########################################################################
# Description:
#
# Copyright (c) 2020 Nokia
###########################################################################

from datetime import datetime, timezone

from srlinux.data import Data, Formatter, TagValueFormatter
from srlinux.location import build_path
from srlinux.schema import FixedSchemaRoot
from srlinux.schema.data_store import DataStore
from srlinux.syntax import Syntax


class BgpSummaryFilter(object):

    def __init__(self):
        self._netinst = None
        self._bgp_node = None
        self._router_id = None
        self._asn = None
        self._local_as = None
        self._admin_state = None
        self._oper_state = None
        self._groups = 0
        self._internal_groups = 0
        self._neighbors = 0
        self._path_memory = None
        self._total_paths = 0
        self._neighbor_data = {}
        self._stats = {
            'total_ipv4_remote_rts': 0,
            'total_ipv6_remote_rts': 0,
            'total_ipv4_backup_rts': 0,
            'total_lblipv4_rem_rts': 0,
            'total_lblipv6_rem_rts': 0,
            'total_lblipv4_bkp_rts': 0,
            'total_supressed_rts': 0,
            'total_decay_rts': 0,
            'total_ipv4_rem_active_rts': 0,
            'total_ipv6_rem_active_rts': 0,
            'total_ipv6_backup_rts': 0,
            'total_lblipv4_rem_act_rts': 0,
            'total_lblipv6_rem_act_rts': 0,
            'total_lblipv6_bkp_rts': 0,
            'total_hist_rts': 0,
            'total_vpn_ipv4_rem_rts': 0,
            'total_vpn_ipv6_rem_rts': 0,
            'total_vpn_ipv4_bkup_rts': 0,
            'total_vpn_local_rts': 0,
            'total_vpn_hist_rts': 0,
            'total_vpn_ipv4_rem_act_rts': 0,
            'total_vpn_ipv6_rem_act_rts': 0,
            'total_vpn_ipv6_bkup_rts': 0,
            'total_vpn_supp_rts': 0,
            'total_vpn_decay_rts': 0,
            'total_evpn_rem_rts': 0,
            'total_evpn_rem_act_rts': 0,
        }

    def get_syntax(self):
        """Returns the Syntax for the show router bgp summary SR-OS command."""
        return Syntax('summary', help='show bgp summary information for a network instance')

    def get_data_schema(self):
        """Returns the Schema describing the data-model of the show routine."""
        root = FixedSchemaRoot()
        bgp = root.add_child(
            'bgp',
            key='router_id',
            fields=[
                'asn',
                'local_as',
                'admin_state',
                'oper_state',
                'groups',
                'internal_groups',
                'neighbors',
                'stats',
                'total_paths',
                'path_memory',
            ],
        )
        neighbor = bgp.add_child(
            'neighbor',
            key='peer_address',
            fields=[
                'ip',
                'asn',
                'pkts_received',
                'pkts_sent',
                'session_state',
                'uptime',
                'routes_received',
                'routes_active',
                'routes_sent',
            ],
        )
        neighbor.add_child(
            'afi_safi',
            key='afi_safi_name',
            fields=[
                'name',
                'received_routes',
                'active_routes',
                'sent_routes',
            ],
        )

        return root

    def print(self, state, arguments, output, **_kwargs):
        """Prints all information for SR-OS command show router bgp summary."""
        self.__init__()

        self._getBgpSummary_(state, arguments)
        self._getBgpNeighborList_(state, arguments)

        result = self._populate_data(arguments, state)
        self._set_formatters(result, state)
        output.print_data(result)
        output.print_line(f'\nTry SR Linux command: show network-instance {self._netinst} protocols bgp summary\n')

    def _populate_data(self, arguments, state):
        """Takes information in attributes in self class and dumps them into a Data object."""
        result = Data(arguments.schema)

        bgp = result.bgp.create(self._router_id or '0.0.0.0')
        bgp.asn = self._asn
        bgp.local_as = self._local_as
        bgp.admin_state = self._admin_state
        bgp.oper_state = self._oper_state
        bgp.groups = self._groups
        bgp.internal_groups = self._internal_groups
        bgp.neighbors = self._neighbors
        bgp.stats = self._stats
        bgp.total_paths = self._total_paths
        bgp.path_memory = self._path_memory

        for neighbor_temp in self._neighbor_data:
            neighbor = bgp.neighbor.create(self._neighbor_data[neighbor_temp]['ip'])
            neighbor.ip = self._neighbor_data[neighbor_temp]['ip']
            neighbor.asn = self._neighbor_data[neighbor_temp]['asn']
            neighbor.pkts_received = self._neighbor_data[neighbor_temp]['pkts_received']
            neighbor.pkts_sent = self._neighbor_data[neighbor_temp]['pkts_sent']
            neighbor.session_state = self._neighbor_data[neighbor_temp]['session_state']
            neighbor.uptime = self._neighbor_data[neighbor_temp]['uptime']
            neighbor.routes_received = self._neighbor_data[neighbor_temp]['routes_received']
            neighbor.routes_active = self._neighbor_data[neighbor_temp]['routes_active']
            neighbor.routes_sent = self._neighbor_data[neighbor_temp]['routes_sent']

            counter = 0
            for _ in self._neighbor_data[neighbor_temp]:
                try:
                    if self._neighbor_data[neighbor_temp][f'afi_safi_{counter}']['admin_state'] == "enable":
                        afi_safi = neighbor.afi_safi.create(f'afi_safi_{counter}')
                        afi_safi.name = self._neighbor_data[neighbor_temp][f'afi_safi_{counter}']['name']
                        afi_safi.received_routes = self._neighbor_data[neighbor_temp][f'afi_safi_{counter}']['received_routes']
                        afi_safi.active_routes = self._neighbor_data[neighbor_temp][f'afi_safi_{counter}']['active_routes']
                        afi_safi.sent_routes = self._neighbor_data[neighbor_temp][f'afi_safi_{counter}']['sent_routes']
                        counter += 1
                except KeyError:
                    break
                except Exception:
                    break

        return result

    def _get_netinst(self, state, arguments):
        if arguments and hasattr(arguments, 'has_node') and arguments.has_node('router'):
            val = arguments.get_value_or('router', 'netinst', 'default')
            if val:
                return val
        if state and hasattr(state, 'line_commands') and state.line_commands:
            if hasattr(state.line_commands, 'has_node') and state.line_commands.has_node('router'):
                val = state.line_commands.get_value_or('router', 'netinst', 'default')
                if val:
                    return val
        return 'default'

    def _getBgpSummary_(self, state, arguments):
        """Retrieves main BGP information from a single recursive /protocols/bgp query."""
        self._netinst = self._get_netinst(state, arguments)

        path = build_path('/network-instance[name={name}]/protocols/bgp', name=self._netinst)
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            bgp_node = data.network_instance.get().protocols.get().bgp.get()
        except Exception:
            self._bgp_node = None
            self._router_id = "0.0.0.0"
            self._asn = 0
            self._local_as = 0
            self._admin_state = "disable"
            self._oper_state = "down"
            self._groups = 0
            self._internal_groups = 0
            self._neighbors = 0
            self._path_memory = 0
            self._total_paths = 0
            return

        self._bgp_node = bgp_node
        self._router_id = getattr(bgp_node, 'router_id', None) or "0.0.0.0"
        self._asn = getattr(bgp_node, 'autonomous_system', None) or 0
        self._local_as = self._asn
        self._admin_state = getattr(bgp_node, 'admin_state', None) or "disable"
        self._oper_state = getattr(bgp_node, 'oper_state', None) or "down"

        self._groups = 0
        internal_group_names = set()
        if hasattr(bgp_node, 'group'):
            for group in bgp_node.group.items():
                self._groups += 1
                group_peer_as = getattr(group, 'peer_as', None)
                group_local_as = None
                if hasattr(group, 'local_as') and group.local_as.exists():
                    try:
                        group_local_as = group.local_as.get().as_number
                    except Exception:
                        group_local_as = None
                effective_local_as = group_local_as or self._local_as
                if group_peer_as and effective_local_as and group_peer_as == effective_local_as:
                    internal_group_names.add(group.group_name)

        self._neighbors = 0
        if hasattr(bgp_node, 'neighbor'):
            for n_node in bgp_node.neighbor.items():
                self._neighbors += 1
                peer_group = getattr(n_node, 'peer_group', None)
                if peer_group and getattr(n_node, 'peer_type', None) == 'ibgp':
                    internal_group_names.add(peer_group)

        self._internal_groups = len(internal_group_names)

        try:
            self._path_memory = bgp_node.statistics.get().path_memory or 0
        except Exception:
            self._path_memory = 0

        try:
            self._total_paths = bgp_node.statistics.get().total_paths or 0
        except Exception:
            self._total_paths = 0

    def _getBgpNeighborList_(self, state, arguments):
        """Retrieves BGP neighbor state from the cached BGP subtree (or queries if uncached)."""
        self._netinst = self._get_netinst(state, arguments)
        bgp_node = self._bgp_node
        if bgp_node is None:
            path = build_path('/network-instance[name={name}]/protocols/bgp', name=self._netinst)
            try:
                data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
                bgp_node = data.network_instance.get().protocols.get().bgp.get()
            except Exception:
                self._neighbor_data = {}
                return

        if not hasattr(bgp_node, 'neighbor'):
            self._neighbor_data = {}
            return

        neighbor_data = {}
        for n_node in bgp_node.neighbor.items():
            neighbor_ip = n_node.peer_address
            neighbor_data[neighbor_ip] = {}
            neighbor_data[neighbor_ip]['ip'] = neighbor_ip
            neighbor_data[neighbor_ip]['asn'] = getattr(n_node, 'peer_as', 0) or 0
            try:
                neighbor_data[neighbor_ip]['pkts_received'] = n_node.received_messages.get().total_messages or 0
            except Exception:
                neighbor_data[neighbor_ip]['pkts_received'] = 0
            try:
                neighbor_data[neighbor_ip]['pkts_sent'] = n_node.sent_messages.get().total_messages or 0
            except Exception:
                neighbor_data[neighbor_ip]['pkts_sent'] = 0

            neighbor_data[neighbor_ip]['session_state'] = getattr(n_node, 'session_state', 'idle') or 'idle'
            if neighbor_data[neighbor_ip]['session_state'] == 'established':
                neighbor_data[neighbor_ip]['uptime'] = getattr(n_node, 'last_established', 0)
                neighbor_data[neighbor_ip]['routes_received'] = 0
                neighbor_data[neighbor_ip]['routes_active'] = 0
                neighbor_data[neighbor_ip]['routes_sent'] = 0

                counter = 0
                for afi_safi in n_node.afi_safi.items():
                    if afi_safi.admin_state == "enable":
                        rcv_r = getattr(afi_safi, 'received_routes', 0) or 0
                        act_r = getattr(afi_safi, 'active_routes', 0) or 0
                        snt_r = getattr(afi_safi, 'sent_routes', 0) or 0
                        neighbor_data[neighbor_ip]['routes_received'] += rcv_r
                        neighbor_data[neighbor_ip]['routes_active'] += act_r
                        neighbor_data[neighbor_ip]['routes_sent'] += snt_r
                        neighbor_data[neighbor_ip][f'afi_safi_{counter}'] = {}
                        neighbor_data[neighbor_ip][f'afi_safi_{counter}']['admin_state'] = afi_safi.admin_state
                        neighbor_data[neighbor_ip][f'afi_safi_{counter}']['name'] = afi_safi.afi_safi_name
                        neighbor_data[neighbor_ip][f'afi_safi_{counter}']['received_routes'] = rcv_r
                        neighbor_data[neighbor_ip][f'afi_safi_{counter}']['active_routes'] = act_r
                        neighbor_data[neighbor_ip][f'afi_safi_{counter}']['sent_routes'] = snt_r
                        counter += 1

                        if afi_safi.afi_safi_name == 'ipv4-unicast':
                            self._stats['total_ipv4_remote_rts'] += rcv_r
                            self._stats['total_ipv4_backup_rts'] += 0
                            self._stats['total_ipv4_rem_active_rts'] += act_r
                        elif afi_safi.afi_safi_name == 'ipv6-unicast':
                            self._stats['total_ipv6_remote_rts'] += rcv_r
                            self._stats['total_ipv6_backup_rts'] += 0
                            self._stats['total_ipv6_rem_active_rts'] += act_r
                        elif afi_safi.afi_safi_name == 'evpn':
                            self._stats['total_evpn_rem_rts'] += rcv_r
                            self._stats['total_evpn_rem_act_rts'] += act_r
                        elif afi_safi.afi_safi_name == 'ipv4-labeled-unicast':
                            self._stats['total_lblipv4_rem_rts'] += rcv_r
                            self._stats['total_lblipv4_bkp_rts'] += 0
                            self._stats['total_lblipv4_rem_act_rts'] += act_r
                        elif afi_safi.afi_safi_name == 'ipv6-labeled-unicast':
                            self._stats['total_lblipv6_rem_rts'] += rcv_r
                            self._stats['total_lblipv6_bkp_rts'] += 0
                            self._stats['total_lblipv6_rem_act_rts'] += act_r
                        elif afi_safi.afi_safi_name == 'l3vpn-ipv4-unicast':
                            self._stats['total_vpn_ipv4_rem_rts'] += rcv_r
                            self._stats['total_vpn_ipv4_bkup_rts'] += 0
                            self._stats['total_vpn_ipv4_rem_act_rts'] += act_r
                        elif afi_safi.afi_safi_name == 'l3vpn-ipv6-unicast':
                            self._stats['total_vpn_ipv6_rem_rts'] += rcv_r
                            self._stats['total_vpn_ipv6_bkup_rts'] += 0
                            self._stats['total_vpn_ipv6_rem_act_rts'] += act_r
            else:
                neighbor_data[neighbor_ip]['uptime'] = 0
                neighbor_data[neighbor_ip]['routes_received'] = 0
                neighbor_data[neighbor_ip]['routes_active'] = 0
                neighbor_data[neighbor_ip]['routes_sent'] = 0
                neighbor_data[neighbor_ip]['afi_safi_0'] = {}

        self._neighbor_data = neighbor_data

    def _set_formatters(self, data: Data, state):
        data.set_formatter('/bgp', SrosBgpHeaderFormatter())
        data.set_formatter('/bgp/neighbor', SrosBgpNeighborFormatter())
        data.set_formatter('/bgp/neighbor/afi_safi', SrosBgpAfiSafiFormatter(self.get_data_schema()))


class SrosBgpHeaderFormatter(Formatter):
    def iter_format(self, entry, max_width):
        yield from self._format_header_line(max_width)
        yield f' BGP Router ID:{entry.router_id:<20} AS:{entry.asn:<10} Local AS:{entry.local_as:<10}'
        yield from self._format_header_line(max_width)
        admin_state = "Up" if entry.admin_state == "enable" else "Down"
        oper_state = "Up" if entry.oper_state == "up" else "Down"
        internal_groups = getattr(entry, 'internal_groups', 0)
        total_paths = getattr(entry, 'total_paths', 0)
        yield f'BGP Admin State         : {admin_state:<11} BGP Oper State              : {oper_state:<10}'
        yield f'Total Peer Groups       : {entry.groups:<3}         Total Peers                 : {entry.neighbors:<4}      '
        yield f'Total VPN Peer Groups   : 0           Total VPN Peers             : 0         '
        yield f'Current Internal Groups : {internal_groups:<12}Max Internal Groups         : {internal_groups:<10}'
        yield f'Total BGP Paths         : {total_paths:<12}Total Path Memory           : {entry.path_memory:<6}'
        yield ' '
        yield f"Total IPv4 Remote Rts   : {entry.stats['total_ipv4_remote_rts']:<10}  Total IPv4 Rem. Active Rts  : {entry.stats['total_ipv4_rem_active_rts']:<10}"
        yield f"Total IPv6 Remote Rts   : {entry.stats['total_ipv6_remote_rts']:<10}  Total IPv6 Rem. Active Rts  : {entry.stats['total_ipv6_rem_active_rts']:<10}"
        yield f"Total IPv4 Backup Rts   : {entry.stats['total_ipv4_backup_rts']:<10}  Total IPv6 Backup Rts       : {entry.stats['total_ipv6_backup_rts']:<10}"
        yield f"Total LblIpv4 Rem Rts   : {entry.stats['total_lblipv4_rem_rts']:<10}  Total LblIpv4 Rem. Act Rts  : {entry.stats['total_lblipv4_rem_act_rts']:<10}"
        yield f"Total LblIpv6 Rem Rts   : {entry.stats['total_lblipv6_rem_rts']:<10}  Total LblIpv6 Rem. Act Rts  : {entry.stats['total_lblipv6_rem_act_rts']:<10}"
        yield f"Total LblIpv4 Bkp Rts   : {entry.stats['total_lblipv4_bkp_rts']:<10}  Total LblIpv6 Bkp Rts       : {entry.stats['total_lblipv6_bkp_rts']:<10}"
        yield f"Total Supressed Rts     : {entry.stats['total_supressed_rts']:<10}  Total Hist. Rts             : {entry.stats['total_hist_rts']:<10}"
        yield f"Total Decay Rts         : {entry.stats['total_decay_rts']:<10}"
        yield ' '
        yield f"Total VPN-IPv4 Rem. Rts : {entry.stats['total_vpn_ipv4_rem_rts']:<10}  Total VPN-IPv4 Rem. Act. Rts: {entry.stats['total_vpn_ipv4_rem_act_rts']:<10}"
        yield f"Total VPN-IPv6 Rem. Rts : {entry.stats['total_vpn_ipv6_rem_rts']:<10}  Total VPN-IPv6 Rem. Act. Rts: {entry.stats['total_vpn_ipv6_rem_act_rts']:<10}"
        yield f"Total VPN-IPv4 Bkup Rts : {entry.stats['total_vpn_ipv4_bkup_rts']:<10}  Total VPN-IPv6 Bkup Rts     : {entry.stats['total_vpn_ipv6_bkup_rts']:<10}"
        yield f"Total VPN Local Rts     : {entry.stats['total_vpn_local_rts']:<10}  Total VPN Supp. Rts         : {entry.stats['total_vpn_supp_rts']:<10}"
        yield f"Total VPN Hist. Rts     : {entry.stats['total_vpn_hist_rts']:<10}  Total VPN Decay Rts         : {entry.stats['total_vpn_decay_rts']:<10}"
        yield ' '
        yield 'Total MVPN-IPv4 Rem Rts : 0           Total MVPN-IPv4 Rem Act Rts : 0         '
        yield 'Total MVPN-IPv6 Rem Rts : 0           Total MVPN-IPv6 Rem Act Rts : 0         '
        yield 'Total MDT-SAFI Rem Rts  : 0           Total MDT-SAFI Rem Act Rts  : 0         '
        yield 'Total McIPv4 Remote Rts : 0           Total McIPv4 Rem. Active Rts: 0         '
        yield 'Total McIPv6 Remote Rts : 0           Total McIPv6 Rem. Active Rts: 0         '
        yield 'Total McVpnIPv4 Rem Rts : 0           Total McVpnIPv4 Rem Act Rts : 0         '
        yield 'Total McVpnIPv6 Rem Rts : 0           Total McVpnIPv6 Rem Act Rts : 0         '
        yield ' '
        yield f"Total EVPN Rem Rts      : {entry.stats['total_evpn_rem_rts']:<10}  Total EVPN Rem Act Rts      : {entry.stats['total_evpn_rem_act_rts']:<10}"
        yield 'Total L2-VPN Rem. Rts   : 0           Total L2VPN Rem. Act. Rts   : 0         '
        yield 'Total MSPW Rem Rts      : 0           Total MSPW Rem Act Rts      : 0         '
        yield 'Total RouteTgt Rem Rts  : 0           Total RouteTgt Rem Act Rts  : 0         '
        yield 'Total FlowIpv4 Rem Rts  : 0           Total FlowIpv4 Rem Act Rts  : 0         '
        yield 'Total FlowIpv6 Rem Rts  : 0           Total FlowIpv6 Rem Act Rts  : 0         '
        yield 'Total FlowVpnv4 Rem Rts : 0           Total FlowVpnv4 Rem Act Rts : 0         '
        yield 'Total FlowVpnv6 Rem Rts : 0           Total FlowVpnv6 Rem Act Rts : 0         '
        yield 'Total Link State Rem Rts: 0           Total Link State Rem Act Rts: 0         '
        yield 'Total SrPlcyIpv4 Rem Rts: 0           Total SrPlcyIpv4 Rem Act Rts: 0         '
        yield 'Total SrPlcyIpv6 Rem Rts: 0           Total SrPlcyIpv6 Rem Act Rts: 0         '

        if entry.neighbor.exists():
            yield from self._format_header(max_width)
            yield from entry.neighbor.iter_format(max_width)

        yield from self._format_footer(max_width)

    def _format_header_line(self, width):
        return (
            '===============================================================================',
        )

    def _format_header(self, width):
        return (
            '',
            '===============================================================================',
            'BGP Summary',
            '===============================================================================',
            'Legend : D - Dynamic Neighbor',
            '===============================================================================',
            'Neighbor',
            'Description',
            '                   AS PktRcvd InQ  Up/Down   State|Rcv/Act/Sent (Addr Family)',
            '                      PktSent OutQ',
            '-------------------------------------------------------------------------------',
        )

    def _format_footer(self, width):
        return (
            '-------------------------------------------------------------------------------',
        )


class SrosBgpNeighborFormatter(Formatter):
    def iter_format(self, entry: Data, max_width):
        if entry.session_state == "established":
            uptime = self._get_time(entry.uptime)
            state_str = ""
        else:
            uptime = "00d00h00m"
            state_str = str(entry.session_state).capitalize()

        afi_lines = list(entry.afi_safi.iter_format(max_width)) if entry.afi_safi.exists() else []
        col0 = afi_lines[0] if len(afi_lines) > 0 else state_str
        col1 = afi_lines[1] if len(afi_lines) > 1 else ""

        yield f'{entry.ip}'
        yield f'                {entry.asn:<7}    {entry.pkts_received:<7}0 {uptime:<10} {col0}'.rstrip()
        yield f'                           {entry.pkts_sent:<7}0            {col1}'.rstrip()
        for extra_afi in afi_lines[2:]:
            yield f'                                             {extra_afi}'

    def _get_time(self, time_value):
        if time_value != 0 and time_value:
            try:
                ts_str = str(time_value).split()[0].replace("Z", "+00:00")
                given_time = datetime.fromisoformat(ts_str)
                if not given_time.tzinfo:
                    given_time = given_time.replace(tzinfo=timezone.utc)

                current_time = datetime.now(timezone.utc)
                time_difference = current_time - given_time

                total_seconds = max(0, int(time_difference.total_seconds()))
                hours, remainder = divmod(total_seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                formatted_output = f"{hours:02}h{minutes:02}m{seconds:02}s"
            except Exception:
                formatted_output = "00h00m00s"
        else:
            formatted_output = ""

        return formatted_output


class SrosBgpAfiSafiFormatter(TagValueFormatter):

    def __init__(self, schema):
        TagValueFormatter.__init__(self)
        self._schema = schema

    def iter_format(self, entry, max_width):
        sros_afisafi = {
            'l3vpn-ipv4-unicast': 'VpnIPv4',
            'l3vpn-ipv6-unicast': 'VpnIPv6',
            'evpn': 'Evpn',
            'ipv4-unicast': 'IPv4',
            'ipv6-unicast': 'IPv6',
            'ipv4-labeled-unicast': 'Lbl-IPv4',
            'ipv6-labeled-unicast': 'Lbl-IPv6',
        }

        afi_safi_label = sros_afisafi.get(entry.name, entry.name)
        yield f'{entry.received_routes}/{entry.active_routes}/{entry.sent_routes} ({afi_safi_label})'
