#!/usr/bin/env python3
# coding=utf-8
###########################################################################
# MultiCLI NDK Agent for Nokia SR Linux
# License: Apache-2.0
###########################################################################

import datetime
import json
import logging
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

import config_service_pb2
import grpc
import sdk_common_pb2
import sdk_service_pb2
import sdk_service_pb2_grpc
import telemetry_service_pb2
import telemetry_service_pb2_grpc

agent_name = "multicli"

enabled_nos_command = "enabled-nos"
repo_url_command = "repo-url"
DEFAULT_REPO_URL = "https://github.com/srl-labs/multicli/archive/refs/heads/main.zip"

cli_plugins_dir = "/etc/opt/srlinux/cli"
required_dirs = {"arista", "cisco-nx", "juniper", "nokia"}

MANIFEST_FILE = ".multicli_manifest.json"
MAX_UNCOMPRESSED_ZIP_BYTES = 100 * 1024 * 1024

LEGACY_MULTICLI_FILES = {
    "plugins/main_arista.py",
    "plugins/main_cisco.py",
    "plugins/main_juniper.py",
    "plugins/main_nokia.py",
    "plugins/ip_reports.py",
    "plugins/mac_reports.py",
    "plugins/Cisco_nxos_lldp_neighbor",
    "plugins/Cisco_nxos_lldp_neighbor.py",
    "plugins/ethernet_switching_reports.py",
    "plugins/show_interfaces.py",
    "plugins/sros_bgp_report.py",
    "plugins/service_report.py",
    "plugins/sros_router_report.py",
    "bgp/bgp_evpn_report.py",
    "bgp/ip_bgp_report.py",
    "bgp/sros_bgpsummary.py",
    "interface/arista_arp_details.py",
    "interface/arista_interface_detail.py",
    "interface/arista_interface_status.py",
    "ip/ip_bgp_report.py",
    "ip/ip_interface_report.py",
    "ip/ip_route_report.py",
    "mac/mac_address_table_report.py",
    "eth_switch/ethernet_switching_table_report.py",
    "evpn/evpn_report.py",
    "default_persona",
    "README.md",
}

LEGACY_MULTICLI_DIRS = [
    "system",
    "routing",
    "interface",
    "ip",
    "mac",
    "eth_switch",
    "bgp",
    "evpn",
    "service",
]


def exit_gracefully(signum, frame):
    global sigterm_exit
    logging.info("Caught signal :: %s; unregistering MultiCLI agent", signum)
    sigterm_exit = True
    try:
        unregister_request = sdk_service_pb2.AgentRegistrationRequest()
        unregister_response = stub.AgentUnRegister(request=unregister_request, metadata=metadata)
        logging.info(
            "Unregister response :: %s",
            sdk_common_pb2.SdkMgrStatus.Name(unregister_response.status),
        )
    except grpc.RpcError as err:
        logging.error("Exit RPC error: %s", err)
    sys.exit(0)


def send_keep_alive():
    while not sigterm_exit:
        try:
            logging.info("Send Keep Alive")
            keepalive_request = sdk_service_pb2.KeepAliveRequest()
            keepalive_response = stub.KeepAlive(request=keepalive_request, metadata=metadata)
            if keepalive_response.status == sdk_common_pb2.SdkMgrStatus.Value("SDK_MGR_STATUS_FAILED"):
                logging.error("Keep Alive failed")
        except grpc.RpcError as err:
            logging.warning("Keep Alive RPC error: %s", err)
        time.sleep(10)


def create_sdk_stream():
    request = sdk_service_pb2.NotificationRegisterRequest(
        op=sdk_service_pb2.NotificationRegisterRequest.Operation.OPERATION_CREATE
    )
    notification_response = stub.NotificationRegister(request=request, metadata=metadata)
    if notification_response.status == sdk_common_pb2.SdkMgrStatus.Value("SDK_MGR_STATUS_FAILED"):
        logging.error("Notification Stream Create failed with error %s", notification_response.error_str)
        return 0
    logging.info("Notification Stream successful. stream ID: %s", notification_response.stream_id)
    return notification_response.stream_id


def add_sdk_subscription(stream_id, sub_type):
    subs_request = None
    if sub_type == "config":
        subs_request = sdk_service_pb2.NotificationRegisterRequest(
            op=sdk_service_pb2.NotificationRegisterRequest.Operation.OPERATION_ADD_SUBSCRIPTION,
            stream_id=stream_id,
            config=config_service_pb2.ConfigSubscriptionRequest(),
        )

    if subs_request is not None:
        subscription_response = stub.NotificationRegister(request=subs_request, metadata=metadata)
        logging.info(subscription_response)
        if subscription_response.status == sdk_common_pb2.SdkMgrStatus.Value("SDK_MGR_STATUS_FAILED"):
            logging.error("%s subscription failed.", sub_type)
        else:
            logging.info("%s subscription successful. Stream ID: %s", sub_type, subscription_response.stream_id)


def update_state_datastore(js_path, js_data):
    try:
        telemetry_stub = telemetry_service_pb2_grpc.SdkMgrTelemetryServiceStub(channel)
        telemetry_update_request = telemetry_service_pb2.TelemetryUpdateRequest()
        telemetry_info = telemetry_update_request.states.add()
        telemetry_info.key.js_path = js_path
        telemetry_info.data.json_content = js_data

        logging.info("Telemetry_Update_Request ::\n%s", telemetry_update_request)
        telemetry_response = telemetry_stub.TelemetryAddOrUpdate(
            request=telemetry_update_request, metadata=metadata
        )
        logging.info("Response: %s %%%%%% %s", telemetry_response.status, telemetry_response.error_str)
        return telemetry_response
    except grpc.RpcError as err:
        logging.error("TelemetryAddOrUpdate RPC error: %s", err)
        return None


def delete_state_datastore(js_path):
    try:
        telemetry_stub = telemetry_service_pb2_grpc.SdkMgrTelemetryServiceStub(channel)
        telemetry_delete_request = telemetry_service_pb2.TelemetryDeleteRequest()
        key = telemetry_delete_request.keys.add()
        key.js_path = js_path

        logging.info("Telemetry_Delete_Request ::\n%s", telemetry_delete_request)
        telemetry_response = telemetry_stub.TelemetryDelete(
            request=telemetry_delete_request, metadata=metadata
        )
        logging.info("Delete Response: %s %%%%%% %s", telemetry_response.status, telemetry_response.error_str)
        return telemetry_response
    except grpc.RpcError as err:
        logging.error("TelemetryDelete RPC error: %s", err)
        return None


def clean_multicli_assets(target_dir=cli_plugins_dir):
    """Remove only MultiCLI-tracked files, preserving all user/third-party plugins."""
    if not os.path.isdir(target_dir):
        return

    manifest_path = os.path.join(target_dir, MANIFEST_FILE)
    installed_files = set()
    installed_dirs = set()

    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as mf:
                data = json.load(mf)
                installed_files = set(data.get("installed_files", []))
                installed_dirs = set(data.get("installed_dirs", []))
        except Exception as err:
            logging.warning("Error reading manifest: %s", err)

    files_to_remove = installed_files | LEGACY_MULTICLI_FILES
    for rel_path in files_to_remove:
        full_path = os.path.join(target_dir, rel_path)
        if os.path.isfile(full_path):
            try:
                os.remove(full_path)
            except Exception as err:
                logging.warning("Failed to remove %s: %s", full_path, err)

    dirs_to_check = (installed_dirs | set(LEGACY_MULTICLI_DIRS)) - {"plugins", "."}
    for rel_dir in sorted(dirs_to_check, key=len, reverse=True):
        full_dir = os.path.join(target_dir, rel_dir)
        if os.path.isdir(full_dir):
            # Clean any leftover __pycache__ inside vendor module directories first
            for root, dirs, _ in os.walk(full_dir, topdown=False):
                if "__pycache__" in dirs:
                    shutil.rmtree(os.path.join(root, "__pycache__"), ignore_errors=True)
            try:
                os.rmdir(full_dir)
            except OSError:
                pass

    if os.path.exists(manifest_path):
        try:
            os.remove(manifest_path)
        except OSError:
            pass

    plugins_dir = os.path.join(target_dir, "plugins")
    if os.path.isdir(plugins_dir):
        for root, dirs, _ in os.walk(plugins_dir):
            if "__pycache__" in dirs:
                shutil.rmtree(os.path.join(root, "__pycache__"), ignore_errors=True)


def copy_with_manifest(source_dirs, target_dir, persona):
    """Copy vendor tree(s) to target and write .multicli_manifest.json."""
    if isinstance(source_dirs, str):
        source_dirs = [source_dirs]

    os.makedirs(target_dir, exist_ok=True)

    manifest = {
        "version": "0.2.0",
        "installed_persona": persona,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "installed_files": [],
        "installed_dirs": [],
    }

    for s_dir in source_dirs:
        for root, dirs, files in os.walk(s_dir):
            dirs[:] = [d for d in dirs if d != "__pycache__" and not d.startswith(".")]
            rel_root = os.path.relpath(root, s_dir)
            dest_root = target_dir if rel_root == "." else os.path.join(target_dir, rel_root)
            os.makedirs(dest_root, exist_ok=True)
            if rel_root != "." and rel_root not in manifest["installed_dirs"]:
                manifest["installed_dirs"].append(rel_root)

            for fname in files:
                if fname.startswith(".") or fname.endswith((".pyc", ".pyo")):
                    continue
                src_f = os.path.join(root, fname)
                dest_f = os.path.join(dest_root, fname)
                shutil.copy2(src_f, dest_f)
                rel_dest = os.path.relpath(dest_f, target_dir)
                if rel_dest not in manifest["installed_files"]:
                    manifest["installed_files"].append(rel_dest)

    persona_file = os.path.join(target_dir, "default_persona")
    with open(persona_file, "w", encoding="utf-8") as pf:
        pf.write(f"{persona}\n")
    if "default_persona" not in manifest["installed_files"]:
        manifest["installed_files"].append("default_persona")

    manifest_path = os.path.join(target_dir, MANIFEST_FILE)
    with open(manifest_path, "w", encoding="utf-8") as mf:
        json.dump(manifest, mf, indent=2)


def safe_extract_zip(zip_path, extract_dir):
    """Safely extract zip_path into extract_dir while preventing zip-slip, symlinks, and zip bombs."""
    os.makedirs(extract_dir, exist_ok=True)
    real_extract_dir = os.path.realpath(extract_dir)
    total_uncompressed = 0
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            if stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError(f"Symlink entries are not permitted in zip archive: {member.filename}")
            total_uncompressed += max(int(member.file_size), 0)
            if total_uncompressed > MAX_UNCOMPRESSED_ZIP_BYTES:
                raise ValueError("Zip archive exceeds maximum permitted uncompressed size")
            target_path = os.path.realpath(os.path.join(real_extract_dir, member.filename))
            if target_path != real_extract_dir and not target_path.startswith(real_extract_dir + os.sep):
                raise ValueError(f"Unsafe zip archive entry: {member.filename}")
        zf.extractall(real_extract_dir)


def find_extracted_root(extract_dir):
    """Locate the extracted MultiCLI root directory (supports flat or nested zip archives)."""
    if not os.path.isdir(extract_dir):
        return None

    top_dirs = {
        name for name in os.listdir(extract_dir)
        if os.path.isdir(os.path.join(extract_dir, name))
    }
    if required_dirs.issubset(top_dirs):
        return extract_dir

    for item in sorted(top_dirs):
        candidate = os.path.join(extract_dir, item)
        sub_dirs = {
            name for name in os.listdir(candidate)
            if os.path.isdir(os.path.join(candidate, name))
        }
        if required_dirs.issubset(sub_dirs):
            return candidate

    return None


def supports_multi_nos_archive(extracted_root):
    """Verify the archive contains unified multi-NOS submode plugins without filename collisions."""
    unified_entrypoints = [
        ("arista", "plugins", "main_arista.py"),
        ("cisco-nx", "plugins", "main_cisco.py"),
        ("juniper", "plugins", "main_juniper.py"),
        ("nokia", "plugins", "main_nokia.py"),
    ]
    if not all(os.path.isfile(os.path.join(extracted_root, *parts)) for parts in unified_entrypoints):
        return False
    legacy_colliding = [
        ("cisco-nx", "plugins", "ip_reports.py"),
        ("juniper", "plugins", "show_interfaces.py"),
        ("nokia", "plugins", "sros_bgp_report.py"),
    ]
    if any(os.path.exists(os.path.join(extracted_root, *parts)) for parts in legacy_colliding):
        return False
    return True


def multicli_function(selected_nos, selected_repo_url):
    if selected_nos == "none":
        logging.info("MultiCLI disabled (enabled-nos set to 'none'); cleaning MultiCLI assets.")
        clean_multicli_assets(cli_plugins_dir)
        update_state_datastore(
            js_path=".multicli",
            js_data=json.dumps({
                "enabled-nos": "none",
                "repo-url": selected_repo_url,
                "error-messages": "No errors",
            }),
        )
        return

    ip_bin = shutil.which("ip") or "/usr/sbin/ip"
    curl_bin = shutil.which("curl") or "/usr/bin/curl"

    with tempfile.TemporaryDirectory(prefix="multicli_") as tmp_dir:
        zip_path = os.path.join(tmp_dir, "repo.zip")
        extract_dir = os.path.join(tmp_dir, "extracted")
        logging.info("Downloading MultiCLI archive from %s via srbase-mgmt", selected_repo_url)

        curl_cmd = [
            curl_bin,
            "-f",
            "-L",
            "--retry",
            "2",
            "--retry-delay",
            "1",
            "--retry-all-errors",
            "--connect-timeout",
            "5",
            "--max-time",
            "60",
            "-o",
            zip_path,
            "--",
            selected_repo_url,
        ]
        if os.path.exists("/var/run/netns/srbase-mgmt"):
            cmd = [ip_bin, "netns", "exec", "srbase-mgmt"] + curl_cmd
        else:
            cmd = curl_cmd

        try:
            subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                env=os.environ,
            )
        except subprocess.CalledProcessError as err:
            err_msg = err.stderr.decode(errors="replace").strip() if err.stderr else str(err)
            logging.error("Download failed: %s", err_msg)
            update_state_datastore(
                js_path=".multicli",
                js_data=json.dumps({
                    "enabled-nos": selected_nos,
                    "repo-url": selected_repo_url,
                    "error-messages": "Verify DNS configuration and repository reachability via mgmt network-instance",
                }),
            )
            return

        logging.info("Extracting MultiCLI archive...")
        try:
            safe_extract_zip(zip_path, extract_dir)
        except (zipfile.BadZipFile, ValueError, OSError) as err:
            logging.error("Extraction failed for %s: %s", zip_path, err)
            update_state_datastore(
                js_path=".multicli",
                js_data=json.dumps({
                    "enabled-nos": selected_nos,
                    "repo-url": selected_repo_url,
                    "error-messages": "Please verify the repo-url or the ZIP file provided in the repository",
                }),
            )
            return

        extracted_root = find_extracted_root(extract_dir)
        if extracted_root is None:
            logging.error("Downloaded archive does not contain required MultiCLI vendor directories")
            update_state_datastore(
                js_path=".multicli",
                js_data=json.dumps({
                    "enabled-nos": selected_nos,
                    "repo-url": selected_repo_url,
                    "error-messages": "The downloaded MultiCLI repository is corrupted",
                }),
            )
            return

        if selected_nos == "all" and not supports_multi_nos_archive(extracted_root):
            logging.error(
                "Archive at %s does not contain unified multi-NOS plugins required for enabled-nos 'all'",
                selected_repo_url,
            )
            update_state_datastore(
                js_path=".multicli",
                js_data=json.dumps({
                    "enabled-nos": selected_nos,
                    "repo-url": selected_repo_url,
                    "error-messages": "Repository archive does not support 'enabled-nos all'; unified multi-NOS plugins are required",
                }),
            )
            return

        logging.info("Applying MultiCLI plugins for selected NOS: %s", selected_nos)
        clean_multicli_assets(cli_plugins_dir)

        match selected_nos:
            case "nokia-sros":
                copy_with_manifest([os.path.join(extracted_root, "nokia")], cli_plugins_dir, "nokia")
            case "arista":
                copy_with_manifest([os.path.join(extracted_root, "arista")], cli_plugins_dir, "arista")
            case "juniper":
                copy_with_manifest([os.path.join(extracted_root, "juniper")], cli_plugins_dir, "juniper")
            case "cisco":
                copy_with_manifest([os.path.join(extracted_root, "cisco-nx")], cli_plugins_dir, "cisco")
            case "all":
                all_vendor_dirs = [
                    os.path.join(extracted_root, d)
                    for d in ["arista", "cisco-nx", "juniper", "nokia"]
                ]
                copy_with_manifest(all_vendor_dirs, cli_plugins_dir, "none")
            case _:
                logging.warning("Unsupported enabled-nos value: %s", selected_nos)
                return

        logging.info("MultiCLI %s commands enabled.", selected_nos)
        update_state_datastore(
            js_path=".multicli",
            js_data=json.dumps({
                "enabled-nos": selected_nos,
                "repo-url": selected_repo_url,
                "error-messages": "No errors",
            }),
        )


def process_notification(notification):
    if notification.HasField("config"):
        if notification.config.key.js_path != ".multicli":
            return

        if notification.config.op == sdk_common_pb2.SdkMgrOperation.Value("SDK_MGR_OPERATION_DELETE"):
            logging.info("--> Received config delete notification; cleaning MultiCLI assets and state")
            clean_multicli_assets(cli_plugins_dir)
            delete_state_datastore(".multicli")
        elif notification.config.HasField("data"):
            logging.info("--> Received config notification")
            logging.info(notification.config)
            data = json.loads(notification.config.data.json) if notification.config.data.json else {}
            selected_nos = data.get(enabled_nos_command, "none")
            repo_url = data.get(repo_url_command, DEFAULT_REPO_URL)
            logging.info("Selected NOS: %s", selected_nos)
            logging.info("Repo URL: %s", repo_url)
            multicli_function(selected_nos, repo_url)
    else:
        logging.info("--> Received unexpected notification")

    if sigterm_exit:
        logging.info("Agent Stopped Time :: %s", datetime.datetime.now())


def run_agent():
    register_request = sdk_service_pb2.AgentRegistrationRequest()
    register_request.agent_liveliness = 15
    register_request.auto_telemetry_state = True

    register_response = stub.AgentRegister(request=register_request, metadata=metadata)
    if register_response.status == sdk_common_pb2.SdkMgrStatus.Value("SDK_MGR_STATUS_FAILED"):
        logging.error("Agent Registration failed with error %s", register_response.error_str)
    else:
        logging.info("Agent Registration successful. App ID: %s", register_response.app_id)

    thread = threading.Thread(target=send_keep_alive, daemon=True)
    thread.start()

    stream_id = create_sdk_stream()
    add_sdk_subscription(stream_id, "config")

    stream_request = sdk_service_pb2.NotificationStreamRequest(stream_id=stream_id)
    stream_response = sdk_notification_service_client.NotificationStream(
        request=stream_request, metadata=metadata
    )

    for response in stream_response:
        for notification in response.notifications:
            logging.info("Received Notification ::\n%s", notification)
            process_notification(notification)


metadata = [("agent_name", agent_name)]
channel = grpc.insecure_channel("localhost:50053")
stub = sdk_service_pb2_grpc.SdkMgrServiceStub(channel)
sdk_notification_service_client = sdk_service_pb2_grpc.SdkNotificationServiceStub(channel)
sigterm_exit = False

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, exit_gracefully)
    log_filename = "/var/log/srlinux/stdout/multicli.log"
    logging.basicConfig(filename=log_filename, filemode="w", datefmt="%H:%M:%S", level=logging.INFO)
    logging.info("Agent Start Time :: %s", datetime.datetime.now())
    run_agent()
    sys.exit(0)
