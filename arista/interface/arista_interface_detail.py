"""
Arista eos Interface Details
Author: Mohammad Zaman
Email: mohammad.zaman@nokia.com

This code is a plugin for SR Linux CLI that provides detailed information about physical network interfaces in Arista format,
        Arista command: show interface {interface_name}
        SRLinux command: show interface {interface_name} detail
        Current usage on SRLinux: show eos interface detail

        This plugin will be updated to exact Arista CLI in 25.3.2 and 24.10.4
"""

from srlinux.mgmt.cli import CliPlugin, KeyCompleter, MultipleKeyCompleters
from srlinux.syntax import Syntax
from srlinux.schema import FixedSchemaRoot
from srlinux.schema.data_store import DataStore
from srlinux.location import build_path
from srlinux import strings
from srlinux.data import Border, ColumnFormatter, TagValueFormatter, Borders, Data, Indent
from srlinux.syntax.value_checkers import IntegerValueInRangeChecker
import json
from jinja2 import Template
from datetime import datetime, timezone


class InterfaceDetails(object):
    
    def get_syntax_details(self):
        result = Syntax('interface', help='Show interface report')
        result.add_unnamed_argument(
            'name', default='*', suggestions=MultipleKeyCompleters(keycompleters=[KeyCompleter(path="/interface[name=*]")]))
        return result


    def _timedelta_str(self, timestamp):
        try:
            ts_str = str(timestamp).replace("Z", "+00:00")
            last_chg_time = datetime.fromisoformat(ts_str)
            now = datetime.now(timezone.utc) if last_chg_time.tzinfo else datetime.utcnow()
            diff = now - last_chg_time
            seconds = max(0, int(diff.total_seconds()))
        except Exception:
            return "never"

        days, seconds = divmod(seconds, 86400)
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)

        time_parts = []
        if days > 0:
            time_parts.append(f"{days} days")
        if hours > 0:
            time_parts.append(f"{hours} hours")
        if minutes > 0:
            time_parts.append(f"{minutes} minutes")
        if seconds > 0 or not time_parts:
            time_parts.append(f"{seconds} seconds")

        return ", ".join(time_parts)
    
    def _build_last_change_string(self, last_change):
        str_time = self._timedelta_str(last_change)
        return f'{str_time}'
    
    def convert_mac(self, mac):
        try:
            if not mac or not isinstance(mac, str):
                raise ValueError("Invalid MAC address provided")

            mac = mac.replace(":", "").replace("-", "").lower()

            if len(mac) != 12:
                return mac

            return f"{mac[0:4]}.{mac[4:8]}.{mac[8:12]}"

        except Exception as e:
            return None
    
    def convert_speed_to_bps(self, speed):
        try:
            if not speed or not isinstance(speed, str):
                raise ValueError("Invalid speed value provided")

            number = float(speed.rstrip('GMKTbps '))  # Remove G/M/K/T suffixes
            unit = speed.strip()[-1].upper()

            if unit == 'T':
                return int(number * 1_000_000_000_000)
            elif unit == 'G':
                return int(number * 1_000_000_000)
            elif unit == 'M':
                return int(number * 1_000_000)
            elif unit == 'K':
                return int(number * 1_000)
            else:
                return int(number)

        except Exception:
            return None

    def convert_speed_to_kbit(self, speed):
        try:
            if not speed or not isinstance(speed, str):
                raise ValueError("Invalid speed value provided")
            clean_speed = speed.strip()
            unit = clean_speed[-1].upper()
            num_str = clean_speed[:-1] if unit in {'T', 'G', 'M', 'K'} else clean_speed
            number = float(num_str)
            multipliers = {
                'T': 1_000_000_000,
                'G': 1_000_000,
                'M': 1_000,
                'K': 1,
            }
            mult = multipliers.get(unit, 1_000_000)
            return int(number * mult)
        except Exception:
            return 100_000_000


                
                
    def calculate_utilization(self, traffic_rate, port_speed):
        if traffic_rate is None:
            # print("Warning: traffic_rate is None, setting to 0")
            traffic_rate = 0.0
        if port_speed is None:
            # print("Warning: port_speed is None, setting to 1 to avoid division by zero")
            port_speed = "1G"  # Default to avoid division by zero
        
        traffic_rate_bps = float(traffic_rate)  
        port_speed_bps = self.convert_speed_to_bps(port_speed)  

        if not port_speed_bps:
            return 0.0

        utilization = (traffic_rate_bps / port_speed_bps) * 100
        return round(utilization, 2)
    

    def _safe_get(self, obj, attr, default=None):
        try:
            val = getattr(obj, attr, default)
            return default if val is None else val
        except Exception:
            return default

    @staticmethod
    def _arista_to_srl_intf(name):
        if not name or name == '*':
            return '*'
        import re
        s = str(name).strip()
        if '.' in s and not s.lower().startswith('vlan'):
            s = s.split('.', 1)[0]
        low = s.lower()
        m = re.match(r'^et(?:h(?:ernet)?)?[-_]?(\d+/\d+(?:/\d+)?)$', low)
        if m:
            return f"ethernet-{m.group(1)}"
        m = re.match(r'^po(?:rt-channel)?[-_]?(\d+)$', low)
        if m:
            return f"lag{m.group(1)}"
        m = re.match(r'^(?:ma(?:nagement)?|mgmt)[-_]?(\d+)$', low)
        if m:
            return "mgmt0"
        m = re.match(r'^lo(?:opback)?[-_]?(\d+)$', low)
        if m:
            return "system0" if m.group(1) == "0" else f"lo{m.group(1)}"
        m = re.match(r'^vl(?:an)?[-_]?(\d+)$', low)
        if m:
            return "irb0"
        if low == 'irb':
            return "irb0"
        return s

    def _fetch_state(self, state, arguments, output):
        interface_name = '*'
        for src in (arguments, getattr(state, 'line_commands', None)):
            if not src or not hasattr(src, 'has_node'):
                continue
            try:
                if src.has_node('interfaces'):
                    val = src.get_value_or('interfaces', 'name', '*')
                    if val and val != '*':
                        interface_name = val
                        break
                if src.has_node('interface'):
                    val = src.get_value_or('interface', 'name', '*')
                    if val and val != '*':
                        interface_name = val
                        break
            except Exception:
                pass

        srl_intf_name = self._arista_to_srl_intf(interface_name)
        path = build_path('/interface[name={name}]', name=srl_intf_name)
        my_data = state.server.get_data_store(DataStore.State).get_data(path, recursive=True, include_container_children=True)

        for intf in my_data.interface.items():
            interface_name = intf.name
            raw_lower = str(interface_name).lower()
            is_eth = hasattr(intf, 'ethernet') and intf.ethernet.exists()
            is_lag = raw_lower.startswith('lag')
            is_loop = raw_lower.startswith('system') or raw_lower.startswith('lo')
            is_irb = raw_lower.startswith('irb')

            admin_status = self._safe_get(intf, 'admin_state', 'disable')
            oper_status = self._safe_get(intf, 'oper_state', 'down')
            if admin_status == "enable":
                line_protocol_status = "up" if oper_status == "up" else "down"
            else:
                line_protocol_status = "down"
            if oper_status == "up":
                connection_status = "connected"
            else:
                connection_status = "notconnected"
            raw_mac_address = ""
            if is_eth:
                raw_mac_address = self._safe_get(intf.ethernet.get(), 'hw_mac_address', '')
            mac_address = self.convert_mac(raw_mac_address) or "0000.0000.0000"
            bia_address = mac_address
            mtu = self._safe_get(intf, 'mtu', None)
            if mtu is None:
                if hasattr(intf, 'subinterface'):
                    for sub in intf.subinterface.items():
                        sub_mtu = self._safe_get(sub, 'ip_mtu', None) or self._safe_get(sub, 'l2_mtu', None)
                        if sub_mtu:
                            mtu = sub_mtu
                            break
                if mtu is None:
                    mtu = 1500 if (is_loop or is_irb or raw_lower.startswith('mgmt')) else 9232

            ip_addr = None
            if hasattr(intf, 'subinterface'):
                for sub in intf.subinterface.items():
                    if hasattr(sub, 'ipv4') and sub.ipv4.exists():
                        v4_obj = sub.ipv4.get()
                        if hasattr(v4_obj, 'address'):
                            for a in v4_obj.address.items():
                                pfx = self._safe_get(a, 'ip_prefix', None)
                                if pfx:
                                    ip_addr = str(pfx)
                                    break
                    if ip_addr:
                        break

            # Determine hardware type, speed, bandwidth, duplex dynamically
            hardware_type = "Ethernet"
            port_speed = None
            bandwidth = 0
            duplex = "Full"
            auto_negotiation = "off"
            show_phys_line = False

            if is_loop:
                hardware_type = "Loopback"
                bandwidth = 8000000
            elif is_irb:
                hardware_type = "VLAN"
                bandwidth = 1000000
            elif is_lag:
                hardware_type = "Port-Channel"
                show_phys_line = True
                if hasattr(intf, 'lag') and intf.lag.exists():
                    lag_spd = self._safe_get(intf.lag.get(), 'lag_speed', None)
                    if lag_spd is not None:
                        try:
                            spd_mbps = int(lag_spd)
                            bandwidth = spd_mbps * 1000
                            port_speed = f"{spd_mbps // 1000}G" if spd_mbps >= 1000 else f"{spd_mbps}M"
                        except Exception:
                            pass
                if not port_speed:
                    port_speed = "0G"
            else:
                hardware_type = "Ethernet"
                show_phys_line = True
                try:
                    if is_eth:
                        eth_obj = intf.ethernet.get()
                        port_speed = self._safe_get(eth_obj, 'port_speed', None)
                        duplex = self._safe_get(eth_obj, 'duplex_mode', 'Full') or 'Full'
                        an = self._safe_get(eth_obj, 'auto_negotiate', None)
                        if an is True or an == 'true' or an == 'enable':
                            auto_negotiation = "on"
                    if port_speed and isinstance(port_speed, str):
                        bandwidth = self.convert_speed_to_kbit(port_speed)
                    else:
                        port_speed = "1G" if raw_lower.startswith('mgmt') else "Unknown"
                        bandwidth = 1000000 if raw_lower.startswith('mgmt') else 0
                except Exception:
                    port_speed = "Unknown"
                    bandwidth = 0

            #calculating the uptime
            last_change_val = self._safe_get(intf, 'last_change', None)
            if oper_status == "up" and last_change_val:
                uptime = self._build_last_change_string(last_change_val)
            else:
                uptime = "never"
            loopback_mode = self._safe_get(intf, 'loopback_mode', 'None')
            link_changes = 0
            input_packets = 0
            input_bytes = 0
            received_broadcasts = 0
            received_multicast = 0
            input_errors = 0
            input_discards = 0
            output_packets = 0
            output_bytes = 0
            sent_broadcasts = 0
            sent_multicast = 0
            output_errors = 0
            output_discards = 0
            if hasattr(intf, 'statistics') and intf.statistics.exists():
                stats = intf.statistics.get()
                link_changes = self._safe_get(stats, 'carrier_transitions', 0)
                input_packets = self._safe_get(stats, 'in_packets', 0)
                input_bytes = self._safe_get(stats, 'in_octets', 0)
                received_broadcasts = self._safe_get(stats, 'in_broadcast_packets', 0)
                received_multicast = self._safe_get(stats, 'in_multicast_packets', 0)
                input_errors = self._safe_get(stats, 'in_error_packets', 0)
                input_discards = self._safe_get(stats, 'in_discarded_packets', 0)
                output_packets = self._safe_get(stats, 'out_packets', 0)
                output_bytes = self._safe_get(stats, 'out_octets', 0)
                sent_broadcasts = self._safe_get(stats, 'out_broadcast_packets', 0)
                sent_multicast = self._safe_get(stats, 'out_multicast_packets', 0)
                output_errors = self._safe_get(stats, 'out_error_packets', 0)
                output_discards = self._safe_get(stats, 'out_discarded_packets', 0)

            runts = 0
            giants = 0
            crc_errors = 0
            pause_input = 0
            pause_output = 0
            if is_eth:
                eth_obj = intf.ethernet.get()
                if hasattr(eth_obj, 'statistics') and eth_obj.statistics.exists():
                    eth_stats = eth_obj.statistics.get()
                    runts = self._safe_get(eth_stats, 'in_undersize_frames', None)
                    if runts is None:
                        runts = self._safe_get(eth_stats, 'in_fragment_frames', 0)
                    giants = self._safe_get(eth_stats, 'in_oversize_frames', 0)
                    crc_errors = self._safe_get(eth_stats, 'in_crc_error_frames', 0)
                    pause_input = self._safe_get(eth_stats, 'in_mac_pause_frames', 0)
                    pause_output = self._safe_get(eth_stats, 'out_mac_pause_frames', 0)
            input_rate = 0
            output_rate = 0
            if hasattr(intf, 'traffic_rate') and intf.traffic_rate.exists():
                tr = intf.traffic_rate.get()
                input_rate = self._safe_get(tr, 'in_bps', 0)
                output_rate = self._safe_get(tr, 'out_bps', 0)
            input_utilization = self.calculate_utilization(input_rate, port_speed)
            output_utilization = self.calculate_utilization(output_rate, port_speed)

            template_string = """
{{ interface_name }} is {{ oper_status }}, line protocol is {{ line_protocol_status }} ({{ connection_status }})
{%- if hardware == 'Loopback' %}
  Hardware is {{ hardware }}
{%- else %}
  Hardware is {{ hardware }}, address is {{ mac_address }} (bia {{ bia_address }})
{%- endif %}
{%- if ip_addr %}
  Internet address is {{ ip_addr }}
{%- endif %}
  {{ mtu_label }} MTU {{ mtu }} bytes, BW {{ bandwidth }} kbit
{%- if show_phys_line %}
  {{ duplex }}-duplex, {{ speed }}, auto negotiation: {{ auto_negotiation }}
{%- endif %}
  Up {{ uptime }}
  Loopback Mode : {{ loopback_mode }}
  {{ link_changes }} link status changes since last clear
  Last clearing of "show interface" counters {{ last_clearing }}
  1 second input rate {{ input_rate }} bps ({{ input_utilization }}% with framing overhead)
  1 second output rate {{ output_rate }} bps ({{ output_utilization }}% with framing overhead)
    {{ input_packets }} packets input, {{ input_bytes }} bytes
    Received {{ received_broadcasts }} broadcasts, {{ received_multicast }} multicast
    {{ runts }} runts, {{ giants }} giants
    {{ input_errors }} input errors, {{ crc_errors }} CRC, {{ alignment_errors }} alignment, {{ symbol_errors }} symbol, {{ input_discards }} input discards
    {{ pause_input }} PAUSE input
    {{ output_packets }} packets output, {{ output_bytes }} bytes
    Sent {{ sent_broadcasts }} broadcasts, {{ sent_multicast }} multicast
    {{ output_errors }} output errors, {{ collisions }} collisions
    {{ late_collisions }} late collision, {{ deferred }} deferred, {{ output_discards }} output discards
    {{ pause_output }} PAUSE output"""

            data = {
            "interface_name": interface_name,
            "oper_status": oper_status,
            "line_protocol_status": line_protocol_status,
            "connection_status": connection_status,
            "hardware": hardware_type,
            "mac_address": mac_address,
            "bia_address": bia_address,
            "ip_addr": ip_addr,
            "mtu_label": "IP" if (is_loop or is_irb) else "Ethernet",
            "mtu": mtu,
            "bandwidth": bandwidth,
            "show_phys_line": show_phys_line,
            "duplex": duplex,
            "speed": port_speed,
            "auto_negotiation": auto_negotiation,
            "uptime": uptime,
            "loopback_mode": loopback_mode,
            "link_changes": link_changes,
            "last_clearing": uptime,
            "input_rate": input_rate,
            "input_utilization": input_utilization,
            "output_rate": output_rate,
            "output_utilization": output_utilization,
            "input_packets": input_packets,
            "input_bytes": input_bytes,
            "received_broadcasts": received_broadcasts,
            "received_multicast": received_multicast,
            "runts": runts,
            "giants": giants,
            "input_errors": input_errors,
            "crc_errors": crc_errors,
            "alignment_errors": 0,
            "symbol_errors": 0,
            "input_discards": input_discards,
            "pause_input": pause_input,
            "output_packets": output_packets,
            "output_bytes": output_bytes,
            "sent_broadcasts": sent_broadcasts,
            "sent_multicast": sent_multicast,
            "output_errors": output_errors,
            "collisions": 0,
            "late_collisions": 0,
            "deferred": 0,
            "output_discards": output_discards,
            "pause_output": pause_output,
            }

            template = Template(template_string)
            rendered = template.render(data)
            output.print_line(rendered)

        return my_data
   
    def print(self, state, arguments, output, **_kwargs):
        self._fetch_state(state, arguments, output)
        