"""
CLI Plugin for SR Linux for Cisco-style IP Interface Command
Provides alternate command syntax for interface information
Author: Alperen Akpinar
Email: alperen.akpinar@nokia.com
"""
from srlinux.location import build_path
from srlinux.data import ColumnFormatter, Data, Borders, Alignment, Border
from srlinux.schema import FixedSchemaRoot
from srlinux.schema.data_store import DataStore

class IpInterfaceReport:
    def _get_schema(self):
        root = FixedSchemaRoot()
        interfaces = root.add_child(
            'interfaces',
            fields=['header']
        )
        interfaces.add_child(
            'interface',  # This must be lowercase
            key='Interface',  # This is what shows up in output
            fields=[
                'IP-Address',
                'Interface-Status', 
                'Protocol-Status',
                'VRF'
            ]
        )
        return root

    def _fetch_state(self, state):
        # Get interface data with recursive=True to get all nested data including IP addresses
        interface_path = build_path('/interface[name=*]')
        self.interface_data = state.server.get_data_store(DataStore.State).get_data(interface_path, recursive=True)
        
        # Get network-instance interface mapping
        ni_path = build_path('/network-instance[name=*]/interface[name=*]')
        self.ni_data = state.server.get_data_store(DataStore.State).get_data(ni_path, recursive=True)
    
    def _get_interface_vrf(self, interface_name):
        # Normalize interface name for matching
        normalized_name = interface_name.replace('Ethernet', 'ethernet-')
        
        # If no network instance data, return empty string
        if not hasattr(self.ni_data, 'network_instance'):
            return ""
        
        # Iterate through network instances
        for ni in self.ni_data.network_instance.items():
            # Check if this network instance has interfaces
            if hasattr(ni, 'interface'):
                for intf in ni.interface.items():
                    # Compare normalized interface names, including subinterface
                    if intf.name == normalized_name or intf.name.startswith(normalized_name + '.'):
                        return ni.name
        
        # If no VRF found
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

    def _set_formatters(self, data):
        formatter = ColumnFormatter(
            borders=Borders.Nothing,
            horizontal_alignment={
                'Interface': Alignment.Left,
                'IP-Address': Alignment.Left,
                'Interface-Status': Alignment.Left,
                'Protocol-Status': Alignment.Left,
                'VRF': Alignment.Center
            },
            widths={
                'Interface': 16,         # Fixed width for Interface
                'IP-Address': 15,        # Enough for IPs like 192.168.100.1/24
                'Interface-Status': 16,  # Wide enough for 'admin down' text
                'Protocol-Status': 16,   # Wide enough for 'up' or 'down'
                'VRF': 15                # Adjust as needed
            }
        )
    
        # Apply borders correctly
        bordered_formatter = Border(
            formatter, 
            position=Border.Above | Border.Below,  # Add borders above and below
            character='-'  # Border character
        )
    
        data.set_formatter('/interfaces/interface', bordered_formatter)
    
    def _populate_data(self, result, state):
        result.synchronizer.flush_fields(result)
        data = result.interfaces.create()
        data.header = ""
        self._fetch_state(state)
        processed_interfaces = set()  # Change to a set for faster lookup
        
        # Process all interfaces
        for interface in self.interface_data.interface.items():
            base_name = interface.name
            
            if hasattr(interface, 'subinterface'):
                for subif in interface.subinterface.items():
                    intf_name = self._format_interface_name(base_name, subif.index)
                    
                    # Use set to check and prevent duplicates
                    if intf_name in processed_interfaces:
                        continue
                    processed_interfaces.add(intf_name)
                    
                    # Change this block to prevent multiple data_child creation
                    try:
                        data_child = data.interface.create(intf_name)
                    except Exception:
                        # If interface already exists, skip
                        continue
                    
                    # Rest of the code remains the same
                    ip_address = "unassigned"
                    if hasattr(subif, 'ipv4'):
                        ipv4 = subif.ipv4.get()
                        try:
                            for addr in ipv4.address.items():
                                full_prefix = getattr(addr, 'ip_prefix', 'unassigned')
                                ip_address = full_prefix.split('/')[0] if full_prefix != 'unassigned' else full_prefix
                                break
                        except Exception:
                            pass
                    
                    # Get states
                    admin_state = getattr(subif, 'admin_state', 'disable')
                    oper_state = getattr(subif, 'oper_state', 'down')
                    
                    if admin_state == "enable":
                        if oper_state == "up":
                            intf_status = "up"
                            proto_status = "up"
                        else:
                            intf_status = "up"
                            proto_status = "down"
                    else:
                        intf_status = "admin down"
                        proto_status = "down"
                    
                    data_child.ip_address = ip_address
                    data_child.interface_status = intf_status
                    data_child.protocol_status = proto_status
                    data_child.vrf = self._get_interface_vrf(intf_name)
                    data_child.synchronizer.flush_fields(data_child)
            
            # Handle unconfigured interfaces
            if base_name not in processed_interfaces:
                intf_name = self._format_interface_name(base_name)
                
                # Check if interface already exists to prevent duplicate
                if intf_name not in processed_interfaces:
                    processed_interfaces.add(intf_name)
                    
                    data_child = data.interface.create(intf_name)
                    data_child.ip_address = "unassigned"
                    data_child.interface_status = "admin down"
                    data_child.protocol_status = "down"
                    data_child.vrf = ""
                    data_child.synchronizer.flush_fields(data_child)
        
        result.synchronizer.flush_children(result.interfaces)
        return result

    def show_interfaces_brief(self, state, output):
        """Main function to display interface brief"""
        result = Data(self._get_schema())
        self._set_formatters(result)
        with output.stream_data(result):
            self._populate_data(result, state)