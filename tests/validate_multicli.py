#!/usr/bin/env python3
"""
validate_multicli.py
Automated validation harness for all MultiCLI commands across
Arista EOS (leaf1-1), Cisco NX-OS (leaf1-2), Juniper JUNOS (leaf2-1),
Nokia SR OS (leaf2-2), and native Multi-NOS Spine (spine).
"""

import argparse
import concurrent.futures
import fcntl
import json
import os
import pty
import re
import select
import struct
import subprocess
import sys
import termios
import threading
import time

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\r")

TEST_SUITES = {
    "Arista EOS": {
        "arg_key": "arista_node",
        "default_node": "leaf1-1",
        "commands": [
            "show version",
            "srl show version",
            "srl show interface ethernet-1/1 brief",
            "show hostname",
            "show clock",
            "show inventory",
            "show environment",
            "show environment cooling",
            "show environment power",
            "show environment temperature",
            "show ip interface brief",
            "show interfaces description",
            "show interfaces transceiver",
            "show interfaces transceiver detail",
            "show module",
            "show processes top once",
            "show lldp neighbors",
            "show lldp neighbors detail",
            "show ip arp",
            "show arp",
            "show port-channel summary",
            "show ip route",
            "show ip route vrf default",
            "show ip route vrf ip-vrf-1",
            "show vrf",
            "show vlan",
            "show mac address-table",
            "show ip ospf neighbor",
            "show ip ospf interface brief",
            "show isis neighbors",
            "show mlag",
            "show ip bgp summary",
            "show ip bgp vrf default summary",
            "show bgp evpn summary",
            "show bgp evpn route-type auto-discovery",
            "show bgp evpn route-type mac-ip",
            "show bgp evpn route-type imet",
            "show bgp evpn route-type ethernet-segment",
            "show bgp evpn route-type ip-prefix",
            "show interfaces status",
            "show interfaces Ethernet1/1 status",
            "show interfaces Et1/1 status",
            "show interfaces Management1 status",
            "show interfaces Ma1 status",
            "show interfaces Ethernet1/1",
            "show interfaces system0",
            "show arp interface Ethernet1/1",
            "show eos interface ethernet-1/1",
            "eos show",
            "eos show version",
            "eos show hostname",
            "eos show ip route",
            "eos show interfaces",
            "eos show interfaces ethernet-1/1",
            "eos show interfaces Ethernet1/1",
            "eos show interfaces status",
            "eos show interfaces Ethernet1/1 status",
        ],
        "submode_tests": [
            ("eos", ["show hostname", "show version"], "Nokia 7220 IXR-D2L"),
            ("eos", ["show interfaces ethernet-1/1"], "ethernet-1/1 is up"),
            ("eos", ["show interfaces", "show interfaces status"], "Ethernet1/1"),
            ("srl", ["show version", "show interface ethernet-1/1 brief"], "Software Version"),
            ("nxos", ["show hostname", "show version"], "Nokia SR Linux Software"),
            ("junos", ["show version"], "Hostname:"),
            ("sros", ["show version"], "SRLinux-"),
        ],
        "negative_assertions": [
            ("srl show version", "Try SR Linux command:", "srl show version must execute native SR Linux version report"),
            ("show environment cooling", "System Temperature", "show environment cooling should not trigger intermediate show environment all"),
            ("show environment power", "System Temperature", "show environment power should not trigger intermediate show environment all"),
            ("show lldp neighbors detail", "Last table change time", "show lldp neighbors detail should not trigger intermediate show lldp neighbors summary"),
            ("show lldp neighbors", "0:01:00 ago", "show lldp neighbors should not output hardcoded fake timestamp '0:01:00 ago'"),
            ("show ip route", "S       10.1.10.0/24", "Local/connected subnet should be classified as C or L, not S"),
            ("show vlan", "--    mac-vrf-1", "show vlan should dynamically derive VLAN tag rather than '--'"),
            ("show vlan", "Vlan1", "show vlan should not convert IRB interface to Vlan1"),
            ("show mac address-table", "Vlan--", "show mac address-table should not output 'Vlan--'"),
            ("show mac address-table", "Vlan1", "show mac address-table should not convert IRB interface to Vlan1"),
            ("show ip interface brief", "Vlan1", "show ip interface brief should not convert IRB interface to Vlan1"),
            ("show ip arp", "Vlan1", "show ip arp should not convert IRB interface to Vlan1"),
            ("show arp", "Vlan1", "show arp should not convert IRB interface to Vlan1"),
            ("show eos interface ethernet-1/1", "packets/sec", "show eos interface detail should not output unsupported packets/sec metric"),
            ("show interfaces system0", "Hardware is Ethernet", "show interfaces system0 must not fake Hardware is Ethernet on loopback interface"),
            ("show interfaces status", "with framing overhead", "show interfaces status should not output interface detail"),
            ("show interfaces description", "with framing overhead", "show interfaces description should not output interface detail"),
            ("show interfaces transceiver", "with framing overhead", "show interfaces transceiver should not output interface detail"),
            ("eos show interfaces status", "with framing overhead", "eos show interfaces status should not output interface detail"),
            ("show interfaces Ethernet1/1 status", "Ethernet1/10", "show interfaces Ethernet1/1 status must filter out non-matching interfaces"),
            ("eos show interfaces Ethernet1/1 status", "Ethernet1/10", "eos show interfaces Ethernet1/1 status must filter out non-matching interfaces"),
            ("show interfaces status", "irb0         notconnect", "show interfaces status must report connected for up irb0 interface"),
            ("show ip route", "ipv4 route", "show ip route must not recommend invalid ipv4 route command"),
            ("show eos interface ethernet-1/1", "{interface_name}", "show eos interface detail must not contain unrendered {interface_name} placeholder"),
            ("show mac address-table", "<instance>", "show mac address-table must not contain <instance> placeholder"),
        ],
        "positive_assertions": [
            ("show version", "Try SR Linux command: srl show version", "show version must recommend non-colliding srl show version"),
            ("srl show version", "Software Version", "srl show version must display native SR Linux version"),
            ("srl show interface ethernet-1/1 brief", "ethernet-1/1", "srl show interface brief must display native SR Linux interface"),
            ("show mac address-table", "Try SR Linux command: show network-instance bridge-table mac-table all", "show mac address-table must recommend valid SRL command"),
            ("show ip route", "Gateway of last resort", "show ip route must contain Gateway of last resort header"),
            ("show ip route", "B E  10.10.10.10/32", "show ip route must classify eBGP underlay routes as B E"),
            ("show ip route", "Try SR Linux command: show network-instance default route-table ipv4-unicast summary", "show ip route must recommend valid SRL route-table command"),
            ("show ip route vrf ip-vrf-1", "B I  10.90.1.0/24", "show ip route vrf ip-vrf-1 must classify iBGP EVPN route as B I"),
            ("show ip route vrf ip-vrf-1", "via 3.3.3.3", "show ip route vrf ip-vrf-1 must render first ECMP next-hop 3.3.3.3"),
            ("show ip route vrf ip-vrf-1", "via 4.4.4.4", "show ip route vrf ip-vrf-1 must render second ECMP next-hop 4.4.4.4"),
            ("show vlan", "Try SR Linux command: show network-instance summary", "show vlan must recommend valid SRL network-instance summary command"),
            ("show ip interface brief", "irb0.0", "show ip interface brief must preserve irb0.0 interface name"),
            ("show ip arp", "Age (min)", "show ip arp must contain Age (min) column"),
            ("show arp", "Hardware Addr", "show arp must contain Hardware Addr column"),
            ("show arp", "Age (sec)", "show arp must contain Age (sec) column"),
            ("show vrf", "ipv4,ipv6", "show vrf must dynamically detect ipv4,ipv6 protocols when IPv6 is enabled on VRF interfaces"),
            ("show vrf", "v6:routing", "show vrf must report v6:routing when IPv6 is enabled on VRF interfaces"),
            ("show bgp evpn route-type auto-discovery", "BGP routing table information for VRF default", "show bgp evpn route-type auto-discovery must display EVPN RT1 table"),
            ("show bgp evpn route-type mac-ip", "mac-ip", "show bgp evpn route-type mac-ip must display EVPN RT2 routes"),
            ("show bgp evpn route-type imet", "imet", "show bgp evpn route-type imet must display EVPN RT3 routes"),
            ("show bgp evpn route-type ethernet-segment", "ethernet-segment", "show bgp evpn route-type ethernet-segment must display EVPN RT4 routes"),
            ("show bgp evpn route-type ip-prefix", "ip-prefix", "show bgp evpn route-type ip-prefix must display EVPN RT5 routes"),
            ("show interfaces status", "Ethernet1/1", "show interfaces status must format interfaces in Arista style EthernetX/Y"),
            ("show interfaces status", "re:irb0\\s+--\\s+connected\\s+routed\\s+N/A", "show interfaces status must report connected and N/A duplex for irb0"),
            ("show interfaces status", "re:Loopback0\\s+--\\s+connected\\s+routed\\s+N/A", "show interfaces status must report connected and N/A duplex for Loopback0"),
            ("show interfaces Ethernet1/1 status", "Ethernet1/1", "show interfaces Ethernet1/1 status must display Ethernet1/1"),
            ("show interfaces Ethernet1/1 status", "Try SR Linux command: show interface ethernet-1/1 brief", "show interfaces Ethernet1/1 status must translate interface name in SRL command hint"),
            ("show interfaces Et1/1 status", "Ethernet1/1", "show interfaces Et1/1 status must accept short Arista interface name"),
            ("show interfaces Management1 status", "Management0", "show interfaces Management1 status must resolve to mgmt0"),
            ("show interfaces Ma1 status", "Management0", "show interfaces Ma1 status must resolve to mgmt0"),
            ("eos show interfaces Ethernet1/1 status", "Ethernet1/1", "eos show interfaces Ethernet1/1 status must display Ethernet1/1"),
            ("eos show interfaces Ethernet1/1 status", "Try SR Linux command: show interface ethernet-1/1 brief", "eos show interfaces Ethernet1/1 status must translate interface name in SRL command hint"),
            ("show interfaces Ethernet1/1", "ethernet-1/1 is up", "show interfaces Ethernet1/1 must accept Arista interface name"),
            ("show interfaces Ethernet1/1", "Try SR Linux command: show interface ethernet-1/1 detail", "show interfaces Ethernet1/1 must translate interface name in SRL command hint"),
            ("show interfaces system0", "Hardware is Loopback", "show interfaces system0 must report Loopback hardware"),
            ("show ip bgp vrf default summary", "BGP summary information for VRF default", "show ip bgp vrf default summary must output VRF BGP summary"),
            ("show vlan", "1     mac-vrf-1", "show vlan must dynamically resolve VLAN 1 for mac-vrf-1"),
            ("show vlan", "irb0.0", "show vlan must preserve irb0.0 interface name"),
            ("show mac address-table", "1       0000.5e00.0101", "show mac address-table must dynamically resolve VLAN 1 for IRB MAC"),
            ("show mac address-table", "irb0.0", "show mac address-table must format IRB port as irb0.0"),
            ("show processes top once", "re:\\d+\\s+root\\s+", "show processes top once must list real system processes"),
            ("show ip ospf neighbor", "Try SR Linux command: show network-instance default protocols ospf neighbor", "show ip ospf neighbor must include valid SRL command hint"),
            ("show ip ospf interface brief", "Try SR Linux command: show network-instance default protocols ospf interface", "show ip ospf interface brief must include valid SRL command hint"),
            ("show isis neighbors", "Try SR Linux command: show network-instance default protocols isis adjacency", "show isis neighbors must include valid SRL command hint"),
            ("show mlag", "state               : Active", "show mlag must show Active state for operational Ethernet Segment"),
            ("show mlag", "peer-address        : 2.2.2.2", "show mlag must resolve ES peer VTEP address"),
            ("show port-channel summary", "Po1(U)", "show port-channel summary must report Po1(U) for active LAG"),
            ("show eos interface ethernet-1/1", "with framing overhead", "show eos interface detail should output input/output rate with framing overhead"),
            ("eos show", "Local commands:", "eos show must display subcommand help"),
            ("eos show version", "Nokia 7220 IXR-D2L", "eos show version must output Arista-formatted version"),
            ("eos show hostname", "leaf1-1", "eos show hostname must output hostname"),
            ("eos show ip route", "Gateway of last resort", "eos show ip route must contain Gateway of last resort header"),
            ("eos show interfaces", "ethernet-1/1 is up", "eos show interfaces must output interface status and statistics"),
            ("eos show interfaces ethernet-1/1", "ethernet-1/1 is up", "eos show interfaces ethernet-1/1 must output interface detail"),
            ("eos show interfaces Ethernet1/1", "ethernet-1/1 is up", "eos show interfaces Ethernet1/1 must output interface detail"),
        ],
        "igp_positive_assertions": [
            ("show ip ospf neighbor", "10.10.10.10", "show ip ospf neighbor must display spine neighbor"),
            ("show ip ospf interface brief", "192.168.10.2/31", "show ip ospf interface brief must display active OSPF interface IP/mask"),
            ("show isis neighbors", "0100.1001.0010", "show isis neighbors must display spine IS-IS adjacency"),
        ],
    },
    "Cisco NX-OS": {
        "arg_key": "cisco_node",
        "default_node": "leaf1-2",
        "commands": [
            "show version",
            "srl show version",
            "srl show interface brief",
            "srl show interface",
            "show hostname",
            "show clock",
            "show inventory",
            "show environment",
            "show environment cooling",
            "show environment power",
            "show environment temperature",
            "show module",
            "show processes cpu",
            "show interface brief",
            "show interface status",
            "show interface description",
            "show interface transceiver",
            "show interface transceiver details",
            "show ipv6 interface brief",
            "show port-channel summary",
            "show ip interface brief",
            "show lldp neighbors",
            "show lldp neighbors detail",
            "show ip arp",
            "show ip route",
            "show ip route vrf default",
            "show ip bgp summary",
            "show ip bgp vrf default summary",
            "show mac address-table",
            "show mac address-table vlan 1",
            "show mac address-table vlan 10",
            "show mac address-table interface ethernet-1/2",
            "show mac address-table interface Ethernet1/2",
            "show mac address-table interface Po1",
            "show mac address-table vni 1",
            "show mac address-table vni 100",
            "show vrf",
            "show vlan",
            "show bfd neighbors",
            "show ip ospf neighbor",
            "show ip ospf interface brief",
            "show nve vni",
            "show nve peers",
            "show vpc",
            "nxos show",
            "nxos show version",
            "nxos show hostname",
            "nxos show ip route",
            "nxos show interface",
            "nxos show interface ethernet-1/2",
            "nxos show interface Ethernet1/2",
            "nxos show interface brief",
            "nxos show lldp neighbors",
            "nxos show lldp neighbors detail",
            "show interface",
            "show interface ethernet-1/2",
            "show interface Ethernet1/2",
            "show interface Eth1/2",
            "show interface Po1",
            "show interface Lo0",
            "show interface system0",
        ],
        "submode_tests": [
            ("nxos", ["show hostname", "show version"], "Nokia SR Linux Software"),
            ("nxos", ["show interface brief", "show interface ethernet-1/2"], "Ethernet1/2 is up"),
            ("nxos", ["show ip route"], "Gateway of last resort"),
            ("srl", ["show version", "show interface brief"], "Admin State"),
            ("eos", ["show hostname", "show version"], "Nokia 7220 IXR-D2L"),
            ("junos", ["show version"], "Hostname:"),
            ("sros", ["show version"], "SRLinux-"),
        ],
        "session_tests": [
            (
                "candidate + srl one-liner + vendor show pipe",
                ["enter candidate", "srl show interface ethernet-1/2 brief", "show ip route | grep 192.168.10", "pwc", "quit"],
                ["ethernet-1/2", "192.168.10"],
                ["srl"],
            ),
        ],
        "negative_assertions": [
            ("srl show version", "Try SR Linux command:", "srl show version must execute native SR Linux version report"),
            ("srl show interface brief", "Eth1/2", "srl show interface brief must execute native SR Linux brief report, not NX-OS"),
            ("show ip route", "ethernet-1/2.0", "show ip route should format interface as Eth1/2 rather than ethernet-1/2.0"),
            ("show mac address-table vlan 1", "irb0.2", "show mac address-table vlan 1 should not leak non-matching VLAN 2 entries"),
            ("show mac address-table vlan 10", "irb0.0", "show mac address-table vlan 10 should not return non-matching entries"),
            ("show vlan", "--    mac-vrf-1", "show vlan should dynamically derive VLAN tag rather than '--'"),
            ("show vlan", "Vlan0.", "show vlan should not output synthetic 'Vlan0.' interface names"),
            ("show vlan", "Vlan1", "show vlan should not convert IRB interface to Vlan1"),
            ("show interface brief", "admin state is up, Dedicated Interface", "show interface brief should not output full interface detail"),
            ("show interface status", "admin state is up, Dedicated Interface", "show interface status should not output full interface detail"),
            ("show interface description", "admin state is up, Dedicated Interface", "show interface description should not output full interface detail"),
            ("show interface transceiver", "admin state is up, Dedicated Interface", "show interface transceiver should not output full interface detail"),
            ("nxos show interface brief", "admin state is up, Dedicated Interface", "nxos show interface brief should not output full interface detail"),
            ("show interface Ethernet1/2", "Ethernet1/10 is", "show interface Ethernet1/2 must filter to Ethernet1/2"),
            ("nxos show interface Ethernet1/2", "Ethernet1/10 is", "nxos show interface Ethernet1/2 must filter to Ethernet1/2"),
            ("show interface system0", "Hardware: Ethernet", "show interface system0 must not fake Hardware: Ethernet on loopback interface"),
            ("show ip route", "ipv4 route", "show ip route must not recommend invalid ipv4 route command"),
            ("show nve vni", "Try SR Linux command: show tunnel-interface\n", "show nve vni must not recommend incomplete show tunnel-interface command"),
            ("show nve peers", "Try SR Linux command: show tunnel-interface vxlan-interface bridge-table\n", "show nve peers must not recommend incomplete bridge-table command"),
            ("show ip ospf neighbor", "<instance>", "show ip ospf neighbor must not contain <instance> placeholder"),
            ("show mac address-table", "<instance>", "show mac address-table must not contain <instance> placeholder"),
            ("show mac address-table", "ethernet-x/y.z", "show mac address-table must not contain placeholder interface"),
            ("show interface ethernet-1/2", "packets/sec", "show interface ethernet-1/2 must not output synthetic packets/sec"),
            ("show lldp neighbors", "Total entries displayed: 0", "show lldp neighbors must not return 0 entries when spine neighbor is active"),
            ("show lldp neighbors detail", "Total entries displayed: 0", "show lldp neighbors detail must not return 0 entries when spine neighbor is active"),
            ("nxos show lldp neighbors", "Total entries displayed: 0", "nxos show lldp neighbors must not return 0 entries when spine neighbor is active"),
            ("show environment", "No temperature sensor data available.", "show environment must resolve control processor temperature sensor data"),
            ("show environment temperature", "No temperature sensor data available.", "show environment temperature must resolve control processor temperature sensor data"),
            ("show nve peers", "No NVE peers discovered.", "show nve peers must resolve active VXLAN peers"),
        ],
        "positive_assertions": [
            ("show version", "Try SR Linux command: srl show version", "show version must recommend non-colliding srl show version"),
            ("srl show version", "Software Version", "srl show version must display native SR Linux version"),
            ("srl show interface brief", "ethernet-1/2", "srl show interface brief must display native SR Linux interface table"),
            ("srl show interface", "ethernet-1/2 is up", "srl show interface must display native SR Linux interface summary"),
            ("show interface brief", "Try SR Linux command: srl show interface brief", "show interface brief must recommend non-colliding srl show interface brief"),
            ("show interface status", "Try SR Linux command: srl show interface", "show interface status must recommend non-colliding srl show interface"),
            ("show interface description", "Try SR Linux command: srl show interface", "show interface description must recommend non-colliding srl show interface"),
            ("show ipv6 interface brief", "Try SR Linux command: srl show interface brief", "show ipv6 interface brief must recommend non-colliding srl show interface brief"),
            ("show ip interface brief", "Try SR Linux command: srl show interface brief", "show ip interface brief must recommend non-colliding srl show interface brief"),
            ("show mac address-table", "Try SR Linux command: srl show interface brief", "show mac address-table must recommend non-colliding srl show interface brief"),
            ("show lldp neighbors", "spine", "show lldp neighbors must list spine neighbor"),
            ("show lldp neighbors", "Total entries displayed: 1", "show lldp neighbors must display total entries count"),
            ("show lldp neighbors detail", "System Name: spine", "show lldp neighbors detail must display System Name: spine"),
            ("show lldp neighbors detail", "Enabled Capabilities: R", "show lldp neighbors detail must resolve Router capability R"),
            ("nxos show lldp neighbors", "spine", "nxos show lldp neighbors must list spine neighbor"),
            ("nxos show lldp neighbors detail", "System Name: spine", "nxos show lldp neighbors detail must display System Name: spine"),
            ("show environment", "Control Processor", "show environment must display Control Processor temperature entry"),
            ("show environment temperature", "Control Processor", "show environment temperature must display Control Processor temperature entry"),
            ("show nve peers", "3.3.3.3", "show nve peers must display active peer VTEP 3.3.3.3"),
            ("show nve peers", "4.4.4.4", "show nve peers must display active peer VTEP 4.4.4.4"),
            ("show ip ospf neighbor", "Try SR Linux command: show network-instance default protocols ospf neighbor", "show ip ospf neighbor must recommend default instance"),
            ("show ip ospf interface brief", "Try SR Linux command: show network-instance default protocols ospf interface", "show ip ospf interface brief must recommend default ospf interface"),
            ("show bfd neighbors", "Try SR Linux command: info from state bfd", "show bfd neighbors must include valid SRL BFD command hint"),
            ("show mac address-table", "show network-instance bridge-table mac-table all", "show mac address-table must recommend valid SRL command"),
            ("show processes cpu", "CPU utilization for five seconds:", "show processes cpu must contain CPU utilization summary"),
            ("show processes cpu", "re:Invoked\\s+uSecs", "show processes cpu must include Invoked and uSecs columns"),
            ("show processes cpu", "re:\\d+\\s+\\d+\\s+\\d+\\s+", "show processes cpu must list real system processes"),
            ("show ip arp", "MAC Address", "show ip arp must contain MAC Address header"),
            ("show ip route", "Try SR Linux command: show network-instance default route-table ipv4-unicast summary", "show ip route must recommend valid SRL route-table command"),
            ("show vlan", "Try SR Linux command: show network-instance summary", "show vlan must recommend valid SRL network-instance summary command"),
            ("show nve vni", "Try SR Linux command: show network-instance * vxlan-interface", "show nve vni must recommend valid SRL vxlan-interface command"),
            ("show nve peers", "Try SR Linux command: show tunnel-interface vxlan-interface bridge-table unicast-destinations destination", "show nve peers must recommend valid SRL unicast destinations command"),
            ("show vpc", "peer-link is up", "show vpc must show active ES peer-link on leaf1-2"),
            ("show ip route", "re:via \\d+\\.\\d+\\.\\d+\\.\\d+", "show ip route must dynamically resolve next-hop IP"),
            ("show ip route", "re:Eth\\d+/\\d+", "show ip route must dynamically resolve outgoing Cisco-formatted interface"),
            ("show ip bgp vrf default summary", "BGP summary information for VRF default", "show ip bgp vrf default summary must output VRF BGP summary"),
            ("show vlan", "1     mac-vrf-1", "show vlan must dynamically resolve VLAN 1 for mac-vrf-1"),
            ("show vlan", "irb0.0", "show vlan must preserve irb0.0 interface name"),
            ("show mac address-table", "1   00:00:5E:00:01:01", "show mac address-table must show dynamic VLAN 1 for mac-vrf-1 MAC"),
            ("show mac address-table vlan 1", "irb0.0(R)", "show mac address-table vlan 1 must return matching VLAN 1 entries"),
            ("show interface", "Ethernet1/2 is up", "show interface must output interface detail"),
            ("show interface ethernet-1/2", "Ethernet1/2 is up", "show interface ethernet-1/2 must output interface detail"),
            ("show interface ethernet-1/2", "Try SR Linux command: show interface ethernet-1/2 detail", "show interface ethernet-1/2 must include interface in SRL command hint"),
            ("show interface Ethernet1/2", "Ethernet1/2 is up", "show interface Ethernet1/2 must accept Cisco interface name"),
            ("show interface Ethernet1/2", "Try SR Linux command: show interface ethernet-1/2 detail", "show interface Ethernet1/2 must include translated interface in SRL command hint"),
            ("show interface Eth1/2", "Ethernet1/2 is up", "show interface Eth1/2 must accept short Cisco interface name"),
            ("show interface Po1", "Port-channel1 is up", "show interface Po1 must accept Cisco port-channel name"),
            ("show interface Lo0", "Loopback0 is up", "show interface Lo0 must accept Cisco loopback name"),
            ("show interface system0", "Hardware: Loopback", "show interface system0 must report Loopback hardware"),
            ("show version", "re:System memory:\\s+\\d{6,9} kB", "show version must report memory in kB rather than raw bytes"),
            ("nxos show", "Local commands:", "nxos show must display subcommand help"),
            ("nxos show version", "Nokia SR Linux Software", "nxos show version must output Cisco-formatted version"),
            ("nxos show hostname", "leaf1-2", "nxos show hostname must output hostname"),
            ("nxos show ip route", "Gateway of last resort", "nxos show ip route must contain Gateway of last resort header"),
            ("nxos show interface", "Ethernet1/2 is up", "nxos show interface must output interface detail"),
            ("nxos show interface ethernet-1/2", "Ethernet1/2 is up", "nxos show interface ethernet-1/2 must output interface detail"),
            ("nxos show interface Ethernet1/2", "Ethernet1/2 is up", "nxos show interface Ethernet1/2 must accept Cisco interface name"),
            ("nxos show interface Ethernet1/2", "Try SR Linux command: show interface ethernet-1/2 detail", "nxos show interface Ethernet1/2 must include translated interface in SRL command hint"),
            ("nxos show interface brief", "Eth1/1", "nxos show interface brief must output Ethernet interfaces"),
        ],
        "igp_positive_assertions": [
            ("show ip ospf neighbor", "10.10.10.10", "show ip ospf neighbor must display spine OSPF neighbor"),
            ("show ip ospf interface brief", "Eth1/2", "show ip ospf interface brief must display Eth1/2"),
            ("show bfd neighbors", "192.168.10.5", "show bfd neighbors must display active BFD neighbor"),
            ("show bfd neighbors", "Eth1/2", "show bfd neighbors must resolve interface Eth1/2"),
        ],
    },
    "Juniper JUNOS": {
        "arg_key": "juniper_node",
        "default_node": "leaf2-1",
        "commands": [
            "show version",
            "srl show version",
            "show system uptime",
            "show system processes",
            "show system processes summary",
            "show system processes brief",
            "show system processes extensive",
            "show chassis hardware",
            "show interfaces",
            "show interfaces et-0/0/2",
            "show interfaces et-1/1/3",
            "show interfaces irb.0",
            "show interfaces brief",
            "show interfaces brief et-1/1/3",
            "show interfaces terse",
            "show interfaces terse et-1/1/3",
            "show interfaces et-0/0/49:0 terse",
            "show arp",
            "show arp no-resolve",
            "show lldp neighbors",
            "show vlans",
            "show lacp interfaces",
            "show ethernet-switching table",
            "show ethernet-switching table vlan 1",
            "show ethernet-switching table instance default",
            "show ethernet-switching table interface ethernet-1/1",
            "show ethernet-switching table interface et-1/1/3",
            "show ethernet-switching table interface et-0/0/49:0",
            "show ethernet-switching table interface irb",
            "junos show ethernet-switching table interface ae2",
            "show route",
            "show route summary",
            "show bgp summary",
            "show ospf neighbor",
            "show isis adjacency",
            "junos show",
            "junos show version",
            "junos show route",
            "junos show interfaces",
            "junos show interfaces et-1/1/3",
            "junos show interfaces et-0/0/0",
        ],
        "submode_tests": [
            ("junos", ["show version", "show route"], "inet.0:"),
            ("junos", ["show interfaces"], "Physical interface:"),
            ("srl", ["show version"], "Software Version"),
            ("eos", ["show hostname", "show version"], "Nokia 7220 IXR-D2L"),
            ("nxos", ["show hostname", "show version"], "Nokia SR Linux Software"),
            ("sros", ["show version"], "SRLinux-"),
        ],
        "negative_assertions": [
            ("srl show version", "Try SR Linux command:", "srl show version must execute native SR Linux version report"),
            ("show system uptime", "Time Source: NTP CLOCK", "show system uptime should dynamically verify NTP state rather than hardcoding NTP CLOCK"),
            ("show vlans", "mac-vrf-1             0", "show vlans should not output tag 0 for mac-vrf-1 when IRB tag is 1"),
            ("show ethernet-switching table vlan 1", "irb0.2", "show ethernet-switching table vlan 1 should not leak VLAN 2 entries"),
            ("show system processes summary", "PID USERNAME", "show system processes summary should not output full process table"),
            ("show route summary", "via 10.", "show route summary should not output individual next-hops"),
            ("show route", "ipv4 route", "show route must not recommend invalid ipv4 route command"),
            ("show route summary", "ipv4 route", "show route summary must not recommend invalid ipv4 route command"),
            ("show ospf neighbor", "<instance>", "show ospf neighbor must not contain <instance> placeholder"),
            ("show isis adjacency", "<instance>", "show isis adjacency must not contain <instance> placeholder"),
            ("show ethernet-switching table", "<instance>", "show ethernet-switching table must not contain <instance> placeholder"),
            ("show interfaces et-1/1/3", "Physical interface: ethernet-1/10", "show interfaces et-1/1/3 must filter to ethernet-1/3"),
            ("junos show interfaces et-1/1/3", "Physical interface: ethernet-1/10", "junos show interfaces et-1/1/3 must filter to ethernet-1/3"),
        ],
        "positive_assertions": [
            ("show version", "Try SR Linux command: srl show version", "show version must recommend non-colliding srl show version"),
            ("srl show version", "Software Version", "srl show version must display native SR Linux version"),
            ("show ethernet-switching table", "show network-instance bridge-table mac-table all", "show ethernet-switching table must recommend valid SRL command"),
            ("show ospf neighbor", "Try SR Linux command: show network-instance default protocols ospf neighbor", "show ospf neighbor must recommend default instance"),
            ("show isis adjacency", "Try SR Linux command: show network-instance default protocols isis adjacency", "show isis adjacency must recommend default instance"),
            ("show route", "re:inet\\.0: \\d+ destinations", "show route must contain destinations and routes header"),
            ("show route", "Try SR Linux command: show network-instance default route-table ipv4-unicast summary", "show route must recommend valid SRL route-table ipv4-unicast summary command"),
            ("show route summary", "Try SR Linux command: show network-instance default route-table summary", "show route summary must recommend valid SRL route-table summary command"),
            ("show vlans", "Try SR Linux command: show network-instance summary", "show vlans must recommend valid SRL network-instance summary command"),
            ("show route", "re:et-\\d+/\\d+/\\d+\\.\\d+", "show route must contain Juniper formatted interfaces"),
            ("show system processes", "re:THR\\s+PRI", "show system processes must include THR column"),
            ("show system processes", "re:\\d+\\s+root\\s+", "show system processes must list real system processes"),
            ("show vlans", "mac-vrf-1             1", "show vlans must dynamically derive tag 1 for mac-vrf-1"),
            ("show ethernet-switching table vlan 1", "irb0.0(R)", "show ethernet-switching table vlan 1 must return VLAN 1 entries"),
            ("show ethernet-switching table interface irb", "irb0.0(R)", "show ethernet-switching table interface irb must match irb0.0 entries"),
            ("show interfaces et-0/0/2", "Physical interface: ethernet-1/3", "show interfaces et-0/0/2 must translate 0-indexed Junos interface name to ethernet-1/3"),
            ("show interfaces et-1/1/3", "Physical interface: ethernet-1/3", "show interfaces et-1/1/3 must translate Junos interface name to ethernet-1/3"),
            ("show interfaces irb.0", "Logical interface irb0.0", "show interfaces irb.0 must translate Junos irb.0 to irb0.0"),
            ("show interfaces brief et-1/1/3", "Physical interface: ethernet-1/3", "show interfaces brief et-1/1/3 must translate Junos interface name to ethernet-1/3"),
            ("show interfaces terse et-1/1/3", "ethernet-1/3", "show interfaces terse et-1/1/3 must translate Junos interface name to ethernet-1/3"),
            ("junos show", "Local commands:", "junos show must display subcommand help"),
            ("junos show version", "Hostname:", "junos show version must output Juniper-formatted version"),
            ("junos show route", "inet.0:", "junos show route must output Juniper-formatted route table"),
            ("junos show interfaces et-1/1/3", "Physical interface: ethernet-1/3", "junos show interfaces et-1/1/3 must translate Junos interface name in one-liner mode"),
            ("junos show interfaces et-0/0/0", "Physical interface: ethernet-1/1", "junos show interfaces et-0/0/0 must translate 0-indexed Junos interface name to ethernet-1/1"),
        ],
        "igp_positive_assertions": [
            ("show ospf neighbor", "10.10.10.10", "show ospf neighbor must display spine OSPF neighbor"),
            ("show isis adjacency", "spine", "show isis adjacency must display spine IS-IS adjacency"),
        ],
    },
    "Nokia SROS": {
        "arg_key": "nokia_node",
        "default_node": "leaf2-2",
        "commands": [
            "show version",
            "srl show version",
            "srl show lag",
            "srl show lag brief",
            "srl show system lldp neighbor",
            "show system information",
            "show chassis",
            "show port",
            "show port 1/1/1",
            "show port description",
            "show lag",
            "show lag 1",
            "show system lldp neighbor",
            "show router route-table",
            "show router default route-table",
            "show router ip-vrf-1 route-table",
            "show router interface",
            "show router arp",
            "show router bgp summary",
            "show router ospf neighbor",
            "show router isis adjacency",
            "show service service-using",
            "show service fdb mac",
            "show service id mac-vrf-1 vxlan",
            "show service id mac-vrf-1 vxlan destinations",
            "show service id ip-vrf-1 vxlan destinations",
            "show service id mac-vrf-1 fdb mac",
            "sros show",
            "sros show version",
            "sros show router route-table",
            "sros show port",
            "sros show chassis",
            "sros show system information",
            "sros show service fdb mac",
        ],
        "submode_tests": [
            ("sros", ["show"], "Local commands:"),
            ("sros", ["show version"], "SRLinux-"),
            ("sros", ["show version", "show router route-table"], "Route Table"),
            ("sros", ["show port", "show chassis"], "Chassis Information"),
            ("srl", ["show lag", "show system lldp neighbor"], "spine"),
            ("eos", ["show version"], "Nokia 7220 IXR-D2L"),
            ("nxos", ["show version"], "Nokia SR Linux Software"),
            ("junos", ["show version"], "Hostname:"),
        ],
        "negative_assertions": [
            ("srl show version", "Try SR Linux command:", "srl show version must execute native SR Linux version report"),
            ("srl show lag", "Lag Data", "srl show lag must execute native SR Linux lag report, not SR OS"),
            ("srl show system lldp neighbor", "LLDP Remote System Information", "srl show system lldp neighbor must execute native SR Linux LLDP report, not SR OS"),
            ("show port", "with framing overhead", "show port should not trigger standard SRL show interface output"),
            ("show router route-table", "Gateway of last resort", "show router route-table should not output Cisco/Arista header"),
            ("show version", "Software image:", "show version should not output Juniper style version header"),
            ("show chassis", "Cannot create node", "show chassis should not raise plugin load errors"),
            ("show version", "TiMOS", "show version should not output TiMOS - must accurately report SR Linux"),
            ("show version", "panos", "show version should not output synthetic SROS panos build path"),
            ("show system information", "2026-09-02T20:32:38.586Z", "show system information must not output hardcoded boot timestamp"),
            ("show system information", "0 days, 00:00:00.00", "show system information must not report zero uptime"),
            ("show router arp", "03h59m50s", "show router arp must not contain hardcoded 03h59m50s expiry"),
            ("show router bgp summary", "Total BGP Paths         : 52", "show router bgp summary must dynamically query total paths rather than hardcoding 52"),
            ("show lag 1", "\n2        ", "show lag 1 must filter out lag 2"),
            ("show service fdb mac", "No. of Entries in FDB: 0", "show service fdb mac must not return 0 entries when EVPN/IRB MACs exist"),
            ("show service id mac-vrf-1 fdb mac", "No. of Entries in FDB: 0", "show service id mac-vrf-1 fdb mac must not return 0 entries"),
            ("sros show service fdb mac", "No. of Entries in FDB: 0", "sros show service fdb mac must not return 0 entries"),
        ],
        "positive_assertions": [
            ("show version", "SRLinux-", "show version must output authentic SRLinux banner in SROS format"),
            ("show version", "7220 IXR-D2L", "show version must output actual chassis model"),
            ("show version", "Try SR Linux command: srl show version", "show version must recommend non-colliding srl show version"),
            ("srl show version", "Software Version", "srl show version must display native SR Linux version"),
            ("srl show lag", "lag2", "srl show lag must display native SR Linux LAG summary"),
            ("srl show system lldp neighbor", "spine", "srl show system lldp neighbor must display native SR Linux LLDP neighbor"),
            ("show system information", "System Up Time", "show system information must output system uptime"),
            ("show system information", "Try SR Linux command: info from state system information", "show system information must recommend SRL command"),
            ("show chassis", "Chassis Information", "show chassis must display chassis information"),
            ("show chassis", "Try SR Linux command: show platform chassis", "show chassis must recommend SRL chassis command"),
            ("show port", "Ports on Slot 1", "show port must display port table"),
            ("show port", "Try SR Linux command: show interface brief", "show port must recommend SRL interface brief"),
            ("show port description", "Port Descriptions on Slot 1", "show port description must display port descriptions"),
            ("show lag", "Lag Data", "show lag must display lag data"),
            ("show lag", "Try SR Linux command: srl show lag", "show lag must recommend non-colliding srl show lag"),
            ("show lag 1", "Lag Data", "show lag 1 must display lag data"),
            ("show system lldp neighbor", "LLDP Remote System Information", "show system lldp neighbor must display lldp info"),
            ("show system lldp neighbor", "Try SR Linux command: srl show system lldp neighbor", "show system lldp neighbor must recommend non-colliding srl show system lldp neighbor"),
            ("show router route-table", "Route Table (Router: default)", "show router route-table must display default route table"),
            ("show router route-table", "Try SR Linux command: show network-instance default route-table ipv4-unicast summary", "show router route-table must recommend SRL route-table command"),
            ("show router interface", "Interface Table (Router: default)", "show router interface must display interface table"),
            ("show router arp", "ARP Table (Router: default)", "show router arp must display ARP table"),
            ("show router bgp summary", "BGP Summary", "show router bgp summary must display BGP summary table"),
            ("show router bgp summary", "re:\\d+\\s+\\d+\\s+\\d+\\s+\\S+\\s+\\d+/\\d+/\\d+\\s+\\(Evpn\\)", "show router bgp summary must align Rcv/Act/Sent (Evpn) inline on the neighbor row"),
            ("show router ospf neighbor", "Try SR Linux command: show network-instance default protocols ospf neighbor", "show router ospf neighbor must include valid SRL hint"),
            ("show router isis adjacency", "Try SR Linux command: show network-instance default protocols isis adjacency", "show router isis adjacency must include valid SRL hint"),
            ("show service service-using", "Services [Customer: All]", "show service service-using must display service table"),
            ("show service service-using", "NA", "show service service-using must display NA for CustomerID"),
            ("show service id mac-vrf-1 vxlan", "Egress VTEP, VNI", "show service id mac-vrf-1 vxlan must display VXLAN destinations"),
            ("show service id mac-vrf-1 vxlan destinations", "Egress VTEP, VNI", "show service id mac-vrf-1 vxlan destinations must display VXLAN destinations"),
            ("show service id mac-vrf-1 vxlan destinations", "Try SR Linux command:", "show service id vxlan destinations must include SR Linux command hint"),
            ("show service id ip-vrf-1 vxlan destinations", "No Matching Entries", "show service id ip-vrf-1 vxlan destinations must handle L3 VXLAN ip-vrf cleanly"),
            ("show service fdb mac", "00:00:5E:00:01:01", "show service fdb mac must list IRB anycast MAC entry"),
            ("show service fdb mac", "irb-interface", "show service fdb mac must resolve destination leaf for IRB MAC"),
            ("show service id mac-vrf-1 fdb mac", "00:00:5E:00:01:01", "show service id mac-vrf-1 fdb mac must list IRB anycast MAC entry"),
            ("show service id mac-vrf-1 fdb mac", "Try SR Linux command:", "show service id fdb mac must include SR Linux command hint"),
            ("sros show", "Local commands:", "sros show must display subcommand help"),
            ("sros show service fdb mac", "00:00:5E:00:01:01", "sros show service fdb mac must list IRB anycast MAC entry"),
        ],
        "igp_positive_assertions": [
            ("show router ospf neighbor", "10.10.10.10", "show router ospf neighbor must display spine OSPF neighbor"),
            ("show router isis adjacency", "spine", "show router isis adjacency must display spine IS-IS adjacency"),
        ],
    },
    "Spine Multi-NOS": {
        "arg_key": "spine_node",
        "default_node": "spine",
        "commands": [
            "show version",
            "srl show version",
            "eos show version",
            "nxos show version",
            "junos show version",
            "sros show version",
            "eos show ip ospf neighbor",
            "nxos show ip ospf neighbor",
            "junos show ospf neighbor",
            "sros show router ospf neighbor",
        ],
        "submode_tests": [
            ("eos", ["show version"], "Nokia 7220 IXR-D2L"),
            ("nxos", ["show version"], "Nokia SR Linux Software"),
            ("junos", ["show version"], "Hostname: spine"),
            ("sros", ["show version"], "SRLinux-"),
        ],
        "negative_assertions": [
            ("show version", "Try SR Linux command:", "Default show version on spine (default_persona=none) must remain native SR Linux"),
        ],
        "positive_assertions": [
            ("show version", "Hostname", "Native show version on spine must display SR Linux version table"),
            ("srl show version", "Software Version", "srl show version on spine must display native SR Linux version"),
            ("eos show version", "Nokia 7220 IXR-D2L", "eos show version on spine must display Arista EOS version"),
            ("nxos show version", "Nokia SR Linux Software", "nxos show version on spine must display Cisco NX-OS version"),
            ("junos show version", "Hostname: spine", "junos show version on spine must display Juniper JUNOS version"),
            ("sros show version", "SRLinux-", "sros show version on spine must display Nokia SR OS version"),
        ],
    },
}

ERROR_PATTERNS = [
    "Traceback (most recent call last)",
    "AssertionError",
    "Cannot create node",
    "DataError",
    "PluginError",
    "Parsing error:",
    "Error: Failed to parse",
    "syntax error",
    "Unknown command",
    "unrecognized argument",
    "CLI command failed",
]

print_lock = threading.Lock()


def run_command(node, cmd):
    full_cmd = ["docker", "exec", node, "sr_cli", cmd]
    t0 = time.time()
    res = subprocess.run(full_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    dt = time.time() - t0
    return res.returncode, res.stdout, res.stderr, dt


def _apply_srl_config(node, candidate_lines):
    payload = "enter candidate\n" + "\n".join(candidate_lines) + "\ncommit now\nquit\n"
    res = subprocess.run(
        ["docker", "exec", "-i", node, "sr_cli"],
        input=payload,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if res.returncode != 0 or "Error:" in res.stdout or "Parsing error:" in res.stdout:
        raise RuntimeError(f"Config commit failed on {node}:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}")


def setup_igp_bfd_fixtures(args):
    """Dynamically enable OSPF, IS-IS (ipv4-unicast), and BFD on uplinks for live adjacency testing."""
    print("\n==> Applying temporary IGP (OSPF + IS-IS ipv4-unicast) & BFD fixtures across lab nodes...")
    node_specs = [
        (
            args.spine_node,
            "10.10.10.10",
            "49.0001.0100.1001.0010.00",
            ["ethernet-1/1.0", "ethernet-1/2.0", "ethernet-1/3.0", "ethernet-1/4.0"],
            ("ethernet-1/2.0", "192.168.10.4"),
        ),
        (args.arista_node, "1.1.1.1", "49.0001.0010.0100.1001.00", ["ethernet-1/1.0"], None),
        (
            args.cisco_node,
            "2.2.2.2",
            "49.0001.0020.0200.2002.00",
            ["ethernet-1/2.0"],
            ("ethernet-1/2.0", "192.168.10.5"),
        ),
        (args.juniper_node, "3.3.3.3", "49.0001.0030.0300.3003.00", ["ethernet-1/3.0"], None),
        (args.nokia_node, "4.4.4.4", "49.0001.0040.0400.4004.00", ["ethernet-1/4.0"], None),
    ]

    for node, rid, net_id, uplinks, bfd_spec in node_specs:
        lines = [
            f"set / network-instance default protocols ospf instance main admin-state enable version ospf-v2 router-id {rid}",
        ]
        for ul in uplinks:
            lines.append(
                f"set / network-instance default protocols ospf instance main area 0.0.0.0 interface {ul} interface-type point-to-point admin-state enable"
            )
        lines.extend([
            f"set / network-instance default protocols isis instance main admin-state enable level-capability L2 net [ {net_id} ]",
            "set / network-instance default protocols isis instance main ipv4-unicast admin-state enable",
        ])
        for ul in uplinks:
            lines.append(
                f"set / network-instance default protocols isis instance main interface {ul} circuit-type point-to-point admin-state enable ipv4-unicast admin-state enable"
            )
        if bfd_spec is not None:
            bfd_subif, bgp_nbr = bfd_spec
            lines.extend([
                f"set / bfd subinterface {bfd_subif} admin-state enable desired-minimum-transmit-interval 100000 required-minimum-receive 100000 detection-multiplier 3",
                f"set / network-instance default protocols bgp neighbor {bgp_nbr} failure-detection enable-bfd true fast-failover true",
            ])
        _apply_srl_config(node, lines)

    deadline = time.time() + 35
    while time.time() < deadline:
        _, out_ospf, _, _ = run_command(args.arista_node, "show network-instance default protocols ospf neighbor")
        _, out_isis, _, _ = run_command(args.juniper_node, "show network-instance default protocols isis adjacency")
        _, out_bfd, _, _ = run_command(args.cisco_node, "info from state bfd network-instance default peer * session-state")
        if ("full" in out_ospf.lower()) and ("up" in out_isis.lower()) and ("up" in out_bfd.lower()):
            print("==> OSPF, IS-IS, and BFD sessions are Up!")
            return
        time.sleep(1.5)
    print("==> Warning: Timed out waiting for all IGP/BFD sessions to reach Full/Up; proceeding with assertions.")


def teardown_igp_bfd_fixtures(args):
    """Roll back temporary OSPF, IS-IS, and BFD configuration cleanly."""
    print("\n==> Rolling back temporary IGP & BFD fixtures...")
    cleanup_specs = [
        (args.spine_node, ("ethernet-1/2.0", "192.168.10.4")),
        (args.arista_node, None),
        (args.cisco_node, ("ethernet-1/2.0", "192.168.10.5")),
        (args.juniper_node, None),
        (args.nokia_node, None),
    ]
    for node, bfd_spec in cleanup_specs:
        lines = [
            "delete / network-instance default protocols ospf",
            "delete / network-instance default protocols isis",
        ]
        if bfd_spec is not None:
            bfd_subif, bgp_nbr = bfd_spec
            lines.extend([
                f"delete / network-instance default protocols bgp neighbor {bgp_nbr} failure-detection",
                f"delete / bfd subinterface {bfd_subif}",
            ])
        try:
            _apply_srl_config(node, lines)
        except Exception as exc:
            print(f"Warning: Failed to roll back IGP/BFD fixtures on {node}: {exc}")


def run_suite(suite_name, suite, args, parallel=True):
    node = getattr(args, suite["arg_key"], suite["default_node"])
    commands = suite["commands"]
    neg_list = list(suite.get("negative_assertions", []))
    pos_list = list(suite.get("positive_assertions", []))
    if getattr(args, "with_igp_fixtures", False):
        pos_list.extend(suite.get("igp_positive_assertions", []))

    with print_lock:
        print(f"\n--- Running {suite_name} on container '{node}' ({len(commands)} commands) ---")

    passed = 0
    failed = 0
    failures = []

    for idx, cmd in enumerate(commands, 1):
        rc, stdout, stderr, dt = run_command(node, cmd)

        errors = []
        if rc != 0:
            errors.append(f"Non-zero exit code: {rc}")
        for pat in ERROR_PATTERNS:
            if pat in stdout or pat in stderr:
                errors.append(f"Found error pattern '{pat}'")

        if not stdout.strip() and not stderr.strip():
            errors.append("Output is completely empty")

        for neg_cmd, bad_pattern, failure_msg in neg_list:
            if cmd == neg_cmd:
                matched = bool(re.search(bad_pattern[3:], stdout)) if bad_pattern.startswith("re:") else (bad_pattern in stdout)
                if matched:
                    errors.append(f"Assertion failed: {failure_msg} (found '{bad_pattern}')")

        for pos_cmd, req_pattern, failure_msg in pos_list:
            if cmd == pos_cmd:
                matched = bool(re.search(req_pattern[3:], stdout)) if req_pattern.startswith("re:") else (req_pattern in stdout)
                if not matched:
                    errors.append(f"Assertion failed: {failure_msg} (missing '{req_pattern}')")

        prefix = f"[{node}] " if parallel else ""
        with print_lock:
            if errors:
                failed += 1
                status = "FAIL"
                failures.append({
                    "suite": suite_name,
                    "node": node,
                    "command": cmd,
                    "errors": errors,
                    "stdout": stdout,
                    "stderr": stderr,
                })
                print(f"  {prefix}[{idx:2d}/{len(commands):2d}] {cmd:<44} -> {status} ({dt:.2f}s) - {'; '.join(errors)}")
            else:
                passed += 1
                status = "PASS"
                print(f"  {prefix}[{idx:2d}/{len(commands):2d}] {cmd:<44} -> {status} ({dt:.2f}s)")

    submode_tests = suite.get("submode_tests", [])
    for submode, subcmds, expected in submode_tests:
        cmds = [subcmds] if isinstance(subcmds, str) else list(subcmds)
        test_display = f"{submode} -> {' ; '.join(cmds)}"
        full_cmd = ["docker", "exec", "-i", node, "sr_cli"]
        input_str = f"{submode}\n" + "\n".join(cmds) + "\npwc\nexit\n"
        t0 = time.time()
        res = subprocess.run(full_cmd, input=input_str, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        dt = time.time() - t0
        errors = []
        if res.returncode != 0:
            errors.append(f"Non-zero exit code: {res.returncode}")
        for pat in ERROR_PATTERNS:
            if pat in res.stdout or pat in res.stderr:
                errors.append(f"Found error pattern '{pat}'")
        if expected not in res.stdout:
            errors.append(f"Expected pattern '{expected}' missing from submode output")
        if submode not in [line.strip() for line in res.stdout.splitlines()]:
            errors.append(f"Submode '{submode}' was not retained as present working context (pwc check failed)")

        prefix = f"[{node}] " if parallel else ""
        with print_lock:
            if errors:
                failed += 1
                status = "FAIL"
                failures.append({
                    "suite": suite_name,
                    "node": node,
                    "command": f"submode: {test_display}",
                    "errors": errors,
                    "stdout": res.stdout,
                    "stderr": res.stderr,
                })
                print(f"  {prefix}[submode] {test_display:<39} -> {status} ({dt:.2f}s) - {'; '.join(errors)}")
            else:
                passed += 1
                status = "PASS"
                print(f"  {prefix}[submode] {test_display:<39} -> {status} ({dt:.2f}s)")

    for label, lines, req_patterns, forbidden_pwc_lines in suite.get("session_tests", []):
        full_cmd = ["docker", "exec", "-i", node, "sr_cli"]
        input_str = "\n".join(lines) + "\n"
        t0 = time.time()
        res = subprocess.run(full_cmd, input=input_str, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        dt = time.time() - t0
        errors = []
        if res.returncode != 0:
            errors.append(f"Non-zero exit code: {res.returncode}")
        for pat in ERROR_PATTERNS:
            if pat in res.stdout or pat in res.stderr:
                errors.append(f"Found error pattern '{pat}'")
        for req in req_patterns:
            if req not in res.stdout:
                errors.append(f"Missing expected output '{req}'")
        out_lines = {ln.strip() for ln in res.stdout.splitlines()}
        for bad_line in forbidden_pwc_lines:
            if bad_line in out_lines:
                errors.append(f"One-liner leaked submode '{bad_line}' into session PWC")

        prefix = f"[{node}] " if parallel else ""
        with print_lock:
            if errors:
                failed += 1
                failures.append({
                    "suite": suite_name,
                    "node": node,
                    "command": f"session: {label}",
                    "errors": errors,
                    "stdout": res.stdout,
                    "stderr": res.stderr,
                })
                print(f"  {prefix}[session] {label:<39} -> FAIL ({dt:.2f}s) - {'; '.join(errors)}")
            else:
                passed += 1
                print(f"  {prefix}[session] {label:<39} -> PASS ({dt:.2f}s)")

    return passed, failed, failures


def validate_recommended_srl_commands(target_nodes="leaf1-1", parallel=True):
    """
    Validate that all recommended SR Linux commands suggested in the output
    footers of MultiCLI show commands are syntactically valid and executable.
    """
    if isinstance(target_nodes, str):
        target_nodes = [target_nodes]

    recommended_commands = [
        "srl show version",
        "srl show interface brief",
        "srl show interface",
        "srl show interface detail",
        "srl show lag",
        "srl show system lldp neighbor",
        "show interface brief",
        "show interface",
        "show interface detail",
        "show interface ethernet-1/1 brief",
        "show interface ethernet-1/1 detail",
        "show interface ethernet-1/2 detail",
        "show system lldp neighbor",
        "show arpnd arp-entries",
        "show lag",
        "show network-instance default protocols bgp neighbor",
        "show network-instance default protocols bgp summary",
        "show network-instance default protocols bgp routes evpn route-type 1 summary",
        "show network-instance default protocols bgp routes evpn route-type 2 summary",
        "show network-instance default protocols bgp routes evpn route-type 3 summary",
        "show network-instance default protocols bgp routes evpn route-type 4 summary",
        "show network-instance default protocols bgp routes evpn route-type 5 summary",
        "show network-instance default route-table ipv4-unicast summary",
        "show network-instance default route-table summary",
        "show network-instance summary",
        "show network-instance bridge-table mac-table all",
        "show network-instance default protocols ospf neighbor",
        "show network-instance default protocols isis adjacency",
        "show network-instance default protocols ospf interface",
        "show system network-instance ethernet-segments",
        "show version",
        "info from state system name",
        "info from state system clock",
        "show platform",
        "show platform environment",
        "show platform chassis",
        "info from state system information",
        "info from state bfd",
        "show network-instance * vxlan-interface",
        "show tunnel-interface vxlan-interface bridge-table unicast-destinations destination",
    ]

    def _validate_node(target_node):
        node_passed = 0
        node_failed = 0
        node_failures = []
        with print_lock:
            print(f"\n--- Validating {len(recommended_commands)} Recommended SR Linux Commands on '{target_node}' ---")
        for idx, cmd in enumerate(recommended_commands, 1):
            rc, stdout, stderr, dt = run_command(target_node, cmd)
            out = stdout + stderr
            errors = []
            if rc != 0:
                errors.append(f"Non-zero exit code: {rc}")
            if "usage: show" in out:
                errors.append("Command printed 'usage: show' (incomplete token)")
            if "Parsing error" in out:
                errors.append("Parsing error in SR Linux syntax")
            if "Unknown command" in out:
                errors.append("Unknown command in SR Linux CLI")
            if not stdout.strip() and not stderr.strip() and "isis" not in cmd:
                errors.append("Output is completely empty")

            with print_lock:
                if errors:
                    node_failed += 1
                    node_failures.append({
                        "suite": "Recommended SRL Commands",
                        "node": target_node,
                        "command": cmd,
                        "errors": errors,
                        "stdout": stdout,
                        "stderr": stderr,
                    })
                    print(f"  [{target_node}] [{idx:2d}/{len(recommended_commands):2d}] {cmd:<60} -> FAIL ({dt:.2f}s) - {'; '.join(errors)}")
                else:
                    node_passed += 1
                    print(f"  [{target_node}] [{idx:2d}/{len(recommended_commands):2d}] {cmd:<60} -> PASS ({dt:.2f}s)")
        return node_passed, node_failed, node_failures

    total_passed = 0
    total_failed = 0
    failures = []

    if parallel and len(target_nodes) > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(target_nodes)) as executor:
            future_to_node = {executor.submit(_validate_node, node): node for node in target_nodes}
            for fut in concurrent.futures.as_completed(future_to_node):
                p, f, fails = fut.result()
                total_passed += p
                total_failed += f
                failures.extend(fails)
    else:
        for node in target_nodes:
            p, f, fails = _validate_node(node)
            total_passed += p
            total_failed += f
            failures.extend(fails)

    return total_passed, total_failed, failures


def _get_mgmt_ip(node):
    res = subprocess.run(
        ["docker", "inspect", node],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    info = json.loads(res.stdout)[0]
    networks = info.get("NetworkSettings", {}).get("Networks", {})
    for net in networks.values():
        ip = net.get("IPAddress")
        if ip:
            return ip
    raise RuntimeError(f"No IPv4 management address found for container '{node}'")


def _run_ssh_cli(host_ip, username, password, command, timeout=25.0):
    t0 = time.time()
    pid, fd = pty.fork()
    if pid == 0:
        os.execvp(
            "ssh",
            [
                "ssh",
                "-tt",
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "PubkeyAuthentication=no",
                "-o", "PreferredAuthentications=password,keyboard-interactive",
                "-o", "LogLevel=ERROR",
                f"{username}@{host_ip}",
            ],
        )

    buf = ""
    sent_pw = False
    sent_cmds = False
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 220, 0, 0))
        deadline = time.time() + timeout
        while time.time() < deadline:
            rlist, _, _ = select.select([fd], [], [], 0.25)
            if fd in rlist:
                try:
                    chunk = os.read(fd, 8192).decode("utf-8", errors="replace")
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk
                if not sent_pw and "assword:" in buf:
                    os.write(fd, (password + "\n").encode("utf-8"))
                    sent_pw = True
                elif sent_pw and not sent_cmds and "--{" in buf and "}--" in buf:
                    os.write(fd, f"environment pagination off\n{command}\nquit\n".encode("utf-8"))
                    sent_cmds = True
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        _, status = os.waitpid(pid, 0)

    clean = ANSI_RE.sub("", buf)
    rc = os.waitstatus_to_exitcode(status) if hasattr(os, "waitstatus_to_exitcode") else (status >> 8)
    return rc, clean, time.time() - t0


def validate_user_personas(target_nodes="leaf1-1", parallel=True):
    """
    Validate per-user CLI personas (auser, cnxuser, juser, nokuser) over real SSH
    (PAM-authenticated AAA sessions) when both /etc/opt/srlinux/cli/plugins and
    ~/cli/plugins are present simultaneously.
    """
    if isinstance(target_nodes, str):
        target_nodes = [target_nodes]

    persona_tests = [
        ("auser", "auser", "show version", ["Nokia 7220 IXR-D2L", "Try SR Linux command: srl show version"], ["Software image version: N/A"]),
        ("auser", "auser", "srl show version | grep Software", ["Software Version"], ["Try SR Linux command:"]),
        ("cnxuser", "cnxuser", "show lldp neighbors", ["spine", "Total entries displayed: 1"], ["Total entries displayed: 0"]),
        ("cnxuser", "cnxuser", "srl show interface brief | grep ethernet-1/1", ["ethernet-1/1"], ["Eth1/1"]),
        ("juser", "juser", "show bgp summary", ["inet.0", "Try SR Linux command: show network-instance default protocols bgp neighbor"], []),
        ("nokuser", "nokuser", "show router bgp summary", ["BGP Admin State", "Try SR Linux command: show network-instance default protocols bgp summary"], []),
        ("nokuser", "nokuser", "show service fdb mac", ["00:00:5E:00:01:01", "irb-interface"], ["No. of Entries in FDB: 0"]),
        ("nokuser", "nokuser", "srl show system lldp neighbor", ["spine", "Neighbor System Name"], ["LLDP Remote System Information"]),
    ]

    def _validate_node_personas(target_node):
        node_passed = 0
        node_failed = 0
        node_failures = []
        mgmt_ip = _get_mgmt_ip(target_node)
        with print_lock:
            print(f"\n--- Validating {len(persona_tests)} Per-User SSH CLI Persona Commands on '{target_node}' ({mgmt_ip}) ---")
        for idx, (user, pw, cmd, pos_pats, neg_pats) in enumerate(persona_tests, 1):
            rc, out, dt = _run_ssh_cli(mgmt_ip, user, pw, cmd)
            errors = []
            if rc != 0:
                errors.append(f"Non-zero SSH exit code: {rc}")
            for pat in ERROR_PATTERNS:
                if pat in out:
                    errors.append(f"Found error pattern '{pat}'")
            for req in pos_pats:
                if req not in out:
                    errors.append(f"Missing expected output '{req}'")
            for bad in neg_pats:
                if bad in out:
                    errors.append(f"Found unexpected output '{bad}'")

            display_cmd = f"ssh {user}@{target_node} \"{cmd}\""
            with print_lock:
                if errors:
                    node_failed += 1
                    node_failures.append({
                        "suite": "Per-User CLI Personas (SSH)",
                        "node": target_node,
                        "command": display_cmd,
                        "errors": errors,
                        "stdout": out,
                        "stderr": "",
                    })
                    print(f"  [{target_node}] [{idx:2d}/{len(persona_tests):2d}] {display_cmd:<60} -> FAIL ({dt:.2f}s) - {'; '.join(errors)}")
                else:
                    node_passed += 1
                    print(f"  [{target_node}] [{idx:2d}/{len(persona_tests):2d}] {display_cmd:<60} -> PASS ({dt:.2f}s)")
        return node_passed, node_failed, node_failures

    total_passed = 0
    total_failed = 0
    failures = []

    if parallel and len(target_nodes) > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(target_nodes)) as executor:
            future_to_node = {executor.submit(_validate_node_personas, node): node for node in target_nodes}
            for fut in concurrent.futures.as_completed(future_to_node):
                p, f, fails = fut.result()
                total_passed += p
                total_failed += f
                failures.extend(fails)
    else:
        for node in target_nodes:
            p, f, fails = _validate_node_personas(node)
            total_passed += p
            total_failed += f
            failures.extend(fails)

    return total_passed, total_failed, failures


def validate(args):
    t_start = time.time()
    total_passed = 0
    total_failed = 0
    all_failures = []

    print("=" * 80)
    print("MultiCLI Comprehensive Automated Validation Test Suite")
    print("=" * 80)

    if getattr(args, "install", False):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        switch_script = os.path.join(script_dir, "..", "tools", "switch-multicli.sh")
        print("\n==> Installing MultiCLI personas to target nodes...")
        install_tasks = [
            ("leaf1-1", "arista_node", "arista"),
            ("leaf1-2", "cisco_node", "cisco"),
            ("leaf2-1", "juniper_node", "juniper"),
            ("leaf2-2", "nokia_node", "nokia"),
            ("spine", "spine_node", "none"),
        ]
        if not getattr(args, "sequential", False):
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futs = [
                    executor.submit(
                        subprocess.run,
                        [switch_script, "all", getattr(args, key, def_node), "--default", persona],
                        check=True,
                    )
                    for def_node, key, persona in install_tasks
                ]
                for f in futs:
                    f.result()
        else:
            for def_node, key, persona in install_tasks:
                subprocess.run(
                    [switch_script, "all", getattr(args, key, def_node), "--default", persona],
                    check=True,
                )
        time.sleep(1)

    igp_applied = False
    try:
        if getattr(args, "with_igp_fixtures", False):
            setup_igp_bfd_fixtures(args)
            igp_applied = True

        suites_to_run = list(TEST_SUITES.items())
        if getattr(args, "sequential", False):
            for s_name, s_data in suites_to_run:
                p, f, fails = run_suite(s_name, s_data, args, parallel=False)
                total_passed += p
                total_failed += f
                all_failures.extend(fails)
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(suites_to_run)) as executor:
                future_to_suite = {
                    executor.submit(run_suite, s_name, s_data, args, parallel=True): s_name
                    for s_name, s_data in suites_to_run
                }
                for fut in concurrent.futures.as_completed(future_to_suite):
                    p, f, fails = fut.result()
                    total_passed += p
                    total_failed += f
                    all_failures.extend(fails)

        leaf_nodes = list(dict.fromkeys([args.arista_node, args.cisco_node, args.juniper_node, args.nokia_node]))
        p_usr, f_usr, fails_usr = validate_user_personas(leaf_nodes, parallel=not getattr(args, "sequential", False))
        total_passed += p_usr
        total_failed += f_usr
        all_failures.extend(fails_usr)

        all_nodes = list(dict.fromkeys(leaf_nodes + [args.spine_node]))
        p_srl, f_srl, fails_srl = validate_recommended_srl_commands(all_nodes, parallel=not getattr(args, "sequential", False))
        total_passed += p_srl
        total_failed += f_srl
        all_failures.extend(fails_srl)
    finally:
        if igp_applied:
            teardown_igp_bfd_fixtures(args)

    elapsed_total = time.time() - t_start
    print("\n" + "=" * 80)
    print(f"Test Summary: Total={total_passed + total_failed} | Passed={total_passed} | Failed={total_failed} (Finished in {elapsed_total:.2f}s)")
    print("=" * 80)

    if all_failures:
        print(f"\nFAILED COMMANDS DETAILS ({len(all_failures)} failures):")
        for f in all_failures:
            print("-" * 60)
            print(f"Suite:   {f['suite']} (Node: {f['node']})")
            print(f"Command: {f['command']}")
            print(f"Errors:  {f['errors']}")
            if f["stderr"]:
                print(f"STDERR:\n{f['stderr']}")
            if f["stdout"]:
                print(f"STDOUT:\n{f['stdout']}")
        return False

    print("\nALL COMMANDS PASSED VALIDATION WITHOUT ERRORS!")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MultiCLI Automated Test Validation Suite")
    parser.add_argument("--arista-node", default="leaf1-1", help="Target node running Arista EOS persona (default: leaf1-1)")
    parser.add_argument("--cisco-node", default="leaf1-2", help="Target node running Cisco NX-OS persona (default: leaf1-2)")
    parser.add_argument("--juniper-node", default="leaf2-1", help="Target node running Juniper JUNOS persona (default: leaf2-1)")
    parser.add_argument("--nokia-node", default="leaf2-2", help="Target node running Nokia SR OS persona (default: leaf2-2)")
    parser.add_argument("--spine-node", default="spine", help="Target node running Multi-NOS spine persona (default: spine)")
    parser.add_argument("--install", action="store_true", help="Automatically configure each target node with tools/switch-multicli.sh before validation")
    parser.add_argument("--with-igp-fixtures", action="store_true", help="Temporarily configure OSPF, IS-IS (ipv4-unicast), and BFD adjacencies for live neighbor assertions and roll back afterward")
    parser.add_argument("--sequential", action="store_true", help="Run node test suites sequentially instead of in parallel")
    cli_args = parser.parse_args()

    success = validate(cli_args)
    sys.exit(0 if success else 1)
