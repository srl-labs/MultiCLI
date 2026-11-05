#!/usr/bin/python
###########################################################################
# Description: MultiCLI Arista EOS System Reports
# Commands: show version, show hostname, show clock, show inventory, show environment
# Copyright (c) 2026 Nokia
###########################################################################

import datetime
import platform
from srlinux.location import build_path
from srlinux.schema.data_store import DataStore

def _safe_get(obj, attr, default=None):
    try:
        val = getattr(obj, attr, default)
        return default if val is None else val
    except Exception:
        return default

def _parse_srl_timestamp(val):
    if not val:
        return None
    try:
        s = str(val).split('(')[0].strip()
        if s.endswith('Z'):
            s = s[:-1] + '+00:00'
        dt = datetime.datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt
    except Exception:
        return None

def format_mac_cisco_arista(mac_str):
    if not mac_str:
        return ""
    clean = str(mac_str).replace(':', '').replace('-', '').replace('.', '').lower()
    if len(clean) == 12:
        return f"{clean[0:4]}.{clean[4:8]}.{clean[8:12]}"
    return mac_str

def format_uptime_words(uptime_seconds):
    try:
        total_seconds = int(uptime_seconds)
    except (ValueError, TypeError):
        return "Unknown"
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    parts = []
    if days > 0:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours > 0 or days > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    return ", ".join(parts)

class AristaSystemReports:
    """Handles Arista EOS system show commands."""

    def show_version(self, state, output):
        """Display Arista EOS style 'show version'."""
        chassis_type = "Chassis"
        hw_mac = ""
        serial_number = ""
        part_number = ""
        chassis_path = build_path('/platform/chassis')
        try:
            chassis_data = state.server.get_data_store(DataStore.State).get_data(chassis_path, recursive=True)
            ch = chassis_data.platform.get().chassis.get()
            ch_type = _safe_get(ch, 'type')
            if ch_type:
                chassis_type = f"Nokia {ch_type}"
            ch_mac = _safe_get(ch, 'hw_mac_address')
            if ch_mac:
                hw_mac = format_mac_cisco_arista(ch_mac)
            ch_sn = _safe_get(ch, 'serial_number')
            if ch_sn:
                serial_number = str(ch_sn)
            ch_pn = _safe_get(ch, 'part_number')
            if ch_pn:
                part_number = str(ch_pn)
        except Exception:
            pass

        sw_version = "N/A"
        last_booted = ""
        uptime_seconds = 0
        sys_info_path = build_path('/system/information')
        try:
            sys_data = state.server.get_data_store(DataStore.State).get_data(sys_info_path, recursive=True)
            info = sys_data.system.get().information.get()
            ver = _safe_get(info, 'version')
            if ver:
                sw_version = str(ver)
            lb = _safe_get(info, 'last_booted')
            if lb:
                last_booted = str(lb)
        except Exception:
            pass

        if uptime_seconds == 0 and last_booted:
            try:
                boot_str = last_booted.split('(')[0].strip()
                if 'Z' in boot_str:
                    boot_str = boot_str.replace('Z', '+00:00')
                boot_time = datetime.datetime.fromisoformat(boot_str)
                now = datetime.datetime.now(datetime.timezone.utc)
                if boot_time.tzinfo is None:
                    boot_time = boot_time.replace(tzinfo=datetime.timezone.utc)
                uptime_seconds = int((now - boot_time).total_seconds())
            except Exception:
                uptime_seconds = 0

        uptime_str = format_uptime_words(uptime_seconds)

        total_mem_kb = 0
        free_mem_kb = 0
        arch = "x86_64"
        ctrl_path = build_path('/platform/control[slot=*]')
        try:
            ctrl_data = state.server.get_data_store(DataStore.State).get_data(ctrl_path, recursive=True)
            for c in ctrl_data.platform.get().control.items():
                mem_c = _safe_get(c, 'memory')
                if mem_c is not None and mem_c.exists():
                    mem = mem_c.get()
                    phys = _safe_get(mem, 'physical')
                    if phys:
                        total_mem_kb = int(phys) // 1024
                    free = _safe_get(mem, 'free')
                    if free:
                        free_mem_kb = int(free) // 1024
                cpu_c = _safe_get(c, 'cpu')
                if cpu_c is not None:
                    for cpu_obj in cpu_c.items():
                        cpu_arch = _safe_get(cpu_obj, 'architecture')
                        if cpu_arch:
                            arch = str(cpu_arch)
                            break
                break
        except Exception:
            pass

        lines = [
            f"{chassis_type}",
            f"Hardware version:    {part_number or '--'}",
            f"Serial number:       {serial_number}",
            f"System MAC address:  {hw_mac}",
            f"",
            f"Software image version: {sw_version}",
            f"Architecture:           {arch}",
            f"Internal build version: {sw_version}",
            f"Internal build ID:      {sw_version}",
            f"",
            f"Uptime:                 {uptime_str}",
            f"Total memory:           {total_mem_kb} kB",
            f"Free memory:            {free_mem_kb} kB",
        ]
        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: srl show version")

    def show_hostname(self, state, output):
        """Display Arista EOS style 'show hostname'."""
        hostname = "unknown"
        p_host = build_path('/system/name/host-name')
        try:
            d_host = state.server.get_data_store(DataStore.State).get_data(p_host, recursive=True)
            hostname = _safe_get(d_host.system.get().name.get(), 'host_name', "unknown") or "unknown"
        except Exception:
            pass

        output.print_line(f"Hostname: {hostname}")
        output.print_line(f"FQDN:     {hostname}")
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: info from state system name")

    def show_clock(self, state, output):
        """Display Arista EOS style 'show clock'."""
        current_dt = datetime.datetime.now(datetime.timezone.utc)
        timezone = "UTC"
        sys_info_path = build_path('/system/information')
        try:
            sys_data = state.server.get_data_store(DataStore.State).get_data(sys_info_path, recursive=True)
            info = sys_data.system.get().information.get()
            curr_dt_val = _safe_get(info, 'current_datetime')
            if curr_dt_val:
                dt_str = str(curr_dt_val).split('(')[0].strip()
                if 'Z' in dt_str:
                    dt_str = dt_str.replace('Z', '+00:00')
                current_dt = datetime.datetime.fromisoformat(dt_str)
        except Exception:
            pass

        try:
            clock_path = build_path('/system/clock')
            clock_data = state.server.get_data_store(DataStore.State).get_data(clock_path, recursive=True)
            clock = clock_data.system.get().clock.get()
            tz = _safe_get(clock, 'timezone')
            if tz:
                timezone = str(tz)
        except Exception:
            pass

        formatted_time = current_dt.strftime("%a %b %d %H:%M:%S %Y")
        output.print_line(f"{formatted_time}")
        output.print_line(f"Timezone: {timezone}")
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: info from state system clock")

    def show_inventory(self, state, output):
        """Display Arista EOS style 'show inventory'."""
        chassis_type = "Nokia Chassis"
        description = "Nokia SR Linux System"
        serial_number = ""
        hw_version = "-"
        try:
            chassis_path = build_path('/platform/chassis')
            chassis_data = state.server.get_data_store(DataStore.State).get_data(chassis_path, recursive=True)
            chassis = chassis_data.platform.get().chassis.get()
            ch_t = _safe_get(chassis, 'type')
            if ch_t:
                chassis_type = str(ch_t)
                description = f"Nokia {ch_t} Chassis"
            ch_sn = _safe_get(chassis, 'serial_number')
            if ch_sn:
                serial_number = str(ch_sn)
            ch_pn = _safe_get(chassis, 'part_number')
            if ch_pn:
                hw_version = str(ch_pn)
        except Exception:
            pass

        lines = [
            "System information",
            f" Model                    Description",
            f" ------------------------ ----------------------------------------------------",
            f" {chassis_type:<24} {description}",
            f"",
            f" HW Version  Serial Number  Mfg Date   Epoch",
            f" ----------- -------------- ---------- -----",
            f" {hw_version:<11} {serial_number:<14} -          -    ",
            f""
        ]

        try:
            psu_path = build_path('/platform/power-supply[id=*]')
            psu_data = state.server.get_data_store(DataStore.State).get_data(psu_path, recursive=True)
            psus = [p for p in psu_data.platform.get().power_supply.items() if _safe_get(p, 'oper_state', '') != 'empty']
            if psus:
                lines.append(f"System has {len(psus)} power supply slot{'s' if len(psus) != 1 else ''}")
                lines.append(f" Slot Model            Serial Number")
                lines.append(f" ---- ---------------- ----------------")
                for psu in psus:
                    slot = _safe_get(psu, 'id', '-')
                    model = _safe_get(psu, 'type', 'PWR') or 'PWR'
                    sn = _safe_get(psu, 'serial_number', '-') or '-'
                    lines.append(f" {str(slot):<4} {str(model):<16} {str(sn):<16}")
                lines.append("")
        except Exception:
            pass

        try:
            fan_path = build_path('/platform/fan-tray[id=*]')
            fan_data = state.server.get_data_store(DataStore.State).get_data(fan_path, recursive=True)
            fans = [f for f in fan_data.platform.get().fan_tray.items() if _safe_get(f, 'oper_state', '') != 'empty']
            if fans:
                lines.append(f"System has {len(fans)} fan module{'s' if len(fans) != 1 else ''}")
                lines.append(f" Module Number of Fans Model            Serial Number")
                lines.append(f" ------- --------------- ---------------- ----------------")
                for fan in fans:
                    tray_id = _safe_get(fan, 'id', '-')
                    model = _safe_get(fan, 'type', 'FAN') or 'FAN'
                    sn = _safe_get(fan, 'serial_number', '-') or '-'
                    lines.append(f" {str(tray_id):<7} 1               {str(model):<16} {str(sn):<16}")
                lines.append("")
        except Exception:
            pass

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show platform")

    def show_environment(self, state, output, component='all'):
        """Display Arista EOS style 'show environment [temperature|cooling|power]'."""
        lines = []
        if component in ('all', 'cooling'):
            lines.append("System cooling status:")
            found_fan = False
            try:
                fan_path = build_path('/platform/fan-tray[id=*]')
                fan_data = state.server.get_data_store(DataStore.State).get_data(fan_path, recursive=True)
                lines.append("Slot  Description                       Status         Speed")
                lines.append("----- --------------------------------- -------------- ------")
                for fan in fan_data.platform.get().fan_tray.items():
                    tray_id = _safe_get(fan, 'id', '-')
                    oper = _safe_get(fan, 'oper_state', '-')
                    if oper != 'empty':
                        found_fan = True
                        status = "ok" if oper in ("up", "ok") else oper
                        speed = _safe_get(fan, 'speed', None)
                        speed_str = f"{speed}%" if speed is not None else "--"
                        lines.append(f"{str(tray_id):<5} Fan-Tray {str(tray_id):<22} {status:<14} {speed_str}")
            except Exception:
                pass
            if not found_fan:
                lines.append("No fan tray modules populated.")
            lines.append("")

        if component in ('all', 'power'):
            lines.append("System power status:")
            found_psu = False
            try:
                psu_path = build_path('/platform/power-supply[id=*]')
                psu_data = state.server.get_data_store(DataStore.State).get_data(psu_path, recursive=True)
                lines.append("Slot  Model            Output Power   Status")
                lines.append("----- ---------------- -------------- -----------------")
                for psu in psu_data.platform.get().power_supply.items():
                    psu_id = _safe_get(psu, 'id', '-')
                    model = _safe_get(psu, 'type', '-')
                    oper = _safe_get(psu, 'oper_state', '-')
                    if oper != 'empty' and model != '-':
                        found_psu = True
                        status = "ok" if oper in ("up", "ok") else oper
                        cap = _safe_get(psu, 'capacity', None)
                        cap_str = f"{cap}W" if cap is not None else "--"
                        lines.append(f"{str(psu_id):<5} {str(model):<16} {cap_str:<14} {status}")
            except Exception:
                pass
            if not found_psu:
                lines.append("No power supply modules populated.")
            lines.append("")

        if component in ('all', 'temperature'):
            lines.append("System temperature status:")
            lines.append("Sensor                Description                       Status    Temp(C)")
            lines.append("--------------------- --------------------------------- --------- -------")
            found_temp = False
            try:
                ctrl_path = build_path('/platform/control[slot=*]')
                ctrl_data = state.server.get_data_store(DataStore.State).get_data(ctrl_path, recursive=True)
                for c in ctrl_data.platform.get().control.items():
                    slot = _safe_get(c, 'slot', 'A')
                    temp_c = _safe_get(c, 'temperature', None)
                    if temp_c is not None:
                        if hasattr(temp_c, 'items'):
                            for s in temp_c.items():
                                t_val = _safe_get(s, 'instant', None)
                                if t_val is not None:
                                    found_temp = True
                                    lines.append(f"Slot-{str(slot):<15} Control Processor Sensor            ok        {str(t_val)}")
                        else:
                            t_node = temp_c.get() if hasattr(temp_c, 'get') else temp_c
                            t_val = _safe_get(t_node, 'instant', None)
                            if t_val is not None:
                                found_temp = True
                                lines.append(f"Slot-{str(slot):<15} Control Processor Sensor            ok        {str(t_val)}")
            except Exception:
                pass
            if not found_temp:
                lines.append("No temperature sensor data available.")
            lines.append("")

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show platform environment")

    def show_module(self, state, output):
        """Display Arista EOS style 'show module'."""
        lines = []
        modules = []
        linecard_path = build_path('/platform/linecard[slot=*]')
        ctrl_path = build_path('/platform/control[slot=*]')

        num_ports = 0
        try:
            intf_data = state.server.get_data_store(DataStore.State).get_data(build_path('/interface[name=*]'), recursive=True)
            num_ports = sum(1 for i in intf_data.interface.items() if i.name.startswith('ethernet-'))
        except Exception:
            num_ports = 0
        ports_str = str(num_ports) if num_ports > 0 else "--"

        uptime_str = "--"
        try:
            sys_data = state.server.get_data_store(DataStore.State).get_data(build_path('/system/information'), recursive=True)
            info = sys_data.system.get().information.get()
            up_secs = 0
            last_booted = _safe_get(info, 'last_booted')
            if last_booted:
                boot_dt = _parse_srl_timestamp(last_booted)
                now_dt = _parse_srl_timestamp(_safe_get(info, 'current_datetime')) or datetime.datetime.now(datetime.timezone.utc)
                if boot_dt:
                    up_secs = max(0, int((now_dt - boot_dt).total_seconds()))
            days = int(up_secs // 86400)
            hours = int((up_secs % 86400) // 3600)
            mins = int((up_secs % 3600) // 60)
            uptime_str = f"{days} days, {hours} hours" if days > 0 else (f"{hours} hours, {mins} mins" if hours > 0 else f"{mins} mins")
        except Exception:
            pass

        try:
            lc_data = state.server.get_data_store(DataStore.State).get_data(linecard_path, recursive=True)
            for lc in lc_data.platform.get().linecard.items():
                slot = _safe_get(lc, 'slot', '1')
                model = _safe_get(lc, 'type', '') or _safe_get(lc, 'part_number', 'Linecard')
                serial = _safe_get(lc, 'serial_number', '--') or '--'
                oper = _safe_get(lc, 'oper_state', 'up')
                status = "Ok" if oper == 'up' else "Disabled"
                modules.append({
                    'mod': str(slot),
                    'ports': ports_str,
                    'card': 'Linecard',
                    'type': 'Linecard',
                    'model': str(model),
                    'serial': str(serial),
                    'status': status,
                    'uptime': uptime_str
                })
        except Exception:
            pass

        if not modules:
            try:
                ctrl_data = state.server.get_data_store(DataStore.State).get_data(ctrl_path, recursive=True)
                for c in ctrl_data.platform.get().control.items():
                    slot = _safe_get(c, 'slot', '1')
                    model = _safe_get(c, 'type', '') or _safe_get(c, 'part_number', 'Control')
                    serial = _safe_get(c, 'serial_number', '--') or '--'
                    oper = _safe_get(c, 'oper_state', 'up')
                    status = "Ok" if oper == 'up' else "Disabled"
                    modules.append({
                        'mod': '1',
                        'ports': ports_str,
                        'card': 'Fabric/Control',
                        'type': 'Fabric/Control',
                        'model': str(model),
                        'serial': str(serial),
                        'status': status,
                        'uptime': uptime_str
                    })
            except Exception:
                pass

        lines.append(f"{'Module':<7} {'Ports':<6} {'Card':<22} {'Type':<10} {'Model':<22} {'Serial No.'}")
        lines.append("------ ----- ---------------------- ---------- ---------------------- ----------")
        for m in modules:
            lines.append(f"{m['mod']:<7} {m['ports']:<6} {m['card']:<22} {m['type']:<10} {m['model']:<22} {m['serial']}")

        lines.append("")
        lines.append(f"{'Module':<7} {'Status':<18} {'Uptime'}")
        lines.append("------ ------------------ -------------------------")
        for m in modules:
            lines.append(f"{m['mod']:<7} {m['status']:<18} {m['uptime']}")

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show platform")

    def show_processes_top_once(self, state, output):
        """Display Arista EOS style 'show processes top once' using SR Linux State datastore."""
        lines = []
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        up_str = "--"
        try:
            sys_data = state.server.get_data_store(DataStore.State).get_data(build_path('/system/information'), recursive=True)
            info = sys_data.system.get().information.get()
            curr_dt_raw = _safe_get(info, 'current_datetime')
            if curr_dt_raw:
                parsed_now = _parse_srl_timestamp(curr_dt_raw)
                if parsed_now:
                    now_dt = parsed_now
            up_secs = 0
            last_booted = _safe_get(info, 'last_booted')
            if last_booted:
                boot_dt = _parse_srl_timestamp(last_booted)
                if boot_dt:
                    up_secs = max(0, int((now_dt - boot_dt).total_seconds()))
            days = int(up_secs // 86400)
            hours = int((up_secs % 86400) // 3600)
            mins = int((up_secs % 3600) // 60)
            if days > 0:
                up_str = f"{days} days, {hours:2d}:{mins:02d}"
            else:
                up_str = f"{hours:2d}:{mins:02d}"
        except Exception:
            pass

        now_time = now_dt.strftime("%H:%M:%S")

        # Active user sessions from /system/aaa/authentication/session[id=*]
        num_users = 1
        try:
            sess_data = state.server.get_data_store(DataStore.State).get_data(
                build_path('/system/aaa/authentication/session[id=*]'), recursive=True
            )
            sessions = list(sess_data.system.get().aaa.get().authentication.get().session.items())
            if sessions:
                num_users = len(sessions)
        except Exception:
            pass

        load1, load5, load15 = "0.00", "0.00", "0.00"
        cpu_line = "%Cpu(s):  0.0 us,  0.0 sy,  0.0 ni, 100.0 id,  0.0 wa,  0.0 hi,  0.0 si,  0.0 st"
        mem_total_kb, mem_free_kb, used_kb, buff_cache, mem_avail_kb = 0, 0, 0, 0, 0
        swap_tot_kb, swap_free_kb, swap_used_kb = 0, 0, 0
        ps_rows = []

        try:
            ctrl_data = state.server.get_data_store(DataStore.State).get_data(
                build_path('/platform/control[slot=*]'), recursive=True
            )
            for c in ctrl_data.platform.get().control.items():
                # CPU & Load metrics
                try:
                    for cpu_obj in c.cpu.items():
                        idx = str(_safe_get(cpu_obj, 'index', ''))
                        if idx == 'all':
                            if hasattr(cpu_obj, 'total') and cpu_obj.total.exists():
                                tot = cpu_obj.total.get()
                                a1 = float(_safe_get(tot, 'average_1', 0) or 0)
                                a5 = float(_safe_get(tot, 'average_5', 0) or 0)
                                a15 = float(_safe_get(tot, 'average_15', 0) or 0)
                                load1 = f"{a1 / 100.0:.2f}"
                                load5 = f"{a5 / 100.0:.2f}"
                                load15 = f"{a15 / 100.0:.2f}"

                            def _inst(attr_name, default_val=0.0):
                                sub = _safe_get(cpu_obj, attr_name, None)
                                if sub and sub.exists():
                                    return float(_safe_get(sub.get(), 'instant', default_val) or default_val)
                                return default_val

                            us = _inst('user', 0.0)
                            sy = _inst('system', 0.0)
                            ni = _inst('nice', 0.0)
                            idl = _inst('idle', 100.0)
                            wa = _inst('iowait', 0.0)
                            hi = _inst('hardware_interrupt', 0.0)
                            si = _inst('software_interrupt', 0.0)
                            cpu_line = f"%Cpu(s): {us:4.1f} us, {sy:4.1f} sy, {ni:4.1f} ni, {idl:4.1f} id, {wa:4.1f} wa, {hi:4.1f} hi, {si:4.1f} si,  0.0 st"
                            break
                except Exception:
                    pass

                # Memory metrics
                try:
                    if hasattr(c, 'memory') and c.memory.exists():
                        mem = c.memory.get()
                        phys = int(_safe_get(mem, 'physical', 0) or 0)
                        free_b = int(_safe_get(mem, 'free', 0) or 0)
                        res_b = int(_safe_get(mem, 'reserved', 0) or 0)
                        mem_total_kb = phys // 1024
                        mem_free_kb = free_b // 1024
                        used_kb = res_b // 1024 if res_b > 0 else max(0, mem_total_kb - mem_free_kb)
                        buff_cache = max(0, mem_total_kb - mem_free_kb - used_kb)
                        mem_avail_kb = mem_free_kb
                except Exception:
                    pass

                # Process table from /platform/control[slot=*]/process[pid=*]
                try:
                    for p in c.process.items():
                        pid = int(_safe_get(p, 'pid', 0) or 0)
                        comm = str(_safe_get(p, 'name', '') or _safe_get(p, 'args', '') or 'unknown')
                        cpu_val = float(_safe_get(p, 'cpu_utilization', 0) or 0)
                        mem_bytes = int(_safe_get(p, 'memory_usage', 0) or 0)
                        mem_val = float(_safe_get(p, 'memory_utilization', 0) or 0)
                        rss_kb = mem_bytes // 1024
                        vsz_kb = rss_kb
                        shr_kb = 0
                        start_dt = _parse_srl_timestamp(_safe_get(p, 'start_time', None))
                        elapsed = max(0.0, (now_dt - start_dt).total_seconds()) if start_dt else 0.0
                        cpu_secs = elapsed * (cpu_val / 100.0)
                        mins_t = int(cpu_secs // 60)
                        secs_t = cpu_secs % 60
                        tm_str = f"{mins_t}:{secs_t:05.2f}"
                        stat_ch = 'R' if cpu_val > 0 else 'S'
                        ps_rows.append({
                            'pid': pid,
                            'user': 'root',
                            'pri': '20',
                            'ni': '0',
                            'vsz': vsz_kb,
                            'rss': rss_kb,
                            'shr': shr_kb,
                            'stat': stat_ch,
                            'cpu': cpu_val,
                            'mem': mem_val,
                            'time': tm_str,
                            'comm': comm,
                        })
                except Exception:
                    pass
                break
        except Exception:
            pass

        ps_rows.sort(key=lambda r: (-r['cpu'], -r['rss'], r['pid']))

        total_tasks = len(ps_rows)
        running = sum(1 for p in ps_rows if p['stat'] == 'R')
        if total_tasks > 0 and running == 0:
            running = 1
        sleeping = max(0, total_tasks - running)
        stopped = 0
        zombie = 0

        lines.append(f"top - {now_time} up {up_str},  {num_users} user{'s' if num_users != 1 else ''},  load average: {load1}, {load5}, {load15}")
        lines.append(f"Tasks: {total_tasks} total,   {running} running, {sleeping} sleeping,   {stopped} stopped,   {zombie} zombie")
        lines.append(cpu_line)
        lines.append(f"KiB Mem : {mem_total_kb} total, {mem_free_kb} free, {used_kb} used,  {buff_cache} buff/cache")
        lines.append(f"KiB Swap: {swap_tot_kb:>9} total, {swap_free_kb:>8} free, {swap_used_kb:>8} used. {mem_avail_kb} avail Mem")
        lines.append("")
        lines.append(f"{'PID':>5} {'USER':<9} {'PR':<4} {'NI':<4} {'VIRT':>8} {'RES':>7} {'SHR':>6} {'S':<2} {'%CPU':>5} {'%MEM':>5} {'TIME+':>8} {'COMMAND'}")

        for r in ps_rows[:25]:
            lines.append(
                f"{r['pid']:>5} {r['user']:<9} {r['pri']:<4} {r['ni']:<4} {r['vsz']:>8} {r['rss']:>7} {r['shr']:>6} {r['stat']:<2} {r['cpu']:>5.1f} {r['mem']:>5.1f} {r['time']:>8} {r['comm']}"
            )

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: info from state system information")

