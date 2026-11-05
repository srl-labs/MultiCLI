#!/bin/bash
###############################################################################
# switch-multicli.sh
# Install or switch MultiCLI NOS submodes and default persona on an SR Linux node.
# Usage: ./tools/switch-multicli.sh <all|arista|cisco|juniper|nokia|none> [node_name] [--default <persona>]
###############################################################################

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET_NOS="${1:-}"
TARGET_NODE="${2:-leaf1-1}"
DEFAULT_PERSONA=""

if [[ ! "$TARGET_NODE" =~ ^[a-zA-Z0-9_.-]+$ ]]; then
    echo "Error: Invalid target node name '$TARGET_NODE'"
    exit 1
fi

shift 2 2>/dev/null || true
while [[ $# -gt 0 ]]; do
    case "$1" in
        --default|-d)
            DEFAULT_PERSONA="${2:-}"
            shift 2 2>/dev/null || shift 1
            ;;
        *)
            shift 1
            ;;
    esac
done

if [ -z "$TARGET_NOS" ]; then
    echo "Usage: $0 <all|arista|cisco|juniper|nokia|none|comma-separated> [node_name (default: leaf1-1)] [--default <arista|cisco|juniper|nokia|none>]"
    echo ""
    echo "Examples:"
    echo "  $0 all spine                           # Installs all submodes (eos, nxos, junos, sros); keeps root 'show' native"
    echo "  $0 all leaf1-1 --default arista        # Installs all submodes and sets root 'show' persona to Arista EOS"
    echo "  $0 arista leaf1-1                      # Installs only Arista EOS and sets root 'show' persona to Arista EOS"
    echo "  $0 cisco leaf1-2                       # Installs only Cisco NX-OS and sets root 'show' persona to Cisco NX-OS"
    echo "  $0 juniper leaf2-1                     # Installs only Juniper JUNOS and sets root 'show' persona to Juniper JUNOS"
    echo "  $0 nokia leaf2-2                       # Installs only Nokia SR OS and sets root 'show' persona to Nokia SR OS"
    echo "  $0 eos,nxos spine                      # Installs Arista EOS and Cisco NX-OS submodes; keeps root 'show' native"
    echo "  $0 none leaf1-1                        # Removes MultiCLI global plugins while preserving unrelated files"
    exit 1
fi

VENDORS=()
IFS=',' read -ra ADDR <<< "$TARGET_NOS"
for part in "${ADDR[@]}"; do
    case "$part" in
        all|multicli)
            VENDORS=("arista" "cisco-nx" "juniper" "nokia")
            break
            ;;
        none|disable|off|srl|srlinux)
            VENDORS=()
            DEFAULT_PERSONA="none"
            break
            ;;
        arista|eos)
            VENDORS+=("arista")
            ;;
        cisco|cisco-nx|nxos)
            VENDORS+=("cisco-nx")
            ;;
        juniper|junos)
            VENDORS+=("juniper")
            ;;
        nokia|sros)
            VENDORS+=("nokia")
            ;;
        *)
            echo "Error: Unknown NOS '$part'. Choose 'all', 'arista', 'cisco', 'juniper', 'nokia', or 'none'."
            exit 1
            ;;
    esac
done

if [ -z "$DEFAULT_PERSONA" ]; then
    if [ "${#VENDORS[@]}" -eq 1 ]; then
        case "${VENDORS[0]}" in
            arista) DEFAULT_PERSONA="arista" ;;
            cisco-nx) DEFAULT_PERSONA="cisco" ;;
            juniper) DEFAULT_PERSONA="juniper" ;;
            nokia) DEFAULT_PERSONA="nokia" ;;
        esac
    else
        DEFAULT_PERSONA="none"
    fi
fi

case "$DEFAULT_PERSONA" in
    arista|cisco|juniper|nokia|none|all)
        ;;
    *)
        echo "Error: Invalid default persona '$DEFAULT_PERSONA'. Must be arista, cisco, juniper, nokia, none, or all."
        exit 1
        ;;
esac

TARGET_CLI_DIR=""
USE_DOCKER_EXEC=false

if [ -n "${CLAB_DIR:-}" ]; then
    if [ -d "$CLAB_DIR/${TARGET_NODE}/config/cli" ]; then
        TARGET_CLI_DIR="$CLAB_DIR/${TARGET_NODE}/config/cli"
    elif [ -d "$CLAB_DIR" ]; then
        TARGET_CLI_DIR="$CLAB_DIR"
    fi
fi

if [ -z "$TARGET_CLI_DIR" ] && command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' | grep -qx "$TARGET_NODE"; then
    USE_DOCKER_EXEC=true
fi

if [ "$USE_DOCKER_EXEC" = false ] && [ -z "$TARGET_CLI_DIR" ]; then
    MATCH="$(find "$REPO_ROOT" -maxdepth 4 -type d -path "*/${TARGET_NODE}/config/cli" 2>/dev/null | head -n 1 || true)"
    if [ -n "$MATCH" ] && [ -d "$MATCH" ]; then
        TARGET_CLI_DIR="$MATCH"
    else
        echo "Error: Could not locate configuration directory for '$TARGET_NODE' and container is not running."
        echo "Please specify CLAB_DIR environment variable or start the Containerlab topology."
        exit 1
    fi
fi

echo "==> Configuring node '$TARGET_NODE' with MultiCLI [${VENDORS[*]:-none}] (default persona: $DEFAULT_PERSONA)..."

TMP_STAGE="$(mktemp -d)"
trap 'rm -rf "$TMP_STAGE"' EXIT

if [ "${#VENDORS[@]}" -gt 0 ]; then
    python3 - "$REPO_ROOT" "$TMP_STAGE" "$DEFAULT_PERSONA" "${VENDORS[@]}" << 'PYEOF'
import json
import os
import shutil
import sys

repo_root = sys.argv[1]
stage_dir = sys.argv[2]
default_persona = sys.argv[3]
vendors = sys.argv[4:]

installed_files = set()
installed_dirs = set()

for v in vendors:
    src_root = os.path.join(repo_root, v)
    if not os.path.isdir(src_root):
        raise SystemExit(f"Error: Vendor directory not found: {src_root}")
    for root, d_list, f_list in os.walk(src_root):
        d_list[:] = [d for d in d_list if d != "__pycache__" and not d.startswith(".")]
        for d in d_list:
            rel_d = os.path.relpath(os.path.join(root, d), src_root)
            os.makedirs(os.path.join(stage_dir, rel_d), exist_ok=True)
            if rel_d != "plugins":
                installed_dirs.add(rel_d)
        for f in f_list:
            if f.startswith(".") or f.endswith((".pyc", ".pyo")) or f.lower() == "readme.md":
                continue
            src_f = os.path.join(root, f)
            rel_f = os.path.relpath(src_f, src_root)
            dst_f = os.path.join(stage_dir, rel_f)
            os.makedirs(os.path.dirname(dst_f), exist_ok=True)
            shutil.copy2(src_f, dst_f)
            installed_files.add(rel_f)

with open(os.path.join(stage_dir, "default_persona"), "w", encoding="utf-8") as fp:
    fp.write(f"{default_persona}\n")
installed_files.add("default_persona")

manifest = {
    "version": "0.2.0",
    "installed_persona": default_persona,
    "installed_files": sorted(installed_files),
    "installed_dirs": sorted(installed_dirs),
}
with open(os.path.join(stage_dir, ".multicli_manifest.json"), "w", encoding="utf-8") as fp:
    json.dump(manifest, fp, indent=2)
    fp.write("\n")
PYEOF
fi

CLEANUP_PY='
import json
import os
import shutil
import sys

cli_dir = sys.argv[1]
manifest_path = os.path.join(cli_dir, ".multicli_manifest.json")
legacy_files = {
    "plugins/main_arista.py", "plugins/main_cisco.py", "plugins/main_juniper.py", "plugins/main_nokia.py",
    "plugins/ip_reports.py", "plugins/mac_reports.py", "plugins/Cisco_nxos_lldp_neighbor",
    "plugins/Cisco_nxos_lldp_neighbor.py", "plugins/ethernet_switching_reports.py", "plugins/show_interfaces.py",
    "plugins/sros_bgp_report.py", "plugins/service_report.py", "plugins/sros_router_report.py",
    "bgp/bgp_evpn_report.py", "bgp/ip_bgp_report.py", "bgp/sros_bgpsummary.py",
    "interface/arista_arp_details.py", "interface/arista_interface_detail.py", "interface/arista_interface_status.py",
    "ip/ip_bgp_report.py", "ip/ip_interface_report.py", "ip/ip_route_report.py",
    "mac/mac_address_table_report.py", "eth_switch/ethernet_switching_table_report.py", "evpn/evpn_report.py",
    "default_persona", "README.md",
}
legacy_dirs = {"system", "routing", "interface", "ip", "mac", "eth_switch", "bgp", "evpn", "service"}

to_remove = set(legacy_files)
dirs_to_clean = set(legacy_dirs)
if os.path.exists(manifest_path):
    try:
        with open(manifest_path, encoding="utf-8") as f:
            m = json.load(f)
            to_remove.update(m.get("installed_files", []))
            dirs_to_clean.update(m.get("installed_dirs", []))
    except Exception:
        pass

for rel in to_remove:
    fp = os.path.join(cli_dir, rel)
    if os.path.isfile(fp) or os.path.islink(fp):
        try:
            os.remove(fp)
        except OSError:
            pass

for root, d_list, _ in os.walk(cli_dir, topdown=False):
    for d in d_list:
        if d == "__pycache__":
            shutil.rmtree(os.path.join(root, d), ignore_errors=True)

for d in sorted(dirs_to_clean - {"plugins", "."}, key=len, reverse=True):
    dp = os.path.join(cli_dir, d)
    if os.path.isdir(dp):
        try:
            os.rmdir(dp)
        except OSError:
            pass

if os.path.exists(manifest_path):
    try:
        os.remove(manifest_path)
    except OSError:
        pass
'

if [ "$USE_DOCKER_EXEC" = true ]; then
    docker exec -u root "$TARGET_NODE" mkdir -p /etc/opt/srlinux/cli/plugins
    docker exec -u root "$TARGET_NODE" /opt/srlinux/python/virtual-env/bin/python3 -c "$CLEANUP_PY" /etc/opt/srlinux/cli
    if [ "${#VENDORS[@]}" -gt 0 ]; then
        tar -C "$TMP_STAGE" -cf - . | docker exec -u root -i "$TARGET_NODE" tar --no-same-owner -C /etc/opt/srlinux/cli -xf -
    fi
    docker exec -u root "$TARGET_NODE" chmod -R a+rX /etc/opt/srlinux/cli
    echo "==> Successfully configured [${VENDORS[*]:-none}] on $TARGET_NODE."
else
    mkdir -p "$TARGET_CLI_DIR"/plugins
    python3 -c "$CLEANUP_PY" "$TARGET_CLI_DIR"
    if [ "${#VENDORS[@]}" -gt 0 ]; then
        cp -rf --no-preserve=ownership,timestamps "$TMP_STAGE"/. "$TARGET_CLI_DIR"/
    fi
    echo "==> Successfully configured [${VENDORS[*]:-none}] on $TARGET_NODE ($TARGET_CLI_DIR)."
fi

echo "==> Test now with: docker exec -it $TARGET_NODE sr_cli"
