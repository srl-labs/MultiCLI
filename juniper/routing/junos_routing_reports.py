#!/usr/bin/python
###########################################################################
# Description: MultiCLI Routing & Protocols Reports for Juniper JUNOS
# Copyright (c) 2025-2026 Nokia
###########################################################################

import datetime
import ipaddress
import re
from srlinux.location import build_path
from srlinux.schema.data_store import DataStore


def _safe_get(obj, attr, default=None):
    try:
        val = getattr(obj, attr, default)
        return default if val is None else val
    except Exception:
        return default


def format_junos_intf(name, with_unit=True):
    """Format SR Linux interface name to Juniper JUNOS format."""
    if not name:
        return "-"
    name = str(name).strip()
    sub_idx = 0
    if '.' in name:
        base, sub = name.rsplit('.', 1)
        try:
            sub_idx = int(sub)
        except ValueError:
            sub_idx = 0
    else:
        base = name

    if base.startswith('ethernet-'):
        try:
            parts = base.split('-', 1)[1].split('/')
            fpc = max(int(parts[0]) - 1, 0)
            port_num = max(int(parts[1]) - 1, 0)
            if len(parts) >= 3:
                chan = max(int(parts[2]) - 1, 0)
                j_base = f"et-{fpc}/0/{port_num}:{chan}"
            else:
                j_base = f"et-{fpc}/0/{port_num}"
        except Exception:
            j_base = base.replace('ethernet-', 'et-0/0/')
    elif base.startswith('mgmt'):
        j_base = "em0"
    elif base.startswith('system0'):
        j_base = "lo0"
    elif base.startswith('irb'):
        j_base = "irb"
    elif base.startswith('lag'):
        num = base.split('lag')[-1]
        j_base = f"ae{num}"
    else:
        j_base = base

    if with_unit:
        return f"{j_base}.{sub_idx}"
    return j_base

def format_mac_junos(mac):
    """Format MAC to Juniper colon-separated lowercase xx:xx:xx:xx:xx:xx."""
    if not mac:
        return "00:00:00:00:00:00"
    raw = re.sub(r'[^0-9a-fA-F]', '', str(mac)).lower().zfill(12)
    return ":".join(raw[i:i+2] for i in range(0, 12, 2))

class JunosRoutingReports:
    """Handles Juniper JUNOS routing and protocol show commands."""

    def show_arp_no_resolve(self, state, output):
        """Display Juniper JUNOS style 'show arp no-resolve'."""
        lines = [
            f"{'MAC Address':<18} {'Address':<16} {'Interface':<14} {'Flags'}"
        ]
        entries = []
        try:
            path_arpnd = build_path('/interface[name=*]/subinterface[index=*]/ipv4/arp/neighbor[ipv4-address=*]')
            data_arpnd = state.server.get_data_store(DataStore.State).get_data(path_arpnd, recursive=True)
            for intf in data_arpnd.interface.items():
                if hasattr(intf, 'subinterface'):
                    for sub in intf.subinterface.items():
                        if hasattr(sub, 'ipv4') and sub.ipv4.exists():
                            arp = _safe_get(sub.ipv4.get(), 'arp', None)
                            if arp and hasattr(arp.get(), 'neighbor'):
                                for n in arp.get().neighbor.items():
                                    ip = n.ipv4_address
                                    mac = format_mac_junos(_safe_get(n, 'link_layer_address', ''))
                                    full_intf = f"{intf.name}.{sub.index}"
                                    j_intf = format_junos_intf(full_intf, with_unit=True)
                                    entries.append((mac, ip, j_intf))
        except Exception:
            pass

        if not entries:
            try:
                path = build_path('/network-instance[name=*]/neighbor[ipv4-address=*]')
                data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
                for ni in data.network_instance.items():
                    if hasattr(ni, 'neighbor'):
                        for n in ni.neighbor.items():
                            ip = n.ipv4_address
                            mac = format_mac_junos(_safe_get(n, 'link_layer_address', ''))
                            intf = format_junos_intf(_safe_get(n, 'interface', ''), with_unit=True)
                            entries.append((mac, ip, intf))
            except Exception:
                pass

        for mac, ip, intf in entries:
            lines.append(f"{mac:<18} {ip:<16} {intf:<14} none")

        lines.append(f"Total entries: {len(entries)}")

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show arpnd arp-entries")

    def show_lldp_neighbors(self, state, output):
        """Display Juniper JUNOS style 'show lldp neighbors'."""
        lines = [
            f"{'Local Interface':<18} {'Parent Interface':<17} {'Chassis Id':<20} {'Port info':<18} {'System Name'}"
        ]
        path = build_path('/system/lldp/interface[name=*]/neighbor[id=*]')
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            for iface in data.get_descendants('/system/lldp/interface'):
                local_name = format_junos_intf(_safe_get(iface, 'name', ''), with_unit=False)
                if hasattr(iface, 'neighbor'):
                    for neigh in iface.neighbor.items():
                        sys_name = _safe_get(neigh, 'system_name', '') or '-'
                        port_id = format_junos_intf(_safe_get(neigh, 'port_id', ''), with_unit=False)
                        chassis_id = _safe_get(neigh, 'chassis_id', '') or '-'
                        lines.append(f"{local_name:<18} {'-':<17} {chassis_id:<20} {port_id:<18} {sys_name}")
        except Exception:
            pass

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show system lldp neighbor")

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

    def show_vlans(self, state, output):
        """Display Juniper JUNOS style 'show vlans'."""
        lines = [
            f"{'Routing instance':<23} {'VLAN name':<21} {'Tag':<8} {'Interfaces'}"
        ]
        intfs_by_ni = {}
        raw_intfs_by_ni = {}
        try:
            intf_p = build_path('/network-instance[name=*]/interface[name=*]')
            intf_data = state.server.get_data_store(DataStore.State).get_data(intf_p, recursive=False)
            for ni in intf_data.network_instance.items():
                if hasattr(ni, 'interface'):
                    raw_intfs_by_ni[ni.name] = [intf.name for intf in ni.interface.items()]
                    intfs_by_ni[ni.name] = [format_junos_intf(intf.name, with_unit=True) for intf in ni.interface.items()]
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
                intfs = intfs_by_ni.get(name, [])
                raw_intfs = raw_intfs_by_ni.get(name, [])

                vlan_tag = self._get_vlan_for_ni(state, raw_intfs)

                first_intf = intfs[0] if intfs else ""
                lines.append(f"{name:<23} {name:<21} {str(vlan_tag):<8} {first_intf}")
                for extra in intfs[1:]:
                    lines.append(f"{'':<23} {'':<21} {'':<8} {extra}")
        except Exception:
            pass

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show network-instance summary")

    def show_lacp_interfaces(self, state, output):
        """Display Juniper JUNOS style 'show lacp interfaces'."""
        lines = []
        path = build_path('/interface[name=lag*]')
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            for intf in data.interface.items():
                name = intf.name
                ae_name = format_junos_intf(name, with_unit=False)
                lines.append(f"Aggregated interface: {ae_name}")
                lines.append("    LACP state:       Role   Exp   Def  Dist  Col  Syn  Aggr  Timeout  Activity")

                members = []
                lag_c = _safe_get(intf, 'lag')
                if lag_c is not None and lag_c.exists():
                    lag_node = lag_c.get()
                    mem_items = []
                    mem_list = _safe_get(lag_node, 'member') or _safe_get(lag_node, 'member_interface')
                    if mem_list is not None and hasattr(mem_list, 'items'):
                        mem_items = mem_list.items()

                    for mem in mem_items:
                        m_name = format_junos_intf(mem.name, with_unit=False)
                        oper = _safe_get(mem, 'oper_state', '-')
                        role = "Actor"
                        exp = "No"
                        df = "No"
                        dist = "No"
                        col = "No"
                        syn = "No"
                        aggr = "Yes"
                        timeout = "Fast"
                        activity = "Active" if oper == "up" else "Down"
                        rx_state = "Current" if oper == "up" else "Port disabled"
                        tx_state = "Fast periodic" if oper == "up" else "No periodic"
                        mux_state = "Collecting distributing" if oper == "up" else "Detached"

                        lacp_obj = _safe_get(mem, 'lacp', None)
                        if lacp_obj is not None:
                            l_node = lacp_obj.get() if hasattr(lacp_obj, 'get') else lacp_obj
                            dist_v = _safe_get(l_node, 'distributing')
                            if dist_v is not None:
                                dist = "Yes" if dist_v else "No"
                            col_v = _safe_get(l_node, 'collecting')
                            if col_v is not None:
                                col = "Yes" if col_v else "No"
                            syn_v = _safe_get(l_node, 'synchronization')
                            if syn_v is not None:
                                syn_val = str(syn_v).lower()
                                syn = "Yes" if "in-sync" in syn_val or "true" in syn_val else "No"
                            aggr_v = _safe_get(l_node, 'aggregatable')
                            if aggr_v is not None:
                                aggr = "Yes" if aggr_v else "No"
                            t_v = _safe_get(l_node, 'timeout')
                            if t_v is not None:
                                t_val = str(t_v).lower()
                                timeout = "Fast" if "short" in t_val or "fast" in t_val else "Slow"
                            act_v = _safe_get(l_node, 'activity')
                            if act_v is not None:
                                act_val = str(act_v).capitalize()
                                if act_val:
                                    activity = act_val

                        lines.append(f"      {m_name:<14} {role:<7} {exp:<5} {df:<4} {dist:<5} {col:<4} {syn:<4} {aggr:<5} {timeout:<8} {activity}")
                        members.append((m_name, rx_state, tx_state, mux_state))

                if members:
                    lines.append("    LACP protocol:        Receive State  Transmit State          Mux State")
                    for m_name, rx, tx, mux in members:
                        lines.append(f"      {m_name:<24} {rx:<14} {tx:<23} {mux}")
                lines.append("")
        except Exception:
            pass

        if not lines:
            lines.append("No aggregated interfaces configured.")

        output.print_line("\n".join(lines).rstrip())
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show lag")

    def show_route(self, state, output, network_instance='default'):
        """Display Juniper JUNOS style 'show route' table."""
        path_routes = build_path(f'/network-instance[name={network_instance}]/route-table')
        routes_data = None
        try:
            routes_data = state.server.get_data_store(DataStore.State).get_data(path_routes, recursive=True)
        except Exception:
            pass

        if not routes_data:
            output.print_line(f"error: table {network_instance} not found")
            return

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

        for nh_info in nh_map.values():
            if not nh_info['interface'] and nh_info.get('resolving_nhg'):
                target_hops = nhg_map.get(nh_info['resolving_nhg'], [])
                for th in target_hops:
                    if th.get('interface'):
                        nh_info['interface'] = th['interface']
                        break

        all_routes = []
        try:
            for r in routes_data.get_descendants('/network-instance/route-table/ipv4-unicast/route'):
                pfx = _safe_get(r, 'ipv4_prefix', None)
                if not pfx:
                    continue
                rtype = str(_safe_get(r, 'route_type', '')).lower()
                rowner = str(_safe_get(r, 'route_owner', '')).lower()
                pref = _safe_get(r, 'preference', None)
                nhg_id = _safe_get(r, 'next_hop_group', None)
                hops = nhg_map.get(str(nhg_id), []) if nhg_id is not None else []

                # Format protocol and preference
                if 'connected' in rowner or (rtype == 'local' and 'host' not in rtype):
                    proto_name = 'Direct'
                    default_pref = 0
                elif 'host' in rtype or 'local' in rowner:
                    proto_name = 'Local'
                    default_pref = 0
                elif 'bgp' in rtype or 'bgp' in rowner:
                    proto_name = 'BGP'
                    default_pref = 170
                elif 'static' in rtype or 'static' in rowner:
                    proto_name = 'Static'
                    default_pref = 5
                elif 'ospf' in rtype or 'ospf' in rowner:
                    proto_name = 'OSPF'
                    default_pref = 10
                elif 'isis' in rtype or 'isis' in rowner:
                    proto_name = 'IS-IS'
                    default_pref = 15
                else:
                    proto_name = rowner.capitalize() if rowner else 'Direct'
                    default_pref = 0

                pref_val = pref if (pref is not None and pref > 0) else default_pref

                # Calculate uptime
                uptime_str = ""
                last_up = _safe_get(r, 'last_app_update', None)
                if last_up:
                    try:
                        ts_str = str(last_up).split(' (')[0].strip()
                        if 'Z' in ts_str:
                            ts_str = ts_str.replace('Z', '+00:00')
                        dt = datetime.datetime.fromisoformat(ts_str)
                        now = datetime.datetime.now(datetime.timezone.utc)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=datetime.timezone.utc)
                        sec = max(0, int((now - dt).total_seconds()))
                        d, rem = divmod(sec, 86400)
                        h, rem = divmod(rem, 3600)
                        m, s = divmod(rem, 60)
                        if d > 0:
                            uptime_str = f"{d}d {h:02d}:{m:02d}:{s:02d}"
                        else:
                            uptime_str = f"{h:02d}:{m:02d}:{s:02d}"
                    except Exception:
                        uptime_str = ""

                intf_val = hops[0].get('interface') if (hops and hops[0].get('interface')) else None

                all_routes.append({
                    'prefix': str(pfx),
                    'proto': proto_name,
                    'pref': pref_val,
                    'uptime': uptime_str,
                    'hops': hops,
                    'interface': intf_val,
                })
        except Exception:
            pass

        try:
            all_routes = sorted(all_routes, key=lambda x: int(ipaddress.ip_network(x['prefix']).network_address))
        except Exception:
            pass

        tbl_name = f"{network_instance}.0" if network_instance != 'default' else "inet.0"
        total = len(all_routes)
        lines = [
            f"{tbl_name}: {total} destinations, {total} routes ({total} active, 0 holddown, 0 hidden)",
            "+ = Active Route, - = Last Active, * = Both",
            ""
        ]

        for rt in all_routes:
            prefix = rt['prefix']
            tag = f"*[{rt['proto']}/{rt['pref']}]"
            up = f" {rt['uptime']}" if rt['uptime'] else ""
            lines.append(f"{prefix:<20}{tag}{up}")

            if rt['proto'] == 'Local':
                intf_str = format_junos_intf(rt['interface']) if rt['interface'] else "lo0.0"
                lines.append(f"                      Local via {intf_str}")
            elif rt['proto'] == 'Direct':
                intf_str = format_junos_intf(rt['interface']) if rt['interface'] else "-"
                lines.append(f"                    > via {intf_str}")
            elif rt['hops']:
                for h in rt['hops']:
                    h_ip = h.get('ip')
                    h_intf = format_junos_intf(h.get('interface')) if h.get('interface') else None
                    if h_ip and h_intf and h_intf != "-":
                        lines.append(f"                    > to {h_ip} via {h_intf}")
                    elif h_ip:
                        lines.append(f"                    > to {h_ip}")
                    elif h_intf and h_intf != "-":
                        lines.append(f"                    > via {h_intf}")
            else:
                lines.append("                    Receive")

        output.print_line("\n".join(lines).rstrip())
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line(f"Try SR Linux command: show network-instance {network_instance} route-table ipv4-unicast summary")

    def show_route_summary(self, state, output):
        """Display Juniper JUNOS style 'show route summary'."""
        asn = "--"
        router_id = "--"

        # Query BGP AS and router ID
        try:
            path_bgp = build_path('/network-instance[name=default]/protocols/bgp')
            bgp_data = state.server.get_data_store(DataStore.State).get_data(path_bgp, recursive=True)
            bgp = bgp_data.network_instance.get().protocols.get().bgp.get()
            asn = _safe_get(bgp, 'autonomous_system', '--')
            router_id = _safe_get(bgp, 'router_id', '--')
        except Exception:
            pass

        # Query route counts
        direct_count = 0
        local_count = 0
        bgp_count = 0
        static_count = 0
        ospf_count = 0
        isis_count = 0

        try:
            path_rt = build_path('/network-instance[name=default]/route-table/ipv4-unicast/route[ipv4-prefix=*]')
            rt_data = state.server.get_data_store(DataStore.State).get_data(path_rt, recursive=True)
            for r in rt_data.network_instance.get().route_table.get().ipv4_unicast.get().route.items():
                rtype = str(_safe_get(r, 'route_type', '')).lower()
                rowner = str(_safe_get(r, 'route_owner', '')).lower()
                if 'connected' in rowner or (rtype == 'local' and 'host' not in rtype):
                    direct_count += 1
                elif 'host' in rtype or 'local' in rowner:
                    local_count += 1
                elif 'bgp' in rtype or 'bgp' in rowner:
                    bgp_count += 1
                elif 'static' in rtype or 'static' in rowner:
                    static_count += 1
                elif 'ospf' in rtype or 'ospf' in rowner:
                    ospf_count += 1
                elif 'isis' in rtype or 'isis' in rowner:
                    isis_count += 1
        except Exception:
            pass

        total_routes = direct_count + local_count + bgp_count + static_count + ospf_count + isis_count

        lines = [
            f"Autonomous system number: {asn}",
            f"Router ID: {router_id}",
            "",
            f"inet.0: {total_routes} destinations, {total_routes} routes ({total_routes} active, 0 holddown, 0 hidden)",
            f"{'Direct:':>20} {direct_count:>10} routes, {direct_count:>10} active",
            f"{'Local:':>20} {local_count:>10} routes, {local_count:>10} active",
            f"{'BGP:':>20} {bgp_count:>10} routes, {bgp_count:>10} active",
            f"{'Static:':>20} {static_count:>10} routes, {static_count:>10} active",
            f"{'OSPF:':>20} {ospf_count:>10} routes, {ospf_count:>10} active",
            f"{'IS-IS:':>20} {isis_count:>10} routes, {isis_count:>10} active"
        ]

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show network-instance default route-table summary")

    def show_bgp_summary(self, state, output):
        """Display Juniper JUNOS style 'show bgp summary'."""
        lines = []
        path = build_path('/network-instance[name=*]/protocols/bgp/neighbor[peer-address=*]')
        peers = []
        peer_groups = set()
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            for n in data.get_descendants('/network-instance/protocols/bgp/neighbor'):
                peer_ip = _safe_get(n, 'peer_address', '-')
                peer_as = _safe_get(n, 'peer_as', '--')
                oper = _safe_get(n, 'session_state', '--')
                state_str = str(oper).capitalize() if oper else '--'
                pg = _safe_get(n, 'peer_group', None)
                if pg:
                    peer_groups.add(str(pg))

                in_pkts = "--"
                recv = _safe_get(n, 'received_messages', None)
                if recv:
                    node = recv.get() if hasattr(recv, 'get') else recv
                    val = _safe_get(node, 'total_messages', None)
                    if val is not None:
                        in_pkts = str(val)

                out_pkts = "--"
                out_q = "0"
                sent = _safe_get(n, 'sent_messages', None)
                if sent:
                    node = sent.get() if hasattr(sent, 'get') else sent
                    val = _safe_get(node, 'total_messages', None)
                    if val is not None:
                        out_pkts = str(val)
                    qd = _safe_get(node, 'queue_depth', None)
                    if qd is not None:
                        out_q = str(qd)

                uptime = _safe_get(n, 'last_established', '--')
                if '(' in str(uptime):
                    uptime = str(uptime).split('(')[-1].rstrip(')')
                flaps = _safe_get(n, 'established_transitions', '0')
                peers.append({
                    'peer_ip': peer_ip,
                    'peer_as': peer_as,
                    'in_pkts': in_pkts,
                    'out_pkts': out_pkts,
                    'out_q': out_q,
                    'flaps': flaps,
                    'uptime': uptime,
                    'state': state_str
                })
        except Exception:
            pass

        # Query configured peer-groups if available
        try:
            pg_path = build_path('/network-instance[name=*]/protocols/bgp/peer-group[peer-group-name=*]')
            pg_data = state.server.get_data_store(DataStore.State).get_data(pg_path, recursive=False)
            for g in pg_data.get_descendants('/network-instance/protocols/bgp/peer-group'):
                gname = _safe_get(g, 'peer_group_name', None)
                if gname:
                    peer_groups.add(str(gname))
        except Exception:
            pass

        num_groups = len(peer_groups) if peer_groups else (1 if peers else 0)

        # Query route counts for active tables
        tables = []
        pfx_count = 0
        try:
            rt_path = build_path('/network-instance[name=default]/route-table/ipv4-unicast/route[ipv4-prefix=*]')
            rt_data = state.server.get_data_store(DataStore.State).get_data(rt_path, recursive=False)
            pfx_count = len(list(rt_data.get_descendants('/network-instance/route-table/ipv4-unicast/route')))
        except Exception:
            pass
        tables.append(("inet.0", pfx_count))

        try:
            rt6_path = build_path('/network-instance[name=default]/route-table/ipv6-unicast/route[ipv6-prefix=*]')
            rt6_data = state.server.get_data_store(DataStore.State).get_data(rt6_path, recursive=False)
            pfx6_count = len(list(rt6_data.get_descendants('/network-instance/route-table/ipv6-unicast/route')))
            if pfx6_count > 0:
                tables.append(("inet6.0", pfx6_count))
        except Exception:
            pass

        down_peers = sum(1 for p in peers if p['state'].lower() != 'established')
        lines.append(f"Groups: {num_groups} Peers: {len(peers)} Down peers: {down_peers}")
        lines.append("Table          Tot Paths  Act Paths Suppressed    History Damp State    Pending")
        for t_name, t_cnt in tables:
            lines.append(f"{t_name:<14} {t_cnt:<10} {t_cnt:<10} 0          0          0          0")
        lines.append(f"{'Peer':<24} {'AS':<7} {'InPkt':<9} {'OutPkt':<10} {'OutQ':<6} {'Flaps':<5} {'Last Up/Down':<12} {'State'}")

        for p in peers:
            lines.append(f"{p['peer_ip']:<24} {str(p['peer_as']):<7} {str(p['in_pkts']):<9} {str(p['out_pkts']):<10} {str(p.get('out_q', '0')):<6} {str(p['flaps']):<5} {str(p['uptime']):<12} {p['state']}")

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show network-instance default protocols bgp neighbor")

    def show_ospf_neighbor(self, state, output):
        """Display Juniper JUNOS style 'show ospf neighbor'."""
        lines = [
            f"{'Address':<16} {'Interface':<23} {'State':<9} {'ID':<16} {'Pri':<4} {'Dead'}"
        ]
        path = build_path('/network-instance[name=*]/protocols/ospf/instance[name=*]/area[area-id=*]/interface[interface-name=*]/neighbor[router-id=*]')
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
                                        for intf in area.interface.items():
                                            intf_name = format_junos_intf(intf.interface_name, with_unit=True)
                                            if hasattr(intf, 'neighbor'):
                                                for n in intf.neighbor.items():
                                                    r_id = _safe_get(n, 'router_id', '--')
                                                    adj_st = _safe_get(n, 'adjacency_state', None)
                                                    n_state = str(adj_st).split(':')[-1].capitalize() if adj_st else '--'
                                                    ip = _safe_get(n, 'address', '--')
                                                    pri = _safe_get(n, 'priority', '--')
                                                    dead = _safe_get(n, 'dead_time', '--')
                                                    lines.append(f"{str(ip):<16} {intf_name:<23} {n_state:<9} {str(r_id):<16} {str(pri):<4} {str(dead)}")
        except Exception:
            pass

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show network-instance default protocols ospf neighbor")

    def show_isis_adjacency(self, state, output):
        """Display Juniper JUNOS style 'show isis adjacency'."""
        lines = [
            f"{'Interface':<21} {'System':<14} {'L':<2} {'State':<13} {'Hold (secs)':<12} {'SNPA'}"
        ]
        path = build_path('/network-instance[name=*]/protocols/isis/instance[name=*]/interface[interface-name=*]/adjacency[neighbor-system-id=*][adjacency-level=*]')
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            for ni in data.network_instance.items():
                if hasattr(ni, 'protocols') and ni.protocols.exists():
                    isis = _safe_get(ni.protocols.get(), 'isis', None)
                    if isis and hasattr(isis.get(), 'instance'):
                        for inst in isis.get().instance.items():
                            if hasattr(inst, 'interface'):
                                for iface in inst.interface.items():
                                    intf = format_junos_intf(iface.interface_name, with_unit=True)
                                    adj_list = _safe_get(iface, 'adjacency')
                                    if adj_list is not None and hasattr(adj_list, 'items'):
                                        for adj in adj_list.items():
                                            sys_id = _safe_get(adj, 'neighbor_hostname', None) or _safe_get(adj, 'neighbor_system_id', '-')
                                            level = str(_safe_get(adj, 'adjacency_level', '2'))
                                            raw_st = _safe_get(adj, 'state', '--')
                                            oper = str(raw_st).split(':')[-1].capitalize() if raw_st else '--'
                                            hold = str(_safe_get(adj, 'remaining_holdtime', '--'))
                                            snpa_raw = _safe_get(adj, 'neighbor_snpa', None)
                                            snpa = format_mac_junos(snpa_raw) if snpa_raw else '--'
                                            lines.append(f"{intf:<21} {str(sys_id):<14} {level:<2} {oper:<13} {hold:<12} {snpa}")
        except Exception:
            pass

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show network-instance default protocols isis adjacency")
