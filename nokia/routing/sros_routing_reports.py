#!/usr/bin/python
###########################################################################
# Description: MultiCLI Nokia SR OS Routing Reports
# Commands: show router route-table, show router interface, show router arp,
#           show router ospf neighbor, show router isis adjacency
# Copyright (c) 2026 Nokia
###########################################################################

import datetime
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


def format_sros_uptime(dt_or_str):
    if not dt_or_str:
        return "00d00h00m"
    try:
        s = str(dt_or_str).strip()
        if '(' in s:
            s = s.split('(')[-1].rstrip(')').replace(' ago', '')
            return s
        if 'Z' in s:
            s = s.replace('Z', '+00:00')
        dt = datetime.datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        delta = datetime.datetime.now(datetime.timezone.utc) - dt
        days = delta.days
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60
        return f"{days:02d}d{hours:02d}h{minutes:02d}m"
    except Exception:
        return "00d00h00m"

class SrosRoutingReports:
    """Handles classic Nokia SR OS routing show reports."""

    def show_route_table(self, state, output, netinst='default'):
        """Display classic Nokia SR OS formatted 'show router route-table'."""
        output.print_line("=" * 79)
        output.print_line(f"Route Table (Router: {netinst})")
        output.print_line("=" * 79)
        output.print_line(f"{'Dest Prefix[Flags]':<46}{'Type':<8}{'Proto':<10}{'Age':<11}{'Pref'}")
        output.print_line(f"{'      Next Hop[Interface Name]':<64}{'Metric'}")
        output.print_line("-" * 79)

        routes_path = build_path(f'/network-instance[name={netinst}]/route-table')
        routes_data = None
        try:
            routes_data = state.server.get_data_store(DataStore.State).get_data(routes_path, recursive=True)
        except Exception:
            pass

        if not routes_data:
            output.print_line("No Matching Entries Found.")
            output.print_line("=" * 79)
            output.print_line(f"\nTry SR Linux command: show network-instance {netinst} route-table ipv4-unicast summary")
            return

        # Build in-memory next-hop map
        nh_map = {}
        try:
            for nh in routes_data.get_descendants('/network-instance/route-table/next-hop'):
                nh_idx = _safe_get(nh, 'index', None)
                if nh_idx is None:
                    continue
                nh_type = _safe_get(nh, 'type', None)
                ip = _safe_get(nh, 'ip_address', None)
                subif = _safe_get(nh, 'subinterface', None)
                resolving_nhg = None
                if nh_type == 'tunnel' and hasattr(nh, 'tunnel'):
                    try:
                        pfx = _safe_get(nh.tunnel.get(), 'ip_prefix', None)
                        if pfx and not ip:
                            ip = str(pfx).split('/')[0]
                    except Exception:
                        pass
                if nh_type == 'indirect' and hasattr(nh, 'indirect'):
                    try:
                        rr = _safe_get(nh.indirect.get(), 'resolving_route', None)
                        if rr:
                            resolving_nhg = _safe_get(rr.get(), 'next_hop_group', None)
                    except Exception:
                        pass
                nh_map[str(nh_idx)] = {
                    'ip': str(ip) if ip else None,
                    'interface': str(subif) if subif else None,
                    'resolving_nhg': str(resolving_nhg) if resolving_nhg is not None else None,
                }
        except Exception:
            pass

        nhg_map = {}
        try:
            for nhg in routes_data.get_descendants('/network-instance/route-table/next-hop-group'):
                nhg_idx = _safe_get(nhg, 'index', None)
                if nhg_idx is not None and hasattr(nhg, 'next_hop'):
                    hops = []
                    for nh_item in nhg.next_hop.items():
                        target_nh = _safe_get(nh_item, 'next_hop', None)
                        if target_nh is not None and str(target_nh) in nh_map:
                            hops.append(nh_map[str(target_nh)])
                    nhg_map[str(nhg_idx)] = hops
        except Exception:
            pass

        def resolve_hops(nhg_id, visited=None):
            if visited is None:
                visited = set()
            if str(nhg_id) in visited or str(nhg_id) not in nhg_map:
                return []
            visited.add(str(nhg_id))
            out = []
            for hop in nhg_map[str(nhg_id)]:
                if hop['resolving_nhg']:
                    resolved = resolve_hops(hop['resolving_nhg'], visited.copy())
                    if resolved:
                        out.extend(resolved)
                    else:
                        out.append(hop)
                else:
                    out.append(hop)
            return out

        route_entries = []
        try:
            for r in routes_data.get_descendants('/network-instance/route-table/ipv4-unicast/route'):
                prefix = _safe_get(r, 'ipv4_prefix', None)
                if not prefix:
                    continue
                rtype = _safe_get(r, 'route_type', 'local')
                pref = _safe_get(r, 'preference', 0)
                metric = _safe_get(r, 'metric', 0)
                nhg_id = _safe_get(r, 'next_hop_group', None)
                last_up = _safe_get(r, 'last_app_update', None)
                age = format_sros_uptime(last_up)

                proto_display = "Local"
                type_display = "Local"
                if rtype in ('bgp', 'bgp-evpn', 'bgp-vpn', 'bgp-label'):
                    proto_display = "BGP"
                    type_display = "Remote"
                elif rtype in ('ospfv2', 'ospfv3'):
                    proto_display = "OSPF"
                    type_display = "Remote"
                elif rtype == 'isis':
                    proto_display = "ISIS"
                    type_display = "Remote"
                elif rtype == 'static':
                    proto_display = "Static"
                    type_display = "Remote"
                elif rtype == 'connected':
                    proto_display = "Local"
                    type_display = "Local"

                resolved = resolve_hops(nhg_id) if nhg_id is not None else []
                hops = []
                if resolved:
                    for h in resolved:
                        hops.append(h['ip'] or h['interface'] or 'system')
                else:
                    hops.append('system')

                route_entries.append({
                    'prefix': str(prefix),
                    'type': type_display,
                    'proto': proto_display,
                    'age': age,
                    'pref': str(pref),
                    'metric': str(metric),
                    'hops': hops
                })
        except Exception:
            pass

        # Sort IP prefixes logically
        def ip_sort_key(entry):
            try:
                return ipaddress.ip_network(entry['prefix'])
            except Exception:
                return ipaddress.ip_network('0.0.0.0/32')

        route_entries.sort(key=ip_sort_key)

        for entry in route_entries:
            first_hop = entry['hops'][0] if entry['hops'] else 'system'
            output.print_line(
                f"{entry['prefix']:<46}{entry['type']:<8}{entry['proto']:<10}{entry['age']:<11}{entry['pref']}"
            )
            output.print_line(f"       {first_hop:<57}{entry['metric']}")
            for extra_hop in entry['hops'][1:]:
                output.print_line(f"       {extra_hop:<57}{entry['metric']}")

        output.print_line("-" * 79)
        output.print_line(f"No. of Routes: {len(route_entries)}")
        output.print_line("Flags: n = Number of active backups")
        output.print_line("=" * 79)
        output.print_line(f"\nTry SR Linux command: show network-instance {netinst} route-table ipv4-unicast summary")

    def show_router_interface(self, state, output, netinst='default'):
        """Display classic Nokia SR OS formatted 'show router interface'."""
        output.print_line("=" * 79)
        output.print_line(f"Interface Table (Router: {netinst})")
        output.print_line("=" * 79)
        output.print_line(f"{'Interface-Name':<33}{'Adm':<10}{'Opr(v4/v6)':<12}{'Mode':<8}{'Pfx/Addr(v4/v6)'}")
        output.print_line(f"{'   IP-Address':<53}{'PfxState'}")
        output.print_line("-" * 79)

        path = build_path(f'/network-instance[name={netinst}]/interface[name=*]')
        entries = []
        try:
            ni_data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            for iface in ni_data.network_instance.get().interface.items():
                intf_name = str(iface.name)
                oper = _safe_get(iface, 'oper_state', 'up')
                adm = "Up"
                v4_addrs = []
                v6_addrs = []
                v4_adm = False
                v6_adm = False

                if '.' in intf_name:
                    p_name, s_idx = intf_name.split('.', 1)
                    try:
                        s_path = build_path(f'/interface[name={p_name}]/subinterface[index={s_idx}]')
                        s_data = state.server.get_data_store(DataStore.State).get_data(s_path, recursive=True)
                        sub = s_data.interface.get().subinterface.get()
                        sub_adm = _safe_get(sub, 'admin_state', 'enable')
                        adm = "Up" if sub_adm == 'enable' else "Down"
                        sub_oper = _safe_get(sub, 'oper_state', oper)
                        if sub_oper:
                            oper = sub_oper
                        if hasattr(sub, 'ipv4') and sub.ipv4.exists():
                            v4_obj = sub.ipv4.get()
                            v4_adm = _safe_get(v4_obj, 'admin_state', 'disable') == 'enable'
                            if hasattr(v4_obj, 'address'):
                                for a in v4_obj.address.items():
                                    pfx = _safe_get(a, 'ip_prefix', None)
                                    if pfx:
                                        st = str(_safe_get(a, 'status', 'n/a') or 'n/a').upper()
                                        v4_addrs.append((str(pfx), st if st != 'NONE' else 'n/a'))
                        if hasattr(sub, 'ipv6') and sub.ipv6.exists():
                            v6_obj = sub.ipv6.get()
                            v6_adm = _safe_get(v6_obj, 'admin_state', 'disable') == 'enable'
                            if hasattr(v6_obj, 'address'):
                                for a in v6_obj.address.items():
                                    pfx = _safe_get(a, 'ip_prefix', None)
                                    if pfx:
                                        st = str(_safe_get(a, 'status', 'n/a') or 'n/a').upper()
                                        v6_addrs.append((str(pfx), st if st != 'NONE' else 'n/a'))
                    except Exception:
                        pass

                v4_opr = "Up" if (oper == "up" and (v4_adm or v4_addrs)) else "Down"
                v6_opr = "Up" if (oper == "up" and (v6_adm or v6_addrs)) else "Down"
                opr = f"{v4_opr}/{v6_opr}"
                pfx_cnt = f"{len(v4_addrs)}/{len(v6_addrs)}"
                all_addrs = v4_addrs + v6_addrs
                if not all_addrs:
                    all_addrs = [("n/a", "n/a")]
                entries.append((intf_name, adm, opr, pfx_cnt, all_addrs))
        except Exception:
            pass

        for name, adm, opr, pfx_cnt, addrs in entries:
            output.print_line(f"{name:<33}{adm:<10}{opr:<12}{'Network':<8}{pfx_cnt}")
            for ip_str, pfx_st in addrs:
                output.print_line(f"   {ip_str:<50}{pfx_st}")

        output.print_line("-" * 79)
        output.print_line(f"Interfaces : {len(entries)}")
        output.print_line("=" * 79)
        output.print_line("\nTry SR Linux command: show interface brief")

    def show_router_arp(self, state, output, netinst='default'):
        """Display classic Nokia SR OS formatted 'show router arp'."""
        output.print_line("=" * 79)
        output.print_line(f"ARP Table (Router: {netinst})")
        output.print_line("=" * 79)
        output.print_line(f"{'IP Address':<16}{'MAC Address':<18}{'Expiry':<12}{'Type':<9}{'Interface'}")
        output.print_line("-" * 79)

        entries = []
        path = build_path('/interface[name=*]/subinterface[index=*]/ipv4/arp/neighbor[ipv4-address=*]')
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            for intf in data.interface.items():
                if hasattr(intf, 'subinterface'):
                    for sub in intf.subinterface.items():
                        full_intf = f"{intf.name}.{sub.index}"
                        if hasattr(sub, 'ipv4') and sub.ipv4.exists():
                            arp = _safe_get(sub.ipv4.get(), 'arp', None)
                            if arp and hasattr(arp.get(), 'neighbor'):
                                for n in arp.get().neighbor.items():
                                    ip = _safe_get(n, 'ipv4_address', None)
                                    mac = _safe_get(n, 'link_layer_address', None)
                                    if ip and mac:
                                        origin = str(_safe_get(n, 'origin', 'dynamic')).lower()
                                        exp_time = _safe_get(n, 'expiration_time', None)
                                        exp_str = "--"
                                        if exp_time and origin != 'static':
                                            try:
                                                ts_str = str(exp_time).split('(')[0].strip()
                                                if ts_str.endswith('Z'):
                                                    ts_str = ts_str[:-1] + '+00:00'
                                                exp_dt = datetime.datetime.fromisoformat(ts_str)
                                                now = datetime.datetime.now(datetime.timezone.utc)
                                                rem_seconds = max(0, int((exp_dt - now).total_seconds()))
                                                h, r = divmod(rem_seconds, 3600)
                                                m, s = divmod(r, 60)
                                                exp_str = f"{h:02d}h{m:02d}m{s:02d}s"
                                            except Exception:
                                                exp_str = "00h00m00s"
                                        atype = "Static" if origin == 'static' else "Dynamic"
                                        entries.append((str(ip), str(mac), exp_str, atype, full_intf))
        except Exception:
            pass

        for ip, mac, exp, atype, iface in entries:
            output.print_line(f"{ip:<16}{mac:<18}{exp:<12}{atype:<9}{iface}")

        output.print_line("-" * 79)
        output.print_line(f"No. of ARP Entries: {len(entries)}")
        output.print_line("=" * 79)
        output.print_line("\nTry SR Linux command: show arpnd arp-entries")

    def show_router_ospf_neighbor(self, state, output, netinst='default'):
        """Display classic Nokia SR OS formatted 'show router ospf neighbor'."""
        output.print_line("=" * 79)
        output.print_line(f"Rtr Base OSPFv2 Instance 0 Neighbors (Router: {netinst})")
        output.print_line("=" * 79)
        output.print_line(f"{'Interface-Name':<33}{'Rtr Id':<16}{'State':<11}{'Pri':<5}{'RetxQ':<8}{'Dead'}")
        output.print_line("-" * 79)

        path = build_path(f'/network-instance[name={netinst}]/protocols/ospf/instance[name=*]/area[area-id=*]/interface[interface-name=*]/neighbor[router-id=*]')
        entries = []
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            for ni in data.network_instance.items():
                if hasattr(ni, 'protocols') and ni.protocols.exists():
                    ospf = _safe_get(ni.protocols.get(), 'ospf', None)
                    if ospf and hasattr(ospf.get(), 'instance'):
                        for inst in ospf.get().instance.items():
                            if hasattr(inst, 'area'):
                                for area in inst.area.items():
                                    if hasattr(area, 'interface'):
                                        for iface in area.interface.items():
                                            iname = str(iface.interface_name)
                                            if hasattr(iface, 'neighbor'):
                                                for n in iface.neighbor.items():
                                                    rid = str(_safe_get(n, 'router_id', '--'))
                                                    st = str(_safe_get(n, 'adjacency_state', '--')).split(':')[-1].capitalize()
                                                    pri = str(_safe_get(n, 'priority', 1))
                                                    retx = str(_safe_get(n, 'retransmission_queue_length', 0))
                                                    dead = str(_safe_get(n, 'dead_time', '--'))
                                                    entries.append((iname, rid, st, pri, retx, dead))
        except Exception:
            pass

        if not entries:
            output.print_line("No Matching Entries Found.")
        else:
            for iname, rid, st, pri, retx, dead in entries:
                output.print_line(f"{iname:<33}{rid:<16}{st:<11}{pri:<5}{retx:<8}{dead}")

        output.print_line("=" * 79)
        output.print_line(f"\nTry SR Linux command: show network-instance {netinst} protocols ospf neighbor")

    def show_router_isis_adjacency(self, state, output, netinst='default'):
        """Display classic Nokia SR OS formatted 'show router isis adjacency'."""
        output.print_line("=" * 79)
        output.print_line(f"Router Base ISIS Instance 0 Adjacencies (Router: {netinst})")
        output.print_line("=" * 79)
        output.print_line(f"{'Interface':<33}{'System ID':<25}{'L':<3}{'State':<7}{'Hold':<6}{'Expires'}")
        output.print_line("-" * 79)

        path = build_path(f'/network-instance[name={netinst}]/protocols/isis/instance[name=*]/interface[interface-name=*]/adjacency[neighbor-system-id=*][adjacency-level=*]')
        entries = []
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            for ni in data.network_instance.items():
                if hasattr(ni, 'protocols') and ni.protocols.exists():
                    isis = _safe_get(ni.protocols.get(), 'isis', None)
                    if isis and hasattr(isis.get(), 'instance'):
                        for inst in isis.get().instance.items():
                            if hasattr(inst, 'interface'):
                                for iface in inst.interface.items():
                                    iname = str(iface.interface_name)
                                    adj_list = _safe_get(iface, 'adjacency')
                                    if adj_list is not None:
                                        for adj in adj_list.items():
                                            sys_id = str(_safe_get(adj, 'neighbor_hostname') or _safe_get(adj, 'neighbor_system_id', '--'))
                                            lvl_val = str(_safe_get(adj, 'adjacency_level', '2'))
                                            lvl = lvl_val.replace('level-', '').replace('L', '') if lvl_val in ('L1', 'L2') else ('3' if lvl_val == 'L1L2' else lvl_val)
                                            st = str(_safe_get(adj, 'state', 'Up')).split(':')[-1].capitalize()
                                            rem_hold = _safe_get(adj, 'remaining_holdtime')
                                            hold = str(rem_hold if rem_hold is not None else 30)
                                            exp = str(rem_hold if rem_hold is not None else hold)
                                            entries.append((iname, sys_id, lvl, st, hold, exp))
        except Exception:
            pass

        if not entries:
            output.print_line("No Matching Entries Found.")
        else:
            for iname, sys_id, lvl, st, hold, exp in entries:
                output.print_line(f"{iname:<33}{sys_id:<25}{lvl:<3}{st:<7}{hold:<6}{exp}")

        output.print_line("=" * 79)
        output.print_line(f"\nTry SR Linux command: show network-instance {netinst} protocols isis adjacency")
