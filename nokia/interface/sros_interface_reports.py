#!/usr/bin/python
###########################################################################
# Description: MultiCLI Nokia SR OS Interface and Port Reports
# Commands: show port, show port description, show lag, show system lldp neighbor
# Copyright (c) 2026 Nokia
###########################################################################

import re
from srlinux.location import build_path
from srlinux.schema.data_store import DataStore


def _safe_get(obj, attr, default=None):
    try:
        val = getattr(obj, attr, default)
        return default if val is None else val
    except Exception:
        return default


def format_sros_port(name):
    if not name:
        return ""
    name_str = str(name)
    m = re.match(r'^ethernet-(\d+)/(\d+)/(\d+)$', name_str)
    if m:
        return f"{m.group(1)}/1/c{m.group(2)}/{m.group(3)}"
    m = re.match(r'^ethernet-(\d+)/(\d+)$', name_str)
    if m:
        return f"{m.group(1)}/1/{m.group(2)}"
    m = re.match(r'^mgmt(\d*)$', name_str)
    if m:
        return "A/1"
    m = re.match(r'^system(\d*)$', name_str)
    if m:
        return "system"
    return name_str

class SrosInterfaceReports:
    """Handles classic Nokia SR OS port, lag, and lldp show reports."""

    def show_port(self, state, output, port_id=None):
        """Display Nokia SR OS formatted 'show port'."""
        path = build_path('/interface[name=*]')
        try:
            intf_data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            interfaces = list(intf_data.interface.items())
        except Exception:
            interfaces = []

        output.print_line("=" * 79)
        output.print_line("Ports on Slot 1")
        output.print_line("=" * 79)
        output.print_line(f"{'Port':<12}{'Admin':<7}{'Link':<6}{'Port':<8}{'Cfg':<7}{'Oper':<7}{'LAG/':<7}{'Port':<6}{'Port':<6}{'Port':<6}{'C/QS/S/XFP/'}")
        output.print_line(f"{'Id':<12}{'State':<7}{'':<6}{'State':<8}{'MTU':<7}{'MTU':<7}{'Bndl':<7}{'Mode':<6}{'Encp':<6}{'Type':<6}{'MDIMDX'}")
        output.print_line("-" * 79)

        count = 0
        for intf in interfaces:
            raw_name = str(intf.name)
            if not raw_name.startswith('ethernet-'):
                continue
            sros_name = format_sros_port(raw_name)
            alt_sros = sros_name.replace('/c', '/')
            if port_id and port_id != '*' and port_id not in (raw_name, sros_name, alt_sros):
                continue

            admin_state = "Up" if _safe_get(intf, 'admin_state', '') == 'enable' else "Down"
            oper_state = "Up" if _safe_get(intf, 'oper_state', '') == 'up' else "Down"
            link = "Yes" if oper_state == "Up" else "No"
            mtu = str(_safe_get(intf, 'mtu', 9232) or 9232)
            lag_str = "-"
            eth_c = _safe_get(intf, 'ethernet')
            if eth_c is not None and eth_c.exists():
                agg_id = _safe_get(eth_c.get(), 'aggregate_id', None)
                if agg_id:
                    lag_str = str(agg_id).replace('lag', '')
            encap = "dot1q" if _safe_get(intf, 'vlan_tagging', False) else "null"
            xcvr_str = ""
            xcvr_c = _safe_get(intf, 'transceiver')
            if xcvr_c is not None and xcvr_c.exists():
                xcvr_obj = xcvr_c.get()
                xcvr_str = str(_safe_get(xcvr_obj, 'form_factor', '') or _safe_get(xcvr_obj, 'ethernet_pmd', '') or '')

            output.print_line(
                f"{sros_name:<12}{admin_state:<7}{link:<6}{oper_state:<8}{mtu:<7}{mtu:<7}{lag_str:<7}{'netw':<6}{encap:<6}{'xcvr':<6}{xcvr_str}"
            )
            count += 1

        output.print_line("=" * 79)
        output.print_line("\nTry SR Linux command: show interface brief")

    def show_port_description(self, state, output):
        """Display Nokia SR OS formatted 'show port description'."""
        path = build_path('/interface[name=*]')
        try:
            intf_data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            interfaces = list(intf_data.interface.items())
        except Exception:
            interfaces = []

        output.print_line("=" * 79)
        output.print_line("Port Descriptions on Slot 1")
        output.print_line("=" * 79)
        output.print_line(f"{'Port Id':<20}{'Description'}")
        output.print_line("-" * 79)

        for intf in interfaces:
            raw_name = str(intf.name)
            if not raw_name.startswith('ethernet-'):
                continue
            sros_name = format_sros_port(raw_name)
            desc = _safe_get(intf, 'description', '') or ''
            output.print_line(f"{sros_name:<20}{desc}")

        output.print_line("=" * 79)
        output.print_line("\nTry SR Linux command: show interface")

    def show_lag(self, state, output, lag_id=None):
        """Display Nokia SR OS formatted 'show lag'."""
        path = build_path('/interface[name=*]')
        lags = []
        try:
            intf_data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            for intf in intf_data.interface.items():
                if str(intf.name).startswith('lag'):
                    lid = str(intf.name).replace('lag', '')
                    if lag_id and lag_id != '*' and str(lag_id) not in (str(intf.name), lid):
                        continue
                    lags.append(intf)
        except Exception:
            pass

        output.print_line("=" * 79)
        output.print_line("Lag Data")
        output.print_line("=" * 79)
        output.print_line(f"{'Lag-id':<10}{'Adm':<8}{'Opr':<8}{'Weighted':<10}{'Threshold':<11}{'Up-Count':<9}{'MC Act/Stdby'}")
        output.print_line("-" * 79)

        if not lags:
            output.print_line("No Matching Entries")
        else:
            for l in lags:
                lid = str(l.name).replace('lag', '') or '1'
                adm = "up" if _safe_get(l, 'admin_state', '') == 'enable' else "down"
                opr = "up" if _safe_get(l, 'oper_state', '') == 'up' else "down"
                threshold = "0"
                up_count = 0
                lag_c = _safe_get(l, 'lag')
                if lag_c is not None and lag_c.exists():
                    lag_obj = lag_c.get()
                    threshold = str(_safe_get(lag_obj, 'min_links', 0))
                    mem_list = _safe_get(lag_obj, 'member')
                    if mem_list is not None and hasattr(mem_list, 'items'):
                        for mem in mem_list.items():
                            if _safe_get(mem, 'oper_state', '') == 'up':
                                up_count += 1
                output.print_line(f"{lid:<10}{adm:<8}{opr:<8}{'No':<10}{threshold:<11}{str(up_count):<9}{'N/A'}")

        output.print_line("=" * 79)
        output.print_line("\nTry SR Linux command: srl show lag")

    def show_lldp_neighbor(self, state, output):
        """Display Nokia SR OS formatted 'show system lldp neighbor'."""
        output.print_line("=" * 79)
        output.print_line("LLDP Remote System Information")
        output.print_line("=" * 79)

        path = build_path('/system/lldp')
        neighbors = []
        try:
            lldp_data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            lldp = lldp_data.system.get().lldp.get()
            intf_list = _safe_get(lldp, 'interface')
            if intf_list is not None and hasattr(intf_list, 'items'):
                for intf in intf_list.items():
                    local_intf = str(intf.name)
                    neigh_list = _safe_get(intf, 'neighbor')
                    if neigh_list is not None and hasattr(neigh_list, 'items'):
                        for n in neigh_list.items():
                            neighbors.append((local_intf, n))
        except Exception:
            pass

        if not neighbors:
            output.print_line("No Matching Entries Found.")
        else:
            for local_intf, n in neighbors:
                sros_port = format_sros_port(local_intf)
                chassis_id = _safe_get(n, 'chassis_id', 'N/A')
                port_id = _safe_get(n, 'port_id', 'N/A')
                sys_name = _safe_get(n, 'system_name', 'N/A')
                sys_desc = _safe_get(n, 'system_description', 'N/A')
                output.print_line(f"Port Id         : {sros_port} ({local_intf})")
                output.print_line(f"Chassis Id      : {chassis_id}")
                output.print_line(f"Port Id         : {port_id}")
                output.print_line(f"System Name     : {sys_name}")
                output.print_line(f"System Descr    : {sys_desc}")
                output.print_line("-" * 79)

        output.print_line("=" * 79)
        output.print_line("\nTry SR Linux command: srl show system lldp neighbor")
