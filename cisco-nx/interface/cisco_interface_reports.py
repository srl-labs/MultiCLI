#!/usr/bin/python
###########################################################################
# Description: MultiCLI Interface Reports for Cisco NX-OS
# Copyright (c) 2025-2026 Nokia
###########################################################################

import re
from srlinux.location import build_path
from srlinux.schema.data_store import DataStore

def format_cisco_intf(name, short=True):
    """Format SR Linux interface name to Cisco NX-OS format."""
    if not name:
        return "-"
    name = str(name).strip()
    if name.startswith('irb'):
        return name
    if name.endswith('.0'):
        name = name[:-2]
    if name.startswith('ethernet-'):
        num = name.split('-', 1)[1]
        return f"Eth{num}" if short else f"Ethernet{num}"
    elif name.startswith('mgmt'):
        return name
    elif name.startswith('system0') or name.startswith('system'):
        num = name.replace('system', '') or '0'
        return f"Lo{num}" if short else f"Loopback{num}"
    elif name.startswith('lo'):
        num = name[2:]
        return f"Lo{num}" if short else f"Loopback{num}"
    elif name.startswith('lag'):
        num = name.split('lag', 1)[1]
        return f"Po{num}" if short else f"Port-channel{num}"
    elif name.startswith('irb'):
        return name
    elif name.startswith('vlan'):
        num = name.split('vlan', 1)[1]
        return f"Vlan{num}"
    return name

def _cisco_to_srl_intf(name):
    """Convert Cisco NX-OS interface name to SR Linux format."""
    if not name or name == '*':
        return '*'
    s = str(name).strip()
    if '.' in s and not s.lower().startswith('vlan'):
        s = s.split('.', 1)[0]
    low = s.lower()
    m = re.match(r'^et(?:h(?:ernet)?)?[-_]?(\d+/\d+(?:/\d+)?)$', low)
    if m:
        return f"ethernet-{m.group(1)}"
    m = re.match(r'^lo(?:opback)?[-_]?(\d+)$', low)
    if m:
        num = m.group(1)
        return "system0" if num == "0" else f"lo{num}"
    m = re.match(r'^po(?:rt-channel)?[-_]?(\d+)$', low)
    if m:
        return f"lag{m.group(1)}"
    m = re.match(r'^(?:ma(?:nagement)?|mgmt)[-_]?(\d+)$', low)
    if m:
        return "mgmt0"
    m = re.match(r'^vl(?:an)?[-_]?(\d+)$', low)
    if m:
        return "irb0"
    if low == 'irb':
        return "irb0"
    return s

cisco_to_srl_intf = _cisco_to_srl_intf

def cisco_mac_format(mac):
    """Format MAC address to Cisco dotted hex notation (xxxx.xxxx.xxxx)."""
    if not mac or mac == '--':
        return "0000.0000.0000"
    clean = re.sub(r'[^0-9a-fA-F]', '', str(mac)).lower()
    if len(clean) == 12:
        return f"{clean[0:4]}.{clean[4:8]}.{clean[8:12]}"
    return str(mac)

def format_cisco_speed(speed_str):
    """Format port speed to Cisco NX-OS format like 100G, 10G, 1000."""
    if not speed_str:
        return "auto"
    s = speed_str.upper()
    if '100G' in s:
        return "100G"
    elif '40G' in s:
        return "40G"
    elif '25G' in s:
        return "25G"
    elif '10G' in s:
        return "10G"
    elif '1G' in s:
        return "1000"
    return speed_str

def cisco_intf_sort_key(name):
    """Sort key for Cisco interface names in natural numerical order.
    Order: Ethernet1/1.. Ethernet1/58, Loopback0, mgmt0, Port-channel, Vlan, etc.
    """
    if not name:
        return (99, [0], "")
    lower = str(name).lower()
    type_priority = 5
    if lower.startswith(('eth', 'ethernet')):
        type_priority = 0
    elif lower.startswith(('lo', 'loopback')):
        type_priority = 1
    elif lower.startswith('mgmt'):
        type_priority = 2
    elif lower.startswith(('po', 'port-channel')):
        type_priority = 3
    elif lower.startswith(('vlan', 'irb')):
        type_priority = 4

    digits = [int(p) for p in re.findall(r'\d+', lower)]
    if not digits:
        digits = [0]
    return (type_priority, digits, lower)

class CiscoInterfaceReports:
    """Handles Cisco NX-OS interface show commands."""

    def show_interface_brief(self, state, output):
        """Display Cisco NX-OS style 'show interface brief'."""
        lines = []

        mgmt_rows = []
        eth_rows = []
        lo_rows = []

        path = build_path('/interface[name=*]')
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            for intf in data.interface.items():
                name = intf.name
                admin = getattr(intf, 'admin_state', 'disable')
                oper = getattr(intf, 'oper_state', 'down')
                mtu = getattr(intf, 'mtu', 1500) or 1500
                desc = getattr(intf, 'description', '')
                speed_str = ""
                if hasattr(intf, 'ethernet') and intf.ethernet.exists():
                    eth_node = intf.ethernet.get()
                    speed_str = getattr(eth_node, 'port_speed', '100G')

                # IP addresses
                ip_addr = "--"
                if hasattr(intf, 'subinterface'):
                    for sub in intf.subinterface.items():
                        if hasattr(sub, 'ipv4') and sub.ipv4.exists():
                            for a in sub.ipv4.get().address.items():
                                ip_addr = a.ip_prefix.split('/')[0]
                                break

                status = "up" if (admin == "enable" and oper == "up") else ("down" if admin == "enable" else "down")
                reason = "none" if status == "up" else "Administratively down" if admin != "enable" else "Link not connected"

                if name.startswith('mgmt'):
                    mgmt_rows.append({
                        'port': name,
                        'vrf': "management",
                        'status': status,
                        'ip': ip_addr if ip_addr != "--" else "unassigned",
                        'speed': "1000",
                        'mtu': str(mtu)
                    })
                elif name.startswith('system0') or name.startswith('lo'):
                    lo_name = format_cisco_intf(name, short=False)
                    lo_rows.append({
                        'interface': lo_name,
                        'status': status,
                        'description': desc if desc else "--"
                    })
                elif name.startswith('ethernet-'):
                    eth_name = format_cisco_intf(name, short=True)
                    speed_val = format_cisco_speed(speed_str)
                    speed_display = f"{speed_val}(D)" if status == "up" else speed_val

                    # Dynamic VLAN, mode, and LAG member detection
                    vlan_str = "1"
                    mode_str = "routed"
                    portch_str = "--"

                    if hasattr(intf, 'ethernet') and intf.ethernet.exists():
                        eth_obj = intf.ethernet.get()
                        agg_id = getattr(eth_obj, 'aggregate_id', None)
                        if agg_id:
                            portch_str = str(agg_id).replace('lag', '')

                    if hasattr(intf, 'subinterface'):
                        bridged_vlans = []
                        has_routed = False
                        for subif in intf.subinterface.items():
                            stype = getattr(subif, 'type', '')
                            if stype == 'routed':
                                has_routed = True
                            elif stype == 'bridged':
                                tag = None
                                if hasattr(subif, 'vlan'):
                                    try:
                                        v_obj = subif.vlan.get() if hasattr(subif.vlan, 'get') else subif.vlan
                                        encap = getattr(v_obj, 'encap', None)
                                        if encap:
                                            st = getattr(encap, 'single_tagged', None)
                                            if st and hasattr(st, 'vlan_id'):
                                                tag = str(st.vlan_id)
                                    except Exception:
                                        pass
                                bridged_vlans.append(tag if tag else "1")

                        if bridged_vlans:
                            mode_str = "trunk" if len(bridged_vlans) > 1 else "access"
                            vlan_str = "trunk" if len(bridged_vlans) > 1 else bridged_vlans[0]
                        elif has_routed:
                            mode_str = "routed"
                            vlan_str = "routed" if status == "up" else "--"

                    eth_rows.append({
                        'interface': eth_name,
                        'vlan': vlan_str,
                        'type': "eth",
                        'mode': mode_str,
                        'status': status,
                        'reason': reason,
                        'speed': speed_display,
                        'portch': portch_str
                    })
        except Exception:
            pass

        mgmt_rows.sort(key=lambda r: cisco_intf_sort_key(r['port']))
        eth_rows.sort(key=lambda r: cisco_intf_sort_key(r['interface']))
        lo_rows.sort(key=lambda r: cisco_intf_sort_key(r['interface']))

        # Management section
        lines.append("--------------------------------------------------------------------------------")
        lines.append(f"{'Port':<6} {'VRF':<12} {'Status':<6} {'IP Address':<39} {'Speed':<8} {'MTU'}")
        lines.append("--------------------------------------------------------------------------------")
        if mgmt_rows:
            for r in mgmt_rows:
                lines.append(f"{r['port']:<6} {r['vrf']:<12} {r['status']:<6} {r['ip']:<39} {r['speed']:<8} {r['mtu']}")
        else:
            lines.append("No management interface configured.")

        lines.append("")
        # Ethernet section
        lines.append("--------------------------------------------------------------------------------")
        lines.append(f"{'Ethernet':<13} {'VLAN':<7} {'Type':<4} {'Mode':<6} {'Status':<7} {'Reason':<24} {'Speed':<9} {'Port'}")
        lines.append(f"{'Interface':<13} {'':<7} {'':<4} {'':<6} {'':<7} {'':<24} {'':<9} {'Ch #'}")
        lines.append("--------------------------------------------------------------------------------")
        for r in eth_rows:
            lines.append(f"{r['interface']:<13} {r['vlan']:<7} {r['type']:<4} {r['mode']:<6} {r['status']:<7} {r['reason']:<24} {r['speed']:<9} {r['portch']}")

        if lo_rows:
            lines.append("")
            lines.append("--------------------------------------------------------------------------------")
            lines.append(f"{'Interface':<20} {'Status':<10} {'Description'}")
            lines.append("--------------------------------------------------------------------------------")
            for r in lo_rows:
                lines.append(f"{r['interface']:<20} {r['status']:<10} {r['description']}")

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: srl show interface brief")

    def show_interface_status(self, state, output):
        """Display Cisco NX-OS style 'show interface status'."""
        lines = [
            "--------------------------------------------------------------------------------",
            f"{'Port':<13} {'Name':<18} {'Status':<9} {'Vlan':<9} {'Duplex':<7} {'Speed':<7} {'Type'}",
            "--------------------------------------------------------------------------------"
        ]
        rows = []
        path = build_path('/interface[name=*]')
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            for intf in data.interface.items():
                try:
                    name = intf.name
                    if not name.startswith('ethernet-'):
                        continue
                    c_name = format_cisco_intf(name, short=True)
                    desc = getattr(intf, 'description', '')
                    if not desc:
                        desc = "--"
                    elif len(desc) > 17:
                        desc = desc[:17]

                    admin = getattr(intf, 'admin_state', 'disable')
                    oper = getattr(intf, 'oper_state', 'down')
                    if admin != "enable":
                        status = "disabled"
                    elif oper == "up":
                        status = "connected"
                    else:
                        status = "notconnec"

                    # Determine VLAN dynamically
                    vlan_str = "routed" if status == "connected" else "--"
                    if hasattr(intf, 'subinterface'):
                        try:
                            bridged_vlans = []
                            has_routed = False
                            for subif in intf.subinterface.items():
                                stype = getattr(subif, 'type', '')
                                if stype == 'routed':
                                    has_routed = True
                                elif stype == 'bridged':
                                    tag = None
                                    if hasattr(subif, 'vlan'):
                                        try:
                                            v_obj = subif.vlan.get() if hasattr(subif.vlan, 'get') else subif.vlan
                                            encap = getattr(v_obj, 'encap', None)
                                            if encap:
                                                st = getattr(encap, 'single_tagged', None)
                                                if st and hasattr(st, 'vlan_id'):
                                                    tag = str(st.vlan_id)
                                        except Exception:
                                            pass
                                    bridged_vlans.append(tag if tag else "1")
                            if bridged_vlans:
                                vlan_str = "trunk" if len(bridged_vlans) > 1 else bridged_vlans[0]
                            elif has_routed:
                                vlan_str = "routed"
                            elif status == "connected":
                                vlan_str = "1"
                        except Exception:
                            pass

                    # Determine Duplex and Speed dynamically
                    duplex_str = "full" if status == "connected" else "auto"
                    speed_str = "--"
                    if hasattr(intf, 'ethernet') and intf.ethernet.exists():
                        try:
                            eth_node = intf.ethernet.get()
                            if hasattr(eth_node, 'port_speed'):
                                raw_speed = getattr(eth_node, 'port_speed', None)
                                if raw_speed:
                                    speed_str = format_cisco_speed(raw_speed)
                        except Exception:
                            pass
                        try:
                            eth_node = intf.ethernet.get()
                            if hasattr(eth_node, 'duplex_mode'):
                                dmode = getattr(eth_node, 'duplex_mode', None)
                                if dmode:
                                    duplex_str = str(dmode).lower()
                        except Exception:
                            pass

                    xcvr_type = "--"
                    if hasattr(intf, 'transceiver') and intf.transceiver.exists():
                        try:
                            xcvr_node = intf.transceiver.get()
                            xcvr_type = getattr(xcvr_node, 'form_factor', '--') or '--'
                        except Exception:
                            pass

                    rows.append({
                        'port': c_name,
                        'name': desc,
                        'status': status,
                        'vlan': vlan_str,
                        'duplex': duplex_str,
                        'speed': speed_str,
                        'type': xcvr_type
                    })
                except Exception:
                    pass
        except Exception:
            pass

        rows.sort(key=lambda r: cisco_intf_sort_key(r['port']))
        for r in rows:
            lines.append(f"{r['port']:<13} {r['name']:<18} {r['status']:<9} {r['vlan']:<9} {r['duplex']:<7} {r['speed']:<7} {r['type']}")

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: srl show interface")

    def show_interface_description(self, state, output):
        """Display Cisco NX-OS style 'show interface description'."""
        lines = [
            f"{'Port':<14} {'Type':<8} {'Speed':<8} {'Description'}",
            "------------------------------------------------------------------"
        ]
        rows = []
        path = build_path('/interface[name=*]')
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            for intf in data.interface.items():
                name = intf.name
                c_name = format_cisco_intf(name, short=True)
                desc = getattr(intf, 'description', '')
                if not desc or desc == 'None':
                    desc = ''
                intf_type = "eth" if name.startswith('ethernet-') else ("mgmt" if name.startswith('mgmt') else "loop")
                speed_str = "--"
                if hasattr(intf, 'ethernet') and intf.ethernet.exists():
                    eth_node = intf.ethernet.get()
                    raw_speed = getattr(eth_node, 'port_speed', None)
                    if raw_speed:
                        speed_str = format_cisco_speed(raw_speed)
                elif name.startswith('mgmt'):
                    speed_str = "1000"

                rows.append({
                    'port': c_name,
                    'type': intf_type,
                    'speed': speed_str,
                    'desc': desc
                })
        except Exception:
            pass

        rows.sort(key=lambda r: cisco_intf_sort_key(r['port']))
        for r in rows:
            lines.append(f"{r['port']:<14} {r['type']:<8} {r['speed']:<8} {r['desc']}".rstrip())

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: srl show interface")

    def show_port_channel_summary(self, state, output):
        """Display Cisco NX-OS style 'show port-channel summary'."""
        lines = [
            "Flags:  D - Down        P - Up in port-channel (members)",
            "        I - Individual  H - Hot-standby (LACP only)",
            "        s - Suspended   r - Module-removed",
            "        b - BFD Session Wait",
            "        S - Switched    R - Routed",
            "        U - Up (port-channel)",
            "        p - Up in nu-port-channel (members)",
            "        M - (Dynamic Module)",
            "--------------------------------------------------------------------------------",
            f"{'Group':<5} {'Port-':<11} {'Type':<8} {'Protocol':<9} {'Member Ports'}",
            f"{'':<5} {'Channel':<11} {'':<8} {'':<9} {''}",
            "--------------------------------------------------------------------------------"
        ]
        path = build_path('/interface[name=lag*]')
        found = False
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            for intf in data.interface.items():
                name = intf.name
                found = True
                lag_num = name.split('lag')[-1]
                po_name = f"Po{lag_num}"
                oper = getattr(intf, 'oper_state', 'down')
                po_flag = "U" if oper == "up" else "D"
                po_full = f"{po_name}({po_flag})"

                proto_val = "NONE"
                members = []
                if hasattr(intf, 'lag') and intf.lag.exists():
                    lag_node = intf.lag.get()
                    if hasattr(lag_node, 'lacp') and lag_node.lacp.exists():
                        proto_val = "LACP"
                    elif hasattr(lag_node, 'lag_type') and str(getattr(lag_node, 'lag_type', '')).lower() == 'lacp':
                        proto_val = "LACP"
                    mem_items = []
                    if hasattr(lag_node, 'member'):
                        mem_items = lag_node.member.items()
                    for mem in mem_items:
                        m_name = format_cisco_intf(mem.name, short=True)
                        m_oper = getattr(mem, 'oper_state', 'down')
                        m_flag = "P" if m_oper == "up" else "D"
                        members.append(f"{m_name}({m_flag})")

                m_str = "    ".join(members) if members else "--"
                lines.append(f"{lag_num:<5} {po_full:<11} {'Eth':<8} {proto_val:<9} {m_str}")
        except Exception:
            pass

        if not found:
            lines.append("")

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show lag")

    def show_interface_transceiver(self, state, output, details=False):
        """Display Cisco NX-OS style 'show interface transceiver [details]'."""
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
                disp_port = format_cisco_intf(name, short=True)
                full_port = format_cisco_intf(name, short=False)
                oper_state = getattr(tr, 'oper_state', 'down')
                oper_reason = getattr(tr, 'oper_down_reason', '') or ''
                
                is_present = oper_state != 'down' or (oper_reason != 'not-present' and oper_reason != '')
                form_factor = getattr(tr, 'form_factor', '--') or '--'
                vendor = getattr(tr, 'vendor', '--') or '--'
                serial = getattr(tr, 'serial_number', '--') or '--'
                part_no = getattr(tr, 'vendor_part_number', '--') or '--'

                temp_str = "--"
                volt_str = "--"
                tx_pwr = "--"
                rx_pwr = "--"
                bias_cur = "--"

                if hasattr(tr, 'temperature') and tr.temperature.exists():
                    try:
                        v = tr.temperature.get().latest_value
                        if v is not None:
                            temp_str = f"{float(v):.2f}"
                    except Exception:
                        pass

                if hasattr(tr, 'voltage') and tr.voltage.exists():
                    try:
                        v = tr.voltage.get().latest_value
                        if v is not None:
                            volt_str = f"{float(v):.2f}"
                    except Exception:
                        pass

                if hasattr(tr, 'channel') and tr.channel.count() > 0:
                    try:
                        ch0 = next(tr.channel.items())
                        if hasattr(ch0, 'input_power') and ch0.input_power.exists():
                            rx_pwr = f"{float(ch0.input_power.get().latest_value):.2f}"
                        if hasattr(ch0, 'output_power') and ch0.output_power.exists():
                            tx_pwr = f"{float(ch0.output_power.get().latest_value):.2f}"
                        if hasattr(ch0, 'laser_bias_current') and ch0.laser_bias_current.exists():
                            bias_cur = f"{float(ch0.laser_bias_current.get().latest_value):.2f}"
                    except Exception:
                        pass

                rows.append({
                    'port': disp_port,
                    'full_port': full_port,
                    'temp': temp_str,
                    'voltage': volt_str,
                    'bias': bias_cur,
                    'tx_power': tx_pwr,
                    'rx_power': rx_pwr,
                    'is_present': is_present,
                    'form_factor': form_factor,
                    'vendor': vendor,
                    'serial': serial,
                    'part_no': part_no,
                })
        except Exception:
            pass

        rows.sort(key=lambda r: cisco_intf_sort_key(r['port']))

        if not details:
            lines.append("-----------------------------------------------------------------------")
            lines.append(f"{'Port':<13} {'Temp':<8} {'Voltage':<9} {'Current':<9} {'Tx Power':<10} {'Rx Power'}")
            lines.append(f"{'':<13} {'(C)':<8} {'(V)':<9} {'(mA)':<9} {'(dBm)':<10} {'(dBm)'}")
            lines.append("-----------------------------------------------------------------------")
            for r in rows:
                lines.append(f"{r['port']:<13} {r['temp']:<8} {r['voltage']:<9} {r['bias']:<9} {r['tx_power']:<10} {r['rx_power']}")
        else:
            for r in rows:
                lines.append(f"{r['full_port']}")
                status_desc = "present" if r['is_present'] else "not present"
                lines.append(f"    transceiver is {status_desc}")
                if r['is_present']:
                    lines.append(f"    type is {r['form_factor']}")
                    lines.append(f"    name is {r['vendor']}")
                    lines.append(f"    part number is {r['part_no']}")
                    lines.append(f"    serial number is {r['serial']}")
                    lines.append(f"    temperature is {r['temp']} C")
                    lines.append(f"    voltage is {r['voltage']} V")
                    lines.append(f"    current is {r['bias']} mA")
                    lines.append(f"    tx power is {r['tx_power']} dBm")
                    lines.append(f"    rx power is {r['rx_power']} dBm")
                lines.append("")

        output.print_line("\n".join(lines).rstrip())
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show interface detail")

    def show_ipv6_interface_brief(self, state, output):
        """Display Cisco NX-OS style 'show ipv6 interface brief'."""
        lines = [
            f"{'Port':<15} {'VRF':<16} {'IP Address':<38} {'Status'}",
            "-----------------------------------------------------------------------------"
        ]
        rows = []
        intf_to_vrf = {}
        try:
            ni_p = build_path('/network-instance[name=*]/interface[name=*]')
            ni_d = state.server.get_data_store(DataStore.State).get_data(ni_p, recursive=False)
            for ni in ni_d.network_instance.items():
                if hasattr(ni, 'interface'):
                    for i in ni.interface.items():
                        intf_to_vrf[i.name] = ni.name
        except Exception:
            pass

        path = build_path('/interface[name=*]/subinterface[index=*]/ipv6/address[ip-prefix=*]')
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            for intf in data.interface.items():
                name = intf.name
                disp_port = format_cisco_intf(name, short=True)
                admin = getattr(intf, 'admin_state', 'disable')
                oper = getattr(intf, 'oper_state', 'down')
                status = "up" if (admin == "enable" and oper == "up") else "down"

                if hasattr(intf, 'subinterface'):
                    for sub in intf.subinterface.items():
                        full_name = f"{name}.{sub.index}"
                        sub_disp = f"{disp_port}.{sub.index}" if str(sub.index) != '0' else disp_port
                        sub_vrf = intf_to_vrf.get(full_name, intf_to_vrf.get(name, "default"))
                        if hasattr(sub, 'ipv6') and sub.ipv6.exists():
                            for a in sub.ipv6.get().address.items():
                                prefix = getattr(a, 'ip_prefix', '--')
                                rows.append({
                                    'port': sub_disp,
                                    'vrf': sub_vrf,
                                    'ip': str(prefix),
                                    'status': status
                                })
        except Exception:
            pass

        rows.sort(key=lambda r: cisco_intf_sort_key(r['port']))
        for r in rows:
            lines.append(f"{r['port']:<15} {r['vrf']:<16} {r['ip']:<38} {r['status']}")

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: srl show interface brief")

    def show_interface_detail(self, state, output, arguments=None):
        """Display Cisco NX-OS style 'show interface [name]'."""
        target_name = '*'
        for src in (arguments, getattr(state, 'line_commands', None)):
            if not src:
                continue
            try:
                if hasattr(src, 'has_node'):
                    if src.has_node('interface'):
                        val = src.get_value_or('interface', 'name', '*')
                        if val and val != '*':
                            target_name = val
                            break
                    if src.has_node('interfaces'):
                        val = src.get_value_or('interfaces', 'name', '*')
                        if val and val != '*':
                            target_name = val
                            break
                if hasattr(src, 'get'):
                    val = src.get('interface', 'name')
                    if val and val != '*':
                        target_name = val
                        break
            except Exception:
                pass

        srl_name = _cisco_to_srl_intf(target_name)
        path = build_path('/interface[name={name}]', name=srl_name)
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True, include_container_children=True)
        except Exception:
            return

        blocks = []
        intf_list = list(data.interface.items())
        intf_list.sort(key=lambda x: cisco_intf_sort_key(x.name))

        for intf in intf_list:
            name = intf.name
            c_name = format_cisco_intf(name, short=False)
            admin = getattr(intf, 'admin_state', 'disable')
            oper = getattr(intf, 'oper_state', 'down')
            admin_status = "up" if admin == "enable" else "down"
            oper_status = "up" if oper == "up" else "down"

            desc = getattr(intf, 'description', '')
            mtu = getattr(intf, 'mtu', 1500) or 1500

            raw_lower = str(name).lower()
            is_eth = hasattr(intf, 'ethernet') and intf.ethernet.exists()
            is_lag = raw_lower.startswith('lag')
            is_loop = raw_lower.startswith('system') or raw_lower.startswith('lo')
            is_irb = raw_lower.startswith('irb')

            # Ethernet/Hardware-specific attributes
            mac_addr = "0000.0000.0000"
            bia_addr = "0000.0000.0000"
            bw_kbit = 8000000 if is_loop else (1000000 if (is_irb or raw_lower.startswith('mgmt')) else 0)
            duplex = "full"
            auto_neg = "off"
            speed_val = "1000 Mb/s" if raw_lower.startswith('mgmt') else "Unknown"
            crc_errors = 0
            giants = 0
            runts = 0

            if is_lag and hasattr(intf, 'lag') and intf.lag.exists():
                try:
                    lag_obj = intf.lag.get()
                    lag_spd = getattr(lag_obj, 'lag_speed', None)
                    if lag_spd is not None:
                        spd_mbps = int(lag_spd)
                        bw_kbit = spd_mbps * 1000
                        speed_val = f"{spd_mbps // 1000} Gb/s" if spd_mbps >= 1000 else f"{spd_mbps} Mb/s"
                except Exception:
                    pass

            if is_eth:
                eth = intf.ethernet.get()
                raw_mac = getattr(eth, 'hw_mac_address', None)
                if raw_mac:
                    mac_addr = cisco_mac_format(raw_mac)
                    bia_addr = mac_addr
                raw_speed = getattr(eth, 'port_speed', None)
                port_speed = str(raw_speed or '').upper()
                if '400G' in port_speed:
                    bw_kbit = 400000000
                    speed_val = "400 Gb/s"
                elif '100G' in port_speed:
                    bw_kbit = 100000000
                    speed_val = "100 Gb/s"
                elif '40G' in port_speed:
                    bw_kbit = 40000000
                    speed_val = "40 Gb/s"
                elif '25G' in port_speed:
                    bw_kbit = 25000000
                    speed_val = "25 Gb/s"
                elif '10G' in port_speed:
                    bw_kbit = 10000000
                    speed_val = "10 Gb/s"
                elif '1G' in port_speed:
                    bw_kbit = 1000000
                    speed_val = "1000 Mb/s"

                auto_neg = "off"
                try:
                    an = getattr(eth, 'auto_negotiate', None)
                    if an is True or an == 'true' or an == 'enable':
                        auto_neg = "on"
                except Exception:
                    auto_neg = "off"

                try:
                    raw_duplex = eth.duplex_mode
                    if raw_duplex:
                        duplex = str(raw_duplex).lower()
                except Exception:
                    duplex = "full"

                try:
                    if hasattr(eth, 'statistics') and eth.statistics.exists():
                        eth_stats = eth.statistics.get()
                        try:
                            crc_errors = getattr(eth_stats, 'in_crc_error_frames', 0) or 0
                        except Exception:
                            crc_errors = 0
                        try:
                            giants = getattr(eth_stats, 'in_oversize_frames', 0) or 0
                        except Exception:
                            giants = 0
                        try:
                            runts = getattr(eth_stats, 'in_undersize_frames', 0) or 0
                        except Exception:
                            try:
                                runts = getattr(eth_stats, 'in_fragment_frames', 0) or 0
                            except Exception:
                                runts = 0
                except Exception:
                    pass

            # Traffic rate & statistics
            in_bps = 0
            out_bps = 0
            if hasattr(intf, 'traffic_rate') and intf.traffic_rate.exists():
                try:
                    tr = intf.traffic_rate.get()
                    in_bps = getattr(tr, 'in_bps', 0) or 0
                    out_bps = getattr(tr, 'out_bps', 0) or 0
                except Exception:
                    pass

            in_pkts = 0
            in_octets = 0
            in_multi = 0
            in_bcast = 0
            in_errors = 0
            out_pkts = 0
            out_octets = 0
            out_multi = 0
            out_bcast = 0
            out_errors = 0
            carrier_transitions = 0
            intf_resets = 0

            if hasattr(intf, 'statistics') and intf.statistics.exists():
                stats = intf.statistics.get()
                def _sget(attr, default=0):
                    try:
                        v = getattr(stats, attr, default)
                        return default if v is None else v
                    except Exception:
                        return default
                in_pkts = _sget('in_packets', 0)
                in_octets = _sget('in_octets', 0)
                in_multi = _sget('in_multicast_packets', 0)
                in_bcast = _sget('in_broadcast_packets', 0)
                in_errors = _sget('in_error_packets', 0)
                out_pkts = _sget('out_packets', 0)
                out_octets = _sget('out_octets', 0)
                out_multi = _sget('out_multicast_packets', 0)
                out_bcast = _sget('out_broadcast_packets', 0)
                out_errors = _sget('out_error_packets', 0)
                carrier_transitions = _sget('carrier_transitions', 0)
                intf_resets = _sget('interface_transitions', None)
                if intf_resets is None:
                    intf_resets = carrier_transitions

            # Mode & IPv4 addresses
            mode_str = "routed"
            ip_line = ""
            if hasattr(intf, 'subinterface'):
                for sub in intf.subinterface.items():
                    if hasattr(sub, 'type') and sub.type == 'bridged':
                        mode_str = "access"
                    if hasattr(sub, 'ipv4') and sub.ipv4.exists():
                        ipv4_node = sub.ipv4.get()
                        if hasattr(ipv4_node, 'address'):
                            for addr in ipv4_node.address.items():
                                ip_line = f"  Internet Address is {addr.ip_prefix}"
                                break

            if is_loop:
                hw_line = "  Hardware: Loopback"
            elif is_irb:
                hw_line = f"  Hardware: SVI, address: {mac_addr} (bia {bia_addr})"
            elif is_lag:
                hw_line = f"  Hardware: Port-Channel, address: {mac_addr} (bia {bia_addr})"
            else:
                hw_line = f"  Hardware: Ethernet, address: {mac_addr} (bia {bia_addr})"

            # Format Cisco NX-OS block
            block_lines = [
                f"{c_name} is {oper_status}",
                f"admin state is {admin_status}, Dedicated Interface",
                hw_line,
            ]
            if desc:
                block_lines.append(f"  Description: {desc}")
            if ip_line:
                block_lines.append(ip_line)
            bw_bps = bw_kbit * 1000
            txload = max(1, min(255, int((out_bps / bw_bps) * 255) + 1)) if bw_bps > 0 else 1
            rxload = max(1, min(255, int((in_bps / bw_bps) * 255) + 1)) if bw_bps > 0 else 1
            tot_pkts = in_pkts + out_pkts
            tot_errs = in_errors + out_errors
            reliability = max(1, min(255, int(255 * (1.0 - (tot_errs / tot_pkts))))) if tot_pkts > 0 and tot_errs > 0 else 255
            try:
                raw_tpid = str(getattr(intf, 'tpid', '') or '')
            except Exception:
                raw_tpid = ''
            ethertype = "0x88a8" if "88A8" in raw_tpid.upper() else "0x8100"
            encap_type = "LOOPBACK" if is_loop else "ARPA"
            block_lines.extend([
                f"  MTU {mtu} bytes, BW {bw_kbit} Kbit",
                f"  reliability {reliability}/255, txload {txload}/255, rxload {rxload}/255",
                f"  Encapsulation {encap_type}, medium is broadcast",
            ])
            if not is_loop and not is_irb:
                block_lines.extend([
                    f"  Port mode is {mode_str}",
                    f"  {duplex}-duplex, {speed_val}",
                    f"  Auto-Negotiation is turned {auto_neg}",
                    f"  Rate mode is dedicated",
                    f"  EtherType is {ethertype}",
                ])
            block_lines.extend([
                f"  {carrier_transitions} link status changes since last clear",
                f"  Last clearing of \"show interface\" counters never",
                f"  {intf_resets} interface resets",
                f"  30 seconds input rate {in_bps} bits/sec",
                f"  30 seconds output rate {out_bps} bits/sec",
                f"  Load-Interval #2: 5 minute (300 seconds)",
                f"    input rate {in_bps} bps; output rate {out_bps} bps",
                f"  RX",
                f"    {in_pkts} packets {in_octets} bytes",
                f"    {in_multi} multicast packets {in_bcast} broadcast packets",
                f"    {in_errors} input errors {crc_errors} CRC 0 frame 0 overrun 0 ignored",
                f"    0 abort {runts} runts {giants} giants 0 invalid length",
                f"  TX",
                f"    {out_pkts} packets {out_octets} bytes",
                f"    {out_multi} multicast packets {out_bcast} broadcast packets",
                f"    {out_errors} output errors 0 collision 0 ignored 0 abort"
            ])
            blocks.append("\n".join(block_lines))

        if blocks:
            output.print_line("\n\n".join(blocks))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        if srl_name and srl_name != '*':
            output.print_line(f"Try SR Linux command: show interface {srl_name} detail")
        else:
            output.print_line("Try SR Linux command: show interface detail")
