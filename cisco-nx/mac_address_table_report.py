"""
CLI Plugin for Cisco-like show "mac" commands
Author: Miguel Redondo (Michel)
Email: miguel.redondo_ferrero@nokia.com

Provides the following commands:
- show mac address-table
- show mac address-table instance <instance_name>
- show mac address-table vlan <vlan_id>
- show mac address-table interface <interface_name>
- show mac address-table vni <vni_id>

"""
from srlinux.location import build_path
from srlinux.data import ColumnFormatter, Data, Borders, Alignment, Border, Formatter
from srlinux.data.data import DataChildrenOfType
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

class MacAddressTableReport:
    '''
        'show mac address-table' : Gives all MAC Table entries
    '''
    def get_schema_instance(self):
        root = FixedSchemaRoot()
        mac_add_table = root.add_child('Mac Address table', fields=['header'])
        mac_add_table.add_child('MAC',
                          keys=['MAC Flags', 'Vlan', 'Address','Type','Age','Secure','NTFY','Ports','instance'])
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
        elif arguments.has_node('vni'):
            netinst_data = self._fetch_state_network('*')
        else:
            netinst_data = self._fetch_state_network('*')

        data_root = Data(arguments.schema)
        self._set_all_formatters(data_root)
        with output.stream_data(data_root):
            self._populate_mac_table(netinst_data, data_root)
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

    def _fetch_state_network_vxlan_interfaces(self, netinst_name):
        table_path = build_path(
            '/network-instance[name={name}]/vxlan-interface[name=*]',
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

    def _fetch_state_subinterface(self, int_name, subint_index):
        table_path = build_path(
            '/interface[name={name}]/subinterface[index={index}]',
            name=int_name,
            index=str(subint_index)
        )
        return self._state.server_data_store.get_data(table_path, recursive=True, include_container_children=True)

    def _fetch_state_tunnel_interface(self, tunnel_name, tunnel_index):
        table_path = build_path(
            '/tunnel-interface[name={name}]/vxlan-interface[index={index}]/ingress/vni',
            name=tunnel_name,
            index=tunnel_index
        )
        return self._state.server_data_store.get_data(table_path, recursive=False, include_container_children=True)

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

    def _fetch_state_mac_learning(self, netinst_name, mac_address=None):
        table_path = build_path(
            '/network-instance[name={name}]/bridge-table/mac-learning/learnt-entries/mac[address={mac}]',
            name=netinst_name,
            mac=mac_address or '*'
        )
        return self._state.server_data_store.stream_data(table_path, recursive=False)

    def _get_vni_from_netinst_data (self, network_vxlan_interface_data):
        vxlan_interface_name_index_list=[]
        for network_vxlan_interface_entry in network_vxlan_interface_data.get_descendants('/network-instance/vxlan-interface'):
            vxlan_interface_name, subint_index = network_vxlan_interface_entry.name.split('.', 1)
            tunnel_interface_data = self._fetch_state_tunnel_interface(vxlan_interface_name, subint_index)
            for vxlan_int in tunnel_interface_data.get_descendants('/tunnel-interface/vxlan-interface'):
                vni = vxlan_int.ingress.get().vni
                vxlan_interface_name_index_list.append({"name": vxlan_interface_name, "index": str(subint_index), "vni": str(vni)})
        return vxlan_interface_name_index_list

    def _get_interface_name_index_from_netinstance_data(self,  network_interface_data  ):
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

    def _get_mac_code(self, mac_type):
        if mac_type=="learnt":
            return "*"
        if mac_type=="evpn":
            return "C"
        if "irb-interface" in mac_type:
            return "G"
        return "*"

    def _get_type(self, mac_type):
        static_dynamic =  "dynamic" if mac_type=="evpn" or mac_type=="learnt" else "static"
        return static_dynamic

    def _get_logical_interface(self, mac_entry_destination):
        match_vxlan_interface = re.search(r'vxlan[\d.]+', mac_entry_destination)
        match_else = re.search(r'^\S+',mac_entry_destination)

        if match_vxlan_interface:
            logical_interface = match_vxlan_interface.group()
        elif match_else:
            logical_interface = match_else.group()
        else:
            logical_interface = ""

        return logical_interface


    def _get_port_info(self, mac_entry_address, mac_entry_destination, mac_entry_destination_type, irb_interface_name_index_list):
        # returns:
        # "destination ethernet-1/11.110" -> ethernet-1/11.110
        # "vxlan-interface:vxlan1.110 vtep:192.168.255.2 vni:110" -> vxlan1.110(192.168.255.2)
        # "vxlan-interface:vxlan1.2 esi:00:00:00:00:34:00:00:00:00:02" -> vxlan1.110(00:00:00:00:34:00:00:00:00:02)
        # destination irb -> irb1.3
        # "" as fallback

        if mac_entry_destination_type =="vxlan":
            esi_match = re.search(r'esi:([\dA-Fa-f:]+)', mac_entry_destination)
            match_ip_vtep = re.search(r'vtep:([\dA-Fa-f:.]+)', mac_entry_destination)
            match_vxlan_interface = re.search(r'vxlan[\d.]+', mac_entry_destination)
            if match_vxlan_interface and esi_match:
                return f'{match_vxlan_interface.group()}({esi_match.group(1)})'
            if match_vxlan_interface and match_ip_vtep:
                return f'{match_vxlan_interface.group()}({match_ip_vtep.group(1)})'

        if mac_entry_destination_type =="sub-interface":
            match_all = re.search(r'^\S+',mac_entry_destination)
            return f'{match_all.group()}'

        if mac_entry_destination_type =="irb-interface":
            for irb in irb_interface_name_index_list:
                if irb["hw_mac"] == mac_entry_address or irb["anycast_gw_mac"] == mac_entry_address:
                    return f'{irb["name"]}.{irb["index"]}(R)'
            return f'irb(R)'

        return ""

    def _get_vni(self, mac_entry_destination , vxlan_interface_name_vni_list):
        # vni info is filled in "destination" state data but not for the case of ESI
        # we use local vni from vxlan-interface config to fill vni data
        match_vxlan_interface = re.search(r'vxlan[\d.]+', mac_entry_destination)
        if match_vxlan_interface:
            vxlan_subint =  match_vxlan_interface.group()
            for vxlan in vxlan_interface_name_vni_list:
                vxlan_subint_from_config = f'{vxlan["name"]}.{vxlan["index"]}'
                if vxlan_subint == vxlan_subint_from_config:
                    return vxlan["vni"]

        return ""

    def _populate_mac_table(self, netinst_server_data, data_root):
        subinterface_name = self._arguments.get_value_or('interface','name',None)
        interface_as_argument = True if subinterface_name and "." not in subinterface_name else False
        vlan_value = self._arguments.get_value_or('vlan','value',None)
        vni_value = self._arguments.get_value_or('vni','value',None)

        mac_add_table_data = data_root.mac_address_table.create()
        mac_add_table_data.header = ""

        for netinst in netinst_server_data.network_instance.items():
            if netinst.type != 'mac-vrf':
                continue
            mac_data = self._fetch_state_mac_table(netinst.name)
            network_interface_data = self._fetch_state_network_interfaces(netinst.name)
            network_vxlan_interface_data = self._fetch_state_network_vxlan_interfaces(netinst.name)
            irb_interface_name_index_list = self._get_irbs_from_netinstance_data(network_interface_data)
            vxlan_interface_name_vni_list = self._get_vni_from_netinst_data ( network_vxlan_interface_data)
            interface_name_index_list = self._get_interface_name_index_from_netinstance_data ( network_interface_data)

            for mac_entry in mac_data.get_descendants('/network-instance/bridge-table/mac-table/mac'):
                logical_subinterface = self._get_logical_interface(mac_entry.destination)
                port_info = self._get_port_info(mac_entry.address, mac_entry.destination, mac_entry.destination_type, irb_interface_name_index_list)
                logical_interface = logical_subinterface.split('.')[0] if logical_subinterface else None
                vlan = self._find_vlan(interface_name_index_list, logical_subinterface)
                vni = self._get_vni(mac_entry.destination, vxlan_interface_name_vni_list)

                # if an interface (without the "".subint") is given as argument we populate the mac table for all its subinterfaces
                if subinterface_name is not None and subinterface_name != logical_subinterface:
                    if not interface_as_argument or subinterface_name != logical_interface:
                        continue
                if vlan_value is not None and vlan_value != vlan:
                     continue
                if vni_value is not None and vni_value != vni:
                     continue

                mac_aging = 'NA'
                mac_learn_data = self._fetch_state_mac_learning(netinst.name, mac_entry.address)
                for mac_learnt_entry in mac_learn_data.get_descendants(
                        '/network-instance/bridge-table/mac-learning/learnt-entries/mac'):
                    mac_aging = mac_learnt_entry.aging

                mac_flags = self._get_mac_code(mac_entry.type)
                mac_ports = port_info
                mac_secure = "F"
                mac_ntfy = "F"
                mac_type = self._get_type(mac_entry.type)
                mac_age = mac_aging
                mac_instance = netinst.name
                mac = mac_add_table_data.mac.create(mac_flags, vlan, mac_entry.address, mac_type, mac_age, mac_secure, mac_ntfy, mac_ports, mac_instance   )
                mac.synchronizer.flush_fields(mac)
            mac_add_table_data.synchronizer.flush_fields(mac_add_table_data)

    def _set_all_formatters(self, data):
        data.set_formatter('/Mac Address table', NetworkHeaderFormatter())
        data.set_formatter('/Mac Address table/MAC',
                                    ColumnFormatter(
                                        ancestor_keys=False,
                                        header_alignment=Alignment.Center,
                                        horizontal_alignment={
                                            'mac_flags': Alignment.Center,
                                            'vlan': Alignment.Right,
                                            'address': Alignment.Center,
                                            'type': Alignment.Left,
                                            'age': Alignment.Left,
                                            'secure': Alignment.Center,
                                            'ntfy': Alignment.Right,
                                            'ports': Alignment.Left,
                                            'instance': Alignment.Left
                                        },
                                        widths={
                                            'mac_flags': 1,
                                            'vlan': 8,
                                            'address': 17,
                                            'type': 8,
                                            'age': 3,
                                            'secure': 1,
                                            'ntfy': 4,
                                            'ports':43,
                                            'instance': 30
                                            },
                                        print_on_data=True,
                                        header=False,
                                        borders=Borders.Nothing
                                    )
                           )

class NetworkHeaderFormatter(Formatter):
    def iter_format(self, entry, max_width):
        yield self._format_header()
        yield from self._line()
        yield from entry.mac.iter_format(max_width)
        yield from self._suggest()

    def _format_header(self):
        MAC_CODES_HEADER = """Legend:
        * - primary entry, G - Gateway MAC, (R) - Routed MAC, O - Overlay MAC
        age - seconds since last seen,+ - primary entry using vPC Peer-Link,
        (T) - True, (F) - False, C - ControlPlane MAC, ~ - vsan,
        (NA)- Not Applicable A - ESI Active Path, S - ESI Standby Path
        TL - True Learned, PS - Peer Sync, RO - Re-originate"""
        return MAC_CODES_HEADER

    def _line(self):
        return (
            '      VLAN      MAC Address        Type      age   Secure NTFY Ports                                         Instance',
            '-------------+-------------------+--------+-------+------+----+---------------------------------------------+------------------------',
        )

    def _suggest(self):
        return (
            '-------------------------------------------------------------------------------------------------------------------------------------',
            'Try SR Linux command:',
            '->   show network-instance <instance> bridge-table mac-table all',
            '->   show interface ethernet-x/y.z | grep Encapsulation'
        )

