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
from srlinux.schema.data_store import DataStore
from srlinux.data.utilities import Percentage, print_line, Width
import itertools
from srlinux import strings
import logging
import re

#logger = logging.getLogger(__name__)
#logger.level = logging.DEBUG

def _junos_to_srl_intf(name):
    """Translate Juniper JUNOS interface naming to SR Linux naming."""
    if not name or name == "*":
        return name
    raw = str(name).strip()
    sub = ""
    if "." in raw:
        base, sub_part = raw.split(".", 1)
        sub = f".{sub_part}"
    else:
        base = raw
    low = base.lower()
    m = re.match(r'^(?:et|xe|ge)-(\d+)/(\d+)/(\d+)(?::(\d+))?$', low)
    if m:
        fpc, pic, port, ch = m.group(1), m.group(2), m.group(3), m.group(4)
        if pic == "0":
            slot = int(fpc) + 1
            port_num = int(port) + 1
            chan_num = int(ch) + 1 if ch is not None else None
        else:
            slot = int(fpc)
            port_num = int(port) if int(port) > 0 else 1
            chan_num = (int(ch) if int(ch) > 0 else 1) if ch is not None else None
        if chan_num is not None:
            return f"ethernet-{slot}/{port_num}/{chan_num}{sub}"
        return f"ethernet-{slot}/{port_num}{sub}"
    m = re.match(r'^ae(\d+)$', low)
    if m:
        return f"lag{m.group(1)}{sub}"
    m = re.match(r'^lo(\d+)$', low)
    if m:
        return f"system0{sub}" if m.group(1) == "0" else f"lo{m.group(1)}{sub}"
    m = re.match(r'^(?:fxp|em|me)(\d+)$', low)
    if m:
        return f"mgmt0{sub}"
    if low == "irb":
        return f"irb0{sub}"
    return raw


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

    def _get_arg(self, node_name, arg_name, default=None):
        for src in (self._arguments, getattr(self._state, 'line_commands', None)):
            if src is None:
                continue
            try:
                if src.has_node(node_name):
                    val = src.get_value_or(node_name, arg_name, default)
                    if val is not None and val != default:
                        return str(val)
            except Exception:
                pass
        return default

    def _show_table_instance(self, state: CliState, output, arguments: CommandNodeWithArguments, **kwargs,):
        """Main display function"""
        self._state = state
        self._arguments = arguments
        inst_name = self._get_arg('instance', 'name', None)
        if inst_name:
            netinst_data = self._fetch_state_network(inst_name)
        else:
            netinst_data = self._fetch_state_network('*')

        data_root = Data(arguments.schema)
        self._set_all_formatters(data_root)
        with output.stream_data(data_root):
            self._populate_mac_table(netinst_data, data_root)
        output.print_line(srlinux_suggested_command)
        data_root.synchronizer.flush_children(data_root)

    def _fetch_state_network(self, netinst_name):
        table_path = build_path(
            '/network-instance[name={name}]',
            name=netinst_name
        )
        return self._state.server.get_data_store(DataStore.State).get_data(table_path, recursive=False)

    def _fetch_state_network_interfaces(self, netinst_name):
        table_path = build_path(
            '/network-instance[name={name}]/interface[name=*]',
            name=netinst_name
        )
        return self._state.server.get_data_store(DataStore.State).get_data(table_path, recursive=False, include_container_children=True)

    def _fetch_state_mac_table(self, netinst_name, mac_address=None):
        table_path = build_path(
            '/network-instance[name={name}]/bridge-table/mac-table/mac[address={mac}]',
            name=netinst_name,
            mac=mac_address or '*'
        )
        return self._state.server.get_data_store(DataStore.State).stream_data(table_path, recursive=True)

    def _fetch_state_mac_table_stats(self, netinst_name):
        table_path = build_path(
            '/network-instance[name={name}]/bridge-table/statistics',
            name=netinst_name
        )
        return self._state.server.get_data_store(DataStore.State).stream_data(table_path, recursive=False, include_container_children=True)

    def _fetch_state_subinterface(self, int_name, subint_index):
        table_path = build_path(
            '/interface[name={name}]/subinterface[index={index}]',
            name=int_name,
            index=str(subint_index)
        )
        return self._state.server.get_data_store(DataStore.State).get_data(table_path, recursive=True, include_container_children=True)

    def _fetch_state_int_hw_mac(self, int_name):
        table_path = build_path(
            '/interface[name={name}]/ethernet/hw-mac-address',
            name=int_name
        )
        return self._state.server.get_data_store(DataStore.State).stream_data(table_path, recursive=False, include_container_children=True)

    def _fetch_state_irb_subinterface_anycast_mac(self, int_name, subint_index):
        table_path = build_path(
            '/interface[name={name}]/subinterface[index={index}]/anycast-gw/anycast-gw-mac',
            name=int_name,
            index=str(subint_index)
        )
        return self._state.server.get_data_store(DataStore.State).stream_data(table_path, recursive=False, include_container_children=True)

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
                    raw_name = str(network_interface_entry.name)
                    interface_name, subint_index = raw_name.split('.', 1) if '.' in raw_name else (raw_name, '0')
            else:
                raw_name = str(network_interface_entry.name)
                interface_name, subint_index = raw_name.split('.', 1) if '.' in raw_name else (raw_name, '0')

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
                    raw_name = str(network_interface_entry.name)
                    interface_name, subint_index = raw_name.split('.', 1) if '.' in raw_name else (raw_name, '0')
            else:
                raw_name = str(network_interface_entry.name)
                interface_name, subint_index = raw_name.split('.', 1) if '.' in raw_name else (raw_name, '0')

            if not "irb" in interface_name:
                continue

            hw_mac_data = self._fetch_state_int_hw_mac(interface_name)
            anycast_gw_mac_data = self._fetch_state_irb_subinterface_anycast_mac(interface_name, subint_index)

            if anycast_gw_mac_data.get("interface").exists():
                anycast_gw_mac = anycast_gw_mac_data.interface.get().subinterface.get().anycast_gw.get().anycast_gw_mac
            else:
                anycast_gw_mac = ""

            hw_mac = ""
            try:
                if hw_mac_data and hasattr(hw_mac_data, 'interface') and hw_mac_data.interface.exists():
                    intf_node = hw_mac_data.interface.get()
                    if hasattr(intf_node, 'ethernet') and intf_node.ethernet.exists():
                        eth_node = intf_node.ethernet.get()
                        hw_mac = getattr(eth_node, 'hw_mac_address', '') or ''
            except Exception:
                hw_mac = ""
            interface_name_index_list.append({"name": interface_name, "index": str(subint_index), "hw_mac": hw_mac, "anycast_gw_mac": anycast_gw_mac})

        return interface_name_index_list
    
    def _find_vlan(self, interfaces, query):
        if not query:
            return "-"
        m_irb = re.search(r'irb\d*\.(\d+)', query)
        if m_irb:
            for entry in interfaces:
                tag = entry.get("tagging", "-")
                if tag and tag not in ("null", "untagged", "-"):
                    return tag
            return m_irb.group(1) if m_irb.group(1) != '0' else '1'
        # Extract interface name and index using regex
        match = re.match(r'(.+)\.(\d+)', query)
        if not match:
            return "-"

        interface_name, index = match.groups()
        index = str(index)
        # Search for the matching interface
        for entry in interfaces:
            if entry["name"] == interface_name and entry["index"] == index:
                tag = entry.get("tagging", "-")
                if tag not in ("null", "untagged", "-"):
                    return tag
                return index if index != '0' else '1'
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
            if logical_interface == "irb(R)" and irb_interface_name_index_list:
                first_irb = irb_interface_name_index_list[0]
                logical_interface = f'{first_irb["name"]}.{first_irb["index"]}(R)'
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
        raw_intf_arg = self._get_arg('interface', 'name', None)
        subinterface_name = _junos_to_srl_intf(raw_intf_arg) if raw_intf_arg is not None else None
        interface_as_argument = True if subinterface_name and "." not in subinterface_name else False
        vlan_value = self._get_arg('vlan', 'value', None)

        for netinst in netinst_server_data.network_instance.items():
            if netinst.type != 'mac-vrf':
                continue
            netinst_data = data_root.network.create(netinst.name)
            mac_data = self._fetch_state_mac_table(netinst.name)
            mac_data_stats = self._fetch_state_mac_table_stats(netinst.name)
            network_interface_data = self._fetch_state_network_interfaces(netinst.name)
            irb_interface_name_index_list = self._get_irbs_from_netinstance_data(network_interface_data)
            interface_name_index_list = self._get_interface_name_index_from_netinstance_data (network_interface_data)

            default_netinst_vlan = "-"
            for intf_entry in interface_name_index_list:
                tag = intf_entry.get("tagging")
                if tag and tag not in ("null", "untagged", "-"):
                    default_netinst_vlan = tag
                    break
            if default_netinst_vlan == "-":
                for irb_entry in irb_interface_name_index_list:
                    idx = irb_entry.get("index")
                    if idx is not None and str(idx) != "":
                        default_netinst_vlan = str(idx) if str(idx) != '0' else '1'
                        break
            if default_netinst_vlan == "-" and interface_name_index_list:
                default_netinst_vlan = '1'

            for mac_entry in mac_data.get_descendants('/network-instance/bridge-table/mac-table/mac'):
                logical_subinterface = self._get_logical_interface(mac_entry.address, mac_entry.destination, irb_interface_name_index_list)
                clean_subintf = logical_subinterface.replace('(R)', '') if logical_subinterface else ''
                logical_interface = clean_subintf.split('.')[0] if clean_subintf else None
                vlan = self._find_vlan(interface_name_index_list,logical_subinterface)
                if vlan == "-":
                    vlan = default_netinst_vlan
                # if an interface (without the "".subint") is given as argument we populate the mac table for all its subinterfaces
                if subinterface_name is not None and subinterface_name not in (logical_subinterface, clean_subintf):
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
Try SR Linux command: show network-instance bridge-table mac-table all
Try SR Linux command: show interface brief
"""

