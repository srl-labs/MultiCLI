"""
CLI Plugin for Junos-like show "ethernet-switching" commands
Author: Miguel Redondo (Michel)
Email: miguel.redondo_ferrero@nokia.com

Provides the following commands:
- show ethernet-switching table
- show ethernet-switching table instance <instance_name>
- show ethernet-switching table vlan-id <vlan_id>
- show ethernet-switching table interface <interface_name>

"""
from srlinux.location import build_path
from srlinux.data import ColumnFormatter, Data, Borders, Alignment, Border, Formatter
from srlinux.mgmt.cli import CliPlugin, CommandNodeWithArguments
from srlinux.mgmt.cli.cli_loader import CliLoader
from srlinux.mgmt.cli.cli_output import CliOutput
from srlinux.mgmt.cli.cli_state import CliState
from srlinux.schema import FixedSchemaRoot
from srlinux.data.utilities import Percentage, print_line, Width
import itertools
from srlinux import strings
import logging
import re

#logger = logging.getLogger(__name__)
#logger.level = logging.DEBUG

class EthernetSwitchingReport:
    '''
        'show ethernet-switching table' : Gives all MAC Table entries
    '''
    MAC_CODES = {
    'static': 'T',
    'duplicate': 'D',
    'learnt' : 'L',
    'irb-interface' : 'I',
    'evpn' : 'E',
    'evpn-static': 'ET',
    'irb-interface-anycast': 'IA',
    'proxy-anti-spoof': 'P',
    'reserved': 'V',
    'eth-cfm': 'C',
    'irb-interface-vrrp': 'IR'
    }

    def get_schema_instance(self):
        root = FixedSchemaRoot()
        network = root.add_child('Network', key='Name')
        network.add_child('Statistics',
                       fields=['Total', 'Active', 'Failed'])
        network.add_child('Ethernet Switching table',
                          keys=['Vlan', 'Address'],
                          fields=[
                              'MAC Flags',
                              'Logical Interface',
                              'SVLBNH/VENH Index',
                              'Active Source'])
        return root

    def _show_table_instance(self, state: CliState, output, arguments: CommandNodeWithArguments, **kwargs,):
        """Main display function"""
        self._state = state
        self._arguments = arguments
        if arguments.has_node('instance'):
            netinst_data = self._fetch_state_network(arguments.get('instance','name'))
        elif arguments.has_node('interface'):
            netinst_data = self._fetch_state_network('*')
        elif arguments.has_node('vlan'):
            netinst_data = self._fetch_state_network('*')
        else:
            netinst_data = self._fetch_state_network('*')

        data_root = Data(arguments.schema)
        self._set_all_formatters(data_root)
        with output.stream_data(data_root):
            self._populate_mac_table(netinst_data, data_root)
        output.print(srlinux_suggested_command)
        data_root.synchronizer.flush_children(data_root)

    def _fetch_state_network(self, netinst_name):
        table_path = build_path(
            '/network-instance[name={name}]',
            name=netinst_name
        )
        return self._state.server_data_store.get_data(table_path, recursive=False)

    def _fetch_state_network_interfaces(self, netinst_name):
        table_path = build_path(
            '/network-instance[name={name}]/interface[name=*]',
            name=netinst_name
        )
        return self._state.server_data_store.get_data(table_path, recursive=False, include_container_children=True)

    def _fetch_state_mac_table(self, netinst_name, mac_address=None):
        table_path = build_path(
            '/network-instance[name={name}]/bridge-table/mac-table/mac[address={mac}]',
            name=netinst_name,
            mac=mac_address or '*'
        )
        return self._state.server_data_store.stream_data(table_path, recursive=True)

    def _fetch_state_mac_table_stats(self, netinst_name):
        table_path = build_path(
            '/network-instance[name={name}]/bridge-table/statistics',
            name=netinst_name
        )
        return self._state.server_data_store.stream_data(table_path, recursive=False, include_container_children=True)

    def _fetch_state_subinterface(self, int_name, subint_index):
        table_path = build_path(
            '/interface[name={name}]/subinterface[index={index}]',
            name=int_name,
            index=str(subint_index)
        )
        return self._state.server_data_store.get_data(table_path, recursive=True, include_container_children=True)

    def _fetch_state_int_hw_mac(self, int_name):
        table_path = build_path(
            '/interface[name={name}]/ethernet/hw-mac-address',
            name=int_name
        )
        return self._state.server_data_store.stream_data(table_path, recursive=False, include_container_children=True)

    def _fetch_state_irb_subinterface_anycast_mac(self, int_name, subint_index):
        table_path = build_path(
            '/interface[name={name}]/subinterface[index={index}]/anycast-gw/anycast-gw-mac',
            name=int_name,
            index=str(subint_index)
        )
        return self._state.server_data_store.stream_data(table_path, recursive=False, include_container_children=True)

    def _get_interface_name_index_from_netinstance_data(self, network_interface_data ):
        interface_name_index_list=[]
        for network_interface_entry in network_interface_data.get_descendants('/network-instance/interface'):
            # get interface name and index for cases with interface-ref and without it
            if "interface-ref" in network_interface_entry.child_names:
                interface_ref = network_interface_entry.interface_ref.get()
                has_interface_ref = interface_ref.interface is not None and interface_ref.subinterface is not None
                if has_interface_ref:
                    interface_name = interface_ref.interface
                    subint_index = interface_ref.subinterface
                else:
                    interface_name, subint_index = network_interface_entry.name.split('.', 1)
            else:
                interface_name, subint_index = network_interface_entry.name.split('.', 1)

            if any(sub in interface_name for sub in ["irb", "lo"]):
                continue

            # get vlan information from interface
            subinterface_data = self._fetch_state_subinterface(interface_name, subint_index)
            for subinterface in subinterface_data.get_descendants('/interface/subinterface'):
                vlan_encap = subinterface.vlan.get().encap.get()
                if vlan_encap.single_tagged.exists():
                    vlan = vlan_encap.single_tagged.get().vlan_id
                    tagging = vlan if vlan else 'null'
                    interface_name_index_list.append({"name": interface_name, "index": str(subint_index), "tagging": str(tagging)})
                elif self._state.system_features.dot1q_vlan_ranges and vlan_encap.single_tagged_range.exists():
                    vlan_ranges = vlan_encap.single_tagged_range.get()
                    tag_ranges = ','.join(f'{entry.range_low_vlan_id}-{entry.high_vlan_id}' for entry in vlan_ranges.low_vlan_id.items())
                    interface_name_index_list.append({"name": interface_name, "index": str(subint_index), "tagging": str(tag_ranges)})
                elif vlan_encap.untagged.exists():
                    interface_name_index_list.append({"name": interface_name, "index": str(subint_index), "tagging": "untagged"})
                else:
                    interface_name_index_list.append({"name": interface_name, "index": str(subint_index), "tagging": "null"})
        
        return interface_name_index_list

    def _get_irbs_from_netinstance_data(self, network_interface_data):
        interface_name_index_list=[]
        for network_interface_entry in network_interface_data.get_descendants('/network-instance/interface'):
            # get interface name and index for cases with interface-ref and without it
            if "interface-ref" in network_interface_entry.child_names:
                interface_ref = network_interface_entry.interface_ref.get()
                has_interface_ref = interface_ref.interface is not None and interface_ref.subinterface is not None
                if has_interface_ref:
                    interface_name = interface_ref.interface
                    subint_index = interface_ref.subinterface
                else:
                    interface_name, subint_index = network_interface_entry.name.split('.', 1)
            else:
                interface_name, subint_index = network_interface_entry.name.split('.', 1)

            if not "irb" in interface_name:
                continue

            hw_mac_data = self._fetch_state_int_hw_mac(interface_name)
            anycast_gw_mac_data = self._fetch_state_irb_subinterface_anycast_mac(interface_name, subint_index)

            if anycast_gw_mac_data.get("interface").exists():
                anycast_gw_mac = anycast_gw_mac_data.interface.get().subinterface.get().anycast_gw.get().anycast_gw_mac
            else:
                anycast_gw_mac = ""

            hw_mac = hw_mac_data.interface.get().ethernet.get().hw_mac_address
            interface_name_index_list.append({"name": interface_name, "index": str(subint_index), "hw_mac": hw_mac, "anycast_gw_mac": anycast_gw_mac})

        return interface_name_index_list
    
    def _find_vlan(self, interfaces, query):
        # Extract interface name and index using regex
        match = re.match(r'(.+)\.(\d+)', query)
        if not match:
            return "-"

        interface_name, index = match.groups()
        index = str(index)
        # Search for the matching interface
        for entry in interfaces:
            if entry["name"] == interface_name and entry["index"] == index:
                return entry["tagging"]
        return "-"

    def _get_mac_code(self, mac_type, active):
        type = self.MAC_CODES.get(mac_type.lower(), '?')
        programming_status =  "S" if active is True else "F"
        return f'{type},{programming_status}'

    def _get_logical_interface(self, mac_entry_address, mac_entry_destination,  irb_interface_name_index_list):
        match_vxlan_interface = re.search(r'vxlan[\d.]+', mac_entry_destination)
        match_else = re.search(r'^\S+',mac_entry_destination)
        if match_vxlan_interface:
            logical_interface = match_vxlan_interface.group()
        elif "irb-interface" in mac_entry_destination:
            logical_interface = "irb(R)"
            for irb in irb_interface_name_index_list:
                if irb["hw_mac"] == mac_entry_address or irb["anycast_gw_mac"] == mac_entry_address:
                    logical_interface = f'{irb["name"]}.{irb["index"]}(R)'
        elif match_else:
            logical_interface = match_else.group()
        else:
            logical_interface = ""
        return logical_interface

    def _get_active_source(self, mac_entry_destination):
        esi_pattern = r'esi:([\dA-Fa-f:]+)'
        vtep_pattern = r'vtep:([\dA-Fa-f:.]+)'
        esi_match = re.search(esi_pattern, mac_entry_destination)
        if esi_match:
            return esi_match.group(1)
        vtep_match = re.search(vtep_pattern, mac_entry_destination)
        if vtep_match:
            return vtep_match.group(1)
        return ""

    def _populate_mac_table(self, netinst_server_data, data_root):
        subinterface_name = self._arguments.get_value_or('interface','name',None)
        interface_as_argument = True if subinterface_name and "." not in subinterface_name else False
        vlan_value = self._arguments.get_value_or('vlan','value',None)

        for netinst in netinst_server_data.network_instance.items():
            if netinst.type != 'mac-vrf':
                continue
            netinst_data = data_root.network.create(netinst.name)
            mac_data = self._fetch_state_mac_table(netinst.name)
            mac_data_stats = self._fetch_state_mac_table_stats(netinst.name)
            network_interface_data = self._fetch_state_network_interfaces(netinst.name)
            irb_interface_name_index_list = self._get_irbs_from_netinstance_data(network_interface_data)
            interface_name_index_list = self._get_interface_name_index_from_netinstance_data (network_interface_data)

            for mac_entry in mac_data.get_descendants('/network-instance/bridge-table/mac-table/mac'):
                logical_subinterface = self._get_logical_interface(mac_entry.address, mac_entry.destination, irb_interface_name_index_list)
                logical_interface = logical_subinterface.split('.')[0] if logical_subinterface else None
                vlan = self._find_vlan(interface_name_index_list,logical_subinterface)
                # if an interface (without the "".subint") is given as argument we populate the mac table for all its subinterfaces
                if subinterface_name is not None and subinterface_name != logical_subinterface:
                    if not interface_as_argument or subinterface_name != logical_interface:
                        continue
                if vlan_value is not None and vlan_value != vlan:
                     continue

                mac = netinst_data.ethernet_switching_table.create( vlan, mac_entry.address  )
                mac.logical_interface = logical_subinterface
                mac.svlbnh_venh_index = mac_entry.destination_index
                active = False if mac_entry.not_programmed_reason else True
                mac.mac_flags = self._get_mac_code(mac_entry.type, active)
                mac.active_source = self._get_active_source(mac_entry.destination)
                mac.synchronizer.flush_fields(mac)

            for mac_stat_entry in mac_data_stats.get_descendants('/network-instance/bridge-table/statistics'):
                mac_stat = netinst_data.statistics.create()
                mac_stat.total = mac_stat_entry.total_entries
                mac_stat.active = mac_stat_entry.active_entries
                mac_stat.failed = mac_stat_entry.failed_entries
                mac_stat.synchronizer.flush_fields(mac_stat)

            netinst_data.synchronizer.flush_fields(netinst_data)
            netinst_data.synchronizer.flush_children(netinst_data.ethernet_switching_table)
            netinst_data.synchronizer.flush_children(netinst_data.statistics)

    def _set_all_formatters(self, data):
        data.set_formatter('/Network', NetworkHeaderFormatter())
        data.set_formatter('/Network/Statistics', StatisticsFormatter())
        data.set_formatter('/Network/Ethernet Switching table',
                                    ColumnFormatter(
                                        ancestor_keys=False,
                                        header_alignment=Alignment.Left,
                                        horizontal_alignment={
                                            'vlan': Alignment.Left,
                                            'address': Alignment.Left,
                                            'mac_flags': Alignment.Left,
                                            'logical_interface': Alignment.Left,
                                            'svlbnh_venh_index':Alignment.Left,
                                            'active_source':Alignment.Left
                                        },
                                        widths={
                                            'vlan': 9,
                                            'address': 18,
                                            'mac_flags': 10,
                                            'logical_interface': 18,
                                            'svlbnh_venh_index':12,
                                            'active_source':30
                                            },
                                        print_on_data=True,
                                        header=False,
                                        borders=Borders.Nothing
                                    )
                           )

class NetworkHeaderFormatter(Formatter):
    def iter_format(self, entry, max_width):
        if entry.ethernet_switching_table.exists():
            yield print_line(max_width, character=' ')
            yield self._format_macflags_header()
            yield print_line(max_width, character=' ')
            yield from entry.statistics.iter_format(max_width)
            yield f'Routing instance : {entry.name}'
            yield from self._format_header()
            yield from entry.ethernet_switching_table.iter_format(max_width)

    def _format_macflags_header(self):
        MAC_CODES_HEADER = """MAC flags (T - static MAC, D - duplicate MAC, L - locally learned, I - irb interface, E - EVPN
            ET - EVPN static, IA - irb interface anycast, P - proxy anti spoof, V - reserved MAC,
            C - eth-cfm, IR - irb interface vrrp, F - programming failed,  S - programming success)
        """
        return MAC_CODES_HEADER
    
    def _format_header(self):
        return (
            "Vlan        MAC                  MAC          Logical Interface    SVLBNH/VENH    Active Source",
            "id          address              flags        interface            Index          Source       "
        )

class StatisticsFormatter(Formatter):
    def __init__(self, tag_value_space=0):
        super(StatisticsFormatter, self).__init__()
        self._tag_value_spacing = tag_value_space

    def iter_format(self, entry, max_width):
        yield f'Ethernet switching table : {entry.total:4} Total {entry.active:4} Active {entry.failed:4} Failed'


srlinux_suggested_command = """ 
------------------------------------------------------------------------------------------------
Try SR Linux command:
->   show network-instance <instance> bridge-table mac-table all
->   show interface ethernet-x/y.z | grep Encapsulation
"""

