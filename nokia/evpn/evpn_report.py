#!/usr/bin/python
###########################################################################
# Description: EVPN-MPLS and EVPN-VXLAN commands for the SRLinux MultiCLI project for SROS commands
#
# Copyright (c) 2025 Nokia
###########################################################################

from datetime import datetime

from srlinux.data import Data, Formatter
from srlinux.location import build_path
from srlinux.mgmt.cli.execute_error import ExecuteError
from srlinux.mgmt.server.server_error import ServerError
from srlinux.schema import FixedSchemaRoot
from srlinux.schema.data_store import DataStore


class EvpnDestinationReport(object):
    """
    Adds `show service id <id> evpn-mpls` and `show service id <id> vxlan destinations` commands.

    Example output:
    ```
    ===============================================================================
    BGP EVPN-MPLS Dest (Instance 1)
    ===============================================================================
    TEP Address                     Transpor:Tnl      Egr Label  Oper  Mcast  Num
                                                                State        MACs
    -------------------------------------------------------------------------------
    10.0.0.4                        sr-isis:20004     103        Up    bum    N/A
    10.0.1.3                        sr-isis:20103     524287     Up    bum    N/A
    10.0.1.3                        sr-isis:20103     524287     Up    None   10
    10.0.1.4                        sr-isis:20104     524287     Up    bum    N/A
    10.0.1.4                        sr-isis:20104     524287     Up    None   10
    -------------------------------------------------------------------------------
    Number of entries: 5
    -------------------------------------------------------------------------------
    ===============================================================================

    ===============================================================================
    BGP EVPN-MPLS Dest (Instance 2)
    ===============================================================================
    TEP Address                     Transpor:Tnl      Egr Label  Oper  Mcast  Num
                                                                State        MACs
    -------------------------------------------------------------------------------
    No Matching Entries
    ===============================================================================

    ===============================================================================
    BGP EVPN-MPLS Ethernet Segment Dest (Instance 1)
    ===============================================================================
    Eth SegId                       Num. Macs               Last Update
    -------------------------------------------------------------------------------
    00:00:00:BE:EF:00:00:00:00:03   10                      2025-04-02 08:48:34
    -------------------------------------------------------------------------------
    Number of entries: 1
    -------------------------------------------------------------------------------
    ===============================================================================

    ===============================================================================
    BGP EVPN-MPLS Ethernet Segment Dest (Instance 2)
    ===============================================================================
    Eth SegId                       Num. Macs               Last Update
    -------------------------------------------------------------------------------
    No Matching Entries
    ===============================================================================
    ```
    """

    def get_schema(self):
        root = FixedSchemaRoot()
        network = root.add_child("network", key="network-instance")
        network.add_child(
            "mpls_tunnel",
            keys=["Tunnel ID", "Egress label", "Mcast"],
            fields=["TEP Address", "Transport Tnl", "Oper State", "Num MACs"],
        )
        network.add_child(
            "vxlan_tunnel",
            keys=["TEP Address", "Egress VNI", "Mcast"],
            fields=["Oper State", "Num Macs"],
        )
        network.add_child(
            "ethernet_segment",
            keys=["ESI"],
            fields=["Num MACs", "Member VTEPs", "Last Update"],
        )

        return root

    def _is_mpls_capable(self, state):
        if state and hasattr(state, "system_features") and state.system_features.features:
            return bool(state.system_features.evpn_mpls)
        c = (self._chassis_type or "").lower()
        return c.startswith("7730") or c.startswith("7250")

    def _is_vxlan_capable(self, state):
        if state and hasattr(state, "system_features") and state.system_features.features:
            return bool(state.system_features.vxlan)
        c = (self._chassis_type or "").lower()
        return not c.startswith("7730")

    def print_mpls(
        self,
        state,
        arguments,
        output,
        **_kwargs,
    ) -> None:
        self._fetch_state(state, arguments, mode="mpls")

        if not self._is_mpls_capable(state):
            raise ExecuteError(
                f"EVPN-MPLS is not supported on chassis type '{self._chassis_type or 'unknown'}'"
            )

        data = Data(schema=arguments.schema)
        self._populate_data_mpls(data)
        self._set_formatters(data, arguments, state, mode="mpls")
        if len(list(data.network.items())) > 0:
            output.print_data(data)
        else:
            empty_tbl = SROSTable("BGP EVPN-MPLS Dest (Instance 1)", "Number of entries: ", 79, [])
            empty_tbl.set_column_widths([32, 18, 11, 6, 7, 4])
            empty_tbl.add_header(["TEP Address", "Transpor:Tnl", "Egr Label", "Oper", "Mcast", "Num"])
            empty_tbl.add_header(["", "", "", "State", "", "MACs"])
            for line in empty_tbl.print_table():
                output.print_line(line)
        output.print_line("\nTry SR Linux command: show network-instance * protocols bgp-evpn")

    def print_vxlan(
        self,
        state,
        arguments,
        output,
        **_kwargs,
    ) -> None:
        self._fetch_state(state, arguments, mode="vxlan")

        if not self._is_vxlan_capable(state):
            raise ExecuteError(
                f"VxLAN is not supported on chassis type '{self._chassis_type or 'unknown'}'"
            )

        data = Data(schema=arguments.schema)
        self._populate_data_vxlan(data)
        self._set_formatters(data, arguments, state, mode="vxlan")
        if len(list(data.network.items())) > 0:
            output.print_data(data)
        else:
            empty_tbl = SROSTable("Egress VTEP, VNI (Instance 1)", "Number of Egress VTEP, VNI : ", 79, [])
            empty_tbl.set_column_widths([52, 11, 6, 6, 4])
            empty_tbl.add_header(["VTEP Address", "Egress VNI", "Oper", "Mcast", "Num"])
            empty_tbl.add_header(["", "", "State", "", "MACs"])
            for line in empty_tbl.print_table():
                output.print_line(line)
        output.print_line("\nTry SR Linux command: show network-instance * vxlan-interface")

    def _fetch_state(self, state, arguments, mode=None):
        chassis_type_path = build_path("/platform/chassis/type")
        self._chassis_type = ""

        try:
            self._chassis_type = (
                state.server.get_data_store(DataStore.State)
                .get_data(chassis_type_path, recursive=False)
                .platform.get()
                .chassis.get()
                .type
            )
        except ServerError:
            self._chassis_type = ""

        if mode in (None, "mpls") and self._is_mpls_capable(state):
            self._fetch_state_mpls(state, arguments)

        if mode in (None, "vxlan") and self._is_vxlan_capable(state):
            self._fetch_state_vxlan(state, arguments)

    def _get_service_name(self, state, arguments):
        if arguments and hasattr(arguments, "has_node") and arguments.has_node("id"):
            val = arguments.get_value_or("id", "name", "*")
            if val:
                return val
        if state and hasattr(state, "line_commands") and state.line_commands:
            if hasattr(state.line_commands, "has_node") and state.line_commands.has_node("id"):
                val = state.line_commands.get_value_or("id", "name", "*")
                if val:
                    return val
        return "*"

    def _fetch_state_mpls(self, state, arguments):
        service_name = self._get_service_name(state, arguments)
        mpls_multicast_destinations_path = build_path(
            "/network-instance[name={netinst_name}]/protocols/bgp-evpn/bgp-instance[id=*]/mpls/bridge-table/multicast-destinations",
            netinst_name=service_name,
        )

        mpls_unicast_destinations_path = build_path(
            "/network-instance[name={netinst_name}]/protocols/bgp-evpn/bgp-instance[id=*]/mpls/bridge-table/unicast-destinations",
            netinst_name=service_name,
        )

        route_table_path = build_path(
            "/network-instance[name={netinst_name}]/route-table",
            netinst_name=service_name,
        )

        try:
            self._mpls_multicast_destinations_data = state.server.get_data_store(DataStore.State).get_data(
                mpls_multicast_destinations_path, recursive=True
            )

            self._mpls_unicast_destinations_data = state.server.get_data_store(DataStore.State).get_data(
                mpls_unicast_destinations_path, recursive=True
            )

            self._route_table_data = state.server.get_data_store(DataStore.State).get_data(
                route_table_path, recursive=True
            )
        except ServerError:
            self._mpls_multicast_destinations_data = None
            self._mpls_unicast_destinations_data = None
            self._route_table_data = None

    def _fetch_state_vxlan(self, state, arguments):
        service_name = self._get_service_name(state, arguments)
        vxlan_interface_path = build_path(
            "/network-instance[name={netinst_name}]/vxlan-interface",
            netinst_name=service_name,
        )

        tunnel_interface_path = build_path("/tunnel-interface")

        try:
            self._vxlan_interface_data = state.server.get_data_store(DataStore.State).get_data(
                vxlan_interface_path, recursive=True
            )

            self._tunnel_interface_data = state.server.get_data_store(DataStore.State).get_data(
                tunnel_interface_path, recursive=True
            )
        except ServerError:
            self._vxlan_interface_data = None
            self._tunnel_interface_data = None

    def _populate_data_mpls(self, data):
        tunnels = {}
        ethernet_segments = {}

        # multicast
        if self._mpls_multicast_destinations_data and hasattr(
            self._mpls_multicast_destinations_data, "network_instance"
        ):
            for network_instance in self._mpls_multicast_destinations_data.network_instance.items():
                tunnels[network_instance.name] = self.get_mpls_multicast_tunnels(
                    network_instance.name
                )

        # unicast
        if self._mpls_unicast_destinations_data and hasattr(
            self._mpls_unicast_destinations_data, "network_instance"
        ):
            for network_instance in self._mpls_unicast_destinations_data.network_instance.items():
                existing_tunnels = (
                    tunnels[network_instance.name]
                    if network_instance.name in tunnels.keys()
                    else []
                )
                unicast_tunnels = self.get_mpls_unicast_tunnels(network_instance.name)
                existing_tunnels.extend(unicast_tunnels)
                tunnels[network_instance.name] = existing_tunnels

            # ethernet segments
            for network_instance in self._mpls_unicast_destinations_data.network_instance.items():
                ethernet_segments[network_instance.name] = self.get_mpls_ethernet_segments(
                    network_instance.name
                )

        # convert to schema node
        for netinst in tunnels:
            netinst_node = data.network.create(netinst)
            for tunnel in sorted(tunnels[netinst], key=lambda x: x.tep_address):
                tunnel.to_node(netinst_node)

        for netinst in ethernet_segments:
            if len(ethernet_segments[netinst]) > 0:
                netinst_node = (
                    data.network.create(netinst)
                    if data.network.get(netinst) is None
                    else data.network.get(netinst)
                )

                for es in ethernet_segments[netinst]:
                    es.to_node(netinst_node)

        return data

    def _get_vxlan_bridge_table(self, vxlan_interface_name):
        if not self._tunnel_interface_data or not hasattr(self._tunnel_interface_data, "tunnel_interface"):
            return None
        parts = str(vxlan_interface_name).split(".", 1)
        if len(parts) != 2:
            return None
        intf, subintf = parts
        ti = self._tunnel_interface_data.tunnel_interface.get(intf)
        if ti is None or not hasattr(ti, "vxlan_interface"):
            return None
        try:
            vxlan_intf = ti.vxlan_interface.get(int(subintf))
        except ValueError:
            return None
        if vxlan_intf is None or not hasattr(vxlan_intf, "bridge_table") or not vxlan_intf.bridge_table.exists():
            return None
        return vxlan_intf.bridge_table.get()

    def _populate_data_vxlan(self, data):
        tunnels = {}
        ethernet_segments = {}

        if self._vxlan_interface_data and hasattr(self._vxlan_interface_data, "network_instance"):
            for network_instance in self._vxlan_interface_data.network_instance.items():
                for vxlan_interface in network_instance.vxlan_interface.items():
                    if self._get_vxlan_bridge_table(vxlan_interface.name) is None:
                        continue
                    tunnels.setdefault(network_instance.name, []).extend(
                        self.get_vxlan_tunnels(vxlan_interface.name)
                    )
                    ethernet_segments.setdefault(network_instance.name, []).extend(
                        self.get_vxlan_ethernet_segments(vxlan_interface.name)
                    )

        # convert to schema node
        for netinst in tunnels:
            netinst_node = data.network.create(netinst)
            for tunnel in sorted(tunnels[netinst], key=lambda x: x.tep_address):
                tunnel.to_node(netinst_node)

            for es in ethernet_segments.get(netinst, []):
                es.to_node(netinst_node)

        return data

    def get_mpls_multicast_tunnels(self, netinst_name):
        tunnels = []
        netinst = self._mpls_multicast_destinations_data.network_instance.get(
            netinst_name
        )
        if netinst is None or not netinst.protocols.exists() or not netinst.protocols.get().bgp_evpn.exists():
            return tunnels

        for bgp_instance in netinst.protocols.get().bgp_evpn.get().bgp_instance.items():
            if not bgp_instance.mpls.exists() or not bgp_instance.mpls.get().bridge_table.exists():
                continue
            bt = bgp_instance.mpls.get().bridge_table.get()
            if not bt.multicast_destinations.exists():
                continue
            for mc_tunnel in bt.multicast_destinations.get().destination.items():
                tunnels.append(
                    MPLSTunnel(
                        mc_tunnel.tunnel_id,
                        mc_tunnel.tep,
                        mc_tunnel.evi_label,
                        self.get_transport_tunnel(
                            netinst_name, mc_tunnel.destination_index
                        ),
                        "Up",
                        "bum",
                        "N/A",
                    )
                )

        return tunnels

    def get_mpls_unicast_tunnels(self, netinst_name):
        tunnels = []
        netinst = self._mpls_unicast_destinations_data.network_instance.get(
            netinst_name
        )
        if netinst is None or not netinst.protocols.exists() or not netinst.protocols.get().bgp_evpn.exists():
            return tunnels

        for bgp_instance in netinst.protocols.get().bgp_evpn.get().bgp_instance.items():
            if not bgp_instance.mpls.exists() or not bgp_instance.mpls.get().bridge_table.exists():
                continue
            bt = bgp_instance.mpls.get().bridge_table.get()
            if not bt.unicast_destinations.exists():
                continue
            for mc_tunnel in bt.unicast_destinations.get().destination.items():
                tunnels.append(
                    MPLSTunnel(
                        mc_tunnel.tunnel_id,
                        mc_tunnel.tep,
                        mc_tunnel.evi_label,
                        self.get_transport_tunnel(
                            netinst_name, mc_tunnel.destination_index
                        ),
                        "Up",
                        "None",
                        mc_tunnel.mac_table.get().mac.count() if mc_tunnel.mac_table.exists() else 0,
                    )
                )

        return tunnels

    def get_mpls_ethernet_segments(self, netinst_name):
        ethernet_segments = []
        netinst = self._mpls_unicast_destinations_data.network_instance.get(
            netinst_name
        )
        if netinst is None or not netinst.protocols.exists() or not netinst.protocols.get().bgp_evpn.exists():
            return ethernet_segments

        for bgp_instance in netinst.protocols.get().bgp_evpn.get().bgp_instance.items():
            if not bgp_instance.mpls.exists() or not bgp_instance.mpls.get().bridge_table.exists():
                continue
            bt = bgp_instance.mpls.get().bridge_table.get()
            if not bt.unicast_destinations.exists():
                continue
            for es_destination in bt.unicast_destinations.get().es_destination.items():
                updates = []
                if hasattr(es_destination, "mac_table") and es_destination.mac_table.exists():
                    for mac in es_destination.mac_table.get().mac.items():
                        if hasattr(mac, "last_update") and mac.last_update:
                            ts = str(mac.last_update).split()[0]
                            try:
                                updates.append(datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ"))
                            except Exception:
                                try:
                                    updates.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
                                except Exception:
                                    pass
                ethernet_segments.append(
                    EthernetSegment(
                        es_destination.esi,
                        sum(
                            mac_type.total_entries
                            for mac_type in es_destination.statistics.get().mac_type.items()
                        ) if es_destination.statistics.exists() else 0,
                        ", ".join(
                            destination.tep
                            for destination in es_destination.destination.items()
                        ),
                        max(updates).strftime("%Y-%m-%d %H:%M:%S") if updates else "N/A",
                    )
                )

        return ethernet_segments

    def get_vxlan_tunnels(self, vxlan_interface_name):
        tunnels = []
        bridge_table = self._get_vxlan_bridge_table(vxlan_interface_name)
        if bridge_table is None:
            return tunnels

        # BUM tunnels
        if hasattr(bridge_table, "multicast_destinations") and bridge_table.multicast_destinations.exists():
            for (
                mcast_tunnel
            ) in bridge_table.multicast_destinations.get().destination.items():
                tunnels.append(
                    VXLANTunnel(
                        mcast_tunnel.vtep,
                        mcast_tunnel.vni,
                        mcast_tunnel.multicast_forwarding,
                        "Up",
                        "N/A",
                    )
                )

        # Unicast tunnels
        if hasattr(bridge_table, "unicast_destinations") and bridge_table.unicast_destinations.exists():
            for (
                unicast_tunnel
            ) in bridge_table.unicast_destinations.get().destination.items():
                tunnels.append(
                    VXLANTunnel(
                        unicast_tunnel.vtep,
                        unicast_tunnel.vni,
                        "None",
                        "Up",
                        sum(
                            mac_type.total_entries
                            for mac_type in unicast_tunnel.statistics.get().mac_type.items()
                        ) if unicast_tunnel.statistics.exists() else 0,
                    )
                )

        return tunnels

    def get_vxlan_ethernet_segments(self, vxlan_interface_name):
        ethernet_segments = []
        bridge_table = self._get_vxlan_bridge_table(vxlan_interface_name)
        if bridge_table is None or not hasattr(bridge_table, "unicast_destinations") or not bridge_table.unicast_destinations.exists():
            return ethernet_segments

        # Ethernet Segments
        for es in bridge_table.unicast_destinations.get().es_destination.items():
            updates = []
            if hasattr(es, "mac_table") and es.mac_table.exists():
                for mac in es.mac_table.get().mac.items():
                    if hasattr(mac, "last_update") and mac.last_update:
                        ts = str(mac.last_update).split()[0]
                        try:
                            updates.append(datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ"))
                        except Exception:
                            try:
                                updates.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
                            except Exception:
                                pass
            ethernet_segments.append(
                EthernetSegment(
                    es.esi,
                    sum(
                        mac_type.total_entries
                        for mac_type in es.statistics.get().mac_type.items()
                    ) if es.statistics.exists() else 0,
                    ", ".join([vtep.address for vtep in es.vtep.items()]),
                    max(updates).strftime("%Y-%m-%d %H:%M:%S") if updates else "N/A",
                )
            )

        return ethernet_segments

    def get_transport_tunnel(self, netinst_name, next_hop_group_id):
        if not self._route_table_data or not hasattr(self._route_table_data, "network_instance"):
            return "N/A"
        netinst = self._route_table_data.network_instance.get(netinst_name)
        if netinst is None or not netinst.route_table.exists():
            return "N/A"
        rt = netinst.route_table.get()
        if not hasattr(rt, "next_hop_group"):
            return "N/A"
        next_hop_group = rt.next_hop_group.get(next_hop_group_id)
        if next_hop_group is None or next_hop_group.next_hop.count() == 0:
            return "N/A"

        resolved = []
        for nh_entry in next_hop_group.next_hop.items():
            nh = rt.next_hop.get(nh_entry.next_hop)
            if nh is not None and hasattr(nh, "resolving_tunnel") and nh.resolving_tunnel.exists():
                resolving_tunnel = nh.resolving_tunnel.get()
                tnl_str = f"{resolving_tunnel.tunnel_type}:{resolving_tunnel.tunnel_id}"
                if tnl_str not in resolved:
                    resolved.append(tnl_str)
        return ", ".join(resolved) if resolved else "N/A"

    def _set_formatters(self, data, arguments, state, mode=None):
        if mode == "vxlan" or (mode is None and self._is_vxlan_capable(state)):
            data.set_formatter("/network/vxlan_tunnel", VXLANVTEPFormatter())
            data.set_formatter("/network/ethernet_segment", VXLANESFormatter())

        if mode == "mpls" or (mode is None and self._is_mpls_capable(state)):
            data.set_formatter("/network/mpls_tunnel", MPLSVTEPFormatter())
            data.set_formatter("/network/ethernet_segment", MPLSESFormatter())


class VXLANVTEPFormatter(Formatter):
    def iter_format(self, entry, max_width):
        pass

    def iter_format_type(self, children, max_width):
        data = [
            [
                child.tep_address,
                child.egress_vni,
                child.oper_state,
                child.mcast,
                child.num_macs,
            ]
            for child in children.items()
        ]
        vtep_instance_1 = SROSTable(
            "Egress VTEP, VNI (Instance 1)", "Number of Egress VTEP, VNI : ", 79, data
        )
        vtep_instance_1.set_column_widths([52, 11, 6, 6, 4])
        vtep_instance_1.add_header(
            ["VTEP Address", "Egress VNI", "Oper", "Mcast", "Num"]
        )
        vtep_instance_1.add_header(["", "", "State", "", "MACs"])
        yield from vtep_instance_1.print_table()

        # second VTEP destination table currently not supported on SXR
        vtep_instance_2 = SROSTable(
            "Egress VTEP, VNI (Instance 2)", "Number of Egress VTEP, VNI : ", 79, []
        )
        vtep_instance_2.set_column_widths([52, 11, 6, 6, 4])
        vtep_instance_2.add_header(
            ["VTEP Address", "Egress VNI", "Oper", "Mcast", "Num"]
        )
        vtep_instance_2.add_header(["", "", "State", "", "MACs"])
        yield from vtep_instance_2.print_table()


class VXLANESFormatter(Formatter):
    def iter_format(self, entry, max_width):
        pass

    def iter_format_type(self, children, max_width):
        data = [
            [child.esi, child.num_macs, child.last_update] for child in children.items()
        ]
        es_instance_1 = SROSTable(
            "BGP EVPN-VXLAN Ethernet Segment Dest (Instance 1)",
            "Number of entries: ",
            79,
            data,
        )
        es_instance_1.set_column_widths([40, 16, 23])
        es_instance_1.add_header(["Eth SegId", "Num. Macs", "Last Update"])
        yield from es_instance_1.print_table()

        es_instance_2 = SROSTable(
            "BGP EVPN-VXLAN Ethernet Segment Dest (Instance 2)",
            "Number of entries: ",
            79,
            [],
        )
        es_instance_2.set_column_widths([40, 16, 23])
        es_instance_2.add_header(["Eth SegId", "Num. Macs", "Last Update"])
        yield from es_instance_2.print_table()


class MPLSVTEPFormatter(Formatter):
    def iter_format(self, entry, max_width):
        pass

    def iter_format_type(self, children, max_width):
        data = [
            [
                child.tep_address,
                child.transport_tnl,
                child.egress_label,
                child.oper_state,
                child.mcast,
                child.num_macs,
            ]
            for child in children.items()
        ]
        vtep_instance_1 = SROSTable(
            "BGP EVPN-MPLS Dest (Instance 1)", "Number of entries: ", 79, data
        )
        vtep_instance_1.set_column_widths([32, 18, 11, 6, 7, 4])
        vtep_instance_1.add_header(
            ["TEP Address", "Transpor:Tnl", "Egr Label", "Oper", "Mcast", "Num"]
        )
        vtep_instance_1.add_header(["", "", "", "State", "", "MACs"])
        yield from vtep_instance_1.print_table()

        vtep_instance_2 = SROSTable(
            "BGP EVPN-MPLS Dest (Instance 2)", "Number of entries: ", 79, []
        )
        vtep_instance_2.set_column_widths([32, 18, 11, 6, 7, 4])
        vtep_instance_2.add_header(
            ["TEP Address", "Transpor:Tnl", "Egr Label", "Oper", "Mcast", "Num"]
        )
        vtep_instance_2.add_header(["", "", "", "State", "", "MACs"])
        yield from vtep_instance_2.print_table()


class MPLSESFormatter(Formatter):
    def iter_format(self, entry, max_width):
        pass

    def iter_format_type(self, children, max_width):
        data = [
            [child.esi, child.num_macs, child.last_update] for child in children.items()
        ]
        es_instance_1 = SROSTable(
            "BGP EVPN-MPLS Ethernet Segment Dest (Instance 1)",
            "Number of entries: ",
            79,
            data,
        )
        es_instance_1.set_column_widths([32, 24, 23])
        es_instance_1.add_header(["Eth SegId", "Num. Macs", "Last Update"])
        yield from es_instance_1.print_table()

        es_instance_2 = SROSTable(
            "BGP EVPN-MPLS Ethernet Segment Dest (Instance 2)",
            "Number of entries: ",
            79,
            [],
        )
        es_instance_2.set_column_widths([32, 24, 23])
        es_instance_2.add_header(["Eth SegId", "Num. Macs", "Last Update"])
        yield from es_instance_2.print_table()


class SROSTable:
    def __init__(self, table_title, table_footer, width, data):
        self.table_title = table_title
        self.table_footer = table_footer
        self.width = width
        self.data = data
        self.headers = []  # stores lists of header names (each one is printed under the other)
        self.columns = []  # stores the width of each column

    def set_column_widths(self, widths):
        self.columns = widths

    def add_header(self, header):
        self.headers.append(header)

    def print_table(self):
        yield from self.print_title()
        yield from self.print_header()

        if len(self.data) == 0:
            yield "No Matching Entries"
        else:
            for entry in self.data:
                yield "".join(
                    [
                        self.padded_string(str(e), self.columns[i])
                        for i, e in enumerate(entry)
                    ]
                )
            yield "-" * self.width
            yield f"{self.table_footer}{len(self.data)}"
            yield "-" * self.width

        yield "=" * self.width

    def print_title(self):
        yield f"\n{'=' * self.width}"
        yield self.table_title
        yield "=" * self.width

    def print_header(self):
        for header in self.headers:
            yield "".join(
                [
                    self.padded_string(str(h), self.columns[i])
                    for i, h in enumerate(header)
                ]
            )
        yield "-" * self.width

    def padded_string(self, text, width):
        return f"{text}{' ' * max(0, width - len(text))}"


class MPLSTunnel:
    def __init__(
        self,
        tunnel_id,
        tep_address,
        egress_label,
        transport_tnl,
        oper_state,
        mcast,
        num_macs,
    ):
        self.tunnel_id = tunnel_id
        self.tep_address = tep_address
        self.egress_label = egress_label
        self.transport_tnl = transport_tnl
        self.oper_state = oper_state
        self.mcast = mcast
        self.num_macs = num_macs

    def to_node(self, netinst_node):
        mpls_tunnel_node = netinst_node.mpls_tunnel.create(
            self.tunnel_id, self.egress_label, self.mcast
        )
        mpls_tunnel_node.tep_address = self.tep_address
        mpls_tunnel_node.num_macs = self.num_macs
        mpls_tunnel_node.oper_state = self.oper_state
        mpls_tunnel_node.transport_tnl = self.transport_tnl


class VXLANTunnel:
    def __init__(self, tep_address, egress_vni, mcast, oper_state, num_macs):
        self.tep_address = tep_address
        self.egress_vni = egress_vni
        self.mcast = mcast
        self.oper_state = oper_state
        self.num_macs = num_macs

    def to_node(self, netinst_node):
        vxlan_tunnel_node = netinst_node.vxlan_tunnel.create(
            self.tep_address, self.egress_vni, self.mcast
        )
        vxlan_tunnel_node.oper_state = self.oper_state
        vxlan_tunnel_node.num_macs = self.num_macs


class EthernetSegment:
    def __init__(self, esi, num_macs, member_vteps, last_update):
        self.esi = esi
        self.num_macs = num_macs
        self.member_vteps = member_vteps
        self.last_update = last_update

    def to_node(self, netinst_node):
        es_node = netinst_node.ethernet_segment.create(self.esi)
        es_node.num_macs = self.num_macs
        es_node.member_vteps = self.member_vteps
        es_node.last_update = self.last_update
