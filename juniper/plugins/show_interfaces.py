#!/usr/bin/python
###########################################################################
# Author: Thomas Hendriks
# Email: thomas.hendriks@nokia.com
# Tested with SRL 7220-D2L version 25.3.1 on containerlab
###########################################################################

"""This module contains an attempted translation of the Juniper command `show interfaces`
with the optional additions `terse` and `brief` to an SR Linux CLI Plugin.
After importing it into a suitable SR Linux machine, the commands mentioned above are enabled.

The outputs provided by the translated commands are made to be as close as possible, though
wherever the attributes don't line up some placeholder values may be used."""

import datetime
import ipaddress
import re

from srlinux.data import (
    Data,
    Formatter,
)
from srlinux.location import build_path
from srlinux.mgmt.cli import KeyCompleter, MultipleKeyCompleters, CliPlugin
from srlinux.schema import FixedSchemaRoot
from srlinux.schema.data_store import DataStore
from srlinux.syntax import Syntax
from srlinux import strings


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


def _extract_junos_intf_arg(state, arguments, subcmd_node=None):
    """Extract interface name argument from arguments or state.line_commands."""
    argument_name = "*"
    for src in (arguments, getattr(state, "line_commands", None)):
        if src is None:
            continue
        try:
            if src.has_node("interfaces"):
                val = src.get_value_or("interfaces", "name", "*")
                if val and val != "*":
                    argument_name = str(val)
                    break
            if subcmd_node and src.has_node(subcmd_node):
                val = src.get_value_or(subcmd_node, "name", "*")
                if val and val != "*":
                    argument_name = str(val)
                    break
        except Exception:
            pass
    return _junos_to_srl_intf(argument_name)


class Plugin(CliPlugin):
    """ Base class that loads three classes each representing one of the
    versions of the command being translated. """
    def load(self, cli, **_kwargs):
        """ Load the commands into the CLI show mode. """
        interface = cli.show_mode.add_command(
            JperInterfaceSummary.get_syntax(),
            update_location=True,
            callback=self._interface_summary,
            schema=JperInterfaceSummary.get_data_schema(),
        )
        interface.add_command(
            JperInterfaceBrief.get_syntax(),
            update_location=True,
            callback=self._interface_brief,
            schema=JperInterfaceBrief.get_data_schema(),
        )
        interface.add_command(
            JperInterfaceTerse.get_syntax(),
            update_location=True,
            callback=self._interface_terse,
            schema=JperInterfaceTerse.get_data_schema(),
        )

    @staticmethod
    def _interface_summary(state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        JperInterfaceSummary().print(state, arguments, output, **_kwargs)

    @staticmethod
    def _interface_brief(state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        JperInterfaceBrief().print(state, arguments, output, **_kwargs)

    @staticmethod
    def _interface_terse(state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        JperInterfaceTerse().print(state, arguments, output, **_kwargs)


class JperInterfaceBrief():
    """SR Linux implementation of the Juniper `show interfaces brief` command.
    The command takes an optional parameter that is an interface name, this parameter
    can be on either side of the `brief` keyword, though the interface name preceding
    the keyword has preference."""
    def __init__(self):
        """Create an instance of the `brief` command with setting to include all interfaces."""
        self._only_subinterface = False

    @staticmethod
    def get_syntax():
        """Show interface report in Juniper brief format. Usage:
            show interfaces brief ethernet-1/1
            show interfaces ethernet-1/1.0 brief
            show interfaces brief
        """
        result = Syntax("brief", help= (
            "Show interface report in Juniper brief format\n"
            + "Usage: \n"
            + "  show interfaces brief ethernet-1/1\n"
            + "  show interfaces ethernet-1/1.0 brief\n"
            + "  show interfaces brief"
            )
        )
        result.add_unnamed_argument(
            "name",
            default="*",
            suggestions=MultipleKeyCompleters(
                keycompleters=[
                    KeyCompleter(path="/interface[name=*]"),
                    KeyCompleter(path="/interface[name=*]/subinterface[index=*]/name:"),
                ]
            ),
        )
        return result

    @staticmethod
    def get_data_schema():
        """Function to create and return the datastructure used to store the information that
        will be used and displayed by the CLI Plugin when the corresponding command is issued."""
        root = FixedSchemaRoot()
        intf = root.add_child(
            "IfBrief",
            key="Interface",
            fields=[
                "Admin",
                "Link",
                "Proto",
                "Local",
                "Remote",
                "MTU",
                "MRU",
                "Type",
                "Mode",
                "Speed",
                "Loopback",
                "Source_Filter",
                "Flow_Control",
                "Auto_Negotiation",
                "Remote_fault",
                "Device_flags",
                "Interface_Flags",
                "Link_Flags",
            ],
        )
        intf.add_child(
            "SubIfBrief",
            key="Subinterface",
            fields=["Proto", "Flags", "Encap", "Local"],
        )
        return root

    def print(self, state, arguments, output, **_kwargs):
        """Main function for the CLI Plugin, acquires necessery data, stores
        it in the appropriate datastructure and attempts to output it to the screen
        using the chosen formatter."""
        chassis_data = _chassis_type(state)
        serve_data, arg_name = self._stream_interfaces(state, arguments)
        result = Data(arguments.schema)
        self._set_formatters(result)
        with output.stream_data(result):
            self._populate_data(result, serve_data, chassis_data, arg_name)

    def _stream_interfaces(self, state, arguments):
        """Function to return state data (specific or all if unspecified) from SR Linux"""
        argument_name = _extract_junos_intf_arg(state, arguments, subcmd_node="brief")
        intf_name, subintf_index = strings.extract_interface_name_subinterface_index(argument_name)
        self._only_subinterface = subintf_index is not None
        path = build_path(f"/interface[name={intf_name}]")
        return state.server.get_data_store(DataStore.State).stream_data(path, recursive=True), argument_name

    def _populate_data(self, data, serve_data, chassis_data, arg_name):
        """Function to iterate over data retrieved from state and populate the datastructure
        corresponding to the `brief` version of the command with the appropriate data"""
        data.synchronizer.flush_fields(data)
        for interface in serve_data.interface.items():
            child = data.ifbrief.create(interface.name)
            if not self._only_subinterface:
                child = _util_populate_intf_brief(
                    data.ifbrief.create(interface.name),
                    interface,
                    chassis_data.platform,
                )
            for subinterface in interface.subinterface.items():
                if self._only_subinterface and subinterface.name != arg_name:
                    continue
                subifchild = child.subifbrief.create(subinterface.name)
                (
                    _, _, _, _, _,
                    subifchild.proto, subifchild.local,
                    _
                ) = _get_add_info(subinterface)
                subifchild_flags_info = "Up" if subinterface.oper_state == "up" else "Down"
                if getattr(interface, 'vlan_tagging', False):
                    try:
                        vlan_id = (
                            subinterface.vlan.get(0)
                            .encap.get(0)
                            .single_tagged.get(0)
                            .vlan_id
                        )
                        tpid = getattr(interface, 'tpid', '')
                        tpid_suffix = tpid[-6:] if tpid else '0x8100'
                        subifchild_flags_addition = (
                            f" VLAN-Tag [ {tpid_suffix}.{vlan_id} ] "
                        )
                        subifchild_flags_info += subifchild_flags_addition
                    except Exception:
                        pass
                subifchild.flags = subifchild_flags_info
                subifchild.encap = "ENET2" if interface.ethernet.exists() else ""
            child.synchronizer.flush_fields(child)

        data.synchronizer.flush_children(data.ifbrief)

    def _set_formatters(self, data):
        """Function that assigns the BriefFormatter to this version of the command"""
        data.set_formatter("/", BriefFormatter(self._only_subinterface))


class BriefFormatter(Formatter):
    """Formatter to approximate the output of `show interfaces brief`"""
    def __init__(self, only_subinterface):
        """Creates a BriefFormatter that returns output to the terminal containing contents
        similar to those present in Juniper's `show interfaces brief` that is formatted similarly.
        Requires the _only_subinterface input as the output changes slightly."""
        self._only_subinterface = only_subinterface
        super().__init__()


    def iter_format(self, entry, max_width):
        """Iterate over the CLI Plugin data and yield output line by line in `brief` format."""
        for k in entry.ifbrief.items():
            if not self._only_subinterface:
                if _is_virtual_interface(k.interface):
                    result_str = self._output_virtual_interface(k)
                else:
                    result_str = self._output_regular_interface(k)
            else:
                result_str = ""
            for subintf in k.subifbrief.items():
                if _is_virtual_interface(k.interface):
                    result_str += self._output_virtual_subinterface(
                        subintf, result_str
                    )
                else:
                    result_str += self._output_regular_subinterface(
                        subintf, result_str
                    )
            yield result_str
        yield "-" * 100
        yield "Try SR Linux command: show interface detail"

    @staticmethod
    def _output_regular_interface(entry):
        """Helper function that returns expected string `brief` output for a physical interface."""
        result_str = (
            f"Physical interface: {entry.interface}, {entry.admin}, Physical link is "
            + f"{entry.link}\n  Link-level type: {entry.type}, MTU: {entry.mtu}, MRU: "
            + f"{entry.mru}, {entry.mode} mode, Speed: {entry.speed}, Loopback: "
            + f"{entry.loopback}, Source filtering: {entry.source_filter}, "
            + f" Flow control: {entry.flow_control}, Auto-negotiation: "
            + f"{entry.auto_negotiation}, Remote fault: {entry.remote_fault}\n"
            + f"  Device flags   : {entry.device_flags}\n"
            + f"  Interface flags: {entry.interface_flags}\n"
            + f"  Link flags     : {entry.link_flags}\n\n"
        )
        return result_str

    @staticmethod
    def _output_virtual_interface(entry):
        """Helper function that returns expected `brief` string output for a virtual interface ."""
        result_str = (
            f"Physical interface: {entry.interface}, {entry.admin}, Physical link is "
            + f"{entry.link}\n  Link-level type: {entry.type}, Link-level type: Unspecified, "
            + f"MTU: {entry.mtu}, Clocking: Unspecified, Speed: Unspecified\n"
            + f"  Device flags   : {entry.device_flags}\n"
            + f"  Interface flags: {entry.interface_flags}\n"
            + f"  Link flags     : {entry.link_flags}\n\n"
        )
        return result_str

    @staticmethod
    def _output_regular_subinterface(entry, curr_result_str):
        """Helper function that returns expected `brief` string output for a physical subintf."""
        result_str = (
            ("" if curr_result_str == "" else "\n")
            + f"  Logical interface {entry.subinterface}\n"
            + f"    Flags: {entry.flags} Encapsulation: {entry.encap}\n"
        )
        for proto in entry.proto:
            addr = entry.local[proto][0]
            result_str += f"    {proto:<6}{addr[0]}/{addr[1].prefixlen}\n"
            for addr in entry.local[proto][1:]:
                result_str += f"{'':<10}{addr[0]}/{addr[1].prefixlen}\n"
        result_str += "    multiservice\n"
        return result_str

    @staticmethod
    def _output_virtual_subinterface(entry, curr_result_str):
        """Helper function that returns expected `brief` string output for a virtual subintf."""
        # Override entry.encap with "Unspecified" as found in target output
        result_str = (
            ("" if curr_result_str == "" else "\n")
            + f"  Logical interface {entry.subinterface}\n"
            + f"    Flags: {entry.flags} Encapsulation: Unspecified\n"
        )
        for proto in entry.proto:
            addr = entry.local[proto][0]
            result_str += f"    {proto:<6}{addr[0]}/{addr[1].prefixlen}\n"
            for addr in entry.local[proto][1:]:
                result_str += f"{'':<10}{addr[0]}/{addr[1].prefixlen}\n"
        return result_str

class JperInterfaceTerse():
    """SR Linux implementation of the Juniper `show interfaces terse` command.
    The command takes an optional parameter that is an interface name, this parameter
    can be on either side of the `terse` keyword, though the interface name preceding
    the keyword has preference."""

    def __init__(self):
        """Create an instance of the `terse` command set to include all interfaces."""
        self._only_subinterface = False

    @staticmethod
    def get_syntax():
        """Show interface report in Juniper terse format. Usage:
            show interfaces terse ethernet-1/1
            show interfaces ethernet-1/1.0 terse
            show interfaces terse
        """
        result = Syntax("terse", help= (
            "Show interface report in Juniper terse format\n"
            + "Usage: \n"
            + "  show interfaces terse ethernet-1/1\n"
            + "  show interfaces ethernet-1/1.0 terse\n"
            + "  show interfaces terse"
            )
        )
        result.add_unnamed_argument(
            "name",
            default="*",
            suggestions=MultipleKeyCompleters(
                keycompleters=[
                    KeyCompleter(path="/interface[name=*]"),
                    KeyCompleter(path="/interface[name=*]/subinterface[index=*]/name:"),
                ]
            ),
        )
        return result

    @staticmethod
    def get_data_schema():
        """Function to create and return the datastructure used to store the information that
        will be used and displayed by the CLI Plugin when the corresponding command is issued."""
        root = FixedSchemaRoot()
        root.add_child(
            "IfTerse",
            key="Interface",
            fields=["Admin", "Link", "Proto", "Local", "Remote"],
        )
        return root

    def print(self, state, arguments, output, **_kwargs):
        """Main function for the CLI Plugin, acquires necessery data, stores
        it in the appropriate datastructure and attempts to output it to the screen
        using the chosen formatter."""
        serve_data, arg_name = self._stream_interfaces(state, arguments)
        result = Data(arguments.schema)
        self._set_formatters(result)
        with output.stream_data(result):
            self._populate_data(result, serve_data, arg_name)

    def _stream_interfaces(self, state, arguments):
        """Function to return state data (specific or all if unspecified) from SR Linux"""
        argument_name = _extract_junos_intf_arg(state, arguments, subcmd_node="terse")
        intf_name, subintf_index = strings.extract_interface_name_subinterface_index(argument_name)
        self._only_subinterface = subintf_index is not None
        path = build_path(f"/interface[name={intf_name}]")
        return state.server.get_data_store(DataStore.State).stream_data(path, recursive=True), argument_name


    def _populate_data(self, data, serve_data, arg_name):
        """Function to iterate over data retrieved from state and populate the datastructure
        corresponding to the `terse` version of the command with the appropriate data"""
        data.synchronizer.flush_fields(data)
        for interface in serve_data.interface.items():
            if not self._only_subinterface:
                child = data.ifterse.create(interface.name)
                child.admin = "up" if interface.admin_state == "enable" else "down"
                child.link = interface.oper_state
                child.proto = []
                child.local = {"inet": [], "inet6": []}
                child.remote = []
                child.synchronizer.flush_fields(child)
            for subinterface in interface.subinterface.items():
                if self._only_subinterface and subinterface.name != arg_name:
                    continue
                child = data.ifterse.create(subinterface.name)
                child.admin = "up" if subinterface.admin_state == "enable" else "down"
                child.link = subinterface.oper_state
                (
                    _, _, _, _, _,
                    child.proto,
                    child.local,
                    child.remote
                ) = _get_add_info(subinterface)
                child.synchronizer.flush_fields(child)
        data.synchronizer.flush_children(data.ifterse)

    @staticmethod
    def _set_formatters(data):
        """Function that assigns the TerseFormatter to this version of the command"""
        data.set_formatter("/", TerseFormatter())


class TerseFormatter(Formatter):
    """Formatter to approximate the output of `show interfaces terse`"""
    def __init__(self):
        """Creates a RegularFormatter that returns output to the terminal with contents
        similar to those present in Juniper's `show interfaces terse` in a similar format."""
        super().__init__()
        self.header = ("Interface               Admin Link Proto    Local                 Remote")

    def iter_format(self, entry, max_width):
        """Iterate over the CLI Plugin data and yield output line by line in `terse` format."""
        yield self.header
        for k in entry.ifterse.items():
            if len(k.proto) > 0:
                addr = k.local[k.proto[0]][0]
                yield (
                    f"{k.interface: <23} {k.admin: <5} {k.link: <4} {k.proto[0]: <8}"
                    + f" {addr[0]}/{addr[1].prefixlen: <21} {k.remote: <13}"
                )
                for i in range(len(k.local[k.proto[0]]) - 1):
                    # Add up the column widths as 23, 5, 4 and 8, followed by 21
                    # and 4 spaces makes 44
                    addr = k.local[k.proto[0]][i+1]
                    yield f"{'': <44}{addr[0]}/{addr[1].prefixlen: <21} {'': <13}"
                for proto in k.proto[1:]:
                    addr = k.local[proto][0]
                    yield f"{'': <35}{proto: <9}{addr[0]}/{addr[1].prefixlen: <21} {'': <13}"
                    for i in range(len(k.local[proto]) - 1):
                        addr = k.local[proto][i+1]
                        yield f"{'': <44}{addr[0]}/{addr[1].prefixlen: <21} {'': <13}"
                yield f"{'': <35}multiservice\n"
            else:
                yield f"{k.interface: <23} {k.admin: <5} {k.link: <4} {'': <8} {'': <21} {'': <13}"
        yield "-" * 100
        yield "Try SR Linux command: show interface"


class JperInterfaceSummary():
    """SR Linux implementation of the Juniper `show interfaces` command.
    The command takes an optional parameter that is an interface name."""

    def __init__(self):
        """Create an instance of the regular command with set to include all interfaces."""
        self._only_subinterface = False

    __slots__ = (
        "_all",
        "_interface_name",
        "_subinterface_index",
        "_only_subinterface",
        "_count_loopback_interfaces",
        "_count_mgmt_interfaces_up",
        "_count_mgmt_interfaces_down",
        "_count_interfaces_up",
        "_count_interfaces_down",
        "_count_subinterfaces_up",
        "_count_subinterfaces_down",
        "_network_instance_interface_cache",
    )

    @staticmethod
    def get_syntax():
        """Show interface report in Juniper format. Usage:
            show interfaces ethernet-1/1
            show interfaces ethernet-1/1.0
            show interfaces
        """
        result = Syntax("interfaces", help= (
            "Show interface report in Juniper format\n"
            + "Usage: \n"
            + "  show interfaces ethernet-1/1\n"
            + "  show interfaces ethernet-1/1.0\n"
            + "  show interfaces"
            )
        )
        result.add_unnamed_argument(
            "name",
            default="*",
            suggestions=MultipleKeyCompleters(
                keycompleters=[
                    KeyCompleter(path="/interface[name=*]"),
                    KeyCompleter(path="/interface[name=*]/subinterface[index=*]/name:"),
                ]
            ),
        )
        return result

    @staticmethod
    def get_data_schema():
        """Function to create and return the datastructure used to store the information that
        will be used and displayed by the CLI Plugin when the corresponding command is issued."""
        root = FixedSchemaRoot()
        intf = root.add_child(
            "Interface",
            key="Interface",
            fields=[
                "Admin",
                "Link",
                "Proto",
                "Local",
                "Remote",
                "MTU",
                "MRU",
                "Type",
                "Mode",
                "Speed",
                "Loopback",
                "Source_Filter",
                "Flow_Control",
                "Auto_Negotiation",
                "Remote_fault",
                "Device_flags",
                "Interface_Flags",
                "Link_Flags",
                "Active_Alarms",
                "Avail_Cos_Queues",
                "Bit_Errors",
                "BPDU_Errors",
                "Ethernet_Switching_Errors",
                "FEC_Corr_Errors",
                "FEC_Corr_Error_Rate",
                "FEC_Uncorr_Errors",
                "FEC_Uncorr_Error_Rate",
                "Input_Rate",
                "Output_Rate",
                "Intf_Index",
                "Time_Since_Last_Flap",
                "Loopback_PDU_Error",
                "MAC_Addr",
                "MAC_Rewrite_Error",
                "Max_COS_Queues",
                "Oper_MAC_Addr",
                "Pad_State",
                "SNMP_Intf_Index",
                "Time_Of_Last_Flap",
                "Tx_Intf_Stats",
                "Input_Rate_Pps",
                "Output_Rate_Pps",
                "Active_Defects",
            ],
        )
        intf.add_child(
            "SubInterface",
            key="Subinterface",
            fields=[
                "Proto",
                "Local",
                "Remote",
                "Flags_First",
                "Encap",
                "Intf_Index",
                "SNMP_Intf_Index",
                "Input_Pkts",
                "Output_Pkts",
                "Nh_Cache",
                "New_Hold_Nh_Limit",
                "Curr_Nh_Count",
                "Dropped_Nh_Count",
                "Addr",
                "Flags_Second",
                "MTU",
                "New_Hold_Curr_Cnt",
            ],
        )
        return root

    def print(self, state, arguments, output, **_kwargs):
        """Main function for the CLI Plugin, acquires necessery data, stores
        it in the appropriate datastructure and attempts to output it to the screen
        using the chosen formatter."""
        chassis_data = _chassis_type(state)
        qos_data = _get_qos(state)
        serve_data, arg_name = self._stream_interfaces(state, arguments)
        result = Data(arguments.schema)
        self._set_formatters(result)
        with output.stream_data(result):
            self._populate_data(result, serve_data, chassis_data, qos_data, arg_name)

    def _stream_interfaces(self, state, arguments):
        """Function to return state data (specific or all if unspecified) from SR Linux"""
        argument_name = _extract_junos_intf_arg(state, arguments)
        intf_name, subintf_index = strings.extract_interface_name_subinterface_index(argument_name)
        self._only_subinterface = subintf_index is not None
        path = build_path(f"/interface[name={intf_name}]")
        return state.server.get_data_store(DataStore.State).stream_data(path, recursive=True), argument_name

    def _populate_data(self, data, serve_data, chassis_data, qos_data, arg_name):
        """Function to iterate over data retrieved from state and populate the datastructure
        corresponding to the regular version of the command with the appropriate data"""
        data.synchronizer.flush_fields(data)
        for interface in serve_data.interface.items():
            child = data.interface.create(interface.name)
            if not self._only_subinterface:
                child = _util_populate_intf_brief(
                    data.interface.create(interface.name),
                    interface,
                    chassis_data.platform,
                )

                count_uc_queue, count_mc_queue = 0, 0
                valid_intf_names = [
                    str(x).split("interface-id=", 1)[1].split("]", 1)[0]
                    for x in qos_data.qos.get(0).interfaces.get(0).interface.items()
                ]
                if interface.name not in valid_intf_names:
                    pass
                else:
                    intf_qos_object = (
                        qos_data.qos.get(interface.name)
                        .interfaces.get(interface.name)
                        .interface.get(interface.name)
                    )
                    queues = intf_qos_object.output.get(0).queues.get(0).queue
                    count_uc_queue, count_mc_queue = 0, 0
                    for queue in queues.items():
                        if "unicast" in queue.queue_name:
                            count_uc_queue += 1
                        elif "multicast" in queue.queue_name:
                            count_mc_queue += 1
                # Not counting multicast queues, though we have 8 unique queues there as well
                child.avail_cos_queues = count_uc_queue
                val = 0
                if hasattr(interface, 'statistics') and interface.statistics.exists():
                    try:
                        val = interface.statistics.get(0).in_fcs_error_packets
                    except Exception:
                        val = 0
                child.bit_errors = val if val else 0

                child.input_rate = 0
                child.output_rate = 0
                if hasattr(interface, 'traffic_rate') and interface.traffic_rate.exists():
                    try:
                        child.input_rate = interface.traffic_rate.get(0).in_bps
                        child.output_rate = interface.traffic_rate.get(0).out_bps
                    except Exception:
                        pass

                child.intf_index = getattr(interface, 'ifindex', '--')
                macaddr = '--'
                if hasattr(interface, 'ethernet') and interface.ethernet.exists():
                    try:
                        macaddr = interface.ethernet.get(0).hw_mac_address
                    except Exception:
                        pass
                child.mac_addr = macaddr
                child.oper_mac_addr = macaddr

                time_of_last_flap_str = getattr(interface, 'last_change', None)
                if time_of_last_flap_str:
                    try:
                        clean_ts = time_of_last_flap_str.replace('Z', '+00:00')
                        time_of_last_flap = datetime.datetime.fromisoformat(clean_ts)
                        if time_of_last_flap.tzinfo is None:
                            time_of_last_flap = time_of_last_flap.replace(tzinfo=datetime.timezone.utc)
                        time_since_last_flap = datetime.datetime.now(datetime.timezone.utc) - time_of_last_flap
                        total_seconds = max(0, int(time_since_last_flap.total_seconds()))
                        weeks, remainder = divmod(total_seconds, 60 * 60 * 24 * 7)
                        days, remainder = divmod(remainder, 60 * 60 * 24)
                        hours, remainder = divmod(remainder, 60 * 60)
                        minutes, __ = divmod(remainder, 60)
                        child.time_of_last_flap = time_of_last_flap.strftime("%Y-%m-%d %H:%M:%S UTC")
                        child.time_since_last_flap = f"({weeks}w{days}d {hours:02}:{minutes:02} ago)"
                    except Exception:
                        child.time_of_last_flap = "Never"
                        child.time_since_last_flap = "Never"
                else:
                    child.time_of_last_flap = "Never"
                    child.time_since_last_flap = "Never"

                # These attributes were given placeholder values due to no direct
                # mapping being available or a lack of understanding the source
                # material. These can be extended upon later.
                child.max_cos_queues = "8"
                child.active_alarms = "N/A"
                child.active_defects = "N/A"
                child.bpdu_errors = "N/A"
                child.ethernet_switching_errors = "N/A"
                child.snmp_intf_index = str(interface.ifindex) if hasattr(interface, 'ifindex') and interface.ifindex is not None else "N/A"
                child.fec_corr_errors = "N/A"
                child.fec_corr_error_rate = "N/A"
                child.fec_uncorr_errors = "N/A"
                child.fec_uncorr_error_rate = "N/A"
                child.loopback_pdu_error = "N/A"
                child.mac_rewrite_error = "N/A"
                child.pad_state = "N/A"
                child.tx_intf_stats = "Disabled"
                child.input_rate_pps = "Uncalculated"
                child.output_rate_pps = "Uncalculated"
            for subinterface in interface.subinterface.items():
                if self._only_subinterface and subinterface.name != arg_name:
                    continue
                subifchild = child.subinterface.create(subinterface.name)
                subifchild_flags_info = "Up" if subinterface.oper_state == "up" else "Down"
                if getattr(interface, 'vlan_tagging', False):
                    try:
                        vlan_id = (
                            subinterface.vlan.get(0)
                            .encap.get(0)
                            .single_tagged.get(0)
                            .vlan_id
                        )
                        tpid = getattr(interface, 'tpid', '')
                        tpid_suffix = tpid[-6:] if tpid else '0x8100'
                        subifchild_flags_addition = (
                            f" VLAN-Tag [ {tpid_suffix}.{vlan_id} ] "
                        )
                        subifchild_flags_info += subifchild_flags_addition
                    except Exception:
                        pass
                subifchild.flags_first = subifchild_flags_info
                subifchild.encap = "ENET2" if interface.ethernet.exists() else ""
                subifchild.intf_index = subinterface.ifindex
                subifchild.snmp_intf_index = "N/A"
                if not _is_virtual_interface(interface.name) and hasattr(subinterface, 'statistics') and subinterface.statistics.exists():
                    try:
                        subifchild.input_pkts = subinterface.statistics.get(0).in_packets
                        subifchild.output_pkts = subinterface.statistics.get(0).out_packets
                    except Exception:
                        subifchild.input_pkts = 0
                        subifchild.output_pkts = 0
                else:
                    subifchild.input_pkts = 0
                    subifchild.output_pkts = 0
                subifchild.mtu = subinterface.ip_mtu if subinterface.ip_mtu else "Unlimited"
                (
                    subifchild.nh_cache,
                    subifchild.new_hold_nh_limit,
                    subifchild.curr_nh_count,
                    subifchild.new_hold_curr_cnt,
                    subifchild.dropped_nh_count,
                    subifchild.proto,
                    subifchild.local,
                    _
                ) = _get_add_info(subinterface)
                subifchild.flags_second = "Sendbcast-pkt-to-re"

            child.synchronizer.flush_fields(child)

        data.synchronizer.flush_children(data.interface)

    def _set_formatters(self, data):
        """Function that assigns the RegularFormatter to this version of the command"""
        data.set_formatter("/", RegularFormatter(self._only_subinterface))


class RegularFormatter(Formatter):
    """Formatter to approximate the output of `show interfaces`"""
    def __init__(self, only_subinterface):
        """Creates a RegularFormatter that returns output to the terminal containing contents
        similar to those present in Juniper's `show interfaces` that is formatted similarly.
        Requires the _only_subinterface input as the output changes slightly."""
        self._only_subinterface = only_subinterface
        super().__init__()

    def iter_format(self, entry, max_width):
        """Iterate over the CLI Plugin data and yield output line by line in regular format."""
        for k in entry.interface.items():
            if not self._only_subinterface:
                if _is_virtual_interface(k.interface):
                    result_str = self._output_virtual_interface(k)
                else:
                    result_str = self._output_regular_interface(k)
            else:
                result_str = ""
            for subintf in k.subinterface.items():
                if _is_virtual_interface(k.interface):
                    result_str += self._output_virtual_subinterface(
                        subintf, result_str
                    )
                else:
                    result_str += self._output_regular_subinterface(
                        subintf, result_str
                    )
            yield result_str
        yield "-" * 100
        yield "Try SR Linux command: show interface detail"

    @staticmethod
    def _output_regular_interface(entry):
        """Helper function that returns expected string output for a physical interface."""
        result_str = (
            f"Physical interface: {entry.interface}, {entry.admin}, Physical link is {entry.link}\n"
            + f"  Interface index: {entry.intf_index}, SNMP ifIndex: {entry.snmp_intf_index}\n"
            + f"  Link-level type: {entry.type}, MTU: {entry.mtu}, MRU: {entry.mru},"
            + f" {entry.mode} mode, Speed: {entry.speed}, BPDU Error: {entry.bpdu_errors},"
            + f" Loop Detect PDU Error: {entry.loopback_pdu_error}, Ethernet-Switching Error:"
            + f" {entry.ethernet_switching_errors}, MAC-REWRITE Error: {entry.mac_rewrite_error}, "
            + f"Loopback: {entry.loopback}, Source filtering: {entry.source_filter},"
            + f"Flow control: {entry.flow_control}, Auto-negotiation: {entry.auto_negotiation},"
            + f" Remote fault: {entry.remote_fault}\n"
            + f"  Pad to minimum frame size: {entry.pad_state}\n"
            + f"  Device flags   : {entry.device_flags}\n"
            + f"  Interface flags: {entry.interface_flags}\n"
            + f"  Link flags     : {entry.link_flags}\n"
            + f"  CoS queues     : {entry.avail_cos_queues} supported,"
            + f" {entry.max_cos_queues} maximum usable queues\n"
            + f"  Current address: {entry.oper_mac_addr}, Hardware address: {entry.mac_addr}\n"
            + f"  Last flapped   : {entry.time_of_last_flap} {entry.time_since_last_flap}\n"
            + f"  Input rate     : {entry.input_rate} bps ({entry.input_rate_pps} pps)\n"
            + f"  Output rate    : {entry.output_rate} bps ({entry.output_rate_pps} pps)\n"
            + f"  Active alarms  : {entry.active_alarms}\n"
            + f"  Active defects : {entry.active_defects}\n"
            + "  PCS statistics                      Seconds\n"
            + f"    Bit errors {entry.bit_errors: >29}\n"
            + f"    Errored blocks {entry.bit_errors: >25}\n"
            + "  Ethernet FEC statistics              Errors\n"
            + f"    FEC Corrected Errors {entry.fec_corr_errors: >21}\n"
            + f"    FEC Uncorrected Errors {entry.fec_uncorr_errors: >19}\n"
            + f"    FEC Corrected Errors Rate {entry.fec_corr_error_rate: >16}\n"
            + f"    FEC Uncorrected Errors Rate {entry.fec_uncorr_error_rate: >14}\n"
            + f"  Interface transmit statistics: {entry.tx_intf_stats}\n"
        )
        return result_str

    @staticmethod
    def _output_virtual_interface(entry):
        """Helper function that returns expected string output for a virtual interface."""
        total_input_pkts, total_output_pkts = 0, 0
        for subintf in entry.subinterface.items():
            total_input_pkts += subintf.input_pkts
            total_output_pkts += subintf.output_pkts
        result_str = (
            f"Physical interface: {entry.interface}, {entry.admin}, Physical link is {entry.link}\n"
            + f"  Interface index: {entry.intf_index}, SNMP ifIndex: {entry.snmp_intf_index}\n"
            + f"  Type: {entry.type}, MTU: {entry.mtu}\n"
            + f"  Device flags   : {entry.device_flags}\n"
            + f"  Interface flags: {entry.interface_flags}\n"
            + f"  Link flags     : {entry.link_flags}\n"
            + f"  Last flapped   : {entry.time_of_last_flap} {entry.time_since_last_flap}\n"
            + f"    Input packets : {total_input_pkts}\n"
            + f"    Output packets: {total_output_pkts}\n"
        )
        return result_str

    @staticmethod
    def _output_regular_subinterface(entry, curr_result_str):
        """Helper function that returns expected string output for a physical subinterface."""
        result_str = (
            ("" if curr_result_str == "" else "\n")
            + f"  Logical interface {entry.subinterface} (Index {entry.intf_index})"
            + f" (SNMP ifIndex {entry.snmp_intf_index})\n"
            + f"    Flags: {entry.flags_first} Encapsulation: {entry.encap}\n"
            + f"    Input packets : {entry.input_pkts}\n"
            + f"    Output packets: {entry.output_pkts}\n"
        )
        for proto in entry.proto:
            result_str += (
                f"    Protocol {proto}, MTU: {entry.mtu}\n"
                + f"    Max nh cache: {entry.nh_cache}, New hold nh limit: "
                + f"{entry.new_hold_nh_limit}, Curr nh cnt: {len(entry.curr_nh_count[proto])},"
                + f" Curr new hold cnt: {entry.new_hold_curr_cnt}, "
                + f"NH drop cnt: {entry.dropped_nh_count}\n"
                + (f"      Flags: {entry.flags_second}\n" if proto == "inet" else "")
            )
            for address in entry.local[proto]:
                result_str += (
                    f"      Addresses, Flags: {address[2]}\n"
                    + f"        Destination: {address[1].network_address}/{address[1].prefixlen},"
                    + f" Local: {address[0]}"
                    + (
                        f", Broadcast: {address[1].broadcast_address}\n"
                        if proto == "inet"
                        else "\n"
                    )
                )

        result_str += "    Protocol multiservice, MTU: Unlimited\n"
        return result_str

    @staticmethod
    def _output_virtual_subinterface(entry, curr_result_str):
        """Helper function that returns expected string output for a virtual subinterface."""
        # Override entry.encap with "Unspecified" as found in target output
        result_str = (
            ("" if curr_result_str == "" else "\n")
            + f"  Logical interface {entry.subinterface} (Index {entry.intf_index})"
            + f" (SNMP ifIndex {entry.snmp_intf_index})\n"
            + f"    Flags: {entry.flags_first} Encapsulation: Unspecified\n"
            + f"    Input packets : {entry.input_pkts}\n"
            + f"    Output packets: {entry.output_pkts}\n"
        )
        for proto in entry.proto:
            result_str += (
                f"    Protocol {proto}, MTU: {entry.mtu}\n"
                + f"    Max nh cache: {entry.nh_cache}, New hold nh limit: "
                + f"{entry.new_hold_nh_limit}, Curr nh cnt: {len(entry.curr_nh_count[proto])}, "
                + f"Curr new hold cnt: {entry.new_hold_curr_cnt},"
                + f" NH drop cnt: {entry.dropped_nh_count}\n"
            )
            for address in entry.local[proto]:
                result_str += (
                    f"      Addresses, Flags: {address[2]}\n"
                    + f"        Local: {address[0]}\n"
                )
        return result_str


def _is_virtual_interface(interface_name):
    """Helper function that returns if an interface is virtual or has a hardware element."""
    # Treat lo# and system0 interface differently
    return interface_name[:2] == "lo" or interface_name == "system0"


def _util_populate_intf_brief(child, interface, platform):
    """Helper function to populate shared elements of the CLI Plugin datastructures that are
    common across the different versions of the command."""
    child.admin = "Enabled" if interface.admin_state == "enable" else "Administratively down"
    if interface.oper_state == "up" and not _is_virtual_interface(interface.name):
        child_link_info = "Up"
        child_link_flag = "Up"
    elif not _is_virtual_interface(interface.name):
        child_link_info = "Down"
        child_link_flag = "Down"
    else:
        child_link_info = "Up"
        child_link_flag = "Loopback"
    child.link = child_link_info
    child.mtu = interface.mtu if interface.mtu else "Unlimited"
    if interface.mtu is not None:
        # maximum you can add is 2*4 if the subintf is QinQ and we assume worst case
        child.mru = interface.mtu + 8
    else:
        child.mru = interface.mtu
    child.loopback = "Disabled" if interface.loopback_mode == "none" else "Enabled"
    if interface.ethernet.exists():
        child.type = "Loopback" if _is_virtual_interface(interface.name) else "Ethernet"
        state_ethernet = interface.ethernet.get(0)
        child.flow_control = "Disabled"
        for state_flow_control in state_ethernet.flow_control.items():
            if state_flow_control.receive:
                child.flow_control = "Enabled"
            child.speed = state_ethernet.port_speed
    else:
        child.type = "Unknown"
        child.speed = "Unknown"
        child.flow_control = "Unknown"
    # If the system is a D1 that might have an autonegotiation setting and that is true
    # by default but can be set to off so we need to find that information somewhere.
    # If it is not a D1 or the port speed is higher than 1 then autoneg  has to be True
    # (or enabled) in all circumstances
    # Any case where autonegotiation on a D1 is controlled via configuration is not handled
    child.auto_negotiation = "Enabled"
    if interface.ethernet.exists():
        try:
            state_eth = interface.ethernet.get(0)
            pspeed = getattr(state_eth, 'port_speed', '')
            if pspeed and any(s in str(pspeed) for s in ['10G', '25G', '40G', '100G', '400G']):
                child.auto_negotiation = "Disabled"
            else:
                child.auto_negotiation = "Enabled"
        except Exception:
            pass

    # These attributes were given placeholder values due to no direct
    # mapping being available or a lack of understanding the source
    # material. These can be extended upon later.
    child.mode = "Unknown"
    child.source_filter = "N/A"
    child.remote_fault = "Online"
    child.device_flags = f"Present Running {child_link_flag}"
    child.interface_flags = f"{child_link_flag}"
    child.link_flags = "None"
    child.proto = []
    child.local = {"inet": [], "inet6": []}
    child.remote = []
    return child

def _get_add_info(subinterface):
    """Helper function to gather information about IPv4 and IPv6 addresses and neighbors."""
    proto = []
    local = {"inet": [], "inet6": []}
    neighbors = {"inet": set(), "inet6": set()}
    remote = ""
    family_info = {
        "inet": ("ipv4", "arp", "ipv4_address"),
        "inet6": ("ipv6", "neighbor_discovery", "ipv6_address")
    }
    for family,info in family_info.items():
        context = getattr(subinterface, info[0])
        if context.exists():
            for ip_context in context.items():
                if ip_context.address.exists():
                    proto.append(family)
                    for address in ip_context.address.items():
                        flags = ""
                        if address.primary:
                            flags += "Primary"
                        if str(address.status) == "preferred":
                            if flags != "":
                                flags += " "
                            flags += "Preferred"
                        local[family].append(
                            (
                                ipaddress.ip_address(address.ip_prefix.split("/")[0]),
                                ipaddress.ip_network(address.ip_prefix, strict=False),
                                flags,
                            )
                        )
                    nd_container = getattr(ip_context, info[1], None)
                    if nd_container is not None and nd_container.exists():
                        for neigh in nd_container.get(0).neighbor.items():
                            neighbors[family].add(getattr(neigh, info[2]))

    return "N/A", "N/A", neighbors, "N/A", "N/A", proto, local, remote

def _chassis_type(state):
    """Function to retrieve chassis type data needed to output the autonegotiation status."""
    path = build_path("/platform/chassis/type")
    return state.server.get_data_store(DataStore.State).stream_data(path, recursive=False)

def _get_qos(state):
    """Function to retrieve QoS data needed to speak on the amount of queues per interface."""
    path_qos = build_path("/qos/interfaces/interface")
    return state.server.get_data_store(DataStore.State).stream_data(path_qos, recursive=True)
