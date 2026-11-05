from srlinux.syntax import Syntax
from srlinux.location import build_path
from srlinux.mgmt.cli import KeyCompleter
from srlinux.schema.data_store import DataStore
import datetime

class IpBgpReport:
    """Handles the 'show bgp evpn summary' command functionality."""
    
    # Class level constants
    PATH_TEMPLATES = {
        'bgp_instance': '/network-instance[name={network_instance}]/protocols/bgp',
    }

    BGP_STATE_MAP = {
        'idle': 'Idle',
        'connect': 'Connect',
        'active': 'Active',
        'opensent': 'OpenSent',
        'openconfirm': 'OpenConfirm',
        'established': 'Estab'
    }

    def __init__(self):
        self._rd = '*'
        self._esi = '*'
        self._mac_address = '*'
        self._ip_address = '*'
        self._ip_prefix = '*'
        self._originating_router = '*'
        self._ethernet_tag = '*'
        self._neighbor = '*'
        self._attrSets_dict = {}


    def show_bgp_summary(self, state, output, network_instance='default'):
        """Main function to display BGP summary"""
        # Get BGP instance data
        try:
            bgp_data = self._get_bgp_data(state, network_instance)
            # Silently exit if no data found (don't print error messages)
            if not bgp_data:
                return
                
            if not self._has_bgp_config(bgp_data):
                return
                
            # Print header and neighbor data
            self._print_bgp_header(output, bgp_data, network_instance)
            neighbors = self._get_neighbor_data(bgp_data)
            
            if neighbors:
                self._print_neighbor_table(output, neighbors)
            else:
                # No neighbors - exit silently
                pass
                
        except Exception as e:
            # Silent error handling - don't print errors
            pass

    def show_evpn_rt1(self, state, output, network_instance='default', esi_value='*'):
        """Main function to display EVPN RT1 summary"""
        # Get BGP instance data
        try:
            bgp_data = self._get_bgp_data(state, network_instance)
            # Silently exit if no data found (don't print error messages)
            if not bgp_data:
                return
                
            if not self._has_bgp_config(bgp_data):
                return
                
            # Print header and neighbor data
            self._print_bgp_rt_header(output, bgp_data, network_instance)
            rt1_data = self._getRibRoute1(state, network_instance, esi_value)
            rt1_routes = self._get_rt1_data(state, network_instance, rt1_data)
            if rt1_routes:
                self._print_rt_table(output, rt1_routes)
            else:
                # No neighbors - exit silently
                pass
                
        except Exception as e:
            # Silent error handling - don't print errors
            pass

    def show_evpn_rt2(self, state, output, network_instance='default', mac_value='*'):
        """Main function to display EVPN RT2 summary"""
        # Get BGP instance data
        try:
            bgp_data = self._get_bgp_data(state, network_instance)
            # Silently exit if no data found (don't print error messages)
            if not bgp_data:
                return
                
            if not self._has_bgp_config(bgp_data):
                return
                
            # Print header and neighbor data
            self._print_bgp_rt_header(output, bgp_data, network_instance)
            rt2_data = self._getRibRoute2(state, network_instance, mac_value)
            rt2_routes = self._get_rt2_data(state, network_instance, rt2_data)
            if rt2_routes:
                self._print_rt_table(output, rt2_routes)
            else:
                # No neighbors - exit silently
                pass
                
        except Exception as e:
            # Silent error handling - don't print errors
            pass

    def show_evpn_rt3(self, state, output, network_instance='default', originr_value='*'):
        """Main function to display EVPN RT3 summary"""
        # Get BGP instance data
        try:
            bgp_data = self._get_bgp_data(state, network_instance)
            # Silently exit if no data found (don't print error messages)
            if not bgp_data:
                return
                
            if not self._has_bgp_config(bgp_data):
                return
                
            # Print header and neighbor data
            self._print_bgp_rt_header(output, bgp_data, network_instance)
            rt3_data = self._getRibRoute3(state, network_instance, originr_value)
            rt3_routes = self._get_rt3_data(state, network_instance, rt3_data)
            if rt3_routes:
                self._print_rt_table(output, rt3_routes)
            else:
                # No neighbors - exit silently
                pass
                
        except Exception as e:
            # Silent error handling - don't print errors
            pass

    def show_evpn_rt4(self, state, output, network_instance='default', esi4_value='*'):
        """Main function to display EVPN RT4 summary"""
        # Get BGP instance data
        try:
            bgp_data = self._get_bgp_data(state, network_instance)
            # Silently exit if no data found (don't print error messages)
            if not bgp_data:
                return
                
            if not self._has_bgp_config(bgp_data):
                return
                
            # Print header and neighbor data
            self._print_bgp_rt_header(output, bgp_data, network_instance)
            rt4_data = self._getRibRoute4(state, network_instance, esi4_value)
            rt4_routes = self._get_rt4_data(state, network_instance, rt4_data)
            if rt4_routes:
                self._print_rt_table(output, rt4_routes)
            else:
                # No neighbors - exit silently
                pass
                
        except Exception as e:
            # Silent error handling - don't print errors
            pass

    def show_evpn_rt5(self, state, output, network_instance='default', ip_value='*'):
        """Main function to display EVPN RT5 summary"""
        # Get BGP instance data
        try:
            bgp_data = self._get_bgp_data(state, network_instance)
            # Silently exit if no data found (don't print error messages)
            if not bgp_data:
                return
                
            if not self._has_bgp_config(bgp_data):
                return
                
            # Print header and neighbor data
            self._print_bgp_rt_header(output, bgp_data, network_instance)
            rt5_data = self._getRibRoute5(state, network_instance, ip_value)
            rt5_routes = self._get_rt5_data(state, network_instance, rt5_data)
            if rt5_routes:
                self._print_rt_table(output, rt5_routes)
            else:
                # No neighbors - exit silently
                pass
                
        except Exception as e:
            # Silent error handling - don't print errors
            pass


    def _get_bgp_data(self, state, network_instance):
        """Get BGP instance data"""
        try:
            path = build_path(self.PATH_TEMPLATES['bgp_instance'].format(
                network_instance=network_instance
            ))
            return state.server.get_data_store(DataStore.State).get_data(path, recursive=True)
        except Exception:
            # Silently handle error
            return None

    def _getRibRoute1(self, state, netinst,esi_value):
        if state.system_features.bgp_rib_afi_safi_list_for_evpn:
            path_1 = build_path('/network-instance[name={name}]/bgp-rib/afi-safi[afi-safi-name=evpn]/evpn/rib-in-out/rib-in-post/ethernet-ad-route[route-distinguisher={rd}][esi={esi}][ethernet-tag-id={etag}][neighbor={neigh}]',
                    name = netinst,
                    rd='*',
                    esi= esi_value,
                    etag='*',
                    neigh='*',
                    #pathid='*'
                )
        else:
            path_1 = build_path('/network-instance[name={name}]/bgp-rib/evpn/rib-in-out/rib-in-post/ethernet-ad-routes[route-distinguisher={rd}][esi={esi}][ethernet-tag-id={etag}][neighbor={neigh}]',
                    name = netinst,
                    rd='*',
                    esi = esi_value,
                    etag='*',
                    neigh='*'
                )
        return state.server.get_data_store(DataStore.State).get_data(path_1, recursive=True)

    def _getRibRoute2(self, state, netinst, mac_value):
        if state.system_features.bgp_rib_afi_safi_list_for_evpn:
            path_2 = build_path('/network-instance[name={name}]/bgp-rib/afi-safi[afi-safi-name=evpn]/evpn/rib-in-out/rib-in-post/mac-ip-route[route-distinguisher={rd}][mac-length=*][mac-address={mac}][ip-address={ip}][ethernet-tag-id={etag}][neighbor={neigh}]',
                name = netinst,
                rd='*',
                mac = mac_value,
                ip='*',
                etag='*',
                neigh='*'
            )
        else:
            path_2 = build_path('/network-instance[name={name}]/bgp-rib/evpn/rib-in-out/rib-in-post/mac-ip-routes[route-distinguisher={rd}][mac-length=*][mac-address={mac}][ip-address={ip}][ethernet-tag-id={etag}][neighbor={neigh}]',
                    name = netinst,
                    rd='*',
                    mac = mac_value,
                    ip='*',
                    etag='*',
                    neigh='*'
                )
        return state.server.get_data_store(DataStore.State).get_data(path_2, recursive=True)

    def _getRibRoute3(self, state, netinst, originr_value):
        if state.system_features.bgp_rib_afi_safi_list_for_evpn:
            path_3 = build_path('/network-instance[name={name}]/bgp-rib/afi-safi[afi-safi-name=evpn]/evpn/rib-in-out/rib-in-post/imet-route[route-distinguisher={rd}][originating-router={orouter}][ethernet-tag-id={etag}][neighbor={neigh}]',
                name = netinst,
                rd='*',
                orouter = originr_value,
                etag='*',
                neigh='*'
            )
        else:
            path_3 = build_path('/network-instance[name={name}]/bgp-rib/evpn/rib-in-out/rib-in-post/imet-routes[route-distinguisher={rd}][originating-router={orouter}][ethernet-tag-id={etag}][neighbor={neigh}]',
                    name = netinst,
                    rd='*',
                    orouter = originr_value,
                    etag='*',
                    neigh='*'
                )
        return state.server.get_data_store(DataStore.State).get_data(path_3, recursive=True)

    def _getRibRoute4(self, state, netinst, esi4_value):
        if state.system_features.bgp_rib_afi_safi_list_for_evpn:
            path_4 = build_path('/network-instance[name={name}]/bgp-rib/afi-safi[afi-safi-name=evpn]/evpn/rib-in-out/rib-in-post/ethernet-segment-route[route-distinguisher={rd}][esi={esi}][originating-router={orouter}][neighbor={neigh}]',
                name = netinst,
                rd='*',
                esi = esi4_value,
                orouter='*',
                neigh='*'
            )
        else:
            path_4 = build_path('/network-instance[name={name}]/bgp-rib/evpn/rib-in-out/rib-in-post/ethernet-segment-routes[route-distinguisher={rd}][esi={esi}][originating-router={orouter}][neighbor={neigh}]',
                    name = netinst,
                    rd='*',
                    esi = esi4_value,
                    orouter='*',
                    neigh='*'
                )
        return state.server.get_data_store(DataStore.State).get_data(path_4, recursive=True)

    def _getRibRoute5(self, state, netinst, ip_value):
        if state.system_features.bgp_rib_afi_safi_list_for_evpn:
            path_5 = build_path('/network-instance[name={name}]/bgp-rib/afi-safi[afi-safi-name=evpn]/evpn/rib-in-out/rib-in-post/ip-prefix-route[route-distinguisher={rd}][ethernet-tag-id={etag}][ip-prefix-length=*][ip-prefix={prefix}][neighbor={neigh}]',
                name = netinst,
                rd='*',
                etag='*',
                prefix = ip_value,
                neigh='*'
            )
        else:
            path_5 = build_path('/network-instance[name={name}]/bgp-rib/evpn/rib-in-out/rib-in-post/ip-prefix-routes[route-distinguisher={rd}][ethernet-tag-id={etag}][ip-prefix-length=*][ip-prefix={prefix}][neighbor={neigh}]',
                name = netinst,
                rd='*',
                etag='*',
                prefix = ip_value,
                neigh='*'
                )
        return state.server.get_data_store(DataStore.State).get_data(path_5, recursive=True)

    def _has_bgp_config(self, bgp_data):
        """Check if BGP is configured"""
        if not bgp_data:
            return False
            
        try:
            network_instance = bgp_data.network_instance.get()
            if not network_instance:
                return False
                
            protocols = network_instance.protocols.get()
            if not protocols:
                return False
                
            return bool(protocols.bgp.get())
        except (AttributeError, Exception):
            return False

    def _print_bgp_header(self, output, bgp_data, network_instance):
        """Print BGP header information"""
        router_id = "0.0.0.0"
        local_as = "N/A"
        
        try:
            bgp = bgp_data.network_instance.get().protocols.get().bgp.get()
            if hasattr(bgp, 'router_id') and bgp.router_id:
                router_id = bgp.router_id
                
            if hasattr(bgp, 'autonomous_system') and bgp.autonomous_system:
                local_as = bgp.autonomous_system
        except (AttributeError, Exception):
            pass
            
        output.print_line(f"BGP summary information for VRF {network_instance}")
        output.print_line(f"Router identifier {router_id}, local AS number {local_as}")
        output.print_line("Neighbor Status Codes: m – Under maintenance")
        
        # Print column headers
        output.print_line("  Neighbor        V    AS     MsgRcvd   MsgSent   InQ    OutQ   Up/Down   State     PfxRcd    PfxAcc")

    def _print_bgp_rt_header(self, output, bgp_data, network_instance):
        """Print BGP header information"""
        router_id = "0.0.0.0"
        local_as = "N/A"
        
        try:
            bgp = bgp_data.network_instance.get().protocols.get().bgp.get()
            if hasattr(bgp, 'router_id') and bgp.router_id:
                router_id = bgp.router_id
            if hasattr(bgp, 'autonomous_system') and bgp.autonomous_system:
                local_as = bgp.autonomous_system
        except (AttributeError, Exception):
            pass
            
        output.print_line(f"BGP routing table information for VRF {network_instance}")
        output.print_line(f"Router identifier {router_id}, local AS number {local_as}")
        output.print_line("Route status codes: s - suppressed, * - valid, > - active, # - not installed, E - ECMP head, e - ECMP")
        output.print_line("                    S - Stale, c - Contributing to ECMP, b - backup")
        output.print_line("                    % - Pending BGP convergence")
        output.print_line("Origin codes: i - IGP, e - EGP, ? - incomplete")
        output.print_line("AS Path Attributes: Or-ID - Originator ID, C-LST - Cluster List, LL Nexthop - Link Local Nexthop")
        
        # Print column headers
        output.print_line("         Network             Next Hop         Metric  LocPref Weight Path")

    def _get_neighbor_data(self, bgp_data):
        """Get BGP neighbor data"""
        neighbors = []
        
        try:
            bgp = bgp_data.network_instance.get().protocols.get().bgp.get()
            if not hasattr(bgp, 'neighbor'):
                return neighbors
                
            for neighbor in bgp.neighbor.items():
                if not neighbor:
                    continue
                # Only check for EVPN neighbors
                if hasattr(neighbor, 'afi_safi'):
                    for afi_safi in neighbor.afi_safi.items():
                        if not afi_safi:
                            continue   
                        if afi_safi.afi_safi_name == 'evpn' and afi_safi.admin_state == 'enable':
                            # Extract neighbor data with safe defaults
                            peer_address = neighbor.peer_address
                            peer_as = "?" 
                            if hasattr(neighbor, 'peer_as'):
                                peer_as = str(neighbor.peer_as)
                            # Get session state - be cautious about case sensitivity
                            session_state = "Idle"
                            state_lower = None
                            if hasattr(neighbor, 'session_state'):
                                state_lower = neighbor.session_state.lower() if neighbor.session_state else None
                                # Map to display format with proper capitalization
                                session_state = self.BGP_STATE_MAP.get(state_lower, "Idle")
                
                            # Get message statistics
                            messages_received = 0
                            messages_sent = 0
                            received_queue = 0
                            sent_queue = 0
                
                            if hasattr(neighbor, 'received_messages'):
                                rm = neighbor.received_messages.get()
                                if rm and hasattr(rm, 'total_messages'):
                                    messages_received = getattr(rm, 'total_messages', 0) or 0
                                    received_queue = getattr(rm, 'queue_depth', 0) or 0
                        
                            if hasattr(neighbor, 'sent_messages'):
                                sm = neighbor.sent_messages.get()
                                if sm and hasattr(sm, 'total_messages'):
                                    messages_sent = getattr(sm, 'total_messages', 0) or 0
                                    sent_queue = getattr(sm, 'queue_depth', 0) or 0
                            # Get prefix information
                            prefixes_received = 0
                            prefixes_accepted = 0                                       
                            if hasattr(afi_safi, 'received_routes'):
                                prefixes_received = afi_safi.received_routes
                            if hasattr(afi_safi, 'active_routes'):
                                prefixes_accepted = afi_safi.active_routes
                
                            # Format uptime
                            uptime = self._format_uptime(neighbor)
                            neighbor_info = {
                                'peer_address': peer_address,
                                'peer_as': peer_as,
                                'msg_rcvd': messages_received,
                                'msg_sent': messages_sent,
                                'state': session_state,
                                'state_lower': state_lower,
                                'pfx_received': prefixes_received,
                                'pfx_accepted': prefixes_accepted,
                                'up_time': uptime,
                                'rx_queue': received_queue,
                                'tx_queue': sent_queue
                            }
                            neighbors.append(neighbor_info)
               
        except Exception:
            # Silent error handling
            pass
            
        return neighbors

    def _get_rt1_data(self, state, network_instance, rt1_data):
        """Get EVPN RT1 data"""
        rt1_dataset = []
        for netinst in rt1_data.network_instance.items():
            if state.system_features.bgp_rib_afi_safi_list_for_evpn:
                evpn_routes = netinst.bgp_rib.get().afi_safi.get().evpn.get().rib_in_out.get()
            else:
                evpn_routes = netinst.bgp_rib.get().evpn.get().rib_in_out.get()

            evpn_rib_in_post = evpn_routes.rib_in_post.get()
            if state.system_features.bgp_rib_afi_safi_list_for_evpn:
                rttable = evpn_rib_in_post.ethernet_ad_route
            else:
                rttable = evpn_rib_in_post.ethernet_ad_routes
            rt_type = '1'
            for route in rttable.items():
                status = self._set_status_code(route)
                route_network = 'RD: ' + route.route_distinguisher + ' auto-discovery ' + str(route.ethernet_tag_id) + ' ' + route.esi
                route_entry = self._create_route_entry(route_network, status)
                self._populate_route_attrs(state, route_entry, netinst.name, route.attr_id, rt_type)
                rt1_dataset.append(route_entry)         
        return rt1_dataset

    def _get_rt2_data(self, state, network_instance, rt2_data):
        """Get EVPN RT2 data"""
        rt2_dataset = []
        for netinst in rt2_data.network_instance.items():
            if state.system_features.bgp_rib_afi_safi_list_for_evpn:
                evpn_routes = netinst.bgp_rib.get().afi_safi.get().evpn.get().rib_in_out.get()
            else:
                evpn_routes = netinst.bgp_rib.get().evpn.get().rib_in_out.get()

            evpn_rib_in_post = evpn_routes.rib_in_post.get()
            if state.system_features.bgp_rib_afi_safi_list_for_evpn:
                rttable = evpn_rib_in_post.mac_ip_route
            else:
                rttable = evpn_rib_in_post.mac_ip_routes
            rt_type = '2'
            for route in rttable.items():
                status = self._set_status_code(route)
                route_network = 'RD: ' + route.route_distinguisher + ' mac-ip ' + route.mac_address + ' ' + route.ip_address
                route_entry = self._create_route_entry(route_network, status)
                self._populate_route_attrs(state, route_entry, netinst.name, route.attr_id, rt_type)
                rt2_dataset.append(route_entry)         
        return rt2_dataset

    def _get_rt3_data(self, state, network_instance, rt3_data):
        """Get EVPN RT3 data"""
        rt3_dataset = []
        for netinst in rt3_data.network_instance.items():
            if state.system_features.bgp_rib_afi_safi_list_for_evpn:
                evpn_routes = netinst.bgp_rib.get().afi_safi.get().evpn.get().rib_in_out.get()
            else:
                evpn_routes = netinst.bgp_rib.get().evpn.get().rib_in_out.get()

            evpn_rib_in_post = evpn_routes.rib_in_post.get()
            if state.system_features.bgp_rib_afi_safi_list_for_evpn:
                rttable = evpn_rib_in_post.imet_route
            else:
                rttable = evpn_rib_in_post.imet_routes
            rt_type = '3'
            for route in rttable.items():
                status = self._set_status_code(route)
                route_network = 'RD: ' + route.route_distinguisher + ' imet ' + route.originating_router
                route_entry = self._create_route_entry(route_network, status)
                self._populate_route_attrs(state, route_entry, netinst.name, route.attr_id, rt_type)
                rt3_dataset.append(route_entry)         
        return rt3_dataset

    def _get_rt4_data(self, state, network_instance, rt4_data):
        """Get EVPN RT4 data"""
        rt4_dataset = []
        for netinst in rt4_data.network_instance.items():
            if state.system_features.bgp_rib_afi_safi_list_for_evpn:
                evpn_routes = netinst.bgp_rib.get().afi_safi.get().evpn.get().rib_in_out.get()
            else:
                evpn_routes = netinst.bgp_rib.get().evpn.get().rib_in_out.get()

            evpn_rib_in_post = evpn_routes.rib_in_post.get()
            if state.system_features.bgp_rib_afi_safi_list_for_evpn:
                rttable = evpn_rib_in_post.ethernet_segment_route
            else:
                rttable = evpn_rib_in_post.ethernet_segment_routes
            rt_type = '4'
            for route in rttable.items():
                status = self._set_status_code(route)
                route_network = 'RD: ' + route.route_distinguisher + ' ethernet-segment ' + route.esi
                route_entry = self._create_route_entry(route_network, status)
                self._populate_route_attrs(state, route_entry, netinst.name, route.attr_id, rt_type)
                rt4_dataset.append(route_entry)         
        return rt4_dataset

    def _get_rt5_data(self, state, network_instance, rt5_data):
        """Get EVPN RT5 data"""
        rt5_dataset = []
        for netinst in rt5_data.network_instance.items():
            if state.system_features.bgp_rib_afi_safi_list_for_evpn:
                evpn_routes = netinst.bgp_rib.get().afi_safi.get().evpn.get().rib_in_out.get()
            else:
                evpn_routes = netinst.bgp_rib.get().evpn.get().rib_in_out.get()

            evpn_rib_in_post = evpn_routes.rib_in_post.get()
            if state.system_features.bgp_rib_afi_safi_list_for_evpn:
                rttable = evpn_rib_in_post.ip_prefix_route
            else:
                rttable = evpn_rib_in_post.ip_prefix_routes
            rt_type = '5'
            for route in rttable.items():
                status = self._set_status_code(route)
                route_network = 'RD: ' + route.route_distinguisher + ' ip-prefix ' + route.ip_prefix
                route_entry = self._create_route_entry(route_network, status)
                self._populate_route_attrs(state, route_entry, netinst.name, route.attr_id, rt_type)
                rt5_dataset.append(route_entry)         
        return rt5_dataset


    def _create_route_entry(self, route_network, status):
        """Create basic route entry with standard fields"""
        return {
            'network_info': route_network,
            'status_info': status,
            'nexthop_info': '',
            'metric_info': '',
            'locpref_info': '',
            'weight_info': '',
            'path_info': ''
        }

    def _populate_route_attrs(self, state, route_entry, netinst_name, attr_id, route_type='*'):
        cache_key = (netinst_name, attr_id)
        if cache_key not in self._attrSets_dict:
            path_attr = build_path('/network-instance[name={vrf}]/bgp-rib/attr-sets/attr-set[index={atr}]',
                              vrf=netinst_name, atr=str(attr_id))
            attrSets = state.server.get_data_store(DataStore.State).get_data(path_attr, recursive=True, include_container_children=True)
            self._attrSets_dict[cache_key] = attrSets
        else:
            attrSets = self._attrSets_dict[cache_key]
        for attr in attrSets.get_descendants('/network-instance/bgp-rib/attr-sets/attr-set'):
            route_entry['nexthop_info'] = getattr(attr, 'next_hop', '') or ''
            route_entry['locpref_info'] = getattr(attr, 'local_pref', '') or ''
            try:
                as_path = attr.as_path.get().segment.get().member or []
            except Exception:
                as_path = []
            as_str = (' '.join(map(str, as_path)) + ' ') if as_path else ''
            origin = getattr(attr, 'origin', '')
            if origin == 'igp':
                route_entry['path_info'] = as_str + 'i'
            elif origin == 'egp':
                route_entry['path_info'] = as_str + 'e'
            elif origin == 'incomplete':
                route_entry['path_info'] = as_str + '?'
            if hasattr(attr, 'med') and attr.med:
                route_entry['metric_info'] = attr.med
            else:
                route_entry['metric_info'] = '-'
            route_entry['weight_info'] = '0'

    def _set_status_code(self, route):
        status = ""
        if route.used_route:
            status = "u"
            #self._used_routes += 1
        if route.stale_route:
            status += "x"
            #self._statle_routes += 1
        if route.valid_route:
            status += "*"
            #self._valid_routes += 1
        if route.best_route:
            status += ">"
        return status or '-'

    def _print_neighbor_table(self, output, neighbors):
        """Print formatted neighbor table"""
        for neighbor in sorted(neighbors, key=lambda x: str(x.get('peer_address', ''))):
            # Show the correct format based on BGP state
            # For established neighbors, show the prefix count
            # For non-established, show the state
            if neighbor.get('state_lower') == 'established':
                state_display = str(neighbor.get('pfx_received', 0))
            else:
                state_display = neighbor.get('state', 'Idle')
            
            output.print_line(f"  {neighbor['peer_address']:<15} 4    {neighbor['peer_as']:<6} "
                              f"{neighbor['msg_rcvd']:<9} {neighbor['msg_sent']:<9} "
                              f"{neighbor['rx_queue']:<6} {neighbor['tx_queue']:<6} "
                              f"{neighbor['up_time']:<9} {neighbor['state']:<9} " 
                              f"{neighbor['pfx_received']:<9} {neighbor['pfx_accepted']:<9}")

    def _format_uptime(self, neighbor):
        """Format uptime for display with safer parsing"""
        # Default for non-established sessions
        if not hasattr(neighbor, 'session_state') or neighbor.session_state != 'established':
            return "never"
        
        # Check if last_established exists and has a value
        if not hasattr(neighbor, 'last_established') or not neighbor.last_established:
            return "never"
            
        try:
            # Safer parsing that handles potential format variations
            timestamp_str = neighbor.last_established
            if '(' in timestamp_str:
                timestamp_str = timestamp_str.split('(')[0].strip()
                
            # Handle ISO format timestamps with timezone information
            if 'Z' in timestamp_str:
                timestamp_str = timestamp_str.replace('Z', '+00:00')
                
            last_established_time = datetime.datetime.fromisoformat(timestamp_str)
            current_time = datetime.datetime.now(datetime.timezone.utc)
            
            # Handle potential timezone differences
            if last_established_time.tzinfo is None:
                last_established_time = last_established_time.replace(tzinfo=datetime.timezone.utc)
                
            uptime = current_time - last_established_time
            
            # Format the uptime string
            days = uptime.days
            hours = uptime.seconds // 3600
            minutes = (uptime.seconds % 3600) // 60
            
            if days > 0:
                return f"{days}d{hours}h"
            elif hours > 0:
                return f"{hours}h{minutes}m"
            else:
                return f"{minutes}m"
                
        except Exception:
            # Fall back to "never" if there's any parsing error
            return "never"

    def _print_rt_table(self, output, rt_entries):
        """Print formatted route type table"""
        for rt_entry in rt_entries:    
            output.print_line(f" {rt_entry['status_info']:<7} {rt_entry['network_info']:<50}\n "
                              f"                            {rt_entry['nexthop_info']:<16} {rt_entry['metric_info']:<7} "
                              f"{rt_entry['locpref_info']:<7} {rt_entry['weight_info']:<6} "
                              f"{rt_entry['path_info']:<20} ")