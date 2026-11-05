# Custom CLI Plugins for Arista EOS

MultiCLI allows users to execute familiar Arista EOS commands on Nokia SR Linux switches with matching output and dynamic state learning.

## Supported Commands

### System & Hardware
| Command | Description |
|---|---|
| `show version` | Arista EOS software version, uptime, memory, and model info |
| `show hostname` | System FQDN and hostname |
| `show clock` | System clock and timezone |
| `show inventory` | System inventory and hardware serials |
| `show environment [cooling\|power\|temperature]` | Fan speeds, power supplies, and temperature sensors |
| `show module` | Linecard, supervisor, and fabric module status |
| `show processes top once` | Process table and memory/swap statistics |

### Interfaces & Layer 2
| Command | Description / Contributor |
|---|---|
| `show ip interface brief` | IPv4 address and operational status per interface |
| `show interfaces [<name>]` | Detailed interface operational state and counters ([mfzhsn](https://github.com/mfzhsn)) |
| `show interfaces status` | Interface status, VLAN, duplex, speed, and type ([mfzhsn](https://github.com/mfzhsn)) |
| `show interfaces description` | Interface descriptions and line protocol status |
| `show interfaces transceiver [detail]` | Optical transceiver diagnostics and DDM |
| `show port-channel summary` | LAG / Port-channel summary with protocol and member ports |
| `show mac address-table` | MAC address table with VLAN, type, and interface |
| `show vlan` | Configured VLANs, status, and member ports |
| `show mlag` | MLAG operational status, peer link, and multi-homing ES |

### Routing & Protocols
| Command | Description / Contributor |
|---|---|
| `show ip route [vrf <name>]` | Routing table with protocol codes (`C`, `S`, `B E`, `B I`, `O`, `I`) and ECMP next-hops |
| `show vrf` | VRF routing instances, protocols, and interfaces |
| `show arp` / `show ip arp` | ARP cache resolution table ([mfzhsn](https://github.com/mfzhsn)) |
| `show ip bgp [vrf <name>] summary` | BGP IPv4 unicast neighbor summary ([sajusal](https://github.com/sajusal)) |
| `show bgp evpn summary` | BGP EVPN neighbor summary ([sajusal](https://github.com/sajusal)) |
| `show bgp evpn route-type [auto-discovery\|mac-ip\|imet\|ethernet-segment\|ip-prefix]` | BGP EVPN route-type specific outputs ([sajusal](https://github.com/sajusal)) |
| `show ip ospf neighbor` | OSPF neighbor adjacencies and states |
| `show ip ospf interface brief` | OSPF interface state, cost, and area |
| `show isis neighbors` | IS-IS neighbor adjacencies and hold times |
| `show lldp neighbors [detail]` | LLDP discovery neighbors and details |

## Usage & Testing

All commands above can be run directly under `show ...` when Arista EOS is the active persona (or when logged in as `auser/auser`), or via the `eos` subtree (`eos show ...` or interactive `eos` mode) when multiple personas are installed. Native SR Linux `show version` remains accessible at any time via `srl show version`.

Deploy the Containerlab topology and log in to a switch configured with the Arista EOS persona:

```bash
docker exec -it leaf1-1 sr_cli
```

Or switch any node on-the-fly using the helper script:
```bash
./tools/switch-multicli.sh arista leaf1-1
```

## Custom CLI Plugin scripts

This folder contains custom CLI python scripts for EOS commands.

The scripts are arranged in this format. `main_arista.py` resolves imports relative to its installed `cli` directory (`/home/auser/cli` or `/etc/opt/srlinux/cli`):

```
/etc/opt/srlinux/cli
├── bgp
│   └── bgp_evpn_report.py            # Handles BGP EVPN Route Type and summary reports
│
├── interface
│   ├── arista_arp_details.py         # Parses and formats ARP entries
│   ├── arista_interface_detail.py    # Displays detailed interface info (Arista style)
│   ├── arista_interface_reports.py   # Interface brief, transceiver, description, LLDP, LAG
│   └── arista_interface_status.py    # Displays brief interface status (Arista style)
│
├── ip
│   └── arista_ip_bgp_report.py       # Generates standard BGP summary reports
│
├── plugins
│   └── main_arista.py                # Loads Arista-style CLI plugins (`show` + `eos` + `srl`)
│
├── routing
│   └── arista_routing_reports.py     # IP route, VRF, VLAN, MAC, OSPF, IS-IS, MLAG
│
└── system
    └── arista_system_reports.py      # Version, hostname, clock, inventory, environment
```

### Verification examples

**Interface Status**:
```
show interfaces status
eos show interfaces status
```

**Interface Details**:
```
show interfaces Ethernet1/1
show interfaces
```

**ARP Details**:
```
show ip arp
show arp --interface Ethernet1/1
```

**Native SR Linux Version (when Arista overrides `show version`)**:
```
srl show version
```
