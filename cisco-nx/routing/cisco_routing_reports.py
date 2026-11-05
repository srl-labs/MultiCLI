#!/usr/bin/python
###########################################################################
# Description: MultiCLI Routing Reports for Cisco NX-OS
# Copyright (c) 2025-2026 Nokia
###########################################################################

import datetime
import re
from srlinux.location import build_path
from srlinux.schema.data_store import DataStore
from cisco_interface_reports import format_cisco_intf


def _safe_get(node, attr, default=None):
    """Safely read an attribute from an SR Linux Data object without raising DataError."""
    if node is None:
        return default
    try:
        val = getattr(node, attr)
        return val if val is not None else default
    except Exception:
        return default


def format_mac_cisco(mac):
    """Convert MAC address to Cisco standard format xxxx.xxxx.xxxx."""
    if not mac:
        return "0000.0000.0000"
    raw = re.sub(r'[^0-9a-fA-F]', '', str(mac)).lower()
    raw = raw.zfill(12)
    return f"{raw[0:4]}.{raw[4:8]}.{raw[8:12]}"

class CiscoRoutingReports:
    """Handles Cisco NX-OS routing show commands."""

    def show_vrf(self, state, output):
        """Display Cisco NX-OS style 'show vrf'."""
        lines = [
            f"{'VRF-Name':<20} {'VRF-ID':<7} {'State':<7} {'Reason'}",
        ]
        path = build_path('/network-instance[name=*]')
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=False)
            vrf_id = 1
            for ni in sorted(data.network_instance.items(), key=lambda x: str(x.name)):
                name = ni.name
                oper = _safe_get(ni, 'oper_state', 'up')
                state_str = "Up" if oper == "up" else "Down"
                lines.append(f"{name:<20} {str(vrf_id):<7} {state_str:<7} {'--'}")
                vrf_id += 1
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
        """Display Cisco NX-OS style 'show vlan'."""
        lines = [
            f"{'VLAN':<5} {'Name':<32} {'Status':<9} {'Ports'}",
            f"----- -------------------------------- --------- -------------------------------"
        ]
        intfs_by_ni = {}
        vlan_by_ni = {}
        try:
            intf_p = build_path('/network-instance[name=*]/interface[name=*]')
            intf_data = state.server.get_data_store(DataStore.State).get_data(intf_p, recursive=False)
            for ni in intf_data.network_instance.items():
                if hasattr(ni, 'interface'):
                    raw_ports = [intf.name for intf in ni.interface.items()]
                    intfs_by_ni[ni.name] = [format_cisco_intf(p, short=True) for p in raw_ports]
                    vlan_by_ni[ni.name] = self._get_vlan_for_ni(state, raw_ports)
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
                status = "active" if oper == "up" else "suspend"

                ports = intfs_by_ni.get(name, [])
                vlan_tag = vlan_by_ni.get(name, "--")

                ports_str = ", ".join(ports) if ports else "--"
                lines.append(f"{str(vlan_tag):<5} {name:<32} {status:<9} {ports_str}")
        except Exception:
            pass

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show network-instance summary")

    def show_ip_arp(self, state, output):
        """Display Cisco NX-OS style 'show ip arp'."""
        lines = [
            f"{'Address':<16} {'Age':<9} {'MAC Address':<17} {'Interface'}"
        ]
        found = False
        try:
            path_arpnd = build_path('/interface[name=*]/subinterface[index=*]/ipv4/arp/neighbor[ipv4-address=*]')
            data_arpnd = state.server.get_data_store(DataStore.State).get_data(path_arpnd, recursive=True)
            for intf in data_arpnd.interface.items():
                if hasattr(intf, 'subinterface'):
                    for sub in intf.subinterface.items():
                        if hasattr(sub, 'ipv4') and sub.ipv4.exists():
                            arp = _safe_get(sub.ipv4.get(), 'arp', None)
                            if arp and hasattr(arp.get(), 'neighbor'):
                                arp_node = arp.get()
                                timeout_val = _safe_get(arp_node, 'timeout', 14400) or 14400
                                for n in arp_node.neighbor.items():
                                    found = True
                                    ip = n.ipv4_address
                                    mac = format_mac_cisco(_safe_get(n, 'link_layer_address', ''))
                                    full_intf = f"{intf.name}.{sub.index}" if str(sub.index) != '0' else intf.name
                                    c_intf = format_cisco_intf(full_intf, short=True)

                                    age_str = "--"
                                    origin = _safe_get(n, 'origin', '')
                                    exp_time = _safe_get(n, 'expiration_time', None)
                                    if exp_time and origin != 'static':
                                        try:
                                            ts_str = str(exp_time).split('(')[0].strip()
                                            if ts_str.endswith('Z'):
                                                ts_str = ts_str[:-1] + '+00:00'
                                            exp_dt = datetime.datetime.fromisoformat(ts_str)
                                            now = datetime.datetime.now(datetime.timezone.utc)
                                            rem_seconds = (exp_dt - now).total_seconds()
                                            age_sec = max(0, int(timeout_val - rem_seconds))
                                            h, r = divmod(age_sec, 3600)
                                            m, s = divmod(r, 60)
                                            age_str = f"{h:02d}:{m:02d}:{s:02d}"
                                        except Exception:
                                            age_str = "00:00:00"
                                    elif origin == 'dynamic':
                                        age_str = "00:00:00"

                                    lines.append(f"{ip:<16} {age_str:<9} {mac:<17} {c_intf}")
        except Exception:
            pass

        if not found:
            try:
                path = build_path('/network-instance[name=*]/neighbor[ipv4-address=*]')
                data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
                for ni in data.network_instance.items():
                    if hasattr(ni, 'neighbor'):
                        for n in ni.neighbor.items():
                            found = True
                            ip = n.ipv4_address
                            mac = format_mac_cisco(_safe_get(n, 'link_layer_address', ''))
                            intf_name = str(_safe_get(n, 'interface', ''))
                            if intf_name.endswith('.0'):
                                intf_name = intf_name[:-2]
                            intf = format_cisco_intf(intf_name, short=True)
                            lines.append(f"{ip:<16} {'--':<9} {mac:<17} {intf}")
            except Exception:
                pass

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show arpnd arp-entries")

    def show_bfd_neighbors(self, state, output):
        """Display Cisco NX-OS style 'show bfd neighbors'."""
        lines = [
            f"{'OurAddr':<15} {'NeighAddr':<15} {'LD/RD':<7} {'RH/RS':<7} {'Holdown(mult)':<15} {'State':<7} {'Int':<8} {'Vrf':<8} {'Type'}"
        ]
        ip_to_intf = {}
        try:
            intf_path = build_path('/interface[name=*]/subinterface[index=*]/ipv4/address[ip-prefix=*]')
            intf_data = state.server.get_data_store(DataStore.State).get_data(intf_path, recursive=True)
            for intf in intf_data.interface.items():
                sub_list = _safe_get(intf, 'subinterface')
                if sub_list is not None:
                    for sub in sub_list.items():
                        full_name = f"{intf.name}.{sub.index}" if str(sub.index) != '0' else str(intf.name)
                        ipv4_c = _safe_get(sub, 'ipv4')
                        if ipv4_c is not None and ipv4_c.exists():
                            addr_list = _safe_get(ipv4_c.get(), 'address')
                            if addr_list is not None:
                                for a in addr_list.items():
                                    pfx = _safe_get(a, 'ip_prefix')
                                    if pfx:
                                        ip_only = str(pfx).split('/')[0]
                                        ip_to_intf[ip_only] = full_name
        except Exception:
            pass

        path = build_path('/bfd/network-instance[name=*]/peer[local-discriminator=*]')
        found = False
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            bfd_node = data.bfd.get() if hasattr(data.bfd, 'get') else data.bfd
            ni_list = _safe_get(bfd_node, 'network_instance')
            if ni_list is not None:
                for ni in ni_list.items():
                    vrf = ni.name
                    peer_list = _safe_get(ni, 'peer')
                    if peer_list is not None:
                        for p in peer_list.items():
                            found = True
                            our_addr = str(_safe_get(p, 'local_address', '--'))
                            neigh_addr = str(_safe_get(p, 'remote_address', '--'))
                            ld = _safe_get(p, 'local_discriminator', '--')
                            rd = _safe_get(p, 'remote_discriminator', '--')
                            state_val = str(_safe_get(p, 'oper_state', 'down')).capitalize()
                            intf_raw = (
                                _safe_get(p, 'ipv4_unnumbered_interface')
                                or _safe_get(p, 'ipv6_link_local_interface')
                                or ip_to_intf.get(our_addr, '')
                            )
                            intf = format_cisco_intf(intf_raw, short=True) if intf_raw else '--'
                            rh_rs = "Up/Up" if state_val == "Up" else f"{state_val}/--"
                            mult = _safe_get(p, 'remote_multiplier')
                            rx_int = _safe_get(p, 'active_receive_interval')
                            if mult is not None and rx_int is not None:
                                try:
                                    hold_ms = (int(rx_int) * int(mult)) // 1000
                                    holdown_str = f"{hold_ms}({mult})"
                                except Exception:
                                    holdown_str = f"--({mult})"
                            elif mult is not None:
                                holdown_str = f"--({mult})"
                            else:
                                holdown_str = "--"
                            raw_proto = _safe_get(p, 'subscribed_protocols')
                            if isinstance(raw_proto, (list, tuple)):
                                proto_type = ",".join(str(x) for x in raw_proto) if raw_proto else "--"
                            elif raw_proto:
                                proto_type = str(raw_proto).strip("[]'\"") or "--"
                            else:
                                proto_type = "--"
                            lines.append(f"{our_addr:<15} {neigh_addr:<15} {f'{ld}/{rd}':<7} {rh_rs:<7} {holdown_str:<15} {state_val:<7} {intf:<8} {vrf:<8} {proto_type}")
        except Exception:
            pass

        if not found:
            lines.append("")

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: info from state bfd")

    def show_ip_ospf_neighbor(self, state, output):
        """Display Cisco NX-OS style 'show ip ospf neighbor'."""
        lines = [
            f"{'Neighbor ID':<15} {'Pri':<4} {'State':<15} {'Up Time':<9} {'Address':<15} {'Interface'}"
        ]
        path = build_path('/network-instance[name=*]/protocols/ospf/instance[name=*]/area[area-id=*]/interface[interface-name=*]/neighbor[router-id=*]')
        found = False
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
                                            intf_name = format_cisco_intf(intf.interface_name, short=True)
                                            if hasattr(intf, 'neighbor'):
                                                for n in intf.neighbor.items():
                                                    found = True
                                                    r_id = _safe_get(n, 'router_id', '--')
                                                    adj_st = _safe_get(n, 'adjacency_state')
                                                    n_state = str(adj_st).split(':')[-1].upper() if adj_st else '--'
                                                    ip = _safe_get(n, 'address', '--')
                                                    pri = _safe_get(n, 'priority', '--')
                                                    uptime_str = "--"
                                                    last_est = _safe_get(n, 'last_established_time')
                                                    if last_est:
                                                        try:
                                                            s_est = str(last_est)
                                                            if '(' in s_est:
                                                                uptime_str = s_est.split('(')[-1].rstrip(')').replace(' ago', '')
                                                            else:
                                                                t_str = s_est.replace('Z', '+00:00')
                                                                dt = datetime.datetime.fromisoformat(t_str)
                                                                if dt.tzinfo is None:
                                                                    dt = dt.replace(tzinfo=datetime.timezone.utc)
                                                                delta = datetime.datetime.now(datetime.timezone.utc) - dt
                                                                days = delta.days
                                                                hours, remainder = divmod(delta.seconds, 3600)
                                                                mins, secs = divmod(remainder, 60)
                                                                if days > 0:
                                                                    uptime_str = f"{days}d{hours:02d}h"
                                                                else:
                                                                    uptime_str = f"{hours:02d}:{mins:02d}:{secs:02d}"
                                                        except Exception:
                                                            uptime_str = "--"
                                                    lines.append(f"{r_id:<15} {str(pri):<4} {n_state:<15} {uptime_str:<9} {str(ip):<15} {intf_name}")
        except Exception:
            pass

        if not found:
            lines.append("No OSPF neighbors configured or active.")

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show network-instance default protocols ospf neighbor")

    def show_ip_ospf_interface_brief(self, state, output):
        """Display Cisco NX-OS style 'show ip ospf interface brief'."""
        lines = [
            f"{'Interface':<15} {'VRF-Name':<12} {'State':<6} {'Area':<15} {'IP Address/Mask':<20} {'Cost'}",
            "--------------- ------------ ------ --------------- -------------------- -----"
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

        found = False
        path = build_path('/network-instance[name=*]/protocols/ospf/instance[name=*]/area[area-id=*]/interface[interface-name=*]')
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            for ni in data.network_instance.items():
                vrf = ni.name
                if hasattr(ni, 'protocols') and ni.protocols.exists():
                    ospf = getattr(ni.protocols.get(), 'ospf', None)
                    if not ospf:
                        continue
                    ospf_obj = ospf.get() if hasattr(ospf, 'get') else ospf
                    
                    if hasattr(ospf_obj, 'instance'):
                        for inst in ospf_obj.instance.items():
                            if hasattr(inst, 'area'):
                                for area in inst.area.items():
                                    area_id = str(_safe_get(area, 'area_id', '0.0.0.0'))
                                    if hasattr(area, 'interface'):
                                        for iface in area.interface.items():
                                            found = True
                                            raw_name = str(iface.interface_name)
                                            intf_disp = format_cisco_intf(raw_name, short=True)
                                            cost = str(_safe_get(iface, 'metric', 10))
                                            st = str(_safe_get(iface, 'oper_state', 'down')).upper()
                                            ip_mask = intf_ip_map.get(raw_name) or str(_safe_get(iface, 'local_ip_address', '--') or '--')
                                            lines.append(f"{intf_disp:<15} {vrf:<12} {st:<6} {area_id:<15} {ip_mask:<20} {cost}")
        except Exception:
            pass

        if not found:
            lines = [
                f"{'Interface':<15} {'VRF-Name':<12} {'State':<6} {'Area':<15} {'IP Address/Mask':<20} {'Cost'}",
                "--------------- ------------ ------ --------------- -------------------- -----",
                "No OSPF interfaces configured."
            ]

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show network-instance default protocols ospf interface")

    def show_nve_vni(self, state, output):
        """Display Cisco NX-OS style 'show nve vni'."""
        lines = [
            f"{'VNI':<10} {'Type':<9} {'Mode':<9} {'BD/VRF':<22} {'Flags':<6} {'State'}",
            "--------- --------- --------- ---------------------- ------ -----"
        ]
        vxlan_to_ni = {}
        try:
            ni_data = state.server.get_data_store(DataStore.State).get_data(build_path('/network-instance[name=*]'), recursive=False)
            ni_types = {ni.name: ("L2" if _safe_get(ni, 'type', 'default') == 'mac-vrf' else "L3") for ni in ni_data.network_instance.items()}
            vxi_data = state.server.get_data_store(DataStore.State).get_data(build_path('/network-instance[name=*]/vxlan-interface[name=*]'), recursive=False)
            for ni in vxi_data.network_instance.items():
                vni_type = ni_types.get(ni.name, "L2")
                if hasattr(ni, 'vxlan_interface'):
                    for vxi in ni.vxlan_interface.items():
                        vxlan_to_ni[vxi.name] = (ni.name, vni_type)
        except Exception:
            pass

        rows = []
        try:
            data = state.server.get_data_store(DataStore.State).get_data(build_path('/tunnel-interface[name=*]/vxlan-interface[index=*]'), recursive=True)
            for ti in data.tunnel_interface.items():
                t_name = ti.name
                if hasattr(ti, 'vxlan_interface'):
                    for vxi in ti.vxlan_interface.items():
                        v_idx = vxi.index
                        full_vxi = f"{t_name}.{v_idx}"
                        oper = str(_safe_get(vxi, 'oper_state', 'down')).capitalize()
                        vni_num = "--"
                        if hasattr(vxi, 'ingress') and vxi.ingress.exists():
                            vni_num = str(_safe_get(vxi.ingress.get(), 'vni', '--'))
                        
                        ni_info = vxlan_to_ni.get(full_vxi, (t_name, "L2"))
                        rows.append({
                            'vni': vni_num,
                            'type': ni_info[1],
                            'mode': 'DP',
                            'bd_vrf': ni_info[0],
                            'flags': 'CP',
                            'state': oper
                        })
        except Exception:
            pass

        if rows:
            rows.sort(key=lambda r: int(r['vni']) if r['vni'].isdigit() else 999999)
            for r in rows:
                lines.append(f"{r['vni']:<10} {r['type']:<9} {r['mode']:<9} {r['bd_vrf']:<22} {r['flags']:<6} {r['state']}")
        else:
            lines.append("No VNIs configured.")

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show network-instance * vxlan-interface")

    def show_nve_peers(self, state, output):
        """Display Cisco NX-OS style 'show nve peers'."""
        lines = [
            f"{'Interface':<10} {'Peer-IP':<16} {'Source-Interface':<17} {'State':<8} {'Learn-Type'}",
            "---------  ---------------  ----------------  -------  ----------"
        ]
        rows = []
        try:
            path = build_path('/tunnel-interface[name=*]/vxlan-interface[index=*]')
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            for ti in data.tunnel_interface.items():
                vxi_list = _safe_get(ti, 'vxlan_interface')
                if vxi_list is not None:
                    for vxi in vxi_list.items():
                        vxi_name = f"{ti.name}.{vxi.index}"
                        vxi_oper = str(_safe_get(vxi, 'oper_state', 'up')).capitalize()
                        bt = _safe_get(vxi, 'bridge_table')
                        if bt is not None and bt.exists():
                            bt_node = bt.get()
                            for dest_container_name in ('unicast_destinations', 'multicast_destinations'):
                                dc = _safe_get(bt_node, dest_container_name)
                                if dc is not None and dc.exists():
                                    dc_node = dc.get()
                                    dest_list = _safe_get(dc_node, 'destination')
                                    if dest_list is not None:
                                        for dest in dest_list.items():
                                            vtep = _safe_get(dest, 'vtep')
                                            if vtep:
                                                dest_oper = str(_safe_get(dest, 'oper_state') or vxi_oper or 'Up').capitalize()
                                                rows.append({
                                                    'intf': 'nve1',
                                                    'peer': str(vtep),
                                                    'src': vxi_name,
                                                    'state': dest_oper if dest_oper in ('Up', 'Down') else 'Up',
                                                    'learn': 'CP'
                                                })
        except Exception:
            pass

        seen = set()
        unique_rows = []
        for r in rows:
            if r['peer'] not in seen:
                seen.add(r['peer'])
                unique_rows.append(r)

        if unique_rows:
            for r in unique_rows:
                lines.append(f"{r['intf']:<10} {r['peer']:<16} {r['src']:<17} {r['state']:<8} {r['learn']}")
        else:
            lines.append("No NVE peers discovered.")

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show tunnel-interface vxlan-interface bridge-table unicast-destinations destination")

    def show_vpc(self, state, output):
        """Display Cisco NX-OS style 'show vpc'."""
        lines = []
        found = False
        vpc_rows = []
        domain_id = 1
        peer_link_up = False
        try:
            path = build_path('/system/network-instance/protocols/evpn/ethernet-segments')
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            sys_node = _safe_get(data, 'system', None)
            if sys_node and hasattr(sys_node.get(), 'network_instance'):
                sys_ni = sys_node.get().network_instance.get()
                if hasattr(sys_ni, 'protocols'):
                    evpn = _safe_get(sys_ni.protocols.get(), 'evpn', None)
                    if evpn and hasattr(evpn.get(), 'ethernet_segments'):
                        es_container = evpn.get().ethernet_segments.get()
                        if hasattr(es_container, 'bgp_instance'):
                            for bi in es_container.bgp_instance.items():
                                domain_id = _safe_get(bi, 'id', 1)
                                if hasattr(bi, 'ethernet_segment'):
                                    for es_idx, es in enumerate(bi.ethernet_segment.items(), 1):
                                        found = True
                                        intf = '--'
                                        try:
                                            intf_attr = _safe_get(es, 'interface', None)
                                            if isinstance(intf_attr, str) and intf_attr:
                                                intf = intf_attr
                                            elif intf_attr is not None and hasattr(intf_attr, 'items'):
                                                for item in intf_attr.items():
                                                    for field in ('ethernet_interface', 'interface_name', 'name'):
                                                        val = _safe_get(item, field, None)
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
                                        admin_st = _safe_get(es, 'admin_state', 'enable')
                                        oper_st = str(_safe_get(es, 'oper_state', 'down')).lower()
                                        is_up = (admin_st == 'enable' and oper_st == 'up')
                                        if is_up:
                                            peer_link_up = True
                                        vpc_rows.append({
                                            'id': str(es_idx),
                                            'port': format_cisco_intf(intf, short=True) if intf != '--' else '--',
                                            'status': 'Up' if is_up else 'Down',
                                            'att': '1' if is_up else '0',
                                            'consistency': 'Passed' if is_up else 'Failed'
                                        })
        except Exception:
            pass

        if found:
            peer_st_str = "peer-link is up" if peer_link_up else "peer-link is down"
            ka_st_str = "Active" if peer_link_up else "Inactive"
            cfg_st_str = "success" if peer_link_up else "failed"
            pl_num = "1" if peer_link_up else "0"
            lines = [
                "Legend:",
                "                (*) - local vPC is down, forwarding via vPC peer-link",
                "",
                f"vPC domain id                     : {domain_id}",
                f"Peer status                       : {peer_st_str}",
                f"vPC keep-alive status             : {ka_st_str}",
                f"Configuration status              : {cfg_st_str}",
                f"Peer-link status                  : {pl_num}",
                "",
                "vPC status",
                "----------------------------------------------------------------------------",
                f"{'Id':<5} {'Port':<23} {'Status':<7} {'Att':<4} {'Consistency'}",
                "--    ----------------------  ------  ---  -----------",
            ]
            for r in vpc_rows:
                lines.append(f"{r['id']:<5} {r['port']:<23} {r['status']:<7} {r['att']:<4} {r['consistency']}")
        else:
            lines = [
                "vPC domain id                     : --",
                "Peer status                       : peer-link is down",
                "vPC keep-alive status             : Disabled / Not Configured",
                "Configuration status              : Disabled",
                "",
                "vPC is not configured on this device."
            ]

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show system network-instance ethernet-segments")
