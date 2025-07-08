#!/usr/bin/python
###########################################################################
# Description: CLI plugin for Extreme SLX commands
#
# Copyright (c) 2025 Nokia
###########################################################################

from srlinux.mgmt.cli import CliPlugin, KeyCompleter
from srlinux.syntax import Syntax
from srlinux.location import build_path
import sys
import os

# Try potential base directories
potential_paths = [
    os.path.expanduser('~/cli'),
    '/etc/opt/srlinux/cli'
]

# Find the first valid path
import_base = None
for path in potential_paths:
    if os.path.exists(path):
        import_base = path
        break

if import_base is None:
    raise ImportError("Could not find a valid CLI plugin base directory")

####################################################################
##### Construct the import path. ###################################
'''
Add your directory and create a similar structure like below
'''
####################################################################

import_path = os.path.join(import_base, "interface")
if import_path not in sys.path:
    sys.path.insert(0, import_path)
from extreme_interface_detail import InterfaceDetails

class Plugin(CliPlugin):

    __slots__ = (
        '_header_string',
        '_netinst',
        '_arguments',
        '_netinst_data',
        '_current_netinst',
        '_used_routes',
        '_valid_routes',
        '_received_count',
        '_attrSets_dict',
        '_route_type',
        '_rd',
        '_mac_address',
        '_ip_address',
        '_ip_prefix',
        '_esi',
        '_ethernet_tag',
        '_originating_router',
        '_neighbor',
        '_multicast_source_address',
        '_multicast_group_address',
        '_bgp_rib'
    )

    def load(self, cli, **_kwargs):
        #### Interface ####

        '''
        This section has preprend command called slx because there is an overlap command with extreme and srlinux
        Going forward in new release slx preprend will be depreciated and run the native commands
        example: show slx interface status
        '''

        syntax = Syntax('slx', help='Show Extreme SLX reports')
        slx = cli.show_mode.add_command(syntax)
        # Adding sub-commands of Extreme command:  "show extreme interface detail"
        interfaces = slx.add_command(
            InterfaceDetails().get_syntax_details(),
            update_location=True,
            callback= self._interface_details
        )

########## Interface ###########

    def _interface_details(self, state, arguments, output, **_kwargs):
        if state.is_intermediate_command:
            return
        InterfaceDetails().print(state, arguments, output, **_kwargs)
        msg = 'Try SR Linux command: show interface {interface_name} detail'
        output.print_line(f'\n{"-" * len(msg)}\n{msg}')
        