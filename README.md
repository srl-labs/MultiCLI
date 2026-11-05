# MultiCLI

Welcome to the MultiCLI project for Nokia SR Linux.

[SR Linux](https://learn.srlinux.dev/) is the industry's most modern Network Operating System (NOS) enabling unmatched automation and programmability features.

One of its capabilities is the ability to customize the CLI on SR Linux.

All SR Linux CLI show commands shipped with the software are written in executable python scripts leveraging the state yang models.

Users are allowed to take those python scripts, modify them to fit their use case or build a brand new CLI command leveraging the same state models.

These customized CLI scripts are called **Custom CLI plugins** in SR Linux.

Since everything is modeled in yang from the ground up, this allows the user to use CLI to access any state object or attribute in the system and display it in the format they are familiar with.

Custom CLI commands also provide the same auto-completion and help features that come with native SR Linux commands.

So how does this benefit the user? There are few use cases that we could think of like:
- Use the same MOP and command set that you previously used for another vendor
- Use the same automation or monitoring scripts that was written for another vendor
- allow users to start using SR Linux using the same commands they used for another vendor

All these are CLI heavy use cases. You may have more use cases in your mind.

This is awesome! But how do i put this into action?

## What is MultiCLI about?

The mission of MultiCLI is to get you started with SR Linux CLI customization feature for your environment.

As part of this project, we are publishing custom CLI plugins for `show` commands that will match the command and output of our friends in the industry.

The user community is free to take these scripts, use them as is or modify them based on their end goal. We will also be happy to accept new contributions from the community.

## MultiCLI Plugins

This repo is structured based on the vendor that we try to match in SR Linux CLI.

In this initial release, we have scripts for:

- [Arista EOS](arista/)
- [Cisco NX-OS](cisco-nx/)
- [Juniper JUNOS](juniper/)
- [Nokia SR OS](nokia/)

## Learn how to customize SR Linux CLI

For those intereted in learning the process of customizing the SR Linux CLI, refer to the official [SR Linux CLI plug-in guide](https://documentation.nokia.com/srlinux/24-10/title/cli_plugin.html).

For practical experience, start by using the beginner SReXperts hackathon use case [here](https://github.com/nokia/SReXperts/tree/main/hackathon/activities/srlinux-i-cli-plugin-show-version) following by an intermediate use case [here](https://github.com/nokia/SReXperts/tree/main/hackathon/activities/srlinux-i-custom-cli).

Also, check out these blogs on SR Linux CLI customization:

[Learn SRLinux](https://learn.srlinux.dev/cli/plugins/getting-started/)

[Blog by Alperen](https://networkcloudandeverything.com/programming-a-custom-show-command-with-sr-linux-cli-plugin/)

## Test Lab

With the power of [Containerlab](https://containerlab.dev/) and the free SR Linux docker image, testing these custom CLI commands is a simple process. This repo contains a [lab](lab/) topology with startup configs where these custom commands can be tested.

To test these scripts:
- Clone this repo to your host or use codespaces
- Deploy the EVPN lab or MPLS lab (coming soon)
- All custom CLI plugin files are bound to the nodes using the `bind` function in the topology file
- Each node is configured with 4 custom users:

| User | Password | NOS |
|------|----------|-----|
| auser | auser | Arista EOS commands |
| cnxuser | cnxuser | Cisco NX-OS commands |
| juser | juser | Juniper JUNOS commands |
| nokuser | nokuser | Nokia SR OS commands |

- Each of the above user's directory is loaded with the custom cli plugin files for that NOS.
- Login to any leaf or spine node using any of the 4 usernames to try these commands.

For example, to try NX-OS plugins, login to any leaf or spine nodes using `cnxuser/cnxuser` and try the supported NX-OS commands.

---
<div align=center>
<a href="https://codespaces.new/srl-labs/multicli?quickstart=1">
<img src="https://gitlab.com/rdodin/pics/-/wikis/uploads/d78a6f9f6869b3ac3c286928dd52fa08/run_in_codespaces-v1.svg?sanitize=true" style="width:50%"/></a>

**[Run](https://codespaces.new/srl-labs/multicli?quickstart=1) this lab in GitHub Codespaces for free**.  
[Learn more](https://containerlab.dev/manual/codespaces/) about Containerlab for Codespaces.

</div>

---

To deploy evpn lab:

Clone this repo:

```bash
git clone https://github.com/srl-labs/multicli.git
```

Change to the repo directory:

```bash
cd multicli
```

Deploy the lab:

```bash
sudo clab dep -t srl-evpn-mh.clab.yml
```

All non-MPLS commands are tested on Nokia 7220 IXR-D2L on SR Linux release 25.3.1.

## Usage Modes: Top-Level `show`, Vendor Subtrees, and `srl` Escape Hatch

MultiCLI supports seamless coexistence between vendor CLI syntax and native SR Linux commands:

1. **Top-Level `show` Mode (Single Persona / User Persona)**:
   - When a node (or user login such as `auser`, `cnxuser`, `juser`, `nokuser`) has an active single default persona, vendor commands are registered directly under the top-level `show` tree (e.g., `show version`, `show interfaces status`, `show ip bgp summary`).
   - When multiple personas are installed without a single default (`--default none` or NDK `enabled-nos all`), top-level `show` remains 100% native SR Linux.
2. **Vendor Subtrees (`eos`, `nxos`, `junos`, `sros`)**:
   - Every installed plugin registers a dedicated top-level vendor node (`eos`, `nxos`, `junos`, `sros`) supporting both **one-liner execution** and **interactive submode**:
     ```
     # One-liner execution from root CLI:
     A:admin@spine# eos show interfaces Ethernet1/1 status
     A:admin@spine# nxos show interface Ethernet1/2
     A:admin@spine# junos show interfaces et-0/0/2
     A:admin@spine# sros show router bgp summary

     # Interactive vendor submode:
     A:admin@spine# eos
     --{ running }--[ eos ]--
     A:admin@spine# show version
     ```
3. **Native SR Linux Escape Hatch (`srl show ...`)**:
   - Whenever a single active persona overrides an overlapping root `show` command (`show version`, Cisco `show interface [brief]`, or Nokia `show lag` / `show system lldp neighbor`), the native SR Linux report remains accessible via `srl show ...` (and all `Try SR Linux command:` hints point to `srl show ...`):
     ```
     A:admin@leaf1-2# srl show version
     A:admin@leaf1-2# srl show interface ethernet-1/1 brief
     ```

## Switching Personas Dynamically

MultiCLI includes [`tools/switch-multicli.sh`](tools/switch-multicli.sh) to hot-swap NOS personas on any running Containerlab node (`leaf1-1`, `leaf1-2`, `leaf2-1`, `leaf2-2`, `spine`):

```bash
# Switch leaf1-1 to Arista EOS
./tools/switch-multicli.sh arista leaf1-1

# Switch leaf1-2 to Cisco NX-OS
./tools/switch-multicli.sh cisco leaf1-2

# Switch leaf2-1 to Juniper JUNOS
./tools/switch-multicli.sh juniper leaf2-1

# Switch leaf2-2 to Nokia SR OS
./tools/switch-multicli.sh nokia leaf2-2

# Install all personas simultaneously on spine (keep root show native, or pick a default)
./tools/switch-multicli.sh all spine --default none
./tools/switch-multicli.sh all leaf1-1 --default arista
```

## Declarative Management via NDK Agent

For declarative configuration via YANG/gNMI/CLI (`/multicli enabled-nos <arista|cisco|juniper|nokia-sros|all>`), install the `srl-multicli` Debian package (`srl-multicli_0.2.0_amd64.deb` or `srl-multicli_0.2.0_arm64.deb`). See [`ndk-agent/README.md`](ndk-agent/README.md) for installation, online/offline repository URLs, and build instructions.

## Automated Validation Suite

An automated test harness ([`tests/validate_multicli.py`](tests/validate_multicli.py)) runs the entire command suite over real SSH/CLI sessions against running switches and verifies that command execution is error-free, non-empty, pipe-compatible, and free of hardcoded mock data:

```bash
# Run all tests against default lab nodes (leaf1-1=Arista, leaf1-2=Cisco, leaf2-1=Juniper, leaf2-2=Nokia, spine=Multi-NOS)
python3 tests/validate_multicli.py --install

# Include temporary live OSPF, IS-IS, and BFD protocol fixtures (automatically rolled back on exit)
python3 tests/validate_multicli.py --install --with-igp-fixtures

# Or specify custom nodes:
python3 tests/validate_multicli.py --arista-node leaf1-1 --cisco-node leaf1-2 --juniper-node leaf2-1 --nokia-node leaf2-2 --spine-node spine
```

## This is great, but i want more commands supported for my network

We are inviting contributions from the open source community towards this project.

Or contact your Nokia Account team to engage Nokia Professional Services.

## Resources for further learning

* [SR Linux documentation](https://documentation.nokia.com/srlinux/)
* [Learn SR Linux](https://learn.srlinux.dev/)
* [YANG Browser](https://yang.srlinux.dev/)
* [gNxI Browser](https://gnxi.srlinux.dev/)
