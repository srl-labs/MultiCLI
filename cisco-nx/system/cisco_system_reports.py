#!/usr/bin/python
###########################################################################
# Description: MultiCLI System Reports for Cisco NX-OS
# Copyright (c) 2025-2026 Nokia
###########################################################################

import datetime
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


def _parse_srl_timestamp(val):
    """Parse an SR Linux YANG date-and-time string into a timezone-aware UTC datetime."""
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


class CiscoSystemReports:
    """Handles Cisco NX-OS system-level show commands."""

    def show_version(self, state, output):
        """Display Cisco NX-OS style 'show version'."""
        hostname = "-"
        chassis_type = "-"
        serial = ""
        sw_version = ""
        last_booted = ""
        uptime_seconds = 0
        total_mem = 0
        free_mem = 0

        # Query platform / chassis info
        path_chassis = build_path('/platform/chassis')
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path_chassis, recursive=True)
            ch = data.platform.get().chassis.get()
            serial = str(_safe_get(ch, 'serial_number', '') or '')
            chassis_type = str(_safe_get(ch, 'type', '-') or '-')
            last_booted = str(_safe_get(ch, 'last_booted', '') or '')
        except Exception:
            pass

        # Query system information (version, uptime)
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

        # Query control / memory info
        path_control = build_path('/platform/control[slot=*]')
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path_control, recursive=True)
            for ctrl in data.platform.get().control.items():
                if hasattr(ctrl, 'memory') and ctrl.memory.exists():
                    mem = ctrl.memory.get()
                    if hasattr(mem, 'physical') and mem.physical:
                        total_mem = int(mem.physical) // 1024
                    if hasattr(mem, 'free') and mem.free:
                        free_mem = int(mem.free) // 1024
        except Exception:
            pass

        # Query system hostname
        path_system = build_path('/system/name/host-name')
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path_system, recursive=False)
            sys_node = data.system.get()
            if hasattr(sys_node, 'name') and sys_node.name.exists():
                name_node = sys_node.name.get()
                if hasattr(name_node, 'host_name') and name_node.host_name:
                    hostname = str(name_node.host_name)
        except Exception:
            pass

        # Calculate uptime
        if uptime_seconds == 0 and last_booted:
            try:
                boot_str = last_booted.split('(')[0].strip()
                if 'Z' in boot_str:
                    boot_str = boot_str.replace('Z', '+00:00')
                boot_time = datetime.datetime.fromisoformat(boot_str)
                now = datetime.datetime.now(datetime.timezone.utc)
                if boot_time.tzinfo is None:
                    boot_time = boot_time.replace(tzinfo=datetime.timezone.utc)
                uptime_seconds = max(0, int((now - boot_time).total_seconds()))
            except Exception:
                uptime_seconds = 0

        days, rem = divmod(uptime_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        uptime_str = f"{days} day(s), {hours} hour(s), {minutes} minute(s), {seconds} second(s)"

        lines = [
            "Nokia SR Linux Software",
            "",
            "Software",
            f"  SRLinux: version {sw_version if sw_version else 'N/A'}",
            "",
            "Hardware",
            f"  Nokia {chassis_type} Chassis" if chassis_type != "-" else "  Chassis",
            f"  System memory: {total_mem} kB",
            f"  Processor Board ID {serial}" if serial else "  Processor Board ID -",
            f"  Device name: {hostname}",
            "",
            f"Kernel uptime is {uptime_str}",
            "",
            "Last reset at " + (last_booted.replace('T', ' ').replace('Z', '') if last_booted else "Unknown"),
            f"  System version: {sw_version if sw_version else 'N/A'}"
        ]

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: srl show version")

    def show_hostname(self, state, output):
        """Display Cisco NX-OS style 'show hostname'."""
        hostname = "-"
        path_system = build_path('/system/name/host-name')
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path_system, recursive=False)
            sys_node = data.system.get()
            if hasattr(sys_node, 'name') and sys_node.name.exists():
                name_node = sys_node.name.get()
                if hasattr(name_node, 'host_name') and name_node.host_name:
                    hostname = str(name_node.host_name)
        except Exception:
            pass

        output.print_line(hostname)
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: info from state system name")

    def show_clock(self, state, output):
        """Display Cisco NX-OS style 'show clock': HH:MM:SS.mmm UTC Day Mon DD YYYY."""
        now = datetime.datetime.now(datetime.timezone.utc)
        tz_str = "UTC"
        try:
            sys_data = state.server.get_data_store(DataStore.State).get_data(build_path('/system/information'), recursive=True)
            info = sys_data.system.get().information.get()
            if hasattr(info, 'current_datetime') and info.current_datetime:
                parsed = _parse_srl_timestamp(info.current_datetime)
                if parsed:
                    now = parsed
        except Exception:
            pass
        try:
            clk_data = state.server.get_data_store(DataStore.State).get_data(build_path('/system/clock'), recursive=True)
            clk = clk_data.system.get().clock.get()
            if hasattr(clk, 'timezone') and clk.timezone:
                tz_str = str(clk.timezone)
        except Exception:
            pass
        clock_str = now.strftime("%H:%M:%S.%f")[:-3] + f" {tz_str} " + now.strftime("%a %b %d %Y")
        output.print_line(clock_str)
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: info from state system clock")

    def show_inventory(self, state, output):
        """Display Cisco NX-OS style 'show inventory'."""
        lines = []

        # Chassis
        path_chassis = build_path('/platform/chassis')
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path_chassis, recursive=True)
            ch = data.platform.get().chassis.get()
            ch_type = _safe_get(ch, 'type', None)
            serial = _safe_get(ch, 'serial_number', None)
            if ch_type:
                lines.append(f'NAME: "Chassis",  DESCR: "Nokia {ch_type} Chassis"')
                lines.append(f'PID: {ch_type:<19},  VID: -   ,  SN: {serial if serial else "-"}\n')
        except Exception:
            pass

        # Power supplies
        path_psu = build_path('/platform/power-supply[id=*]')
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path_psu, recursive=True)
            for psu in data.platform.get().power_supply.items():
                p_id = _safe_get(psu, 'id', '-')
                p_type = _safe_get(psu, 'type', None)
                p_sn = _safe_get(psu, 'serial_number', None)
                if p_type:
                    lines.append(f'NAME: "Power Supply {p_id}",  DESCR: "Nokia Power Supply"')
                    lines.append(f'PID: {p_type:<19},  VID: -   ,  SN: {p_sn if p_sn else "-"}\n')
        except Exception:
            pass

        # Fan modules
        path_fan = build_path('/platform/fan-tray[id=*]')
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path_fan, recursive=True)
            for fan in data.platform.get().fan_tray.items():
                f_id = _safe_get(fan, 'id', '-')
                f_sn = _safe_get(fan, 'serial_number', None)
                f_type = _safe_get(fan, 'type', 'FAN-MODULE')
                if f_sn:
                    lines.append(f'NAME: "Fan {f_id}",  DESCR: "Chassis Fan Module"')
                    lines.append(f'PID: {f_type:<19},  VID: -   ,  SN: {f_sn}\n')
        except Exception:
            pass

        if not lines:
            lines.append("No inventory components detected.")

        output.print_line("\n".join(lines).rstrip())
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show platform chassis")

    def show_environment(self, state, output, sub_type='all'):
        """Display Cisco NX-OS style 'show environment'."""
        lines = []

        if sub_type in ('all', 'temperature'):
            lines.append("Temperature:")
            lines.append("--------------------------------------------------------------------")
            lines.append(f"{'Module':<10} {'Sensor':<22} {'MajorThresh':<12} {'MinorThresh':<12} {'CurTemp':<8} {'Status'}")
            lines.append(f"{'':<10} {'':<22} {'(Celsius)':<12} {'(Celsius)':<12} {'(Celsius)':<8} {''}")
            lines.append("--------------------------------------------------------------------")
            path_temp = build_path('/platform/control[slot=*]')
            found_temp = False
            try:
                data = state.server.get_data_store(DataStore.State).get_data(path_temp, recursive=True)
                for ctrl in data.platform.get().control.items():
                    slot = _safe_get(ctrl, 'slot', 'A')
                    temp_c = _safe_get(ctrl, 'temperature', None)
                    if temp_c is not None:
                        if hasattr(temp_c, 'items'):
                            for s in temp_c.items():
                                cur = _safe_get(s, 'instant', None)
                                if cur is not None:
                                    found_temp = True
                                    status = "Ok" if _safe_get(s, 'alarm_status', False) is False else "Alarm"
                                    s_name = _safe_get(s, 'sensor_name', 'Control Processor')
                                    lines.append(f"Slot-{str(slot):<5} {str(s_name):<22} {'--':<12} {'--':<12} {str(cur):<8} {status}")
                        else:
                            t_node = temp_c.get() if hasattr(temp_c, 'get') else temp_c
                            cur = _safe_get(t_node, 'instant', None)
                            if cur is not None:
                                found_temp = True
                                status = "Ok" if _safe_get(t_node, 'alarm_status', False) is False else "Alarm"
                                s_name = _safe_get(t_node, 'sensor_name', 'Control Processor')
                                lines.append(f"Slot-{str(slot):<5} {str(s_name):<22} {'--':<12} {'--':<12} {str(cur):<8} {status}")
            except Exception:
                pass
            if not found_temp:
                lines.append("No temperature sensor data available.")
            lines.append("")

        if sub_type in ('all', 'power'):
            lines.append("Power Supply:")
            lines.append("---------------------------------------------------------------------------")
            lines.append(f"{'PS':<6} {'Model':<18} {'Power(W)':<12} {'Status'}")
            lines.append("---------------------------------------------------------------------------")
            path_psu = build_path('/platform/power-supply[id=*]')
            found_psu = False
            try:
                data = state.server.get_data_store(DataStore.State).get_data(path_psu, recursive=True)
                for psu in data.platform.get().power_supply.items():
                    p_id = _safe_get(psu, 'id', '-')
                    p_type = _safe_get(psu, 'type', '-')
                    oper = _safe_get(psu, 'oper_state', '-')
                    p_cap = _safe_get(psu, 'capacity', None)
                    p_cap_str = f"{p_cap}W" if p_cap is not None else "--"
                    if oper != 'empty' and p_type != '-':
                        found_psu = True
                        lines.append(f"{str(p_id):<6} {str(p_type):<18} {p_cap_str:<12} {str(oper)}")
            except Exception:
                pass
            if not found_psu:
                lines.append("No power supply modules populated.")
            lines.append("")

        if sub_type in ('all', 'cooling'):
            lines.append("Fan:")
            lines.append("------------------------------------------------------")
            lines.append(f"{'Fan':<10} {'Model':<20} {'Status'}")
            lines.append("------------------------------------------------------")
            path_fan = build_path('/platform/fan-tray[id=*]')
            found_fan = False
            try:
                data = state.server.get_data_store(DataStore.State).get_data(path_fan, recursive=True)
                for fan in data.platform.get().fan_tray.items():
                    f_id = _safe_get(fan, 'id', '-')
                    oper = _safe_get(fan, 'oper_state', '-')
                    if oper != 'empty':
                        found_fan = True
                        lines.append(f"Fan{str(f_id):<7} Chassis Fan          {str(oper)}")
            except Exception:
                pass
            if not found_fan:
                lines.append("No fan tray modules populated.")
            lines.append("")

        output.print_line("\n".join(lines).rstrip())
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show platform environment")

    def show_module(self, state, output):
        """Display Cisco NX-OS style 'show module'."""
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

        sw_version = "--"
        try:
            sys_info = state.server.get_data_store(DataStore.State).get_data(build_path('/system/information'), recursive=True)
            info = sys_info.system.get().information.get()
            if hasattr(info, 'version') and info.version:
                sw_version = str(info.version)
        except Exception:
            pass

        serial = "--"
        mac = "--"
        try:
            ch_data = state.server.get_data_store(DataStore.State).get_data(build_path('/platform/chassis'), recursive=True)
            ch = ch_data.platform.get().chassis.get()
            if hasattr(ch, 'serial_number') and ch.serial_number:
                serial = str(ch.serial_number)
            if hasattr(ch, 'hw_mac_address') and ch.hw_mac_address:
                mac = str(ch.hw_mac_address)
        except Exception:
            pass

        try:
            lc_data = state.server.get_data_store(DataStore.State).get_data(linecard_path, recursive=True)
            for lc in lc_data.platform.get().linecard.items():
                slot = _safe_get(lc, 'slot', '1')
                model = _safe_get(lc, 'type', '') or _safe_get(lc, 'part_number', 'Linecard')
                oper = _safe_get(lc, 'oper_state', 'up')
                status = "ok" if oper == 'up' else "down"
                modules.append({
                    'mod': str(slot),
                    'ports': ports_str,
                    'type': 'Linecard',
                    'model': str(model),
                    'status': status,
                    'sw': sw_version,
                    'hw': '--',
                    'mac': mac,
                    'serial': serial
                })
        except Exception:
            pass

        if not modules:
            try:
                ctrl_data = state.server.get_data_store(DataStore.State).get_data(ctrl_path, recursive=True)
                for c in ctrl_data.platform.get().control.items():
                    slot = _safe_get(c, 'slot', '1')
                    model = _safe_get(c, 'type', '') or _safe_get(c, 'part_number', 'Control')
                    oper = _safe_get(c, 'oper_state', 'up')
                    status = "ok" if oper == 'up' else "down"
                    modules.append({
                        'mod': '1',
                        'ports': ports_str,
                        'type': 'Fabric/Control',
                        'model': str(model),
                        'status': status,
                        'sw': sw_version,
                        'hw': '--',
                        'mac': mac,
                        'serial': serial
                    })
            except Exception:
                pass

        lines.append(f"{'Mod':<5} {'Ports':<6} {'Module-Type':<35} {'Model':<18} {'Status'}")
        lines.append(f"---  -----  ----------------------------------- ------------------ ----------")
        for m in modules:
            lines.append(f"{m['mod']:<5} {m['ports']:<6} {m['type']:<35} {m['model']:<18} {m['status']}")

        lines.append("")
        lines.append(f"{'Mod':<5} {'Sw':<16} {'Hw'}")
        lines.append(f"---  --------------  ------")
        for m in modules:
            lines.append(f"{m['mod']:<5} {m['sw']:<16} {m['hw']}")

        lines.append("")
        lines.append(f"{'Mod':<5} {'MAC-Address(es)':<39} {'Serial-Num'}")
        lines.append(f"---  --------------------------------------  ----------")
        for m in modules:
            lines.append(f"{m['mod']:<5} {m['mac']:<39} {m['serial']}")

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show platform")

    def show_processes_cpu(self, state, output):
        """Display Cisco NX-OS style 'show processes cpu' using SR Linux State datastore."""
        lines = []
        cpu_5sec = "0"
        cpu_1min = "0"
        cpu_5min = "0"
        now_dt = datetime.datetime.now(datetime.timezone.utc)

        try:
            sys_data = state.server.get_data_store(DataStore.State).get_data(build_path('/system/information'), recursive=True)
            info = sys_data.system.get().information.get()
            curr_dt = _safe_get(info, 'current_datetime')
            if curr_dt:
                parsed_now = _parse_srl_timestamp(curr_dt)
                if parsed_now:
                    now_dt = parsed_now
        except Exception:
            pass

        ps_rows = []
        path_ctrl = build_path('/platform/control[slot=*]')
        try:
            ctrl_data = state.server.get_data_store(DataStore.State).get_data(path_ctrl, recursive=True)
            for ctrl in ctrl_data.platform.get().control.items():
                cpu_list = _safe_get(ctrl, 'cpu')
                if cpu_list is not None:
                    for cpu_obj in cpu_list.items():
                        idx = str(_safe_get(cpu_obj, 'index', ''))
                        tot_container = _safe_get(cpu_obj, 'total')
                        if idx == 'all' and tot_container is not None and tot_container.exists():
                            tot = tot_container.get()
                            inst = _safe_get(tot, 'instant')
                            avg1 = _safe_get(tot, 'average_1')
                            avg5 = _safe_get(tot, 'average_5')
                            if inst is not None:
                                cpu_5sec = str(inst)
                            if avg1 is not None:
                                cpu_1min = str(avg1)
                            if avg5 is not None:
                                cpu_5min = str(avg5)
                            break

                proc_list = _safe_get(ctrl, 'process')
                if proc_list is not None:
                    for p in proc_list.items():
                        pid = int(_safe_get(p, 'pid', 0) or 0)
                        comm = str(_safe_get(p, 'name', '') or _safe_get(p, 'args', '') or 'unknown')
                        cpu_val = float(_safe_get(p, 'cpu_utilization', 0) or 0)
                        mem_bytes = int(_safe_get(p, 'memory_usage', 0) or 0)
                        start_dt = _parse_srl_timestamp(_safe_get(p, 'start_time'))
                        elapsed = max(1.0, (now_dt - start_dt).total_seconds()) if start_dt else 1.0
                        runtime_ms = int(elapsed * (cpu_val / 100.0) * 1000)
                        invoked_val = max(1, int(elapsed))
                        usecs_val = (runtime_ms * 1000) // invoked_val if invoked_val > 0 else 0
                        ps_rows.append({
                            'pid': pid,
                            'ms': runtime_ms,
                            'invoked': invoked_val,
                            'usecs': usecs_val,
                            'cpu': cpu_val,
                            'mem': mem_bytes,
                            'comm': comm,
                        })
                break
        except Exception:
            pass

        ps_rows.sort(key=lambda r: (-r['cpu'], -r['mem'], r['pid']))

        lines.append(f"{'PID':<6} {'Runtime(ms)':<13} {'Invoked':<12} {'uSecs':<6} {'1Sec':<6} {'Process'}")
        lines.append(f"-----  ------------  -----------  -----  -----  -----------------")

        for r in ps_rows[:30]:
            cpu_str = f"{r['cpu']:.1f}%"
            lines.append(
                f"{str(r['pid']):<6} {str(r['ms']):<13} {str(r['invoked']):<12} {str(r['usecs']):<6} {cpu_str:<6} {r['comm']}"
            )

        lines.append("")
        lines.append(f"CPU utilization for five seconds: {cpu_5sec}%; one minute: {cpu_1min}%; five minutes: {cpu_5min}%")

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: info from state system information")
