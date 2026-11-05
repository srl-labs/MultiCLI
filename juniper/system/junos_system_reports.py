#!/usr/bin/python
###########################################################################
# Description: MultiCLI System Reports for Juniper JUNOS
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


class JunosSystemReports:
    """Handles Juniper JUNOS system show commands."""

    def show_version(self, state, output):
        """Display Juniper JUNOS style 'show version'."""
        hostname = "-"
        model = "-"
        sw_version = "-"

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

        # Query chassis model
        path_chassis = build_path('/platform/chassis')
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path_chassis, recursive=True)
            ch = data.platform.get().chassis.get()
            if hasattr(ch, 'type') and ch.type:
                model = str(ch.type)
        except Exception:
            pass

        # Query system version
        sys_info_path = build_path('/system/information')
        try:
            sys_data = state.server.get_data_store(DataStore.State).get_data(sys_info_path, recursive=True)
            info = sys_data.system.get().information.get()
            if hasattr(info, 'version') and info.version:
                sw_version = str(info.version).lstrip('v').split('-')[0]
        except Exception:
            pass

        lines = [
            f"Hostname: {hostname}",
            f"Model: {model}",
            f"SRLinux: {sw_version}",
            f"Nokia SR Linux Base OS Software Suite [{sw_version}]",
            f"Nokia SR Linux Kernel Software Suite [{sw_version}]",
            f"Nokia SR Linux Routing Software Suite [{sw_version}]"
        ]

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: srl show version")

    def show_system_uptime(self, state, output):
        """Display Juniper JUNOS style 'show system uptime'."""
        now = datetime.datetime.now(datetime.timezone.utc)
        tz_str = "UTC"

        last_booted = ""
        uptime_seconds = 0
        sys_info_path = build_path('/system/information')
        try:
            sys_data = state.server.get_data_store(DataStore.State).get_data(sys_info_path, recursive=True)
            info = sys_data.system.get().information.get()
            curr_dt = _safe_get(info, 'current_datetime')
            if curr_dt:
                c_str = str(curr_dt).split('(')[0].strip()
                if 'Z' in c_str:
                    c_str = c_str.replace('Z', '+00:00')
                c_dt = datetime.datetime.fromisoformat(c_str)
                if c_dt.tzinfo is None:
                    c_dt = c_dt.replace(tzinfo=datetime.timezone.utc)
                now = c_dt
            lb = _safe_get(info, 'last_booted')
            if lb:
                last_booted = str(lb)
        except Exception:
            pass

        try:
            clk_data = state.server.get_data_store(DataStore.State).get_data(build_path('/system/clock'), recursive=True)
            clk = clk_data.system.get().clock.get()
            tz = _safe_get(clk, 'timezone')
            if tz:
                tz_str = str(tz)
        except Exception:
            pass

        curr_time_str = now.strftime(f"%Y-%m-%d %H:%M:%S {tz_str}")

        if uptime_seconds == 0 and last_booted:
            try:
                boot_str = last_booted.split('(')[0].strip()
                if 'Z' in boot_str:
                    boot_str = boot_str.replace('Z', '+00:00')
                boot_time = datetime.datetime.fromisoformat(boot_str)
                if boot_time.tzinfo is None:
                    boot_time = boot_time.replace(tzinfo=datetime.timezone.utc)
                uptime_seconds = max(0, int((now - boot_time).total_seconds()))
            except Exception:
                uptime_seconds = 0

        days, rem = divmod(uptime_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, _ = divmod(rem, 60)
        ago_str = f"({days}d {hours:02}:{minutes:02} ago)"

        boot_dt = now - datetime.timedelta(seconds=uptime_seconds)
        boot_str = boot_dt.strftime("%Y-%m-%d %H:%M:%S UTC")

        # Dynamic time source check
        time_source = "LOCAL CLOCK"
        try:
            ntp_path = build_path('/system/ntp')
            ntp_data = state.server.get_data_store(DataStore.State).get_data(ntp_path, recursive=True)
            ntp_node = ntp_data.system.get().ntp.get()
            sync_st = _safe_get(ntp_node, 'synchronization_state')
            if sync_st and str(sync_st).lower() in ('synchronized', 'sync'):
                time_source = "NTP CLOCK"
        except Exception:
            pass

        # Dynamic last configured check
        last_cfg_str = f"{boot_str} {ago_str}"
        try:
            cfg_path = build_path('/system/configuration')
            cfg_data = state.server.get_data_store(DataStore.State).get_data(cfg_path, recursive=True)
            cfg_node = cfg_data.system.get().configuration.get()
            commits = []
            commit_list = _safe_get(cfg_node, 'commit')
            if commit_list is not None:
                for c in commit_list.items():
                    c_end = _safe_get(c, 'ended') or _safe_get(c, 'started')
                    c_user = _safe_get(c, 'username', '') or ''
                    if c_end:
                        commits.append((c_end, c_user))
            if commits:
                latest_commit = commits[-1]
                ts_raw = str(latest_commit[0])
                c_user = latest_commit[1]
                ts_iso = ts_raw.split('(')[0].strip() if '(' in ts_raw else ts_raw
                ts_ago = ('(' + ts_raw.split('(')[1].strip()) if '(' in ts_raw else ""
                if 'Z' in ts_iso:
                    ts_iso = ts_iso.replace('Z', '+00:00')
                try:
                    c_dt = datetime.datetime.fromisoformat(ts_iso)
                    user_str = f" by {c_user}" if c_user else ""
                    last_cfg_str = f"{c_dt.strftime('%Y-%m-%d %H:%M:%S UTC')} {ts_ago}{user_str}".strip()
                except Exception:
                    user_str = f" by {c_user}" if c_user else ""
                    last_cfg_str = f"{ts_raw}{user_str}"
        except Exception:
            pass

        lines = [
            f"Current time: {curr_time_str}",
            f"Time Source: {time_source}",
            f"System booted: {boot_str} {ago_str}",
            f"Protocols started: {boot_str} {ago_str}",
            f"Last configured: {last_cfg_str}",
            f" {now.strftime('%I:%M%p')}  up {days} days,  {hours:02}:{minutes:02}"
        ]

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: info from state system information")

    def show_chassis_hardware(self, state, output):
        """Display Juniper JUNOS style 'show chassis hardware'."""
        lines = [
            "Hardware inventory:",
            f"{'Item':<16} {'Version':<8} {'Part number':<12} {'Serial number':<17} {'Description'}"
        ]

        # Chassis
        ch_type = "-"
        serial = "-"
        path_chassis = build_path('/platform/chassis')
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path_chassis, recursive=True)
            ch = data.platform.get().chassis.get()
            ch_type = _safe_get(ch, 'type', '-') or '-'
            serial = _safe_get(ch, 'serial_number', '-') or '-'
        except Exception:
            pass

        lines.append(f"{'Chassis':<16} {'':<8} {'':<12} {serial:<17} {ch_type}")

        # Control module
        path_ctrl = build_path('/platform/control[slot=*]')
        try:
            data_ctrl = state.server.get_data_store(DataStore.State).get_data(path_ctrl, recursive=True)
            for c in data_ctrl.platform.get().control.items():
                slot = _safe_get(c, 'slot', 'A')
                c_type = _safe_get(c, 'type', 'Control Module') or f"Control Card {slot}"
                c_sn = _safe_get(c, 'serial_number', '-') or '-'
                c_part = _safe_get(c, 'part_number', '-') or '-'
                lines.append(f"{f'Control Card {slot}':<16} {'':<8} {c_part:<12} {c_sn:<17} {c_type}")
        except Exception:
            pass

        # Power supplies
        path_psu = build_path('/platform/power-supply[id=*]')
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path_psu, recursive=True)
            for psu in data.platform.get().power_supply.items():
                p_id = psu.id
                oper = _safe_get(psu, 'oper_state', '-')
                p_sn = _safe_get(psu, 'serial_number')
                if oper != 'empty' and p_sn:
                    lines.append(f"{f'Power Supply {p_id}':<16} {'':<8} {'-':<12} {p_sn:<17} {'Power Supply'}")
        except Exception:
            pass

        # Fan modules
        path_fan = build_path('/platform/fan-tray[id=*]')
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path_fan, recursive=True)
            for fan in data.platform.get().fan_tray.items():
                f_id = fan.id
                oper = _safe_get(fan, 'oper_state', '-')
                f_sn = _safe_get(fan, 'serial_number')
                if oper != 'empty' and f_sn:
                    lines.append(f"{f'Fan Tray {f_id}':<16} {'':<8} {'-':<12} {f_sn:<17} {'Fan Tray'}")
        except Exception:
            pass

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: show platform chassis")

    def show_system_processes(self, state, output, summary=False):
        """Display Juniper JUNOS style 'show system processes [summary|extensive]' using SR Linux State datastore."""
        lines = []
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        up_str = "--"
        try:
            sys_data = state.server.get_data_store(DataStore.State).get_data(build_path('/system/information'), recursive=True)
            info = sys_data.system.get().information.get()
            curr_dt = _safe_get(info, 'current_datetime')
            if curr_dt:
                c_str = str(curr_dt).split('(')[0].strip()
                if 'Z' in c_str:
                    c_str = c_str.replace('Z', '+00:00')
                c_dt = datetime.datetime.fromisoformat(c_str)
                if c_dt.tzinfo is None:
                    c_dt = c_dt.replace(tzinfo=datetime.timezone.utc)
                now_dt = c_dt
            up_secs = 0
            lb = _safe_get(info, 'last_booted')
            if lb:
                b_str = str(lb).split('(')[0].strip()
                if 'Z' in b_str:
                    b_str = b_str.replace('Z', '+00:00')
                b_dt = datetime.datetime.fromisoformat(b_str)
                if b_dt.tzinfo is None:
                    b_dt = b_dt.replace(tzinfo=datetime.timezone.utc)
                up_secs = max(0, int((now_dt - b_dt).total_seconds()))
            days = int(up_secs // 86400)
            hours = int((up_secs % 86400) // 3600)
            mins = int((up_secs % 3600) // 60)
            secs = int(up_secs % 60)
            up_str = f"{days}+{hours:02d}:{mins:02d}:{secs:02d}"
        except Exception:
            pass

        now_time = now_dt.strftime("%H:%M:%S")
        last_pid = "0"
        load1, load5, load15 = "0.00", "0.00", "0.00"
        cpu_line = "CPU:  0.0% user,  0.0% nice,  0.0% system,  0.0% interrupt, 100.0% idle"
        active_m, inact_m, wired_m, mem_free_m = 0, 0, 0, 0
        swap_tot_m, swap_free_m = 0, 0
        ps_rows = []

        try:
            ctrl_data = state.server.get_data_store(DataStore.State).get_data(
                build_path('/platform/control[slot=*]'), recursive=True
            )
            for c in ctrl_data.platform.get().control.items():
                cpu_list = _safe_get(c, 'cpu')
                if cpu_list is not None:
                    for cpu_obj in cpu_list.items():
                        idx = str(_safe_get(cpu_obj, 'index', ''))
                        if idx == 'all':
                            tot_container = _safe_get(cpu_obj, 'total')
                            if tot_container is not None and tot_container.exists():
                                tot = tot_container.get()
                                a1 = float(_safe_get(tot, 'average_1', 0) or 0)
                                a5 = float(_safe_get(tot, 'average_5', 0) or 0)
                                a15 = float(_safe_get(tot, 'average_15', 0) or 0)
                                load1 = f"{a1 / 100.0:.2f}"
                                load5 = f"{a5 / 100.0:.2f}"
                                load15 = f"{a15 / 100.0:.2f}"

                            def _inst(attr_name, default_val=0.0):
                                sub = _safe_get(cpu_obj, attr_name)
                                if sub is not None and sub.exists():
                                    return float(_safe_get(sub.get(), 'instant', default_val) or default_val)
                                return default_val

                            us = _inst('user', 0.0)
                            ni = _inst('nice', 0.0)
                            sy = _inst('system', 0.0)
                            idl = _inst('idle', 100.0)
                            intr = _inst('hardware_interrupt', 0.0) + _inst('software_interrupt', 0.0)
                            cpu_line = f"CPU:  {us:4.1f}% user,  {ni:4.1f}% nice,  {sy:4.1f}% system,  {intr:4.1f}% interrupt, {idl:4.1f}% idle"
                            break

                mem_container = _safe_get(c, 'memory')
                if mem_container is not None and mem_container.exists():
                    mem = mem_container.get()
                    phys = int(_safe_get(mem, 'physical', 0) or 0)
                    free_b = int(_safe_get(mem, 'free', 0) or 0)
                    res_b = int(_safe_get(mem, 'reserved', 0) or 0)
                    tot_m = phys // (1024 * 1024)
                    mem_free_m = free_b // (1024 * 1024)
                    active_m = res_b // (1024 * 1024) if res_b > 0 else max(0, tot_m - mem_free_m)
                    inact_m = 0
                    wired_m = max(0, tot_m - active_m - mem_free_m)

                proc_list = _safe_get(c, 'process')
                if proc_list is not None:
                    for p in proc_list.items():
                        pid = int(_safe_get(p, 'pid', 0) or 0)
                        comm = str(_safe_get(p, 'name', '') or _safe_get(p, 'args', '') or 'unknown')
                        cpu_val = float(_safe_get(p, 'cpu_utilization', 0) or 0)
                        mem_bytes = int(_safe_get(p, 'memory_usage', 0) or 0)
                        rss_kb = mem_bytes // 1024
                        vsz_kb = rss_kb
                        s_raw = _safe_get(p, 'start_time')
                        elapsed = 0.0
                        if s_raw:
                            try:
                                st_str = str(s_raw).split('(')[0].strip().replace('Z', '+00:00')
                                st_dt = datetime.datetime.fromisoformat(st_str)
                                if st_dt.tzinfo is None:
                                    st_dt = st_dt.replace(tzinfo=datetime.timezone.utc)
                                elapsed = max(0.0, (now_dt - st_dt).total_seconds())
                            except Exception:
                                pass
                        cpu_secs = int(elapsed * (cpu_val / 100.0))
                        tm_str = f"{cpu_secs // 60}:{cpu_secs % 60:02d}"
                        s_name = "run" if cpu_val > 0 else "select"
                        ps_rows.append({
                            'pid': pid,
                            'user': 'root',
                            'thr': '1',
                            'pri': '20',
                            'ni': '0',
                            'vsz': vsz_kb,
                            'rss': rss_kb,
                            'state': s_name,
                            'time': tm_str,
                            'cpu': cpu_val,
                            'comm': comm,
                        })
                break
        except Exception:
            pass

        if ps_rows:
            last_pid = str(max(p['pid'] for p in ps_rows))

        ps_rows.sort(key=lambda r: (-r['cpu'], -r['rss'], r['pid']))

        total_procs = len(ps_rows)
        running = sum(1 for p in ps_rows if p['state'] == 'run')
        if total_procs > 0 and running == 0:
            running = 1
        sleeping = max(0, total_procs - running)

        lines.append(f"last pid: {last_pid:>6};  load averages:  {load1},  {load5},  {load15}  up {up_str}    {now_time}")
        lines.append(f"{total_procs} processes: {running} running, {sleeping} sleeping")
        lines.append(cpu_line)
        lines.append(f"Mem: {active_m}M Active, {inact_m}M Inact, {wired_m}M Wired, {mem_free_m}M Free")
        lines.append(f"Swap: {swap_tot_m}M Total, {swap_free_m}M Free")

        if not summary:
            lines.append("")
            lines.append(f"{'PID':>6} {'USERNAME':<10} {'THR':<4} {'PRI':<4} {'NICE':<5} {'SIZE':>8} {'RES':>7} {'STATE':<8} {'TIME':>8} {'WCPU':>6} {'COMMAND'}")
            for p in ps_rows[:25]:
                size_k = f"{p['vsz']}K"
                res_k = f"{p['rss']}K"
                wcpu = f"{p['cpu']:.1f}%"
                lines.append(
                    f"{p['pid']:>6} {p['user']:<10} {p['thr']:<4} {p['pri']:<4} {p['ni']:<5} {size_k:>8} {res_k:>7} {p['state']:<8} {p['time']:>8} {wcpu:>6} {p['comm']}"
                )

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: info from state system information")
