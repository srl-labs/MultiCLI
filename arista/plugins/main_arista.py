#!/usr/bin/python
###########################################################################
# Description: CLI plugin for EOS bgp command
#
# Copyright (c) 2025 Nokia
###########################################################################

from srlinux.mgmt.cli import CliPlugin, KeyCompleter
from srlinux.syntax import Syntax
from srlinux.location import build_path
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

####################################################################
##### Construct the import path. ###################################
'''
Add your directory and create a similar structure like below
'''
####################################################################
import_path_ip = os.path.join(import_base, "ip")
if import_path_ip not in sys.path:
    sys.path.insert(0, import_path_ip)
from ip_bgp_report import IpBgpReport as BaseBgpReport

import_path_bgp = os.path.join(import_base, "bgp")
if import_path_bgp not in sys.path:
    sys.path.insert(0, import_path_bgp)
from bgp_evpn_report import IpBgpReport as EvpnBgpReport

import_path = os.path.join(import_base, "interface")
if import_path not in sys.path:
    sys.path.insert(0, import_path)
from arista_interface_detail import InterfaceDetails
from arista_interface_status import InterfaceStatus
from arista_arp_details import ArpDetails

class Plugin(CliPlugin):

    __slots__ = (
        '_header_string',
        '_netinst',
        '_arguments',
        '_netinst_data',
        '_current_netinst',
        '_used_routes',
        '_valid_routes',
        '_received_count',
        '_attrSets_dict',
        '_route_type',
        '_rd',
        '_mac_address',
        '_ip_address',
        '_ip_prefix',
        '_esi',
        '_ethernet_tag',
        '_originating_router',
        '_neighbor',
        '_multicast_source_address',
        '_multicast_group_address',
        '_bgp_rib'
    )

    def load(self, cli, **_kwargs):
        syntax = Syntax('ip', help='display ip protocol information')
        ip = cli.show_mode.add_command(syntax, update_location=True)
        bgp = ip.add_command(
            Syntax('bgp', help='show bgp information'),
            update_location=True)
        bgp_summary = bgp.add_command(
            Syntax('summary')
            .add_named_argument('vrf', default='default', help = 'network instance name', suggestions=KeyCompleter('/network-instance[name=*]')),
            callback = self._print_summary)

        ##### adding evpn: saju ######

        syntax = Syntax('bgp', help='display bgp information')
        bgp = cli.show_mode.add_command(syntax, update_location=True)
        evpn = bgp.add_command(
            Syntax('evpn', help='show EVPN information'),
            update_location=True)
        evpn_summary = evpn.add_command(
            Syntax('summary')
            .add_named_argument('vrf', default='default', help = 'network instance name', suggestions=KeyCompleter('/network-instance[name=*]')),
            callback = self._print_evpn_summary)
        route_type = evpn.add_command(Syntax('route-type', help='specify the EVPN route type'))
        rt_eth_ad = route_type.add_command(
            Syntax('auto-discovery')
            .add_named_argument('vrf', default='default', help = 'network instance name', suggestions=KeyCompleter('/network-instance[name=*]'))
            .add_named_argument('esi', default='*', help = 'ESI value'),
            callback = self._print_1)
        rt_mac_ip = route_type.add_command(
            Syntax('mac-ip')
            .add_named_argument('vrf', default='default', help = 'network instance name', suggestions=KeyCompleter('/network-instance[name=*]'))
            .add_named_argument('mac-address', default='*', help = 'MAC address'),
            callback = self._print_2)
        rt_imet = route_type.add_command(
            Syntax('imet')
            .add_named_argument('vrf', default='default', help = 'network instance name', suggestions=KeyCompleter('/network-instance[name=*]'))
            .add_named_argument('origin-router', default='*', help = 'Originating router IPv4 or IPv6 address'),
            callback = self._print_3)
        rt_eth_seg = route_type.add_command(
            Syntax('ethernet-segment')
            .add_named_argument('vrf', default='default', help = 'network instance name', suggestions=KeyCompleter('/network-instance[name=*]'))
            .add_named_argument('esi', default='*', help = 'ESI value'),
            callback = self._print_4)
        rt_ip_prefix = route_type.add_command(
            Syntax('ip-prefix')
            .add_named_argument('vrf', default='default', help = 'network instance name', suggestions=KeyCompleter('/network-instance[name=*]'))
            .add_named_argument('ip-address', default='*', help = 'IPv4 or IPv6 address prefix'),
            callback = self._print_5)
        
        #### interface and arp : mozaman ####

        '''
        This section has preprend command called eos because there is an overlap command with arista and srlinux
        Going forward in new release eos preprend will be depreciated and run the native commands
        example: show eos interface status
        '''

        syntax = Syntax('eos', help='Show Arista EOS reports')
        eos = cli.show_mode.add_command(syntax)
        # Adding sub-commands of Arista command:  "show arista interface detail"
        interfaces = eos.add_command(
            InterfaceDetails().get_syntax_details(),
            update_location=True,
            callback= self._interface_details
        )
        # Adding sub-commands of Arista command:  "show Arista EOS interface status"
        interfaces.add_command(
            InterfaceStatus().get_syntax_status(),
            update_location=True,
            callback=self._interface_status,
            schema = InterfaceStatus().get_data_schema()
        )
        # ARP Commands of Arista EOS command: "show arp"
        eos.add_command(
            ArpDetails()._get_syntax_arp(),
            update_location=True,
            callback=self._arp_entries,
            # callback=ArpDetails()._print,
            schema=ArpDetails()._get_arp_schema(True),
        )

############# Base BGP IP : saju ###########

    def _print_summary(self, state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        self._arguments = arguments
        netinst = self._arguments.get('summary', 'vrf')
        BaseBgpReport().show_bgp_summary(state, output, network_instance=netinst)
        output.print_line("-" * 100)
        output.print_line(f'Try SR Linux command: show network-instance {netinst} protocols bgp neighbor')

############### EVPN BGP : saju ############

    def _print_evpn_summary(self, state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        self._arguments = arguments
        netinst = self._arguments.get('summary', 'vrf')
        EvpnBgpReport().show_bgp_summary(state, output, network_instance=netinst)
        output.print_line("-" * 100)
        output.print_line(f'Try SR Linux command: show network-instance {netinst} protocols bgp neighbor')


    def __init__(self):
        self._rd = '*'
        self._esi = '*'
        self._mac_address = '*'
        self._ip_address = '*'
        self._ip_prefix = '*'
        self._originating_router = '*'
        self._ethernet_tag = '*'
        self._neighbor = '*'
        self._multicast_source_address = '*'
        self._multicast_group_address = '*'
        self._bgp_rib = None
        self._attrSets_dict = {}

    def reset_counters(self):
        self._used_routes = 0
        self._valid_routes = 0
        self._received_count = 0

    def _print_1(self, state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        self._route_type = '1'
        self._arguments = arguments
        netinst = self._arguments.get('auto-discovery', 'vrf')
        esi_input = self._arguments.get('auto-discovery', 'esi')
        EvpnBgpReport().show_evpn_rt1(state, output, network_instance=netinst, esi_value=esi_input)
        output.print_line("-" * 100)
        output.print_line(f'Try SR Linux command: show network-instance {netinst} protocols bgp routes evpn route-type 1 summary')

    def _print_2(self, state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        self._route_type = '2'
        self._arguments = arguments
        netinst = self._arguments.get('mac-ip', 'vrf')
        mac_input = self._arguments.get('mac-ip', 'mac-address')
        EvpnBgpReport().show_evpn_rt2(state, output, network_instance=netinst, mac_value=mac_input)
        output.print_line("-" * 100)
        output.print_line(f'Try SR Linux command: show network-instance {netinst} protocols bgp routes evpn route-type 2 summary')

    def _print_3(self, state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        self._route_type = '3'
        self._arguments = arguments
        netinst = self._arguments.get('imet', 'vrf')
        originr_input = self._arguments.get('imet', 'origin-router')
        EvpnBgpReport().show_evpn_rt3(state, output, network_instance=netinst, originr_value=originr_input)
        output.print_line("-" * 100)
        output.print_line(f'Try SR Linux command: show network-instance {netinst} protocols bgp routes evpn route-type 3 summary')

    def _print_4(self, state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        self._route_type = '4'
        self._arguments = arguments
        netinst = self._arguments.get('ethernet-segment', 'vrf')
        esi4_input = self._arguments.get('ethernet-segment', 'esi')
        EvpnBgpReport().show_evpn_rt4(state, output, network_instance=netinst, esi4_value=esi4_input)
        output.print_line("-" * 100)
        output.print_line(f'Try SR Linux command: show network-instance {netinst} protocols bgp routes evpn route-type 4 summary')

    def _print_5(self, state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        self._route_type = '5'
        self._arguments = arguments
        netinst = self._arguments.get('ip-prefix', 'vrf')
        ip_input = self._arguments.get('ip-prefix', 'ip-address')
        EvpnBgpReport().show_evpn_rt5(state, output, network_instance=netinst, ip_value=ip_input)
        output.print_line("-" * 100)
        output.print_line(f'Try SR Linux command: show network-instance {netinst} protocols bgp routes evpn route-type 5 summary')

########## Interface and ARP: mozaman ###########

    def _interface_details(self, state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        InterfaceDetails().print(state, arguments, output, **_kwargs)
        msg = 'Try SR Linux command: show interface {interface_name} detail'
        output.print_line(f'\n{"-" * len(msg)}\n{msg}')
        
    def _interface_status(self, state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        InterfaceStatus().print(state, arguments, output)
        msg = 'Try SR Linux command: show interface {interface_name} brief'
        output.print_line(f'\n{"-" * len(msg)}\n{msg}')

    def _arp_entries(self, state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        ArpDetails().print(state, arguments, output)
        msg = 'Try SR Linux command: show arpnd arp-entries'
        output.print_line(f'\n{"-" * len(msg)}\n{msg}')
