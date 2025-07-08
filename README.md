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
- [Extreme Networks](extreme/)

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
- Each node is configured with 5 custom users:

| User | Password | NOS |
|------|----------|-----|
| auser | auser | Arista EOS commands |
| cnxuser | cnxuser | Cisco NX-OS commands |
| exuser | exuser | Extreme Networks commands |
| juser | juser | Juniper JUNOS commands |
| nokuser | nokuser | Nokia SR OS commands |

- Each of the above user's directory is loaded with the custom cli plugin files for that NOS.
- Login to any leaf or spine node using any of the 5 usernames to try these commands.

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

## This is great, but i want more commands supported for my network

We are inviting contributions from the open source community towards this project.

Or contact your Nokia Account team to engage Nokia Professional Services.

## Resources for further learning

* [SR Linux documentation](https://documentation.nokia.com/srlinux/)
* [Learn SR Linux](https://learn.srlinux.dev/)
* [YANG Browser](https://yang.srlinux.dev/)
* [gNxI Browser](https://gnxi.srlinux.dev/)
