# Custom CLI Plugins for Cisco NX-OS

MultiCLI allows users to execute familiar Cisco NX-OS commands on Nokia SR Linux switches with matching output and dynamic state learning.

## Supported Commands

### System & Hardware
| Command | Description |
|---|---|
| `show version` | System version, uptime, and hardware details |
| `show hostname` | System hostname |
| `show clock` | System clock and time zone |
| `show inventory` | Hardware inventory and chassis serials |
| `show environment [cooling\|power\|temperature]` | Fan speeds, power supplies, and temperature sensors |
| `show module` | Linecard, control module, and fabric status |
| `show processes cpu` | System and CPU utilization statistics |

### Interfaces & Layer 2
| Command | Description / Contributor |
|---|---|
| `show interface [<name>]` | Detailed interface operational state and counters |
| `show interface brief` | Brief summary of physical, LAG, and subinterfaces |
| `show interface status` | Port status, speed, duplex, and type |
| `show interface description` | Interface descriptions |
| `show interface transceiver [details]` | Optical transceiver diagnostics and DDM |
| `show ip interface brief` | IPv4 address and operational state per interface ([aaakpinar](https://github.com/aaakpinar)) |
| `show ipv6 interface brief` | IPv6 address and operational state per interface |
| `show port-channel summary` | LAG / Port-channel status and member ports |
| `show mac address-table` | MAC address table with VLAN, type, and age ([michelredondo](https://github.com/michelredondo)) |
| `show mac address-table instance <name>` | Filter MAC table by network-instance ([michelredondo](https://github.com/michelredondo)) |
| `show mac address-table vlan <id>` | Filter MAC table by VLAN ([michelredondo](https://github.com/michelredondo)) |
| `show mac address-table interface <name>` | Filter MAC table by interface ([michelredondo](https://github.com/michelredondo)) |
| `show mac address-table vni <vni_id>` | Filter MAC table by EVPN VNI ([michelredondo](https://github.com/michelredondo)) |
| `show vlan` | Configured VLANs, status, and member ports |

### Routing, Protocols & EVPN
| Command | Description / Contributor |
|---|---|
| `show ip route [vrf <name>]` | IPv4 routing table with next hops and protocols ([aaakpinar](https://github.com/aaakpinar)) |
| `show vrf` | VRF instances, state, and route distinguishers |
| `show ip arp` | ARP cache resolution table |
| `show ip bgp [vrf <name>] summary` | BGP neighbor summary, prefixes, and session states ([aaakpinar](https://github.com/aaakpinar)) |
| `show bfd neighbors` | BFD session states, intervals, and diagnostics |
| `show ip ospf neighbor` | OSPF neighbor adjacencies and states |
| `show ip ospf interface brief` | OSPF enabled interfaces, areas, and costs |
| `show lldp neighbors [detail]` | LLDP discovery neighbors and port information ([shashsha09](https://github.com/shashsha09)) |
| `show nve vni` | NVE VXLAN VNI mappings and states |
| `show nve peers` | NVE VTEP tunnel peers |
| `show vpc` | Virtual Port Channel / Multi-homing status |

## Usage & Testing

All commands above can be executed directly under `show ...` when Cisco NX-OS is the active persona (or when logged in as `cnxuser/cnxuser`), or via the `nxos` subtree (`nxos show ...` or interactive `nxos` mode) when multiple personas are installed. Because Cisco NX-OS overrides `show version`, `show interface`, and `show interface brief` at the root `show` tree, native SR Linux equivalents remain accessible via `srl show version`, `srl show interface [<name>] [detail]`, and `srl show interface brief`.

Deploy the Containerlab topology and log in to a switch configured with the Cisco NX-OS persona:

```bash
docker exec -it leaf1-2 sr_cli
```

Or switch any node on-the-fly using the helper script:
```bash
./tools/switch-multicli.sh cisco leaf1-2
```
