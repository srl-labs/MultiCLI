"""
Extreme slx Interface Details

This code is a plugin for SR Linux CLI that provides detailed information about physical network interfaces in Extreme format,
        Extreme command: show interface {interface_name}
        SRLinux command: show interface {interface_name} detail
        Current usage on SRLinux: show slx interface detail
"""

from srlinux.mgmt.cli import CliPlugin, KeyCompleter, MultipleKeyCompleters
from srlinux.syntax import Syntax
from srlinux.schema import FixedSchemaRoot
from srlinux.location import build_path
from srlinux import strings
from srlinux.data import Border, ColumnFormatter, TagValueFormatter, Borders, Data, Indent
from srlinux.syntax.value_checkers import IntegerValueInRangeChecker
import json
from jinja2 import Template
from datetime import datetime


class InterfaceDetails(object):
    
    def get_syntax_details(self):
        result = Syntax('interface', help='Show interface report')
        result.add_unnamed_argument(
            'name', default='*', suggestions=MultipleKeyCompleters(keycompleters=[KeyCompleter(path="/interface[name=*]")]))
        return result


    def _timedelta_str(self, timestamp):
        last_chg_time = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
        diff = datetime.utcnow() - last_chg_time
        seconds = int(diff.total_seconds())

        days, seconds = divmod(seconds, 86400)
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)

        time_parts = []
        if days > 0:
            time_parts.append(f"{days}d")
        if hours > 0:
            time_parts.append(f"{hours}h")
        if minutes > 0:
            time_parts.append(f"{minutes}m")

        return "".join(time_parts)
    
    def _build_last_change_string(self, last_change):
        str_time = self._timedelta_str(last_change)
        return f'{str_time}'
    
    def convert_mac(self, mac):
        try:
            if not mac or not isinstance(mac, str):
                raise ValueError("Invalid MAC address provided")

            print(mac)
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

            number = float(speed.rstrip('GMK'))  # Remove G/M/K suffixes
            unit = speed[-1]

            if unit == 'G':
                return int(number * 1_000_000_000)
            elif unit == 'M':
                return int(number * 1_000_000)
            elif unit == 'K':
                return int(number * 1_000)
            else:
                return int(number)

        except Exception as e:
            print(f"Error converting speed '{speed}' to bps: {e}")
            return None


                
                
    def calculate_utilization(self, traffic_rate, port_speed):
        if traffic_rate is None:
            # print("Warning: traffic_rate is None, setting to 0")
            traffic_rate = 0.0
        if port_speed is None:
            # print("Warning: port_speed is None, setting to 1 to avoid division by zero")
            port_speed = "1G"  # Default to avoid division by zero
        
        traffic_rate_bps = float(traffic_rate)  
        port_speed_bps = self.convert_speed_to_bps(port_speed)  

        if port_speed_bps == 0:
            return 0.0

        utilization = (traffic_rate_bps / port_speed_bps) * 100
        return round(utilization, 2)
    

    def _fetch_state(self, state, arguments):
        interface_name = arguments.get('interface', 'name')

        path = build_path('/interface[name={name}]', name=interface_name) 
        my_data = state.server_data_store.get_data(path, recursive=True, include_container_children=True)

        for intf in my_data.interface.items():
            interface_name = intf.name
            admin_status = getattr(intf, 'admin_state', 'disable')
            oper_status = getattr(intf, 'oper_state', 'down')
            if admin_status == "enable":
                line_protocol_status = "up" if oper_status == "up" else "down"
            else:
                line_protocol_status = "down"
            line_protocol_status = line_protocol_status
            if oper_status == "up":
                connection_status = "connected"
            else:
                connection_status = "notconnected"
            connection_status = connection_status
            # hardware = intf.hardware
            raw_mac_address = intf.ethernet.get().hw_mac_address
            mac_address = self.convert_mac(raw_mac_address)
            bia_address = mac_address
            mtu = intf.mtu
            #bandwidth calculation with exception handling
            try:
                port_speed = intf.ethernet.get().port_speed
                if not port_speed or not isinstance(port_speed, str):
                    raise ValueError("Invalid or missing port speed")

                bandwidth = int(port_speed.rstrip("G")) * 1_000_000

            except Exception as e:
                print(f"Error calculating bandwidth from port speed: {e}")
                bandwidth = None
            try:
                duplex = intf.ethernet.get().duplex_mode
            except:
                duplex = "Full"
            port_speed = intf.ethernet.get().port_speed
            auto_negotiation = "on"
            uni_link = "disabled"
            #calculating the uptime
            if oper_status == "up":
                uptime = self._build_last_change_string(intf.last_change)
            else:
                uptime = "00"
            loopback_mode = intf.loopback_mode
            link_changes = intf.statistics.get().carrier_transitions
            input_packets = intf.statistics.get().in_packets
            input_bytes = intf.statistics.get().in_octets
            received_broadcasts = intf.statistics.get().in_broadcast_packets
            received_multicast = intf.statistics.get().in_multicast_packets
            giants = intf.ethernet.get().statistics.get().in_oversize_frames
            input_errors = intf.statistics.get().in_error_packets
            crc_errors = intf.ethernet.get().statistics.get().in_crc_error_frames
            #alignment_errors = intf.statistics.get().in_alignment_error_frames
            #symbol_errors = intf.statistics.get().in_symbol_error_frames
            input_discards = intf.statistics.get().in_discarded_packets
            pause_input = intf.ethernet.get().statistics.get().in_mac_pause_frames
            output_packets = intf.statistics.get().out_packets
            output_bytes = intf.statistics.get().out_octets
            sent_broadcasts = intf.statistics.get().out_broadcast_packets
            sent_multicast = intf.statistics.get().out_multicast_packets
            output_errors = intf.statistics.get().out_error_packets
            #collisions = intf.statistics.get().out_collision_packets
            #late_collisions = intf.statistics.get().out_late_collision_packets
            #deferred = intf.statistics.get().out_deferred_packets
            output_discards = intf.statistics.get().out_discarded_packets
            pause_output = getattr(getattr(getattr(intf.ethernet.get(), 'statistics', None), 'get', lambda: None)(), 'out_mac_pause_frames', None) or 0
            input_rate_bps = intf.traffic_rate.get().in_bps
            output_rate_bps = intf.traffic_rate.get().out_bps
            input_utilization = self.calculate_utilization(input_rate_bps, port_speed)
            output_utilization = self.calculate_utilization(output_rate_bps, port_speed)
            # Convert bps to Mbps for display
            input_rate_mbps = input_rate_bps / 1_000_000
            output_rate_mbps = output_rate_bps / 1_000_000
            input_65b_to_127b_frames = intf.ethernet.get().statistics.get().in_65b_to_127b_frames
            input_128b_to_255b_frames = intf.ethernet.get().statistics.get().in_128b_to_255b_frames
            input_256b_to_511b_frames = intf.ethernet.get().statistics.get().in_256b_to_511b_frames
            input_512b_to_1023b_frames = intf.ethernet.get().statistics.get().in_512b_to_1023b_frames
            input_1024b_to_1518b_frames = intf.ethernet.get().statistics.get().in_1024b_to_1518b_frames
            input_oversized_frames = intf.ethernet.get().statistics.get().in_oversize_frames
            input_64b_frames = intf.ethernet.get().statistics.get().in_64b_frames
            input_jabber_frames = intf.ethernet.get().statistics.get().in_jabber_frames
            ifindex = intf.ifindex
            last_change = intf.last_change
            

            template_string = """
{{ interface_name }} is {{ oper_status }}, line protocol is {{ line_protocol_status}} ({{ connection_status }})
Hardware is {{ hardware }}, address is {{ mac_address }}
    Current address is {{ bia_address}}
Pluggable media TODO:present
Interface index (ifindex) is {{ ifindex }} ({{ "0x%x"|format(ifindex) }})
MTU {{ mtu }} bytes
IP MTU TODO:1500 bytes
Maximum Speed        : {{ speed }}
LineSpeed Actual     : {{ speed }}
LineSpeed Configured : {{ speed }}, Duplex: {{ duplex }}
Priority Tag TODO:disable
Forward LACP PDU: TODO:Disable
Route Only: TODO:Disabled
Tag-type: TODO:0x8100
BFD Software Session : TODO:Disabled
Last clearing of show interface counters: {{ last_clearing }}
Queueing strategy: fifo
 Primary Internet Address is TODO:CIDR broadcast is TODO:broadcast
Receive Statistics:
    {{ input_packets }} packets, {{ input_bytes }} bytes
    Unicasts: TODO:9674569, Multicasts: {{ received_multicast }}, Broadcasts: {{ received_broadcasts }}
    64-byte pkts: {{ input_64b_frames }}, Over 64-byte pkts: {{ input_65b_to_127b_frames }}, Over 127-byte pkts: {{ input_128b_to_255b_frames }}
    Over 255-byte pkts: {{ input_256b_to_511b_frames }}, Over 511-byte pkts: {{ input_512b_to_1023b_frames }}, Over 1023-byte pkts: {{ input_1024b_to_1518b_frames }}
    Over 1518-byte pkts(Jumbo): {{ input_oversized_frames }}
    Runts:  {{ runts }}, Jabbers: {{ input_jabber_frames }}, CRC: {{ crc_errors }}, Overruns: {{ overruns }}
    Errors: {{ input_errors }}, Discards: {{ input_discards }}
Transmit Statistics:
    {{ output_packets }} packets, {{ output_bytes }} bytes
    Unicasts: 9592669, Multicasts: {{ sent_multicast }}, Broadcasts: {{ sent_broadcasts }}
    Underruns: {{ underruns }}
    Errors: {{ output_errors }}, Discards: {{ output_discards }}
Rate info:
    Input {{ input_rate_mbps }} Mbits/sec,  {{ input_packets_rate }} packets/sec, {{ "%.2f"|format(input_utilization) }}% of line-rate
    Output {{ output_rate_mbps }} Mbits/sec, {{ output_packets_rate }} packets/sec, {{ "%.2f"|format(output_utilization) }}% of line-rate
Route-Only Packets Dropped: TODO:0
FEC:
    Mode: TODO:Disabled
    Corrected Blocks: TODO:0, Uncorrected Blocks: TODO:0
Time since last interface status change: {{ uptime }}"""


            data = {
            "bia_address": bia_address,
            "connection_status": connection_status,
            "crc_errors": crc_errors,
            "duplex": duplex,
            "hardware": "Ethernet",
            "ifindex": ifindex,
            "input_1024b_to_1518b_frames": input_1024b_to_1518b_frames,
            "input_128b_to_255b_frames": input_128b_to_255b_frames,
            "input_256b_to_511b_frames": input_256b_to_511b_frames,
            "input_512b_to_1023b_frames": input_512b_to_1023b_frames,
            "input_64b_frames": input_64b_frames,
            "input_65b_to_127b_frames": input_65b_to_127b_frames,
            "input_bytes": input_bytes,
            "input_discards": input_discards,
            "input_errors": input_errors,
            "input_jabber_frames": input_jabber_frames,
            "input_oversized_frames": input_oversized_frames,
            "input_packets": input_packets,
            "input_packets_rate": "N/A",
            "input_rate_mbps": input_rate_mbps,
            "input_utilization": input_utilization,
            "interface_name": interface_name,
            "last_clearing": uptime,
            "line_protocol_status": oper_status,
            "mac_address": mac_address,
            "mtu": mtu,
            "oper_status": oper_status,
            "output_bytes": output_bytes,
            "output_discards": output_discards,
            "output_errors": output_errors,
            "output_packets": output_packets,
            "output_packets_rate": "N/A",
            "output_rate_mbps": output_rate_mbps,
            "output_utilization": output_utilization,
            "overruns": "N/A",
            "received_broadcasts": received_broadcasts,
            "received_multicast": received_multicast,
            "runts": "N/A",
            "sent_broadcasts": sent_broadcasts,
            "sent_multicast": sent_multicast,
            "speed": port_speed,
            "underruns": "N/A",
            "uptime": uptime,
            }

            template = Template(template_string)
            output = template.render(data)
            print(output, end='')
            print()

        return my_data
   
    def print(self, state, arguments, output, **_kwargs):
        self._fetch_state(state, arguments)
        