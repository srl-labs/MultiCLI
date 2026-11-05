#!/usr/bin/python
###########################################################################
# Description: MultiCLI LLDP Reports for Cisco NX-OS
# Contributors: Shashi Sharma
# Copyright (c) 2025-2026 Nokia
###########################################################################

import re
from srlinux.location import build_path
from srlinux.schema.data_store import DataStore
from cisco_interface_reports import format_cisco_intf

def _safe_get(obj, attr, default=None):
    try:
        val = getattr(obj, attr, default)
        return default if val is None else val
    except Exception:
        return default


class CiscoLldpReports:
    """Handles Cisco NX-OS LLDP show commands."""

    def _get_capability_code(self, neighbor):
        caps = []
        try:
            cap_obj = _safe_get(neighbor, 'capability')
            if cap_obj and hasattr(cap_obj, 'items'):
                for c in cap_obj.items():
                    if _safe_get(c, 'enabled', False):
                        cname = str(_safe_get(c, 'name', '')).upper()
                        if 'ROUTER' in cname and 'R' not in caps:
                            caps.append('R')
                        elif 'BRIDGE' in cname and 'B' not in caps:
                            caps.append('B')
                        elif 'TELEPHONE' in cname and 'T' not in caps:
                            caps.append('T')
                        elif 'DOCSIS' in cname and 'C' not in caps:
                            caps.append('C')
                        elif 'WLAN' in cname and 'W' not in caps:
                            caps.append('W')
                        elif 'REPEATER' in cname and 'P' not in caps:
                            caps.append('P')
                        elif 'STATION' in cname and 'S' not in caps:
                            caps.append('S')
                        elif 'OTHER' in cname and 'O' not in caps:
                            caps.append('O')
        except Exception:
            pass
        return "".join(caps) if caps else "--"

    def show_lldp_neighbors(self, state, output, detail=False):
        """Display Cisco NX-OS style 'show lldp neighbors' or 'detail'."""
        calculated_ttl = 120
        try:
            lldp_sys_path = build_path('/system/lldp')
            lldp_sys_data = state.server.get_data_store(DataStore.State).get_data(lldp_sys_path, recursive=False)
            lldp_node = lldp_sys_data.system.get().lldp.get()
            hello = _safe_get(lldp_node, 'hello_timer', 30) or 30
            multiplier = _safe_get(lldp_node, 'hold_multiplier', 4) or 4
            calculated_ttl = int(hello) * int(multiplier)
        except Exception:
            pass

        path = build_path('/system/lldp/interface[name=*]/neighbor[id=*]')
        entries = []
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            for intf in data.get_descendants('/system/lldp/interface'):
                local_intf = format_cisco_intf(_safe_get(intf, 'name', ''), short=True)
                neigh_list = _safe_get(intf, 'neighbor')
                if neigh_list and hasattr(neigh_list, 'items'):
                    for n in neigh_list.items():
                        sys_name = str(_safe_get(n, 'system_name', '') or '')
                        port_id = format_cisco_intf(_safe_get(n, 'port_id', ''), short=True)
                        chassis_id = str(_safe_get(n, 'chassis_id', '') or '')
                        desc = str(_safe_get(n, 'system_description', '') or '')
                        mgmt_ip = ""
                        mgmt_obj = _safe_get(n, 'management_address')
                        if mgmt_obj:
                            if hasattr(mgmt_obj, 'items'):
                                for m in mgmt_obj.items():
                                    addr = _safe_get(m, 'address', '')
                                    if addr:
                                        mgmt_ip = str(addr)
                                        break
                            elif isinstance(mgmt_obj, str):
                                mgmt_ip = mgmt_obj
                        ttl_str = str(calculated_ttl)
                        cap = self._get_capability_code(n)
                        entries.append({
                            'local_intf': local_intf,
                            'device_id': sys_name,
                            'port_id': port_id,
                            'chassis_id': chassis_id,
                            'desc': desc,
                            'mgmt_ip': mgmt_ip,
                            'cap': cap,
                            'hold_time': ttl_str
                        })
        except Exception:
            pass

        if not detail:
            lines = [
                "Capability codes:",
                "  (R) Router, (B) Bridge, (T) Telephone, (C) DOCSIS Cable Device",
                "  (W) WLAN Access Point, (P) Repeater, (S) Station, (O) Other",
                "",
                f"{'Device ID':<20} {'Local Intf':<15} {'Hold-time':<10} {'Capability':<11} {'Port ID'}",
                ""
            ]
            for e in entries:
                lines.append(f"{e['device_id']:<20} {e['local_intf']:<15} {e['hold_time']:<10} {e['cap']:<11} {e['port_id']}")
            lines.append(f"Total entries displayed: {len(entries)}")

            output.print_line("\n".join(lines))
        else:
            lines = []
            for e in entries:
                lines.append(f"Chassis id: {e['chassis_id']}")
                lines.append(f"Port id: {e['port_id']}")
                lines.append(f"Local Port id: {e['local_intf']}")
                lines.append(f"System Name: {e['device_id']}")
                lines.append(f"System Description: {e['desc']}")
                lines.append(f"Enabled Capabilities: {', '.join(list(e['cap'])) if e['cap'] != '--' else 'none'}")
                lines.append(f"Management Address: {e['mgmt_ip'] if e['mgmt_ip'] else 'not advertised'}")
                lines.append("")
            lines.append(f"Total entries displayed: {len(entries)}")
            output.print_line("\n".join(lines).rstrip())

        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show system lldp neighbor")
