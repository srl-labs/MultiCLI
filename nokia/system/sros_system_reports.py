#!/usr/bin/python
###########################################################################
# Description: MultiCLI Nokia SR OS System Reports
# Commands: show version, show system information, show chassis
# Copyright (c) 2026 Nokia
###########################################################################

import datetime
import platform
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


class SrosSystemReports:
    """Handles classic Nokia SR OS system show reports."""

    def show_version(self, state, output):
        """Display Nokia SR OS formatted 'show version'."""
        chassis_type = "Chassis"
        chassis_path = build_path('/platform/chassis')
        try:
            ch_data = state.server.get_data_store(DataStore.State).get_data(chassis_path, recursive=True)
            ch = ch_data.platform.get().chassis.get()
            ct = _safe_get(ch, 'type')
            if ct:
                chassis_type = str(ct)
        except Exception:
            pass

        sw_version = "N/A"
        last_booted = ""
        sys_info_path = build_path('/system/information')
        try:
            sys_data = state.server.get_data_store(DataStore.State).get_data(sys_info_path, recursive=True)
            info = sys_data.system.get().information.get()
            ver = _safe_get(info, 'version')
            if ver:
                sw_version = str(ver).lstrip('v')
            lb = _safe_get(info, 'last_booted')
            if lb:
                last_booted = str(lb)
        except Exception:
            pass

        arch = "x86_64"
        try:
            ctrl_data = state.server.get_data_store(DataStore.State).get_data(build_path('/platform/control[slot=*]'), recursive=True)
            for c in ctrl_data.platform.get().control.items():
                cpu_list = _safe_get(c, 'cpu')
                if cpu_list is not None:
                    for cpu_obj in cpu_list.items():
                        cpu_arch = _safe_get(cpu_obj, 'architecture')
                        if cpu_arch:
                            arch = str(cpu_arch)
                            break
                break
        except Exception:
            arch = platform.machine() or "x86_64"

        output.print_line("=" * 79)
        output.print_line(f"SRLinux-{sw_version} both/{arch} Nokia {chassis_type} Copyright (c) 2000-2026 Nokia.")
        output.print_line("All rights reserved. All use subject to applicable license agreements.")
        output.print_line(f"Built on {last_booted if last_booted else 'N/A'}")
        output.print_line("=" * 79)
        output.print_line("\nTry SR Linux command: srl show version")

    def show_system_information(self, state, output):
        """Display Nokia SR OS formatted 'show system information'."""
        hostname = "unknown"
        name_path = build_path('/system/name')
        try:
            name_data = state.server.get_data_store(DataStore.State).get_data(name_path, recursive=True)
            n_node = name_data.system.get().name.get()
            hn = _safe_get(n_node, 'host_name')
            if hn:
                hostname = str(hn)
        except Exception:
            pass

        uptime_seconds = 0
        contact = ""
        location = ""
        coordinates = ""
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        sys_info_path = build_path('/system/information')
        try:
            sys_data = state.server.get_data_store(DataStore.State).get_data(sys_info_path, recursive=True)
            info = sys_data.system.get().information.get()
            contact = str(_safe_get(info, 'contact', '') or '')
            location = str(_safe_get(info, 'location', '') or '')
            coordinates = str(_safe_get(info, 'coordinates', '') or '')
            curr_dt = _safe_get(info, 'current_datetime')
            if curr_dt:
                c_str = str(curr_dt).split('(')[0].strip()
                if 'Z' in c_str:
                    c_str = c_str.replace('Z', '+00:00')
                c_dt = datetime.datetime.fromisoformat(c_str)
                if c_dt.tzinfo is None:
                    c_dt = c_dt.replace(tzinfo=datetime.timezone.utc)
                now_dt = c_dt
            lb = _safe_get(info, 'last_booted')
            if lb:
                boot_str = str(lb).split('(')[0].strip()
                if 'Z' in boot_str:
                    boot_str = boot_str.replace('Z', '+00:00')
                boot_time = datetime.datetime.fromisoformat(boot_str)
                if boot_time.tzinfo is None:
                    boot_time = boot_time.replace(tzinfo=datetime.timezone.utc)
                uptime_seconds = max(0, int((now_dt - boot_time).total_seconds()))
        except Exception:
            pass

        active_slot = "A"
        try:
            ctrl_path = build_path('/platform/control[slot=*]')
            ctrl_data = state.server.get_data_store(DataStore.State).get_data(ctrl_path, recursive=True)
            for c in ctrl_data.platform.get().control.items():
                if hasattr(c, 'slot') and c.slot:
                    active_slot = str(c.slot)
                    break
        except Exception:
            pass

        days, rem = divmod(uptime_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        uptime_str = f"{days} days, {hours:02d}:{minutes:02d}:{seconds:02d}.00 (hr:min:sec)"

        tz_str = "UTC"
        clock_path = build_path('/system/clock')
        try:
            clk_data = state.server.get_data_store(DataStore.State).get_data(clock_path, recursive=True)
            clk = clk_data.system.get().clock.get()
            if hasattr(clk, 'timezone') and clk.timezone:
                tz_str = str(clk.timezone)
        except Exception:
            pass
        current_time_str = now_dt.strftime(f"%Y/%m/%d %H:%M:%S {tz_str}")

        # Dynamically query SSH server state
        ssh_status = "Disabled"
        try:
            ssh_path = build_path('/system/ssh-server[name=*]')
            ssh_data = state.server.get_data_store(DataStore.State).get_data(ssh_path, recursive=True)
            for s in ssh_data.system.get().ssh_server.items():
                admin_st = getattr(s, 'admin_state', 'disable')
                oper_st = getattr(s, 'oper_state', 'down')
                if admin_st == 'enable' or oper_st == 'up':
                    ssh_status = "Enabled"
                    break
        except Exception:
            pass

        # Dynamically query SNMP engine ID and operational state
        snmp_engine_id = ""
        try:
            snmp_path = build_path('/system/snmp/network-instance[name=*]')
            snmp_data = state.server.get_data_store(DataStore.State).get_data(snmp_path, recursive=True)
            for ni in snmp_data.system.get().snmp.get().network_instance.items():
                eid = getattr(ni, 'engine_id', None)
                if eid:
                    snmp_engine_id = str(eid)
                    break
        except Exception:
            pass

        output.print_line("=" * 79)
        output.print_line("System Information")
        output.print_line("=" * 79)
        output.print_line(f"System Name            : {hostname}")
        output.print_line(f"System Contact         : {contact}")
        output.print_line(f"System Location        : {location}")
        output.print_line(f"System Coordinates     : {coordinates}")
        output.print_line(f"System Active Slot     : {active_slot}")
        output.print_line(f"System Up Time         : {uptime_str}")
        output.print_line("SNMP Port              : 161")
        output.print_line(f"SNMP Engine ID         : {snmp_engine_id}")
        output.print_line("SNMP Max Message Size  : 1500")
        output.print_line("Telnet Server          : Disabled")
        output.print_line(f"SSH Server             : {ssh_status}")
        output.print_line(f"System Current Time    : {current_time_str}")
        output.print_line("=" * 79)
        output.print_line("\nTry SR Linux command: info from state system information")

    def show_chassis(self, state, output):
        """Display Nokia SR OS formatted 'show chassis'."""
        hostname = "unknown"
        name_path = build_path('/system/name')
        try:
            name_data = state.server.get_data_store(DataStore.State).get_data(name_path, recursive=True)
            n_node = name_data.system.get().name.get()
            hn = _safe_get(n_node, 'host_name')
            if hn:
                hostname = str(hn)
        except Exception:
            pass

        chassis_type = "Chassis"
        serial = ""
        clei = ""
        oper_state = "up"
        chassis_path = build_path('/platform/chassis')
        try:
            ch_data = state.server.get_data_store(DataStore.State).get_data(chassis_path, recursive=True)
            ch = ch_data.platform.get().chassis.get()
            ct = _safe_get(ch, 'type')
            if ct:
                chassis_type = str(ct)
            sn = _safe_get(ch, 'serial_number')
            if sn:
                serial = str(sn)
            cl = _safe_get(ch, 'clei_code')
            if cl:
                clei = str(cl)
            op = _safe_get(ch, 'oper_state')
            if op:
                oper_state = str(op)
        except Exception:
            pass

        location = ""
        coordinates = ""
        try:
            sys_info_path = build_path('/system/information')
            sys_data = state.server.get_data_store(DataStore.State).get_data(sys_info_path, recursive=True)
            info = sys_data.system.get().information.get()
            loc = _safe_get(info, 'location')
            if loc:
                location = str(loc)
            coord = _safe_get(info, 'coordinates')
            if coord:
                coordinates = str(coord)
        except Exception:
            pass

        fan_count = 0
        fan_path = build_path('/platform/fan-tray[id=*]')
        try:
            f_data = state.server.get_data_store(DataStore.State).get_data(fan_path, recursive=True)
            fan_count = len(list(f_data.platform.get().fan_tray.items()))
        except Exception:
            pass

        psu_count = 0
        psu_path = build_path('/platform/power-supply[id=*]')
        try:
            p_data = state.server.get_data_store(DataStore.State).get_data(psu_path, recursive=True)
            psu_count = len(list(p_data.platform.get().power_supply.items()))
        except Exception:
            pass

        output.print_line("=" * 79)
        output.print_line("Chassis Information")
        output.print_line("=" * 79)
        output.print_line(f"Name                   : {hostname}")
        output.print_line(f"Type                   : {chassis_type}")
        output.print_line(f"Location               : {location}")
        output.print_line(f"Coordinates            : {coordinates}")
        output.print_line(f"CLLI code              : {clei}")
        output.print_line(f"Serial Number          : {serial}")
        output.print_line(f"Number of fan trays    : {fan_count}")
        output.print_line(f"Number of power supplies: {psu_count}")
        output.print_line(f"Operational state      : {oper_state}")
        output.print_line("=" * 79)
        output.print_line("\nTry SR Linux command: show platform chassis")
