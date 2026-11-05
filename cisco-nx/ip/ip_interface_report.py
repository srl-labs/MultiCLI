"""
CLI Plugin for SR Linux for Cisco-style IP Interface Command
Provides alternate command syntax for interface information
Author: Alperen Akpinar
Email: alperen.akpinar@nokia.com
"""
import os
import re
import sys
from srlinux.location import build_path
from srlinux.schema.data_store import DataStore

# Add interface directory to sys.path if not present
interface_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'interface'))
if interface_dir not in sys.path:
    sys.path.insert(0, interface_dir)

try:
    from cisco_interface_reports import format_cisco_intf, cisco_intf_sort_key
except ImportError:
    def format_cisco_intf(name, short=True):
        if not name:
            return "-"
        name = str(name).strip()
        if name.startswith('ethernet-'):
            num = name.split('-', 1)[1]
            return f"Eth{num}" if short else f"Ethernet{num}"
        elif name.startswith('mgmt'):
            return name
        elif name.startswith('system0'):
            return "Lo0" if short else "Loopback0"
        elif name.startswith('lo'):
            num = name[2:]
            return f"Lo{num}" if short else f"Loopback{num}"
        elif name.startswith('lag'):
            num = name.split('lag', 1)[1]
            return f"Po{num}" if short else f"Port-channel{num}"
        elif name.startswith('irb'):
            return name
        elif name.startswith('vlan'):
            num = re.split(r'vlan', name)[-1]
            return f"Vlan{num}"
        return name

    def cisco_intf_sort_key(name):
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
        return (type_priority, digits or [0], lower)


class IpInterfaceReport:
    def _fetch_state(self, state):
        interface_path = build_path('/interface[name=*]')
        self.interface_data = state.server.get_data_store(DataStore.State).get_data(interface_path, recursive=True)

        ni_path = build_path('/network-instance[name=*]/interface[name=*]')
        self.ni_data = state.server.get_data_store(DataStore.State).get_data(ni_path, recursive=True)

    def _get_interface_vrf(self, interface_name):
        normalized_name = interface_name.replace('Ethernet', 'ethernet-')
        if not hasattr(self.ni_data, 'network_instance'):
            return ""
        for ni in self.ni_data.network_instance.items():
            if hasattr(ni, 'interface'):
                for intf in ni.interface.items():
                    if intf.name == normalized_name or intf.name.startswith(normalized_name + '.'):
                        return ni.name
        return ""

    def _format_interface_name(self, base_name, subindex=None):
        if base_name.startswith('ethernet-'):
            name = f"Ethernet{base_name[9:]}"
        elif base_name.startswith('lo'):
            name = f"Loopback{base_name[2:]}"
        elif base_name.startswith('vlan'):
            name = f"Vlan{base_name[4:]}"
        else:
            name = base_name

        if subindex is not None and subindex != 0:
            return f"{name}.{subindex}"
        return name

    def show_ip_interface_brief(self, state, output, vrf='default'):
        """Display Cisco NX-OS style 'show ip interface brief'."""
        self._fetch_state(state)
        vrf_id = 1
        if vrf != 'default':
            try:
                ni_list = list(self.ni_data.network_instance.items())
                for idx, ni in enumerate(ni_list, 1):
                    if getattr(ni, 'name', '') == vrf:
                        vrf_id = idx
                        break
            except Exception:
                vrf_id = 1

        lines = [
            f'IP Interface Status for VRF "{vrf}"({vrf_id})',
            f"{'Interface':<20} {'IP Address':<15} {'Interface Status'}"
        ]

        entries = []
        for interface in self.interface_data.interface.items():
            base_name = interface.name
            if hasattr(interface, 'subinterface'):
                for subif in interface.subinterface.items():
                    sub_idx = subif.index
                    intf_name = self._format_interface_name(base_name, sub_idx)
                    intf_vrf = self._get_interface_vrf(intf_name) or "default"
                    if intf_vrf != vrf:
                        continue

                    ip_address = ""
                    if hasattr(subif, 'ipv4') and subif.ipv4.exists():
                        try:
                            for addr in subif.ipv4.get().address.items():
                                pfx = getattr(addr, 'ip_prefix', '')
                                if pfx:
                                    ip_address = pfx.split('/')[0]
                                    break
                        except Exception:
                            pass

                    if not ip_address:
                        continue

                    admin = getattr(subif, 'admin_state', 'disable')
                    oper = getattr(subif, 'oper_state', 'down')
                    proto_str = "proto-up" if oper == "up" else "proto-down"
                    link_str = "link-up" if oper == "up" else "link-down"
                    admin_str = "admin-up" if admin == "enable" else "admin-down"
                    status_str = f"{proto_str}/{link_str}/{admin_str}"

                    short_name = format_cisco_intf(intf_name, short=True)
                    entries.append({
                        'name': short_name,
                        'ip': ip_address,
                        'status': status_str
                    })

        entries.sort(key=lambda e: cisco_intf_sort_key(e['name']))
        for e in entries:
            lines.append(f"{e['name']:<20} {e['ip']:<15} {e['status']}")

        output.print_line("\n".join(lines))
        output.print_line("\n----------------------------------------------------------------------------------------------------")
        output.print_line("Try SR Linux command: srl show interface brief")