#!/usr/bin/python
###########################################################################
# Description: MultiCLI Arista EOS Routing Reports
# Commands: show ip route, show vrf, show vlan, show mac address-table,
#           show ip ospf neighbor, show isis neighbors
# Copyright (c) 2026 Nokia
###########################################################################

import ipaddress
import re
from srlinux.location import build_path
from srlinux.schema.data_store import DataStore


def _safe_get(node, attr, default=None):
    """Safely read an attribute from an SR Linux Data object without raising DataError."""
    if node is None:
        return default
    try:
        val = getattr(node, attr)
        return val if val is not None else default
    except Exception:
        return default


def format_mac_cisco_arista(mac_str):
    if not mac_str:
        return ""
    clean = str(mac_str).replace(':', '').replace('-', '').replace('.', '').lower()
    if len(clean) == 12:
        return f"{clean[0:4]}.{clean[4:8]}.{clean[8:12]}"
    return mac_str

def format_arista_intf(name, short=False):
    if not name:
        return ""
    name = str(name)
    if name.startswith('irb'):
        return name
    if name.endswith('.0'):
        name = name[:-2]
    if name.startswith('ethernet-'):
        num = name.replace('ethernet-', '')
        return f"Et{num}" if short else f"Ethernet{num}"
    if name.startswith('mgmt'):
        num = name.replace('mgmt', '') or '1'
        return f"Ma{num}" if short else f"Management{num}"
    if name.startswith('lag'):
        num = name.replace('lag', '')
        return f"Po{num}" if short else f"Port-Channel{num}"
    if name.startswith(('lo', 'system')):
        num = name.replace('system', '').replace('lo', '') or '0'
        return f"Lo{num}" if short else f"Loopback{num}"
    if name.startswith('irb'):
        return name
    return name

class AristaRoutingReports:
    """Handles Arista EOS routing show commands."""

    def show_ip_route(self, state, output, vrf='default'):
        """Display Arista EOS style 'show ip route [vrf <vrf>]'."""
        lines = [
            f"VRF name: {vrf}",
            "Codes: C - connected, S - static, K - kernel,",
            "       O - OSPF, IA - OSPF inter area, E1 - OSPF external type 1,",
            "       E2 - OSPF external type 2, N1 - OSPF NSSA external type 1,",
            "       N2 - OSPF NSSA external type2, B I - iBGP, B E - eBGP,",
            "       R - RIP, I L1 - ISIS level 1, I L2 - ISIS level 2,",
            "       O3 - OSPFv3, A B - BGP Aggregate, A O - OSPF Summary,",
            "       NG - Nexthop Group Static Route, V - VXLAN Control Service",
            ""
        ]

        routes = []
        nh_map = {}
        nhg_map = {}
        bgp_peer_types = {}
        evpn_peer_types = set()

        try:
            bgp_path = build_path('/network-instance[name=*]/protocols/bgp')
            bgp_data = state.server.get_data_store(DataStore.State).get_data(bgp_path, recursive=True)
            for ni in bgp_data.network_instance.items():
                ni_peers = {}
                if hasattr(ni, 'protocols') and ni.protocols.exists():
                    bgp_container = _safe_get(ni.protocols.get(), 'bgp', None)
                    if bgp_container and hasattr(bgp_container, 'exists') and bgp_container.exists():
                        bgp_obj = bgp_container.get()
                        if hasattr(bgp_obj, 'neighbor'):
                            for nbr in bgp_obj.neighbor.items():
                                p_addr = str(_safe_get(nbr, 'peer_address', '')).strip()
                                p_type = str(_safe_get(nbr, 'peer_type', '')).strip().lower()
                                if p_addr and p_type:
                                    ni_peers[p_addr] = p_type
                                if p_type and hasattr(nbr, 'afi_safi'):
                                    for afi in nbr.afi_safi.items():
                                        if str(_safe_get(afi, 'afi_safi_name', '')).lower() == 'evpn':
                                            if str(_safe_get(afi, 'admin_state', '')).lower() == 'enable':
                                                evpn_peer_types.add(p_type)
                bgp_peer_types[ni.name] = ni_peers
        except Exception:
            pass

        try:
            rt_path = build_path('/network-instance[name={name}]/route-table', name=vrf)
            rt_data = state.server.get_data_store(DataStore.State).get_data(rt_path, recursive=True)

            # Build next-hop index to IP/interface mapping
            for nh in rt_data.get_descendants('/network-instance/route-table/next-hop'):
                nh_idx = _safe_get(nh, 'index', None)
                if nh_idx is None:
                    continue

                nh_type = _safe_get(nh, 'type', None)
                ip = _safe_get(nh, 'ip_address', None)
                subif = _safe_get(nh, 'subinterface', None)
                resolving_nhg = None

                if nh_type == 'tunnel' and hasattr(nh, 'tunnel'):
                    try:
                        t = nh.tunnel.get()
                        pfx = _safe_get(t, 'ip_prefix', None)
                        if pfx and not ip:
                            ip = str(pfx).split('/')[0]
                    except Exception:
                        pass

                if nh_type == 'indirect' and hasattr(nh, 'indirect'):
                    try:
                        ind = nh.indirect.get()
                        rr = _safe_get(ind, 'resolving_route', None)
                        if rr:
                            resolving_nhg = _safe_get(rr.get(), 'next_hop_group', None)
                    except Exception:
                        pass

                nh_map[str(nh_idx)] = {
                    'ip': str(ip) if ip else None,
                    'interface': str(subif) if subif else None,
                    'resolving_nhg': str(resolving_nhg) if resolving_nhg is not None else None,
                }

            # Build next-hop group mapping
            for nhg in rt_data.get_descendants('/network-instance/route-table/next-hop-group'):
                nhg_idx = _safe_get(nhg, 'index', None)
                if nhg_idx is not None and hasattr(nhg, 'next_hop'):
                    hops = []
                    for nh_item in nhg.next_hop.items():
                        target_nh = _safe_get(nh_item, 'next_hop', None)
                        if target_nh is not None and str(target_nh) in nh_map:
                            hops.append(nh_map[str(target_nh)])
                    nhg_map[str(nhg_idx)] = hops

            # Resolve indirect next-hop interfaces via resolving route's next-hop group
            for nh_info in nh_map.values():
                if not nh_info['interface'] and nh_info.get('resolving_nhg'):
                    target_hops = nhg_map.get(nh_info['resolving_nhg'], [])
                    for th in target_hops:
                        if th.get('interface'):
                            nh_info['interface'] = th['interface']
                            break

            vrf_peers = bgp_peer_types.get(vrf, {})

            for r in rt_data.get_descendants('/network-instance/route-table/ipv4-unicast/route'):
                pfx = _safe_get(r, 'ipv4_prefix', None)
                if not pfx:
                    continue
                rtype = str(_safe_get(r, 'route_type', '')).lower()
                rowner = str(_safe_get(r, 'route_owner', '')).lower()
                metric = _safe_get(r, 'metric', 0)
                pref = _safe_get(r, 'preference', 0)
                nhg_id = _safe_get(r, 'next_hop_group', None)
                route_hops = nhg_map.get(str(nhg_id), [])

                if 'connected' in rowner or 'direct' in rowner or rtype in ('local', 'connected'):
                    code = ' C   '
                elif 'host' in rtype or 'local' in rowner:
                    code = ' L   '
                elif 'bgp' in rowner or 'bgp' in rtype:
                    matched_peer_type = None
                    for hop in route_hops:
                        hop_ip = hop.get('ip')
                        if hop_ip and hop_ip in vrf_peers:
                            matched_peer_type = vrf_peers[hop_ip]
                            break
                    if matched_peer_type == 'ebgp':
                        code = ' B E '
                    elif matched_peer_type == 'ibgp':
                        code = ' B I '
                    elif 'evpn' in rtype or 'evpn' in rowner:
                        code = ' B E ' if (evpn_peer_types == {'ebgp'}) else ' B I '
                    else:
                        v4_types = {pt for ip_k, pt in vrf_peers.items() if ':' not in ip_k}
                        code = ' B E ' if (v4_types == {'ebgp'}) else ' B I '
                elif 'aggregate' in rowner or 'aggregate' in rtype:
                    code = ' A B '
                elif 'ospfv3' in rowner or 'ospfv3' in rtype:
                    code = ' O3  '
                elif 'ospf' in rowner or 'ospf' in rtype:
                    code = ' O   '
                elif 'isis' in rowner or 'isis' in rtype:
                    code = ' I L2'
                elif 'static' in rowner or 'static' in rtype:
                    code = ' S   '
                else:
                    code = ' ?   '

                routes.append({
                    'prefix': pfx,
                    'code': code,
                    'pref': pref,
                    'metric': metric,
                    'owner': rowner,
                    'type': rtype,
                    'hops': route_hops
                })
        except Exception:
            pass

        default_route = next((r for r in routes if r['prefix'] == '0.0.0.0/0'), None)
        if default_route:
            lines.append("Gateway of last resort is set\n")
        else:
            lines.append("Gateway of last resort is not set\n")

        # Sort routes by IP network
        try:
            sorted_routes = sorted(routes, key=lambda x: ipaddress.ip_network(x['prefix']).network_address)
        except Exception:
            sorted_routes = routes

        for r in sorted_routes:
            hops = r.get('hops', [])
            is_conn = ('C' in r['code'] or 'L' in r['code'])
            if is_conn:
                if hops and hops[0].get('interface'):
                    disp_intf = format_arista_intf(hops[0]['interface'], short=False)
                    lines.append(f"{r['code']:<5} {r['prefix']} is directly connected, {disp_intf}")
                else:
                    lines.append(f"{r['code']:<5} {r['prefix']} is directly connected")
            else:
                if hops and hops[0].get('ip'):
                    first_prefix = f"{r['code']:<5} {r['prefix']} [{r['pref']}/{r['metric']}] "
                    nh_ip = hops[0]['ip']
                    nh_intf = f", {format_arista_intf(hops[0]['interface'], short=False)}" if hops[0].get('interface') else ""
                    lines.append(f"{first_prefix}via {nh_ip}{nh_intf}")
                    indent = " " * len(first_prefix)
                    for extra_hop in hops[1:]:
                        if extra_hop.get('ip'):
                            eh_intf = f", {format_arista_intf(extra_hop['interface'], short=False)}" if extra_hop.get('interface') else ""
                            lines.append(f"{indent}via {extra_hop['ip']}{eh_intf}")
                else:
                    lines.append(f"{r['code']:<5} {r['prefix']} [{r['pref']}/{r['metric']}]")

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line(f"Try SR Linux command: show network-instance {vrf} route-table ipv4-unicast summary")

    def show_vrf(self, state, output):
        """Display Arista EOS style 'show vrf'."""
        lines = [
            "Maximum number of vrfs allowed: 4095",
            f"  {'Vrf':<9} {'RD':<14} {'Protocols':<14} {'State':<19} {'Interfaces'}",
            f"--------- -------------- -------------- ------------------- ---------------------"
        ]
        rd_by_ni = {}
        try:
            bv_p = build_path('/network-instance[name=*]/protocols/bgp-vpn')
            bv_data = state.server.get_data_store(DataStore.State).get_data(bv_p, recursive=True)
            for ni in bv_data.network_instance.items():
                if hasattr(ni, 'protocols') and ni.protocols.exists():
                    p_obj = ni.protocols.get()
                    bgp_vpn = _safe_get(p_obj, 'bgp_vpn', None)
                    if bgp_vpn and hasattr(bgp_vpn, 'exists') and bgp_vpn.exists():
                        bv_obj = bgp_vpn.get()
                        if hasattr(bv_obj, 'bgp_instance'):
                            for bi in bv_obj.bgp_instance.items():
                                rd_val = _safe_get(bi, 'route_distinguisher', None)
                                if rd_val:
                                    m = re.search(r'rd\s+([0-9\.:]+)', str(rd_val))
                                    if m:
                                        rd_by_ni[ni.name] = m.group(1)
                                    else:
                                        rd_by_ni[ni.name] = str(_safe_get(rd_val, 'rd', rd_val)).strip()
                                    break
        except Exception:
            pass

        intfs_by_ni = {}
        raw_intfs_by_ni = {}
        try:
            intf_p = build_path('/network-instance[name=*]/interface[name=*]')
            intf_data = state.server.get_data_store(DataStore.State).get_data(intf_p, recursive=False)
            for ni in intf_data.network_instance.items():
                if hasattr(ni, 'interface'):
                    raw_list = [intf.name for intf in ni.interface.items()]
                    raw_intfs_by_ni[ni.name] = raw_list
                    intfs_by_ni[ni.name] = [format_arista_intf(n, short=False) for n in raw_list]
        except Exception:
            pass

        v4_subintfs = set()
        v6_subintfs = set()
        try:
            v4_p = build_path('/interface[name=*]/subinterface[index=*]/ipv4/admin-state')
            v4_data = state.server.get_data_store(DataStore.State).get_data(v4_p, recursive=False)
            for intf in v4_data.interface.items():
                if hasattr(intf, 'subinterface'):
                    for sub in intf.subinterface.items():
                        if hasattr(sub, 'ipv4') and sub.ipv4.exists():
                            if _safe_get(sub.ipv4.get(), 'admin_state', '') == 'enable':
                                v4_subintfs.add(f"{intf.name}.{sub.index}")
        except Exception:
            pass
        try:
            v6_p = build_path('/interface[name=*]/subinterface[index=*]/ipv6/admin-state')
            v6_data = state.server.get_data_store(DataStore.State).get_data(v6_p, recursive=False)
            for intf in v6_data.interface.items():
                if hasattr(intf, 'subinterface'):
                    for sub in intf.subinterface.items():
                        if hasattr(sub, 'ipv6') and sub.ipv6.exists():
                            if _safe_get(sub.ipv6.get(), 'admin_state', '') == 'enable':
                                v6_subintfs.add(f"{intf.name}.{sub.index}")
        except Exception:
            pass

        path = build_path('/network-instance[name=*]')
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=False)
            for ni in sorted(data.network_instance.items(), key=lambda x: str(x.name)):
                try:
                    name = ni.name
                    ni_type = _safe_get(ni, 'type', 'default')
                    rd = rd_by_ni.get(name, "-")

                    intfs = intfs_by_ni.get(name, [])
                    raw_intfs = raw_intfs_by_ni.get(name, [])

                    if ni_type == 'mac-vrf':
                        proto_str = "-"
                        v4_state = "v4:no routing,"
                        v6_state = "v6:no routing"
                    else:
                        has_v4 = any(ri in v4_subintfs for ri in raw_intfs) or bool(intfs)
                        has_v6 = any(ri in v6_subintfs for ri in raw_intfs)
                        protos = ['ipv4']
                        if has_v6:
                            protos.append('ipv6')
                        proto_str = ",".join(protos) if protos else "ipv4"
                        v4_state = "v4:routing," if has_v4 else "v4:no routing,"
                        v6_state = "v6:routing" if has_v6 else "v6:no routing"

                    intf_str = ", ".join(intfs[:3]) if intfs else "-"
                    lines.append(f"  {name:<9} {rd:<14} {proto_str:<14} {v4_state:<19} {intf_str}")
                    lines.append(f"  {'':<9} {'':<14} {'':<14} {v6_state:<19}")
                except Exception:
                    pass
        except Exception:
            pass

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show network-instance summary")

    def _get_vlan_for_ni(self, state, raw_intfs):
        """Extract VLAN ID for a mac-vrf network instance:
        1. Check member subinterfaces' single-tagged VLAN encapsulation.
        2. Fall back to IRB subinterface index if > 0 (or 1 if 0).
        3. Fall back to subinterface index if > 0 (or 1 if member exists).
        4. Fall back to '--'.
        """
        # 1. Single-tagged encapsulation from member subinterfaces
        for intf_name in raw_intfs:
            if '.' in intf_name and not intf_name.startswith('irb'):
                p_name, sub_idx = intf_name.split('.', 1)
                try:
                    p = build_path(f'/interface[name={p_name}]/subinterface[index={sub_idx}]/vlan/encap/single-tagged/vlan-id')
                    d = state.server.get_data_store(DataStore.State).get_data(p, recursive=False)
                    vlan_val = _safe_get(d.interface.get().subinterface.get().vlan.get().encap.get().single_tagged.get(), 'vlan_id', None)
                    if vlan_val is not None:
                        return str(vlan_val)
                except Exception:
                    pass

        # 2. Fall back to IRB subinterface index
        for intf_name in raw_intfs:
            if 'irb' in intf_name:
                m = re.search(r'irb\d*\.(\d+)', intf_name)
                if m:
                    return m.group(1) if m.group(1) != '0' else '1'

        # 3. Fall back to subinterface index if > 0
        for intf_name in raw_intfs:
            if '.' in intf_name:
                sub_idx = intf_name.split('.', 1)[1]
                if sub_idx != '0':
                    return sub_idx

        if raw_intfs:
            return '1'
        return "--"

    def show_vlan(self, state, output):
        """Display Arista EOS style 'show vlan'."""
        lines = [
            f"{'VLAN':<5} {'Name':<32} {'Status':<9} {'Ports'}",
            f"----- -------------------------------- --------- -------------------------------"
        ]
        intfs_by_ni = {}
        raw_intfs_by_ni = {}
        try:
            intf_p = build_path('/network-instance[name=*]/interface[name=*]')
            intf_data = state.server.get_data_store(DataStore.State).get_data(intf_p, recursive=False)
            for ni in intf_data.network_instance.items():
                if hasattr(ni, 'interface'):
                    raw_intfs_by_ni[ni.name] = [intf.name for intf in ni.interface.items()]
                    intfs_by_ni[ni.name] = [format_arista_intf(intf.name, short=True) for intf in ni.interface.items()]
        except Exception:
            pass

        path = build_path('/network-instance[name=*]')
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=False)
            for ni in sorted(data.network_instance.items(), key=lambda x: str(x.name)):
                ni_type = _safe_get(ni, 'type', '')
                if ni_type != 'mac-vrf':
                    continue
                name = ni.name
                oper = _safe_get(ni, 'oper_state', 'up')
                status = "active" if oper == "up" else "suspended"

                ports = intfs_by_ni.get(name, [])
                raw_ports = raw_intfs_by_ni.get(name, [])
                vlan_tag = self._get_vlan_for_ni(state, raw_ports)

                ports_str = ", ".join(ports) if ports else "-"
                lines.append(f"{str(vlan_tag):<5} {name:<32} {status:<9} {ports_str}")
        except Exception:
            pass

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show network-instance summary")

    def show_mac_address_table(self, state, output):
        """Display Arista EOS style 'show mac address-table'."""
        lines = [
            f"{'':>10}Mac Address Table",
            f"------------------------------------------------------------------\n",
            f"{'Vlan':<7} {'Mac Address':<17} {'Type':<11} {'Ports':<10} {'Moves':<7} {'Last Move'}",
            f"{'----':<7} {'-----------':<17} {'----':<11} {'-----':<10} {'-----':<7} {'---------'}"
        ]
        vlan_by_ni = {}
        ports_by_ni = {}
        try:
            intf_p = build_path('/network-instance[name=*]/interface[name=*]')
            intf_data = state.server.get_data_store(DataStore.State).get_data(intf_p, recursive=False)
            for ni in intf_data.network_instance.items():
                if hasattr(ni, 'interface'):
                    raw_ports = [intf.name for intf in ni.interface.items()]
                    ports_by_ni[ni.name] = raw_ports
                    vlan_by_ni[ni.name] = self._get_vlan_for_ni(state, raw_ports)
        except Exception:
            pass

        path = build_path('/network-instance[name=*]/bridge-table/mac-table/mac[address=*]')
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            for ni in _safe_get(data, 'network_instance', []).items() if hasattr(data, 'network_instance') else []:
                ni_name = ni.name
                ni_vlan = vlan_by_ni.get(ni_name, "--")
                bridge_table = _safe_get(ni, 'bridge_table', None)
                if not bridge_table:
                    continue
                mac_table = _safe_get(bridge_table.get(), 'mac_table', None)
                if not mac_table:
                    continue
                for entry in mac_table.get().mac.items():
                    mac_addr = format_mac_cisco_arista(_safe_get(entry, 'address', ''))
                    raw_type = _safe_get(entry, 'type', 'learnt')
                    mac_type = "STATIC" if ('irb' in raw_type or raw_type == 'static') else "DYNAMIC"
                    dest = _safe_get(entry, 'destination', '')
                    vlan_str = ni_vlan
                    if 'vxlan' in dest.lower():
                        m_vni = re.search(r'vni:(\d+)', dest)
                        if m_vni:
                            port = 'Vx' + m_vni.group(1)
                        else:
                            port = 'VxLAN'
                    elif 'irb' in dest.lower():
                        ni_ports = ports_by_ni.get(ni_name, [])
                        irb_ports = [p for p in ni_ports if 'irb' in p]
                        port = irb_ports[0] if irb_ports else "irb"
                    else:
                        port = format_arista_intf(dest.split()[0] if dest else "-", short=True)
                    lines.append(f"{vlan_str:<7} {mac_addr:<17} {mac_type:<11} {port:<10} {'--':<7} {'-'}")
        except Exception:
            pass

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show network-instance bridge-table mac-table all")

    def show_ip_ospf_neighbor(self, state, output):
        """Display Arista EOS style 'show ip ospf neighbor'."""
        lines = [
            f"{'Neighbor ID':<15} {'VRF':<6} {'Pri':<5} {'State':<16} {'Dead Time':<11} {'Address':<15} {'Interface'}"
        ]
        path = build_path('/network-instance[name=*]/protocols/ospf/instance[name=*]/area[area-id=*]/interface[interface-name=*]/neighbor[router-id=*]')
        found = False
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            for ni in data.network_instance.items():
                vrf = ni.name
                if hasattr(ni, 'protocols') and ni.protocols.exists():
                    ospf = _safe_get(ni.protocols.get(), 'ospf', None)
                    if ospf and hasattr(ospf.get(), 'instance'):
                        for inst in ospf.get().instance.items():
                            if hasattr(inst, 'area'):
                                for area in inst.area.items():
                                    if hasattr(area, 'interface'):
                                        for intf in area.interface.items():
                                            intf_name = format_arista_intf(intf.interface_name, short=False)
                                            if hasattr(intf, 'neighbor'):
                                                for n in intf.neighbor.items():
                                                    found = True
                                                    r_id = _safe_get(n, 'router_id', '--')
                                                    adj_st = _safe_get(n, 'adjacency_state')
                                                    n_state = str(adj_st).split(':')[-1].upper() if adj_st else '--'
                                                    ip = _safe_get(n, 'address', '--')
                                                    pri = _safe_get(n, 'priority', '--')
                                                    dead = _safe_get(n, 'dead_time')
                                                    if dead is not None:
                                                        try:
                                                            d_sec = int(dead)
                                                            m, s = divmod(d_sec, 60)
                                                            h, m = divmod(m, 60)
                                                            dead_str = f"{h:02d}:{m:02d}:{s:02d}"
                                                        except Exception:
                                                            dead_str = str(dead)
                                                    else:
                                                        dead_str = '--'
                                                    lines.append(f"{r_id:<15} {vrf:<6} {str(pri):<5} {n_state:<16} {dead_str:<11} {str(ip):<15} {intf_name}")
        except Exception:
            pass

        if not found:
            lines.append("No OSPF neighbors configured or active.")

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show network-instance default protocols ospf neighbor")

    def show_isis_neighbors(self, state, output):
        """Display Arista EOS style 'show isis neighbors'."""
        lines = [
            f"{'Instance':<13} {'VRF':<12} {'System Id':<15} {'Type':<4} {'Interface':<18} {'Sni':<8} {'Holdtime':<8} {'State'}"
        ]
        path = build_path('/network-instance[name=*]/protocols/isis/instance[name=*]/interface[interface-name=*]/adjacency[neighbor-system-id=*][adjacency-level=*]')
        found = False
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            for ni in data.network_instance.items():
                vrf = ni.name
                if hasattr(ni, 'protocols') and ni.protocols.exists():
                    isis = _safe_get(ni.protocols.get(), 'isis', None)
                    if isis and hasattr(isis.get(), 'instance'):
                        for inst in isis.get().instance.items():
                            inst_name = inst.name
                            if hasattr(inst, 'interface'):
                                for iface in inst.interface.items():
                                    intf_name = format_arista_intf(iface.interface_name, short=False)
                                    if hasattr(iface, 'adjacency'):
                                        for adj in iface.adjacency.items():
                                            found = True
                                            sys_id = _safe_get(adj, 'neighbor_system_id', '--')
                                            level = _safe_get(adj, 'adjacency_level', '2')
                                            type_str = f"L{level}" if not str(level).startswith('L') else str(level)
                                            raw_st = _safe_get(adj, 'state', '--')
                                            oper = str(raw_st).split(':')[-1].upper() if raw_st else '--'
                                            hold = _safe_get(adj, 'remaining_holdtime', '--')
                                            lines.append(f"{inst_name:<13} {vrf:<12} {sys_id:<15} {type_str:<4} {intf_name:<18} {'-':<8} {str(hold):<8} {oper}")
        except Exception:
            pass

        if not found:
            lines.append("No IS-IS neighbors configured or active.")

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show network-instance default protocols isis adjacency")

    def show_ip_ospf_interface_brief(self, state, output):
        """Display Arista EOS style 'show ip ospf interface brief'."""
        lines = [
            f"{'Interface':<16} {'Instance':<9} {'VRF':<9} {'Area':<16} {'IP Address/Mask':<19} {'Cost':<6} {'State':<7} {'Nbrs'}",
            "---------------- -------- -------- --------------- ------------------ ----- ------ ----"
        ]
        intf_ip_map = {}
        try:
            intf_path = build_path('/interface[name=*]/subinterface[index=*]/ipv4/address[ip-prefix=*]')
            intf_data = state.server.get_data_store(DataStore.State).get_data(intf_path, recursive=True)
            for intf in intf_data.interface.items():
                sub_list = _safe_get(intf, 'subinterface')
                if sub_list is not None:
                    for sub in sub_list.items():
                        full_name = f"{intf.name}.{sub.index}"
                        ipv4_c = _safe_get(sub, 'ipv4')
                        if ipv4_c is not None and ipv4_c.exists():
                            ipv4_node = ipv4_c.get()
                            addr_list = _safe_get(ipv4_node, 'address')
                            if addr_list is not None:
                                for a in addr_list.items():
                                    pfx = _safe_get(a, 'ip_prefix')
                                    if pfx:
                                        intf_ip_map[full_name] = str(pfx)
                                        break
        except Exception:
            pass

        path = build_path('/network-instance[name=*]/protocols/ospf/instance[name=*]/area[area-id=*]/interface[interface-name=*]')
        found = False
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            for ni in data.network_instance.items():
                vrf = ni.name
                if hasattr(ni, 'protocols') and ni.protocols.exists():
                    ospf = _safe_get(ni.protocols.get(), 'ospf', None)
                    if ospf and hasattr(ospf.get(), 'instance'):
                        for inst in ospf.get().instance.items():
                            inst_name = inst.name
                            if hasattr(inst, 'area'):
                                for area in inst.area.items():
                                    area_id = area.area_id
                                    if hasattr(area, 'interface'):
                                        for iface in area.interface.items():
                                            found = True
                                            raw_name = str(iface.interface_name)
                                            intf_disp = format_arista_intf(raw_name, short=False)
                                            cost = _safe_get(iface, 'metric', 10)
                                            st = str(_safe_get(iface, 'oper_state', 'down')).upper()
                                            nbrs = _safe_get(iface, 'neighbor_count', 0)
                                            ip_mask = intf_ip_map.get(raw_name) or str(_safe_get(iface, 'local_ip_address', '--') or '--')
                                            lines.append(f"{intf_disp:<16} {inst_name:<9} {vrf:<9} {str(area_id):<16} {ip_mask:<19} {str(cost):<6} {st:<7} {str(nbrs)}")
        except Exception:
            pass

        if not found:
            lines = [
                f"{'Interface':<16} {'Instance':<9} {'VRF':<9} {'Area':<16} {'IP Address/Mask':<19} {'Cost':<6} {'State':<7} {'Nbrs'}",
                "---------------- -------- -------- --------------- ------------------ ----- ------ ----",
                "No OSPF interfaces configured."
            ]

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show network-instance default protocols ospf interface")

    def show_mlag(self, state, output):
        """Display Arista EOS style 'show mlag'."""
        lines = []
        path = build_path('/system/network-instance/protocols/evpn/ethernet-segments')
        found = False
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            # Check for EVPN MH / ESI
            es_container = getattr(data.system.get().network_instance.get().protocols.get().evpn.get(), 'ethernet_segments', None)
            if es_container and hasattr(es_container.get(), 'bgp_instance'):
                for bi in es_container.get().bgp_instance.items():
                    if hasattr(bi, 'ethernet_segment'):
                        for es in bi.ethernet_segment.items():
                            found = True
                            intf = '--'
                            try:
                                intf_attr = _safe_get(es, 'interface')
                                if isinstance(intf_attr, str) and intf_attr:
                                    intf = intf_attr
                                elif intf_attr is not None and hasattr(intf_attr, 'items'):
                                    for item in intf_attr.items():
                                        for field in ('ethernet_interface', 'interface_name', 'name'):
                                            val = _safe_get(item, field)
                                            if val:
                                                intf = str(val)
                                                break
                                        if intf != '--':
                                            break
                                elif intf_attr is not None:
                                    m = re.search(r'interface\s+(\S+)', str(intf_attr))
                                    if m:
                                        intf = m.group(1)
                            except Exception:
                                intf = '--'
                            domain_id = _safe_get(bi, 'id', 1)
                            admin_st = _safe_get(es, 'admin_state', 'enable')
                            oper_st = _safe_get(es, 'oper_state', 'down')
                            mlag_state = "Active" if (admin_st == "enable" and oper_st == "up") else "Inactive"

                            intf_fmt = format_arista_intf(intf, short=True) if intf != '--' else '--'
                            peer_addr = "--"
                            try:
                                local_sys_ips = set()
                                try:
                                    sys_p = build_path('/interface[name=system0]/subinterface[index=*]/ipv4/address[ip-prefix=*]')
                                    sys_d = state.server.get_data_store(DataStore.State).get_data(sys_p, recursive=True)
                                    for s_intf in sys_d.interface.items():
                                        for s_sub in s_intf.subinterface.items():
                                            if hasattr(s_sub, 'ipv4') and s_sub.ipv4.exists():
                                                for a_obj in s_sub.ipv4.get().address.items():
                                                    ip_p = _safe_get(a_obj, 'ip_prefix')
                                                    if ip_p:
                                                        local_sys_ips.add(str(ip_p).split('/')[0])
                                except Exception:
                                    pass
                                assoc = _safe_get(es, 'association')
                                if assoc is not None and assoc.exists():
                                    assoc_node = assoc.get()
                                    if hasattr(assoc_node, 'network_instance'):
                                        for assoc_ni in assoc_node.network_instance.items():
                                            if hasattr(assoc_ni, 'bgp_instance'):
                                                for assoc_bi in assoc_ni.bgp_instance.items():
                                                    cdfc = _safe_get(assoc_bi, 'computed_designated_forwarder_candidates')
                                                    if cdfc is not None and cdfc.exists():
                                                        cdfc_node = cdfc.get()
                                                        if hasattr(cdfc_node, 'designated_forwarder_candidate'):
                                                            for cand in cdfc_node.designated_forwarder_candidate.items():
                                                                c_addr = _safe_get(cand, 'address')
                                                                if c_addr and str(c_addr) not in local_sys_ips:
                                                                    peer_addr = str(c_addr)
                                                                    break
                                                    if peer_addr != "--":
                                                        break
                                            if peer_addr != "--":
                                                break
                            except Exception:
                                pass
                            lines = [
                                "MLAG Configuration:",
                                f"domain-id           : {domain_id}",
                                f"local-interface     : {intf_fmt}",
                                f"peer-address        : {peer_addr}",
                                f"peer-link           : {intf_fmt}",
                                f"state               : {mlag_state}"
                            ]
                            break
        except Exception:
            pass

        if not found:
            lines = [
                "MLAG Configuration:",
                "domain-id           : --",
                "local-interface     : --",
                "peer-address        : --",
                "peer-link           : --",
                "state               : Disabled / Not Configured"
            ]

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show system network-instance ethernet-segments")

