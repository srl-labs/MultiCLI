#!/usr/bin/python
###########################################################################
# Description: MultiCLI Nokia SR OS Service Reports
# Commands: show service service-using, show service fdb mac,
#           show service id <id> fdb mac
# Copyright (c) 2026 Nokia
###########################################################################

import datetime
from srlinux.location import build_path
from srlinux.schema.data_store import DataStore

def _safe_get(obj, attr, default=None):
    try:
        val = getattr(obj, attr, default)
        return default if val is None else val
    except Exception:
        return default


def format_sros_age(dt_or_str):
    if not dt_or_str:
        return "00d00h00m"
    try:
        s = str(dt_or_str).split('(')[0].strip()
        if s.endswith('Z'):
            s = s[:-1] + '+00:00'
        dt = datetime.datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        delta = max(datetime.timedelta(0), datetime.datetime.now(datetime.timezone.utc) - dt)
        days = delta.days
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60
        return f"{days:02d}d{hours:02d}h{minutes:02d}m"
    except Exception:
        return "00d00h00m"


class SrosServiceReports:
    """Handles classic Nokia SR OS service and FDB show reports."""

    def show_service_using(self, state, output):
        """Display Nokia SR OS formatted 'show service service-using'."""
        output.print_line("=" * 79)
        output.print_line("Services [Customer: All]")
        output.print_line("=" * 79)
        output.print_line(f"{'ServiceId':<13}{'Type':<10}{'Adm':<5}{'Opr':<5}{'CustomerID':<12}{'Service Name'}")
        output.print_line("-" * 79)

        path = build_path('/network-instance[name=*]')
        services = []
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=False)
            svc_id = 1
            for ni in sorted(data.network_instance.items(), key=lambda x: str(x.name)):
                name = str(ni.name)
                ntype = _safe_get(ni, 'type', 'default')
                if ntype == 'default':
                    continue

                sros_type = "VPLS" if ntype == 'mac-vrf' else "VPRN"
                adm = "Up" if _safe_get(ni, 'admin_state', 'enable') == 'enable' else "Down"
                opr = "Up" if _safe_get(ni, 'oper_state', 'up') == 'up' else "Down"
                services.append((str(svc_id), sros_type, adm, opr, "NA", name))
                svc_id += 1
        except Exception:
            pass

        for sid, stype, adm, opr, cid, sname in services:
            output.print_line(f"{sid:<13}{stype:<10}{adm:<5}{opr:<5}{cid:<12}{sname}")

        output.print_line("-" * 79)
        output.print_line(f"Matching Services : {len(services)}")
        output.print_line("=" * 79)
        output.print_line("\nTry SR Linux command: show network-instance summary")

    def show_service_fdb_mac(self, state, output, service_name=None):
        """Display Nokia SR OS formatted 'show service fdb mac' or for specific service."""
        header_name = f"Service {service_name}" if service_name else "All Services"
        output.print_line("=" * 79)
        output.print_line(f"Forwarding Database, {header_name}")
        output.print_line("=" * 79)
        output.print_line(f"{'ServId':<10}{'MAC':<20}{'Source-Identifier':<25}{'Type':<9}{'Last Change'}")
        output.print_line(f"{'':<64}{'Age'}")
        output.print_line("-" * 79)

        # Map non-default network-instance names to sequential service IDs (consistent with show_service_using)
        ni_map = {}
        id_to_name = {}
        try:
            ni_data = state.server.get_data_store(DataStore.State).get_data(build_path('/network-instance[name=*]'), recursive=False)
            idx = 1
            for ni in sorted(ni_data.network_instance.items(), key=lambda x: str(x.name)):
                if _safe_get(ni, 'type', 'default') == 'default':
                    continue
                ni_name = str(ni.name)
                ni_map[ni_name] = str(idx)
                id_to_name[str(idx)] = ni_name
                idx += 1
        except Exception:
            pass

        if service_name and str(service_name) in id_to_name:
            target_ni = id_to_name[str(service_name)]
        else:
            target_ni = '*' if not service_name or service_name == '*' else service_name

        path = build_path(f'/network-instance[name={target_ni}]/bridge-table/mac-table/mac[address=*]')
        entries = []
        try:
            data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
            for ni in data.network_instance.items():
                cur_name = str(ni.name)
                sid = ni_map.get(cur_name, "1")
                bt = _safe_get(ni, 'bridge_table')
                if bt and hasattr(bt, 'get'):
                    bt_node = bt.get()
                    mt = _safe_get(bt_node, 'mac_table')
                    if mt and hasattr(mt, 'get'):
                        mt_node = mt.get()
                        mac_list = _safe_get(mt_node, 'mac')
                        if mac_list and hasattr(mac_list, 'items'):
                            for m in mac_list.items():
                                addr = str(_safe_get(m, 'address', '') or '')
                                if not addr:
                                    continue
                                dest = str(_safe_get(m, 'destination', '') or '--')
                                raw_type = str(_safe_get(m, 'type', 'learned') or 'learned').lower()
                                if 'learned' in raw_type or 'learnt' in raw_type or 'dynamic' in raw_type:
                                    mtype = "Learned"
                                elif 'evpn' in raw_type:
                                    mtype = "Evpn"
                                else:
                                    mtype = "Static"
                                lup = _safe_get(m, 'last_update', None)
                                age = format_sros_age(lup)
                                entries.append((sid, addr, dest, mtype, age))
        except Exception:
            pass

        for sid, addr, dest, mtype, age in entries:
            output.print_line(f"{sid:<10}{addr:<20}{dest:<25}{mtype:<9}{age}")

        output.print_line("-" * 79)
        output.print_line(f"No. of Entries in FDB: {len(entries)}")
        output.print_line("=" * 79)
        output.print_line("\nTry SR Linux command: show network-instance bridge-table mac-table all")
