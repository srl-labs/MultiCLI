"""
CLI Plugin for SR Linux for Cisco-style IP Route Command
Provides alternate command syntax for route information
Author: Alperen Akpinar
Email: alperen.akpinar@nokia.com
"""
from srlinux.syntax import Syntax
from srlinux.location import build_path
from srlinux.mgmt.cli import KeyCompleter
import datetime
import ipaddress
from srlinux.schema import FixedSchemaRoot
from srlinux.schema.data_store import DataStore

try:
    from cisco_interface_reports import format_cisco_intf
except ImportError:
    def format_cisco_intf(name, short=True):
        if not name:
            return ""
        name = str(name).strip()
        if name.endswith('.0'):
            name = name[:-2]
        if name.startswith('ethernet-'):
            num = name.split('-', 1)[1]
            return f"Eth{num}" if short else f"Ethernet{num}"
        return name

class IpRouteReport:
    """Handles the 'ip route' command functionality."""
    
    # Class level constants
    ROUTE_CODES = {
        'aggregate': 'Ag',
        'arp-nd': 'Ar',
        'bgp': 'B',
        'bgp-label': 'BL',
        'bgp-evpn': 'BE', 
        'bgp-vpn': 'BV',
        'connected': 'C',
        'dhcp': 'D',
        'gribi': 'G',
        'host': 'H',
        'isis': 'IS',
        'linux': 'Li',
        'ndk1': 'N1',
        'ndk2': 'N2',
        'ospfv2': 'O',
        'ospfv3': 'O',
        'static': 'S',
    }

    PATH_TEMPLATES = {
        'route_table': '/network-instance[name={network_instance}]/route-table',
    }

    def _show_routes(self, state, output, network_instance):
        """Main function to display routes"""
        self._print_header(output)

        if network_instance != 'default':
            output.print_line(f'Routing Table: VRF {network_instance}\n')

        # Get all routes
        routes_data = self._get_routes_data(state, network_instance)
        if not routes_data:
            self._print_not_found_message(output, network_instance)
            return

        route_entries = self._process_routes(state, network_instance, routes_data)
        self._display_routes(output, route_entries, network_instance)

    def _print_header(self, output):
        """Print command header and legend"""
        output.print_line('''Codes: C - connected, L - local, S - static, B - BGP, O - OSPF, IS - IS-IS,
       Ag - aggregate, Ar - arp-nd, BL - bgp-label, BE - bgp-evpn, BV - bgp-vpn
       D - dhcp, G - gribi, H - host, Li - linux, N1/N2 - ndk\n''')

    def _print_not_found_message(self, output, network_instance):
        """Print error message when VRF/routes not found"""
        output.print_line(f"Error: VRF '{network_instance}' not found or no routes present.")

    def _get_routes_data(self, state, network_instance):
        """Get routes with proper error handling"""
        try:
            routes_path = build_path(self.PATH_TEMPLATES['route_table'].format(network_instance=network_instance))
            return state.server.get_data_store(DataStore.State).get_data(routes_path, recursive=True)
        except Exception:
            return None

    def _process_routes(self, state, network_instance, routes_data):
        """Process all routes and return sorted entries using in-memory mapping"""
        nh_map = {}
        try:
            for nh in routes_data.get_descendants('/network-instance/route-table/next-hop'):
                nh_idx = getattr(nh, 'index', None)
                if nh_idx is None:
                    continue

                nh_type = getattr(nh, 'type', None)
                ip = getattr(nh, 'ip_address', None)
                subif = getattr(nh, 'subinterface', None)
                resolving_nhg = None

                if nh_type == 'tunnel' and hasattr(nh, 'tunnel'):
                    try:
                        t = nh.tunnel.get()
                        pfx = getattr(t, 'ip_prefix', None)
                        if pfx and not ip:
                            ip = str(pfx).split('/')[0]
                    except Exception:
                        pass

                if nh_type == 'indirect' and hasattr(nh, 'indirect'):
                    try:
                        ind = nh.indirect.get()
                        rr = getattr(ind, 'resolving_route', None)
                        if rr:
                            resolving_nhg = getattr(rr.get(), 'next_hop_group', None)
                    except Exception:
                        pass

                nh_map[str(nh_idx)] = {
                    'ip': str(ip) if ip else None,
                    'interface': str(subif) if subif else None,
                    'resolving_nhg': str(resolving_nhg) if resolving_nhg is not None else None,
                }
        except Exception:
            pass

        nhg_map = {}
        try:
            for nhg in routes_data.get_descendants('/network-instance/route-table/next-hop-group'):
                nhg_idx = getattr(nhg, 'index', None)
                if nhg_idx is not None and hasattr(nhg, 'next_hop'):
                    hops = []
                    for nh_item in nhg.next_hop.items():
                        target_nh = getattr(nh_item, 'next_hop', None)
                        if target_nh is not None and str(target_nh) in nh_map:
                            hops.append(nh_map[str(target_nh)])
                    nhg_map[str(nhg_idx)] = hops
        except Exception:
            pass

        # Resolve indirect next-hop interfaces via resolving route's next-hop group
        for nh_info in nh_map.values():
            if not nh_info['interface'] and nh_info.get('resolving_nhg'):
                target_hops = nhg_map.get(nh_info['resolving_nhg'], [])
                for th in target_hops:
                    if th.get('interface'):
                        nh_info['interface'] = th['interface']
                        break

        all_routes = []
        try:
            for route in routes_data.get_descendants('/network-instance/route-table/ipv4-unicast/route'):
                pfx = getattr(route, 'ipv4_prefix', None)
                if not pfx:
                    continue

                route_entry = self._create_route_entry(route)
                nhg_id = getattr(route, 'next_hop_group', None)
                hops = nhg_map.get(str(nhg_id), []) if nhg_id is not None else []

                if route_entry['type'] in ['local', 'connected']:
                    if hops and hops[0].get('interface'):
                        route_entry['interface'] = hops[0]['interface']
                else:
                    route_entry['next_hops'] = hops

                all_routes.append(route_entry)
        except Exception:
            pass

        try:
            return sorted(all_routes, key=lambda x: int(ipaddress.ip_network(x['prefix']).network_address))
        except Exception:
            return all_routes

    def _create_route_entry(self, route):
        """Create basic route entry with standard fields"""
        return {
            'prefix': getattr(route, 'ipv4_prefix', ''),
            'code': self._get_route_code(getattr(route, 'route_type', ''), getattr(route, 'route_owner', '')),
            'type': getattr(route, 'route_type', ''),
            'owner': getattr(route, 'route_owner', ''),
            'next_hops': [],
            'uptime': self._format_uptime(route),
            'interface': None,
            'preference': getattr(route, 'preference', 0),
            'metric': getattr(route, 'metric', 0)
        }

    def _format_uptime(self, route):
        """Extract and format uptime for a route"""
        try:
            if not getattr(route, 'active', False):
                return ""

            if route.route_type == 'bgp':
                try:
                    last_update_str = route.last_app_update
                    if last_update_str:
                        timestamp = last_update_str.split(' (')[0]
                        last_update_time = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        current_time = datetime.datetime.now(datetime.timezone.utc)
                        uptime = current_time - last_update_time
                        days, seconds = uptime.days, uptime.seconds
                        hours = seconds // 3600
                        if days > 0:
                            return f"{days}d{hours:02d}h"
                        else:
                            minutes, seconds = divmod(seconds % 3600, 60)
                            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                except Exception:
                    pass
            return ""
        except Exception:
            return ""

    def _get_route_code(self, route_type, route_owner):
        """Get single character code for route type"""
        rtype = (route_type or '').lower()
        rowner = (route_owner or '').lower()
        if rtype == 'host':
            return 'L'
        if rtype in ('local', 'connected') or rowner in ('local', 'connected'):
            return 'C'
        if rtype in self.ROUTE_CODES:
            return self.ROUTE_CODES[rtype]
        if rowner in self.ROUTE_CODES:
            return self.ROUTE_CODES[rowner]
        return '?'

    def _display_routes(self, output, routes, network_instance):
        """Display formatted routes"""
        # Check for default route
        default_route = next((route for route in routes if route['prefix'] == '0.0.0.0/0'), None)
        if default_route and default_route.get('next_hops'):
            nh_ip = default_route['next_hops'][0].get('ip', 'unknown')
            output.print_line(f"Gateway of last resort is {nh_ip} to network 0.0.0.0\n")
        elif default_route and default_route.get('interface'):
            intf_disp = format_cisco_intf(default_route['interface'], short=True)
            output.print_line(f"Gateway of last resort is {intf_disp} to network 0.0.0.0\n")
        else:
            output.print_line("Gateway of last resort is not set\n")

        for route in routes:
            self._display_route(output, route)

    def _display_route(self, output, route):
        """Display a single route entry"""
        if route['interface']:
            intf_disp = format_cisco_intf(route['interface'], short=True)
            output.print_line(f"{route['code']}    {route['prefix']} is directly connected, {intf_disp}")
        elif route['code'] == 'L':
            output.print_line(f"{route['code']}    {route['prefix']} is directly connected")
        elif not route['next_hops']:
            output.print_line(f"{route['code']}    {route['prefix']}")
        else:
            self._display_route_with_next_hops(output, route)

    def _display_route_with_next_hops(self, output, route):
        """Display route with its next-hops"""
        if len(route['next_hops']) > 1:
            # First next-hop
            first_hop = route['next_hops'][0]
            self._print_next_hop(output, route, first_hop, is_first=True)
            
            # Additional next-hops
            for next_hop in route['next_hops'][1:]:
                self._print_next_hop(output, route, next_hop, is_first=False)
        else:
            # Single next-hop
            self._print_next_hop(output, route, route['next_hops'][0], is_first=True)

    def _print_next_hop(self, output, route, next_hop, is_first):
        """Print a single next-hop entry"""
        nh_ip = next_hop.get('ip')
        nh_intf = next_hop.get('interface')
        nh_target = nh_ip or (format_cisco_intf(nh_intf, short=True) if nh_intf else 'unknown')

        if is_first:
            line = f"{route['code']}    {route['prefix']} [{route['preference']}/{route['metric']}] via {nh_target}"
        else:
            line = f"           [{route['preference']}/{route['metric']}] via {nh_target}"

        if route.get('uptime'):
            line += f", {route['uptime']}"
        if nh_intf and nh_ip:
            intf_disp = format_cisco_intf(nh_intf, short=True)
            line += f", {intf_disp}"

        output.print_line(line)