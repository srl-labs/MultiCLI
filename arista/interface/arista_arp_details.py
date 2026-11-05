"""
Arista eos Interface Details
Author: Mohammad Zaman
Email: mohammad.zaman@nokia.com

This code is a plugin for SR Linux CLI that provides detailed information about physical network interfaces in Arista format,
        Arista command: show arp 
        SRLinux command: show arpnd arp-entries
        Current usage on SRLinux: show eos arp

        This plugin will be updated to exact Arista CLI in 25.3.2 and 24.10.4
"""

from srlinux import strings
from srlinux.data import ColumnFormatter, Data, Alignment, Formatter, print_line
from srlinux.data.utilities import Percentage
from srlinux.location import build_path
from srlinux.mgmt.cli.cli_plugin import CliPlugin
from srlinux.mgmt.cli.key_completer import KeyCompleter
from srlinux.schema import FixedSchemaRoot
from srlinux.schema.data_store import DataStore
from srlinux.syntax import Syntax
from datetime import datetime, timedelta

class ArpDetails(object):
    
    def _get_syntax_arp(self):        
        result = Syntax('arp', help='Show IPv4 arp entries report')
        result.add_named_argument('interface', default='*', suggestions=KeyCompleter(path=self._interface_path))
        result.add_named_argument('subinterface', default='*', suggestions=KeyCompleter(path=self._subinterface_path))
        result.add_named_argument('ipv4-address', default='*',
                                suggestions=KeyCompleter(path=lambda arguments: self._ipv4_address_path(arguments)))
        return result

    @staticmethod
    def _arista_to_srl_intf(name):
        if not name or name == '*':
            return '*', None
        import re
        s = str(name).strip()
        sub = None
        if '.' in s and not s.lower().startswith('vlan'):
            s, sub = s.split('.', 1)
        low = s.lower()
        m = re.match(r'^et(?:h(?:ernet)?)?[-_]?(\d+/\d+(?:/\d+)?)$', low)
        if m:
            return f"ethernet-{m.group(1)}", sub
        m = re.match(r'^po(?:rt-channel)?[-_]?(\d+)$', low)
        if m:
            return f"lag{m.group(1)}", sub
        m = re.match(r'^(?:ma(?:nagement)?|mgmt)[-_]?(\d+)$', low)
        if m:
            return "mgmt0", sub
        m = re.match(r'^lo(?:opback)?[-_]?(\d+)$', low)
        if m:
            return ("system0" if m.group(1) == "0" else f"lo{m.group(1)}"), sub
        m = re.match(r'^vl(?:an)?[-_]?(\d+)$', low)
        if m:
            return "irb0", m.group(1)
        if low == 'irb':
            return "irb0", sub
        return s, sub

    @staticmethod
    def _format_arista_intf(name, subindex=0):
        import re
        s = str(name or '')
        if s.startswith('irb'):
            if '.' in s:
                return s
            return f"{s}.{subindex}" if subindex is not None else s
        if s.endswith('.0'):
            s = s[:-2]
        m = re.match(r'^ethernet-(\d+)/(\d+)$', s)
        if m:
            base = f"Ethernet{m.group(1)}/{m.group(2)}"
        elif s.startswith('mgmt'):
            base = f"Management{s[4:] or '0'}"
        elif s.startswith('lag'):
            base = f"Port-Channel{s[3:]}"
        elif s.startswith('system') or s.startswith('lo'):
            idx = re.sub(r'^(?:system|lo)', '', s) or '0'
            base = f"Loopback{idx}"
        else:
            base = s
        if subindex and str(subindex) != '0':
            return f"{base}.{subindex}"
        return base

    def _get_arp_schema(self, v4):
        root = FixedSchemaRoot()
        if v4:
            root.add_child('neighbor',
                        keys=['Address'],
                        fields=['Age (sec)', 'Hardware Addr', 'Interface'])
        else:
            root.add_child('neighbor',
                        keys=['Subinterface', 'Age (sec)', 'Neighbor'],
                        fields=[
                            'Origin',
                            'Link layer address',
                            'Current state',
                            'Next state change',
                            'Is Router'
                        ])
        return root
    
    def _interface_path(self, arguments):
        return build_path('/interface[name=*]')

    def _subinterface_path(self, arguments):
        intf_name, _ = self._arista_to_srl_intf(arguments.get('interface'))
        return build_path(
            '/interface[name={name}]/subinterface[index=*]',
            name=intf_name)

    def _extract_arg(self, state, arguments, arg_name, default='*'):
        for src in (arguments, getattr(state, 'line_commands', None) if state else None):
            if not src:
                continue
            try:
                if hasattr(src, 'has_node') and src.has_node('arp'):
                    val = src.get_value_or('arp', arg_name, default)
                    if val and val != default:
                        return val
                if hasattr(src, 'has_node') and src.has_node(arg_name):
                    val = src.get_value_or(arg_name, arg_name, default)
                    if val and val != default:
                        return val
                    val = src.get_value_or(arg_name, 'name', default)
                    if val and val != default:
                        return val
                if hasattr(src, 'get_value_or'):
                    val = src.get_value_or(arg_name, arg_name, default)
                    if val and val != default:
                        return val
                if hasattr(src, 'get'):
                    val = src.get(arg_name)
                    if val and val != default:
                        return val
            except Exception:
                pass
        return default

    def _ipv4_address_path(self, arguments, wildcard=True, state=None):
        raw_intf = getattr(self, 'interface', None) or self._extract_arg(state, arguments, 'interface', '*')
        intf_name, implied_sub = self._arista_to_srl_intf(raw_intf)
        sub_idx = self._extract_arg(state, arguments, 'subinterface', '*')
        if (not sub_idx or sub_idx == '*') and implied_sub is not None:
            sub_idx = implied_sub
        addr = '*' if wildcard else self._extract_arg(state, arguments, 'ipv4-address', '*')
        return build_path(
            '/interface[name={name}]/subinterface[index={index}]/ipv4/arp/neighbor[ipv4-address={address}]',
            name=intf_name,
            index=sub_idx,
            address=addr
        )

    def _ipv6_address_path(self, arguments, wildcard=True, state=None):
        raw_intf = getattr(self, 'interface', None) or self._extract_arg(state, arguments, 'interface', '*')
        intf_name, implied_sub = self._arista_to_srl_intf(raw_intf)
        sub_idx = self._extract_arg(state, arguments, 'subinterface', '*')
        if (not sub_idx or sub_idx == '*') and implied_sub is not None:
            sub_idx = implied_sub
        addr = '*' if wildcard else self._extract_arg(state, arguments, 'ipv6-address', '*')
        return build_path(
            '/interface[name={name}]/subinterface[index={index}]/ipv6/neighbor-discovery/neighbor[ipv6-address={address}]',
            name=intf_name,
            index=sub_idx,
            address=addr
        )

    def _fetch_state(self, state, arguments, v4):
        self.interface = self._extract_arg(state, arguments, 'interface', '*')
        path = self._ipv4_address_path(
            arguments, False, state=state) if v4 else self._ipv6_address_path(arguments, False, state=state)

        return state.server.get_data_store(DataStore.State).stream_data(path, recursive=True)

    def _init_members(self):
        self._total_entries = 0
        self._static_entries = 0
        self._dynamic_entries = 0

    def _populate_data(self, data, server_data, v4):
        self._init_members()
        data.synchronizer.flush_fields(data)

        for interface in server_data.interface.items():
            self._add_subinterface(data, interface.name,
                                   interface.subinterface, v4)

        data.synchronizer.flush_children(data.neighbor)
        return data
    
    def _add_subinterface(self, data, interface_name, server_data, v4):
        if not server_data:
            return
        for subinterface in server_data.items():
            neighbor_data = None
            timeout_val = 14400
            try:
                if v4:
                    ipv4 = subinterface.ipv4.get() if hasattr(subinterface, 'ipv4') else None
                    arp = ipv4.arp.get() if ipv4 and hasattr(ipv4, 'arp') else None
                    if arp:
                        timeout_val = getattr(arp, 'timeout', 14400) or 14400
                    neighbor_data = arp.neighbor if arp and hasattr(arp, 'neighbor') else None
                else:
                    ipv6 = subinterface.ipv6.get() if hasattr(subinterface, 'ipv6') else None
                    nd = ipv6.neighbor_discovery.get() if ipv6 and hasattr(ipv6, 'neighbor_discovery') else None
                    neighbor_data = nd.neighbor if nd and hasattr(nd, 'neighbor') else None
            except Exception:
                neighbor_data = None
            if neighbor_data:
                self._add_neighbor(data, interface_name, subinterface.index, neighbor_data, v4, timeout_val=timeout_val)
    
    @staticmethod
    def convert_mac(mac):
            if not mac:
                return ""
            mac = str(mac).replace(":", "").replace("-", "").lower()
            if len(mac) != 12:
                return mac
            return f"{mac[0:4]}.{mac[4:8]}.{mac[8:12]}"

    @staticmethod
    def convert_iso_to_hms(iso_time_str, timeout_val=14400):
        if not iso_time_str:
            return "-"
        try:
            from datetime import timezone
            ts_str = str(iso_time_str).split('(')[0].strip()
            if ts_str.endswith("Z"):
                ts_str = ts_str[:-1] + "+00:00"
            exp_dt = datetime.fromisoformat(ts_str)
            now = datetime.now(timezone.utc)
            rem_seconds = (exp_dt - now).total_seconds()
            age_sec = max(0, int((timeout_val or 14400) - rem_seconds))
            hours, rem = divmod(age_sec, 3600)
            minutes, seconds = divmod(rem, 60)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        except Exception:
            return str(iso_time_str)

    def _add_neighbor(self, data, interface_name, subinterface_index, server_data, v4, timeout_val=14400):   
        if not server_data:
            return
        for neighbor in server_data.items():
            if not neighbor:
                continue
            if v4:
                # Create the neighbor row using the new schema.
                child = data.neighbor.create(neighbor.ipv4_address)
                self._total_entries += 1

                # Compute the "Age (sec)" as elapsed time string (or '-' for static entries).
                origin = str(getattr(neighbor, 'origin', 'dynamic') or 'dynamic').lower()
                expiration_time = getattr(neighbor, 'expiration_time', None)
                if origin == 'static' or not expiration_time:
                    child.age__sec_ = '-'
                else:
                    child.age__sec_ = self.convert_iso_to_hms(expiration_time, timeout_val=timeout_val)
                # The "Hardware Addr" column.
                hw_addr = getattr(neighbor, 'link_layer_address', '')
                child.hardware_addr = self.convert_mac(hw_addr) if hw_addr else ''
                child.interface = self._format_arista_intf(interface_name, subinterface_index)
                child.synchronizer.flush_fields(child)
            else:
                child = data.neighbor.create(interface_name, subinterface_index, neighbor.ipv6_address)
                self._total_entries += 1
                expiration_time = getattr(neighbor, 'next_state_time', None)
                time_remaining = strings.natural_relative_time(expiration_time) if expiration_time else None
                child.link_layer_address = getattr(neighbor, 'link_layer_address', '')
                child.next_state_change = time_remaining
                child.current_state = getattr(neighbor, 'current_state', '')
                child.is_router = getattr(neighbor, 'is_router', False)
                child.synchronizer.flush_fields(child)

    
    def _set_formatters(self, data, v4):
        if v4:
            data.set_formatter('/neighbor',
                            ColumnFormatter(ancestor_keys=True,
                                            borders=0,
                                            widths=[15, 10, 15, 20],
                                            horizontal_alignment={
                                                'Address': Alignment.Left,
                                                'Age (sec)': Alignment.Center,
                                                'Hardware Addr': Alignment.Center,
                                                'Interface': Alignment.Center,
                },
                                            )
                            )
        else:
            ip_length = 39
            column_widths = [
                Percentage(10),
                ip_length,
                Percentage(10),
                Percentage(20),
            ]
            if not v4:
                column_widths.extend([Percentage(10), Percentage(20), Percentage(10)])
            data.set_formatter('/neighbor',
                            ColumnFormatter(ancestor_keys=True,
                                            borders=0,
                                            widths=column_widths,
                                            horizontal_alignment={
                                                'Subinterface': Alignment.Right,
                                                'Neighbor': Alignment.Right,
                                                'Age (sec)': Alignment.Right
                                            }
                                            )
                            )

    def _ipv4_variant(self, arguments):
        return arguments.node.name == 'arp'

    def print(self, state, arguments, output, **_kwargs): 
        v4 = self._ipv4_variant(arguments)
        server_data = self._fetch_state(state, arguments, v4)
        result = Data(arguments.schema)
        self._set_formatters(result, v4)

        with output.stream_data(result):
            self._populate_data(result, server_data, v4)


class SummaryFormatter(Formatter):

    def iter_format(self, entry, max_width):
        yield print_line(max_width, '-')
        yield from self._format_entry(entry, max_width)
        yield print_line(max_width, '-')

    def _format_entry(self, entry, max_width):
        yield f'  Total entries : {entry.total_entries} ({entry.static_entries} static, {entry.dynamic_entries} dynamic)'
