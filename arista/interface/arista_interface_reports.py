#!/usr/bin/python
###########################################################################
# Description: MultiCLI Arista EOS Interface Reports
# Commands: show ip interface brief, show interfaces description,
#           show lldp neighbors (and detail), show port-channel summary, show ip arp
# Copyright (c) 2026 Nokia
###########################################################################

import datetime
import re
from srlinux.location import build_path
from srlinux.schema.data_store import DataStore

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
    if name.startswith('lo'):
        num = name.replace('lo', '')
        return f"Lo{num}" if short else f"Loopback{num}"
    if name.startswith('system'):
        num = name.replace('system', '') or '0'
        return f"Lo{num}" if short else f"Loopback{num}"
    return name

def arista_intf_sort_key(name):
    """
    Produce a sorting key that orders interfaces naturally/numerically:
    1. Family Priority (Ethernet -> Loopback -> Management -> Port-Channel -> Vlan)
    2. Tuple of integer components extracted from name (e.g., (1, 2) for Ethernet1/2)
    3. Lowercase name string as fallback
    """
    if not name:
        return (99, (), "")
    s = str(name).strip()
    s_lower = s.lower()

    if s_lower.startswith(('ethernet', 'et')):
        prio = 1
    elif s_lower.startswith(('loopback', 'lo', 'system')):
        prio = 2
    elif s_lower.startswith(('management', 'ma', 'mgmt')):
        prio = 3
    elif s_lower.startswith(('port-channel', 'po', 'lag')):
        prio = 4
    elif s_lower.startswith(('vlan', 'irb')):
        prio = 5
    elif s_lower.startswith(('vxlan',)):
        prio = 6
    else:
        prio = 10

    nums = tuple(int(x) for x in re.findall(r'\d+', s))
    return (prio, nums, s_lower)

class AristaInterfaceReports:
    """Handles Arista EOS interface show commands."""

    def show_ip_interface_brief(self, state, output):
        """Display Arista EOS style 'show ip interface brief'."""
        lines = [
            f"{'Interface':<22} {'IP Address':<18} {'Status':<10} {'Protocol':<16} {'MTU':<6}"
        ]
        rows = []
        
        path = build_path('/interface[name=*]')
        try:
            intf_data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            for intf in intf_data.interface.items():
                intf_name = intf.name
                parent_admin = getattr(intf, 'admin_state', 'disable')
                parent_oper = getattr(intf, 'oper_state', 'down')
                mtu_val = getattr(intf, 'mtu', 1500) or 1500

                # Check subinterfaces
                has_sub = False
                if hasattr(intf, 'subinterface'):
                    for sub in sorted(intf.subinterface.items(), key=lambda s: int(getattr(s, 'index', 0))):
                        has_sub = True
                        sub_admin = getattr(sub, 'admin_state', parent_admin)
                        sub_oper = getattr(sub, 'oper_state', parent_oper)
                        
                        status = "up" if sub_admin == "enable" else "admin down"
                        proto = "up" if sub_oper == "up" else "down"
                        if status == "admin down" and proto == "down":
                            proto = "down"

                        # Retrieve IPv4 address
                        ip_addr = "unassigned"
                        if hasattr(sub, 'ipv4') and sub.ipv4.exists():
                            ipv4_obj = sub.ipv4.get()
                            if hasattr(ipv4_obj, 'address'):
                                for addr in ipv4_obj.address.items():
                                    pfx = getattr(addr, 'ip_prefix', None)
                                    if pfx:
                                        ip_addr = str(pfx)
                                        break

                        sub_mtu = getattr(sub, 'ip_mtu', None) or mtu_val
                        sub_name = f"{intf_name}.{sub.index}"
                        display_name = format_arista_intf(sub_name, short=False)
                        rows.append({
                            'display_name': display_name,
                            'ip_addr': ip_addr,
                            'status': status,
                            'proto': proto,
                            'mtu': str(sub_mtu)
                        })

                if not has_sub:
                    status = "up" if parent_admin == "enable" else "admin down"
                    proto = "up" if parent_oper == "up" else "down"
                    display_name = format_arista_intf(intf_name, short=False)
                    rows.append({
                        'display_name': display_name,
                        'ip_addr': "unassigned",
                        'status': status,
                        'proto': proto,
                        'mtu': str(mtu_val)
                    })
        except Exception:
            pass

        rows.sort(key=lambda r: arista_intf_sort_key(r['display_name']))
        for r in rows:
            lines.append(f"{r['display_name']:<22} {r['ip_addr']:<18} {r['status']:<10} {r['proto']:<16} {r['mtu']:<6}")

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show interface brief")

    def show_interfaces_description(self, state, output):
        """Display Arista EOS style 'show interfaces description'."""
        lines = [
            f"{'Interface':<30} {'Status':<14} {'Protocol':<18} {'Description'}"
        ]
        rows = []
        path = build_path('/interface[name=*]')
        try:
            intf_data = state.server.get_data_store(DataStore.State).get_data(path, recursive=False)
            for intf in intf_data.interface.items():
                name = intf.name
                admin_state = getattr(intf, 'admin_state', 'disable')
                oper_state = getattr(intf, 'oper_state', 'down')
                descr = getattr(intf, 'description', '') or ''

                status = "up" if admin_state == "enable" else "admin down"
                proto = "up" if oper_state == "up" else "down"
                disp_name = format_arista_intf(name, short=True)
                rows.append({
                    'disp_name': disp_name,
                    'status': status,
                    'proto': proto,
                    'descr': descr
                })
        except Exception:
            pass

        rows.sort(key=lambda r: arista_intf_sort_key(r['disp_name']))
        for r in rows:
            lines.append(f"{r['disp_name']:<30} {r['status']:<14} {r['proto']:<18} {r['descr']}")

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show interface")

    def show_lldp_neighbors(self, state, output, detail=False):
        """Display Arista EOS style 'show lldp neighbors [detail]'."""
        neighbors = []
        calculated_ttl = 120
        age_outs = 0
        table_drops = 0
        min_elapsed_seconds = None

        try:
            lldp_sys_path = build_path('/system/lldp')
            lldp_sys_data = state.server.get_data_store(DataStore.State).get_data(lldp_sys_path, recursive=False)
            lldp_node = lldp_sys_data.system.get().lldp.get()
            hello = getattr(lldp_node, 'hello_timer', 30) or 30
            multiplier = getattr(lldp_node, 'hold_multiplier', 4) or 4
            calculated_ttl = int(hello) * int(multiplier)
            if hasattr(lldp_node, 'statistics') and lldp_node.statistics.exists():
                stats = lldp_node.statistics.get()
                age_outs = getattr(stats, 'entries_aged_out', 0) or 0
                table_drops = getattr(stats, 'frame_discard', 0) or getattr(stats, 'frame_error_in', 0) or 0
        except Exception:
            pass

        path = build_path('/system/lldp/interface[name=*]/neighbor[id=*]')
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            for iface in data.get_descendants('/system/lldp/interface'):
                local_name = getattr(iface, 'name', '')
                if hasattr(iface, 'neighbor'):
                    for neigh in iface.neighbor.items():
                        sys_name = getattr(neigh, 'system_name', '') or ''
                        port_id = getattr(neigh, 'port_id', '') or ''
                        chassis_id = getattr(neigh, 'chassis_id', '') or ''
                        sys_descr = getattr(neigh, 'system_description', '') or ''
                        port_descr = getattr(neigh, 'port_description', '') or ''
                        mgmt_addr = getattr(neigh, 'management_address', '') or ''
                        last_up = getattr(neigh, 'last_update', '')
                        if last_up:
                            try:
                                ts_str = str(last_up).split('(')[0].strip()
                                if ts_str.endswith('Z'):
                                    ts_str = ts_str[:-1] + '+00:00'
                                dt = datetime.datetime.fromisoformat(ts_str)
                                now = datetime.datetime.now(datetime.timezone.utc)
                                diff = max(0, int((now - dt).total_seconds()))
                                if min_elapsed_seconds is None or diff < min_elapsed_seconds:
                                    min_elapsed_seconds = diff
                            except Exception:
                                pass

                        neighbors.append({
                            'local_port': local_name,
                            'device_id': sys_name,
                            'port_id': port_id,
                            'chassis_id': chassis_id,
                            'sys_descr': sys_descr,
                            'port_descr': port_descr,
                            'mgmt_addr': mgmt_addr,
                            'ttl': calculated_ttl
                        })
        except Exception:
            pass

        if min_elapsed_seconds is not None:
            hours, rem = divmod(min_elapsed_seconds, 3600)
            minutes, seconds = divmod(rem, 60)
            last_change_str = f"{hours}:{minutes:02d}:{seconds:02d} ago"
        else:
            last_change_str = "never"

        lines = []
        if not detail:
            lines.append(f"Last table change time   : {last_change_str}")
            lines.append(f"Number of table inserts  : {len(neighbors)}")
            lines.append("Number of table deletes  : 0")
            lines.append(f"Number of table drops    : {table_drops}")
            lines.append(f"Number of table age-outs : {age_outs}")
            lines.append(f"{'Port':<13} {'Neighbor Device ID':<24} {'Neighbor Port ID':<22} {'TTL':<3}")
            lines.append(f"{'----------':<13} {'------------------------':<24} {'----------------------':<22} {'---':<3}")
            for n in neighbors:
                port_disp = format_arista_intf(n['local_port'], short=True)
                lines.append(f"{port_disp:<13} {n['device_id']:<24} {n['port_id']:<22} {str(n['ttl']):<3}")
        else:
            for n in neighbors:
                port_disp = format_arista_intf(n['local_port'], short=True)
                lines.append(f"Interface {port_disp} detected 1 LLDP neighbor:")
                lines.append("  Community:")
                lines.append(f"    Chassis ID:          {n['chassis_id']}")
                lines.append(f"    Port ID:             {n['port_id']}")
                lines.append(f"    Port Description:    {n['port_descr']}")
                lines.append(f"    System Name:         {n['device_id']}")
                lines.append(f"    System Description:  {n['sys_descr']}")
                lines.append(f"    Management Address:  {n['mgmt_addr']}")
                lines.append(f"    Time To Live:        {n['ttl']} seconds")
                lines.append("")

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show system lldp neighbor")

    def show_ip_arp(self, state, output):
        """Display Arista EOS style 'show ip arp'."""
        lines = [
            f"{'Address':<15} {'Age (min)':<11} {'Hardware Addr':<16} {'Interface'}"
        ]
        path = build_path('/interface[name=*]/subinterface[index=*]/ipv4/arp/neighbor[ipv4-address=*]')
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            for intf in data.interface.items():
                if hasattr(intf, 'subinterface'):
                    for sub in intf.subinterface.items():
                        if hasattr(sub, 'ipv4') and sub.ipv4.exists():
                            arp_container = getattr(sub.ipv4.get(), 'arp', None)
                            if arp_container and hasattr(arp_container.get(), 'neighbor'):
                                arp_node = arp_container.get()
                                timeout_val = getattr(arp_node, 'timeout', 14400) or 14400
                                for n in arp_node.neighbor.items():
                                    ip_addr = getattr(n, 'ipv4_address', '')
                                    mac = format_mac_cisco_arista(getattr(n, 'link_layer_address', ''))
                                    full_intf = f"{intf.name}.{sub.index}"
                                    disp_intf = format_arista_intf(full_intf, short=False)
                                    
                                    age_str = "-"
                                    origin = getattr(n, 'origin', '')
                                    exp_time = getattr(n, 'expiration_time', None)
                                    if exp_time and origin != 'static':
                                        try:
                                            ts_str = str(exp_time).split('(')[0].strip()
                                            if ts_str.endswith('Z'):
                                                ts_str = ts_str[:-1] + '+00:00'
                                            exp_dt = datetime.datetime.fromisoformat(ts_str)
                                            now = datetime.datetime.now(datetime.timezone.utc)
                                            rem_seconds = (exp_dt - now).total_seconds()
                                            age_sec = max(0, int(timeout_val - rem_seconds))
                                            age_str = str(age_sec // 60)
                                        except Exception:
                                            age_str = "0"
                                    elif origin == 'dynamic':
                                        age_str = "0"

                                    lines.append(f"{ip_addr:<15} {age_str:<11} {mac:<16} {disp_intf}")
        except Exception:
            pass

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show arpnd arp-entries")

    def show_port_channel_summary(self, state, output):
        """Display Arista EOS style 'show port-channel summary'."""
        lines = [
            "Flags",
            "-------------------------- ----------------------------- -------------------------",
            "   a - LACP Active            p - LACP Passive           * - static fallback",
            "   F - Fallback enabled       f - Fallback configured    ^ - individual fallback",
            "   U - In Use                 D - Down",
            "   + - In-Sync                - - Out-of-Sync            i - incompatible with agg",
            "   P - bundled in Po          s - suspended              G - Aggregable",
            "   I - Individual             S - ShortTimeout           w - wait for agg",
            ""
        ]

        lags = []
        path = build_path('/interface[name=lag*]')
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            for lag in data.interface.items():
                lag_name = lag.name
                oper = getattr(lag, 'oper_state', 'down')
                status_flag = "U" if oper == "up" else "D"
                po_name = format_arista_intf(lag_name, short=True) + f"({status_flag})"
                
                proto_val = "STATIC"
                members = []
                # Check lag members and protocol
                if hasattr(lag, 'lag') and lag.lag.exists():
                    lag_obj = lag.lag.get()
                    if hasattr(lag_obj, 'lacp') and lag_obj.lacp.exists():
                        proto_val = "LACP(a)"
                    elif hasattr(lag_obj, 'lag_type') and str(getattr(lag_obj, 'lag_type', '')).lower() == 'lacp':
                        proto_val = "LACP(a)"
                    mem_items = []
                    if hasattr(lag_obj, 'member'):
                        mem_items = lag_obj.member.items()
                    for m in mem_items:
                        m_name = format_arista_intf(m.name, short=True)
                        m_oper = getattr(m, 'oper_state', 'down')
                        m_flag = "P" if m_oper == "up" else "D"
                        members.append(f"{m_name}({m_flag})")

                ports_str = " ".join(members) if members else "-"
                lags.append({
                    'po': po_name,
                    'proto': proto_val,
                    'ports': ports_str
                })
        except Exception:
            pass

        lines.append(f"Number of channels in use: {len(lags)}")
        lines.append(f"Number of aggregators: {len(lags)}")
        lines.append("")
        lines.append(f"   {'Port-Channel':<18} {'Protocol':<15} {'Ports'}")
        lines.append(f"------------------ --------------- --------------------------------")
        for l in lags:
            lines.append(f"   {l['po']:<18} {l['proto']:<15} {l['ports']}")

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show lag")

    def show_interfaces_transceiver(self, state, output, detail=False):
        """Display Arista EOS style 'show interfaces transceiver [detail]'."""
        lines = []
        path = build_path('/interface[name=*]/transceiver')
        rows = []
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True, include_container_children=True)
            for intf in data.interface.items():
                name = intf.name
                if not hasattr(intf, 'transceiver') or not intf.transceiver.exists():
                    continue
                tr = intf.transceiver.get()
                disp_port = format_arista_intf(name, short=True)
                oper_state = getattr(tr, 'oper_state', 'down')
                oper_reason = getattr(tr, 'oper_down_reason', '') or ''
                
                is_present = oper_state != 'down' or (oper_reason != 'not-present' and oper_reason != '')
                form_factor = getattr(tr, 'form_factor', '--') or '--'
                vendor = getattr(tr, 'vendor', '--') or '--'
                serial = getattr(tr, 'serial_number', '--') or '--'
                part_no = getattr(tr, 'vendor_part_number', '--') or '--'

                temp_str = "N/A"
                volt_str = "N/A"
                tx_pwr = "N/A"
                rx_pwr = "N/A"
                bias_cur = "N/A"

                if hasattr(tr, 'temperature') and tr.temperature.exists():
                    try:
                        v = tr.temperature.get().latest_value
                        if v is not None:
                            temp_str = f"{float(v):.1f} C"
                    except Exception:
                        pass

                if hasattr(tr, 'voltage') and tr.voltage.exists():
                    try:
                        v = tr.voltage.get().latest_value
                        if v is not None:
                            volt_str = f"{float(v):.2f} V"
                    except Exception:
                        pass

                if hasattr(tr, 'channel') and tr.channel.count() > 0:
                    try:
                        ch0 = next(tr.channel.items())
                        if hasattr(ch0, 'input_power') and ch0.input_power.exists():
                            rx_pwr = f"{float(ch0.input_power.get().latest_value):.2f} dBm"
                        if hasattr(ch0, 'output_power') and ch0.output_power.exists():
                            tx_pwr = f"{float(ch0.output_power.get().latest_value):.2f} dBm"
                        if hasattr(ch0, 'laser_bias_current') and ch0.laser_bias_current.exists():
                            bias_cur = f"{float(ch0.laser_bias_current.get().latest_value):.2f} mA"
                    except Exception:
                        pass

                rows.append({
                    'port': disp_port,
                    'temp': temp_str,
                    'voltage': volt_str,
                    'bias': bias_cur,
                    'tx_power': tx_pwr,
                    'rx_power': rx_pwr,
                    'last_update': "--" if is_present else "N/A",
                    'is_present': is_present,
                    'form_factor': form_factor,
                    'vendor': vendor,
                    'serial': serial,
                    'part_no': part_no,
                })
        except Exception:
            pass

        rows.sort(key=lambda r: arista_intf_sort_key(r['port']))

        if not detail:
            lines.append(f"{'Port':<10} {'Temp':<10} {'Voltage':<10} {'Bias Current':<15} {'Tx Power':<12} {'Rx Power':<12} {'Last Update'}")
            lines.append("---------------------------------------------------------------------------------")
            for r in rows:
                lines.append(f"{r['port']:<10} {r['temp']:<10} {r['voltage']:<10} {r['bias']:<15} {r['tx_power']:<12} {r['rx_power']:<12} {r['last_update']}")
        else:
            for r in rows:
                lines.append(f"Port {r['port']}:")
                status_desc = "present" if r['is_present'] else "not present"
                lines.append(f"   Transceiver is {status_desc}")
                if r['is_present']:
                    lines.append(f"   Form Factor:         {r['form_factor']}")
                    lines.append(f"   Vendor Name:         {r['vendor']}")
                    lines.append(f"   Part Number:         {r['part_no']}")
                    lines.append(f"   Serial Number:       {r['serial']}")
                    lines.append(f"   Temperature:         {r['temp']}")
                    lines.append(f"   Voltage:             {r['voltage']}")
                    lines.append(f"   Tx Power:            {r['tx_power']}")
                    lines.append(f"   Rx Power:            {r['rx_power']}")
                lines.append("")

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show interface detail")

