# Custom CLI Plugins for Juniper JUNOS

MultiCLI allows users to execute familiar Juniper JUNOS commands on Nokia SR Linux switches with matching output and dynamic state learning.

## Supported Commands

### System & Hardware
| Command | Description / Contributor |
|---|---|
| `show version` | JUNOS software version, model, and OS release info |
| `show system uptime` | Current time, boot time, uptime, and last commit info |
| `show system processes [summary\|brief\|extensive]` | CPU, memory, swap, and top active system processes |
| `show chassis hardware` | Chassis model, serial number, and hardware components |

### Interfaces & Switching
| Command | Description / Contributor |
|---|---|
| `show interfaces [<name>]` | Comprehensive interface statistics and operational parameters ([hendriksthomas](https://github.com/hendriksthomas)) |
| `show interfaces brief [<name>]` | Physical link, flags, and logical interface IP addresses ([hendriksthomas](https://github.com/hendriksthomas)) |
| `show interfaces terse [<name>]` | Compact table of interfaces, admin/link status, and addresses ([hendriksthomas](https://github.com/hendriksthomas)) |
| `show ethernet-switching table` | MAC table with VLAN, MAC, age, and logical interface ([michelredondo](https://github.com/michelredondo)) |
| `show ethernet-switching table instance <instance_name>` | Filter MAC table by routing/bridge instance ([michelredondo](https://github.com/michelredondo)) |
| `show ethernet-switching table vlan <vlan_id>` | Filter MAC table by VLAN ([michelredondo](https://github.com/michelredondo)) |
| `show ethernet-switching table interface <name>` | Filter MAC table by interface ([michelredondo](https://github.com/michelredondo)) |
| `show vlans` | Active VLANs, routing instances, 802.1Q tags, and member ports |
| `show lacp interfaces` | LACP aggregated interfaces, actor/partner states, and mux flags |

### Routing & Protocols
| Command | Description / Contributor |
|---|---|
| `show route` | Full IPv4 routing table with destinations, routes, and next-hops |
| `show route summary` | Route summary counts (Direct, Local, BGP, Static, OSPF, IS-IS) |
| `show bgp summary` | BGP groups, peer states, packet counters, and route tables |
| `show ospf neighbor` | OSPF neighbor adjacencies, interface, and router ID |
| `show isis adjacency` | IS-IS adjacency state, level, and hold times |
| `show lldp neighbors` | LLDP neighbors, chassis ID, and system names |
| `show arp` / `show arp no-resolve` | ARP cache resolution entries |

## Usage & Testing

All commands above can be executed directly under `show ...` when Juniper JUNOS is the active persona (or when logged in as `juser/juser`), or via the `junos` subtree (`junos show ...` or interactive `junos` mode) when multiple personas are installed. Native SR Linux `show version` remains accessible at any time via `srl show version`.

Deploy the Containerlab topology and log in to a switch configured with the Juniper JUNOS persona:

```bash
docker exec -it leaf2-1 sr_cli
```

Or switch any node on-the-fly using the helper script:
```bash
./tools/switch-multicli.sh juniper leaf2-1
```

> [!NOTE]
> `plugins/main_juniper.py` loads helper modules from the sibling `eth_switch`, `interface`, `routing`, and `system` directories.

## `show_interfaces.py`

This script introduces a custom command that allows the user to visualize state and configuration of interfaces in the SR Linux system in a manner similar to what is rendered by JunOS' `show interfaces` command. Both native SR Linux interface names (`ethernet-1/3`) and Junos-style names (`et-0/0/2`, `ae1`, `lo0.0`) are accepted.

### Command syntax (all options)

```
/show interfaces <name>
/show interfaces <name> terse
/show interfaces terse <name>
/show interfaces <name> brief
/show interfaces brief <name>
```

Where `<name>` is either omitted or identifies a (sub-)interface on the system.

<details>
    <summary>Example execution (terse)</summary>

    --{ running }--[  ]--
    A:admin@leaf2-1# show interfaces ethernet-1/3 terse
    Interface               Admin Link Proto    Local                 Remote
    et-0/0/2                up    up
    et-0/0/2.0              up    up   inet     10.3.3.1/24
                                    inet6    fd00::3:3:1/104
                                                fd00::33:33:1/104
                                                fd00::333:333:1/104
                                                fd00::3333:3333:1/104
                                                fe80::1880:ff:feff:3/64
    ----------------------------------------------------------------------------------------------------
    Try SR Linux command: show interface

</details>

<details>
    <summary>Example execution (brief)</summary>

    --{ running }--[  ]--
    A:admin@leaf2-1# show interfaces brief ethernet-1/3
    Physical interface: et-0/0/2, Enabled, Physical link is Up
    Link-level type: Ethernet, MTU: 9232, MRU: 9240, Unknown mode, Speed: 25G, Loopback: Disabled, Source filtering: N/A,  Flow control: Disabled, Auto-negotiation: Enabled, Remote fault: Online
    Device flags   : Present Running Up
    Interface flags: Up
    Link flags     : None


    Logical interface et-0/0/2.0
        Flags: Up Encapsulation: ENET2
        inet  10.3.3.1/24
        inet6 fd00::3:3:1/104
            fd00::33:33:1/104
            fd00::333:333:1/104
            fd00::3333:3333:1/104
            fe80::1880:ff:feff:3/64

    ----------------------------------------------------------------------------------------------------
    Try SR Linux command: show interface detail

</details>

<details>
    <summary>Example execution (regular)</summary>

    --{ running }--[  ]--
    A:admin@leaf2-1# show interfaces ethernet-1/3
    Physical interface: et-0/0/2, Enabled, Physical link is Up
    Interface index: 81918, SNMP ifIndex: N/A
    Link-level type: Ethernet, MTU: 9232, MRU: 9240, Unknown mode, Speed: 25G, BPDU Error: N/A, Loop Detect PDU Error: N/A, Ethernet-Switching Error: N/A, MAC-REWRITE Error: N/A, Loopback: Disabled, Source filtering: N/A,Flow control: Disabled, Auto-negotiation: Enabled, Remote fault: Online
    Pad to minimum frame size: N/A
    Device flags   : Present Running Up
    Interface flags: Up
    Link flags     : None
    CoS queues     : 8 supported, 8 maximum usable queues
    Current address: 1A:80:00:FF:00:03, Hardware address: 1A:80:00:FF:00:03
    Last flapped   : 2025-04-17 11:40:48 UTC (0w0d 01:20 ago)
    Input rate     : 0 bps (Uncalculated pps)
    Output rate    : 0 bps (Uncalculated pps)
    Active alarms  : N/A
    Active defects : N/A
    PCS statistics                      Seconds
        Bit errors                             0
        Errored blocks                         0
    Ethernet FEC statistics              Errors
        FEC Corrected Errors                   N/A
        FEC Uncorrected Errors                 N/A
        FEC Corrected Errors Rate              N/A
        FEC Uncorrected Errors Rate            N/A
    Interface transmit statistics: Disabled

    Logical interface et-0/0/2.0 (Index 65537) (SNMP ifIndex N/A)
        Flags: Up Encapsulation: ENET2
        Input packets : 55
        Output packets: 44
        Protocol inet, MTU: 1500
        Max nh cache: N/A, New hold nh limit: N/A, Curr nh cnt: 1, Curr new hold cnt: N/A, NH drop cnt: N/A
        Flags: Sendbcast-pkt-to-re
        Addresses, Flags: Primary Preferred
            Destination: 10.3.3.0/24, Local: 10.3.3.1, Broadcast: 10.3.3.255
        Protocol inet6, MTU: 1500
        Max nh cache: N/A, New hold nh limit: N/A, Curr nh cnt: 2, Curr new hold cnt: N/A, NH drop cnt: N/A
        Addresses, Flags: Primary Preferred
            Destination: fd00::3:0:0/104, Local: fd00::3:3:1
        Addresses, Flags: Preferred
            Destination: fd00::33:0:0/104, Local: fd00::33:33:1
        Addresses, Flags: Preferred
            Destination: fd00::333:300:0/104, Local: fd00::333:333:1
        Addresses, Flags: Preferred
            Destination: fd00::3333:3300:0/104, Local: fd00::3333:3333:1
        Addresses, Flags: Preferred
            Destination: fe80::/64, Local: fe80::1880:ff:feff:3
        Protocol multiservice, MTU: Unlimited

    ----------------------------------------------------------------------------------------------------
    Try SR Linux command: show interface detail

</details>
