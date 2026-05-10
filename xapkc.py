#!/usr/bin/env python3
import os
import re
import shutil
import zipfile
import json
import time
import subprocess
import sys
import argparse
import tempfile
from colorama import init, Fore, Style

try:
    import questionary
    HAS_TUI = True
except Exception:
    HAS_TUI = False

# Initialize colorama for colored output
init(autoreset=True)

KNOWN_ABIS = {
    "arm64_v8a",
    "armeabi_v7a",
    "armeabi",
    "x86",
    "x86_64",
    "mips",
    "mips64",
    "riscv64",
    "universal",
}
STREAM_PREFIX = "      → "
SPLIT_INSTALL_ERROR = "Split package requires APKS install-multiple. Ensure objection output is .apks."

def detect_input_kind(path_value):
    lower = path_value.lower()
    if lower.endswith(".xapk"):
        return "xapk"
    if lower.endswith(".apks"):
        return "apks"
    if lower.endswith(".apk"):
        return "apk"
    return "unknown"

def default_objection_output(source_path):
    kind = detect_input_kind(source_path)
    base_name = os.path.splitext(source_path)[0]
    if kind in {"apks", "xapk"}:
        return f"{base_name}.objection.apks"
    return f"{base_name}.objection.apk"

def check_apksigner():
    return shutil.which("apksigner") is not None

def zip_directory(source_dir, output_zip_path):
    with zipfile.ZipFile(output_zip_path, "w", zipfile.ZIP_DEFLATED) as out_zip:
        for root, _, files in os.walk(source_dir):
            for file_name in files:
                file_path = os.path.join(root, file_name)
                arcname = os.path.relpath(file_path, source_dir)
                out_zip.write(file_path, arcname)

def run_stages(stages):
    for label, func in stages:
        print(f"  > {label}")
        try:
            func()
            print(f"  √ {label}")
        except Exception:
            print(f"  x {label}")
            raise

def print_artifact_summary(input_path, artifacts):
    ui_print("info", f"Resolved input: {input_path}")
    if not artifacts:
        return
    ui_print("info", "Artifacts:")
    for name, value in artifacts:
        ui_print("info", f"  - {name}: {value}")

def ui_print(level, message):
    prefixes = {
        "info": "[*]",
        "ok": "[+]",
        "warn": "[!]",
        "err": "[x]",
        "step": "[>]",
    }
    prefix = prefixes.get(level, "[*]")
    colors = {
        "info": Fore.CYAN,
        "ok": Fore.GREEN,
        "warn": Fore.YELLOW,
        "err": Fore.RED,
        "step": Fore.LIGHTBLUE_EX,
    }
    color = colors.get(level, Fore.CYAN)
    print(f"{color}{prefix}{Style.RESET_ALL} {message}")

def sanitize_filename(filepath, dry_run=False):
    """
    Sanitize the filename by replacing disallowed characters with underscores.
    Allowed characters: letters, digits, underscore, hyphen and dot.
    Renames the file if needed.
    """
    path, filename = os.path.split(filepath)
    sanitized_filename = re.sub(r'[^A-Za-z0-9_.-]', '_', filename)
    new_filepath = os.path.join(path, sanitized_filename)

    if filepath != new_filepath:
        if dry_run:
            ui_print("info", f"Dry-run: would rename {filename} -> {sanitized_filename}")
            return new_filepath
        try:
            shutil.move(filepath, new_filepath)
            ui_print("ok", f"File renamed: {filename} -> {sanitized_filename}")
        except Exception as e:
            ui_print("err", f"Error renaming file: {e}")
            return filepath

    return new_filepath

def convert_xapk_to_apks(xapk_path, output_apks_path, dry_run=False):
    """
    Convert an XAPK file to an APKS file:
      1. Extract the XAPK archive.
      2. Read manifest.json to process APK files.
      3. Rename base APK to "base.apk" and split APKs to "split_config.<suffix>.apk".
      4. Create metadata files (meta.sai_v1.json and meta.sai_v2.json).
      5. Package the processed files into a new .apks archive.
    """
    work_dir = tempfile.mkdtemp(prefix="xapk_extract_")
    apks_build_dir = tempfile.mkdtemp(prefix="apks_build_")
    backup_size = 0

    try:
        with zipfile.ZipFile(xapk_path, 'r') as zip_ref:
            zip_ref.extractall(work_dir)
        ui_print("step", f"Extracted XAPK to temporary directory: {work_dir}")

        manifest_path = os.path.join(work_dir, "manifest.json")
        if not os.path.exists(manifest_path):
            raise FileNotFoundError("manifest.json not found in the XAPK.")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        icon_name = manifest.get("icon")
        if icon_name:
            icon_src = os.path.join(work_dir, icon_name)
            if os.path.exists(icon_src):
                shutil.copy(icon_src, os.path.join(apks_build_dir, icon_name))

        split_apks = manifest.get("split_apks", [])
        for entry in split_apks:
            file_name = entry.get("file")
            apk_id = entry.get("id")
            if not file_name or not apk_id:
                continue
            src_file = os.path.join(work_dir, file_name)
            if not os.path.exists(src_file):
                ui_print("warn", f"{file_name} not found; skipping.")
                continue
            backup_size += os.path.getsize(src_file)

            if apk_id == "base":
                dest_name = "base.apk"
            elif apk_id.startswith("config."):
                suffix = apk_id.split("config.", 1)[-1]
                dest_name = f"split_config.{suffix}.apk"
            else:
                dest_name = file_name
            dest_path = os.path.join(apks_build_dir, dest_name)
            shutil.copy(src_file, dest_path)
            ui_print("info", f"Copied and renamed {file_name} as {dest_name}")

        export_timestamp = int(time.time() * 1000)
        label = manifest.get("name", "")
        package_name = manifest.get("package_name", "")
        version_code = int(manifest.get("version_code", 0))
        version_name = manifest.get("version_name", "")
        min_sdk = int(manifest.get("min_sdk_version", 0))
        target_sdk = int(manifest.get("target_sdk_version", 0))

        meta_v1 = {
            "export_timestamp": export_timestamp,
            "label": label,
            "package": package_name,
            "version_code": version_code,
            "version_name": version_name
        }

        meta_v2 = {
            "backup_components": [{
                "size": backup_size,
                "type": "apk_files"
            }],
            "export_timestamp": export_timestamp,
            "split_apk": True,
            "label": label,
            "meta_version": 2,
            "min_sdk": min_sdk,
            "package": package_name,
            "target_sdk": target_sdk,
            "version_code": version_code,
            "version_name": version_name
        }

        with open(os.path.join(apks_build_dir, "meta.sai_v1.json"), "w", encoding="utf-8") as f:
            json.dump(meta_v1, f, separators=(',', ':'))
        with open(os.path.join(apks_build_dir, "meta.sai_v2.json"), "w", encoding="utf-8") as f:
            json.dump(meta_v2, f, separators=(',', ':'))
        ui_print("ok", "Created metadata files: meta.sai_v1.json and meta.sai_v2.json")

        if dry_run:
            ui_print("info", f"Dry-run: skipping APKS packaging to {output_apks_path}")
        else:
            with zipfile.ZipFile(output_apks_path, "w", zipfile.ZIP_DEFLATED) as apks_zip:
                for root, _, files in os.walk(apks_build_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, apks_build_dir)
                        apks_zip.write(file_path, arcname)
            ui_print("ok", f"APKS file created: {output_apks_path}")

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        shutil.rmtree(apks_build_dir, ignore_errors=True)

def run_apk_mitm(apks_path, dry_run=False):
    """
    Execute the apk-mitm command on the given APKS file.
    Displays the output in real time.
    """
    if dry_run:
        ui_print("info", f"Dry-run: would run apk-mitm {apks_path}")
        return
    if not check_apk_mitm():
        ui_print("err", "apk-mitm is not installed or not in the system PATH.")
        return

    ui_print("step", "Launching apk-mitm on the APKS file...")
    cmd = ["apk-mitm", apks_path]
    ui_print("info", f"Running command: {' '.join(cmd)}")
    return_code = stream_command(cmd, label="apk-mitm")
    ui_print("info", f"apk-mitm finished with return code: {return_code}")

def stream_command(cmd, label, dry_run=False):
    if dry_run:
        ui_print("info", f"Dry-run: would run {label}: {' '.join(cmd)}")
        return 0
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            stdin=subprocess.DEVNULL
        )
    except Exception as e:
        ui_print("err", f"Failed to start {label}: {e}")
        return 1

    for line in process.stdout:
        text = line.strip()
        if text:
            print(f"{STREAM_PREFIX}{text}")
    process.wait()
    return process.returncode

def print_help():
    """
    Display the help message with available commands and usage examples.
    """
    help_text = f"""
{Fore.CYAN}(XAPC){Style.RESET_ALL}{Fore.LIGHTBLUE_EX}XAPK Converter{Style.RESET_ALL} v1.8.1
BY {Fore.CYAN}Zetsu4i{Style.RESET_ALL},

{Fore.YELLOW}HOW TO USE:{Style.RESET_ALL}
{Fore.YELLOW}Commands:{Style.RESET_ALL}
  - <input_xapk_file>: Path to the input XAPK file (or APKS/APK for other actions).
  - <output_apks_file> (optional): Path for the output APKS file (should end with .apks).
  - -mit: Run apk-mitm after converting the XAPK to APKS.
    - -adb: Install APK/APKS to device using adb.
  - -obj: Run objection patchapk (supports .apk and .apks).
  - --adb-serial <serial>: Target adb device serial (skip selector).
  - --obj-arch <arch>: Override objection architecture (e.g., arm64-v8a).
    - --obj-out <path>: Output path for objection patched APK.
  - --dry-run: Show actions without executing external commands.
    - -tui: Launch interactive TUI (questionary required).

{Fore.YELLOW}Usage examples:{Style.RESET_ALL}
  {Fore.LIGHTMAGENTA_EX}$ python {os.path.basename(__file__)} -mit <input_xapk_file> [<output_apks_file>][OPTIONAL]{Style.RESET_ALL}
  {Fore.GREEN}$ python {os.path.basename(__file__)} app.xapk app.apks{Style.RESET_ALL}
    (Converts XAPK to APKS without running apk-mitm)

  {Fore.GREEN}$ python {os.path.basename(__file__)} -mit app.xapk{Style.RESET_ALL}
    (Converts XAPK to APKS and then runs apk-mitm)

    {Fore.GREEN}$ python {os.path.basename(__file__)} -adb app.apks{Style.RESET_ALL}
        (Installs APKS using adb install-multiple)

    {Fore.GREEN}$ python {os.path.basename(__file__)} -adb app.apk{Style.RESET_ALL}
        (Installs APK using adb install)

  {Fore.GREEN}$ python {os.path.basename(__file__)} -obj app.apks{Style.RESET_ALL}
    (Runs objection patchapk on base.apk extracted from APKS)

  {Fore.GREEN}$ python {os.path.basename(__file__)} -obj app.apk{Style.RESET_ALL}
    (Runs objection patchapk on a single APK)

  {Fore.GREEN}$ python {os.path.basename(__file__)} -tui{Style.RESET_ALL}
    (Launch interactive TUI)

  {Fore.GREEN}$ python {os.path.basename(__file__)} <input_apks_file>{Style.RESET_ALL}
    (Runs apk-mitm on an existing APKS file)

{Fore.YELLOW}Notes:{Style.RESET_ALL}
  - If you don't specify an output file name, the default is <input_xapk_file>.apks.
  - If you provide an output file name, it should end with .apks.
    - For TUI, install questionary: pip install questionary

{Fore.YELLOW}License:{Style.RESET_ALL}
This script is licensed under the MIT License, .

{Fore.YELLOW}Disclaimer:{Style.RESET_ALL}
{Fore.RED}This script is provided as-is, without any warranty. Use at your own risk.
The author is not responsible for any misuse or damage caused by this script.
Always ensure you have the necessary permissions before running any script.
{Style.RESET_ALL}

IF you need help create issue, visit: {Fore.LIGHTGREEN_EX}https://Github:github/Zitsu4i{Style.RESET_ALL}
"""
    print(help_text)

def check_apk_mitm():
    """
    Check if apk-mitm is installed and available in the system PATH.
    """
    return shutil.which("apk-mitm") is not None

def check_objection():
    """
    Check if objection is installed and available in the system PATH.
    """
    return shutil.which("objection") is not None

def check_adb():
    """
    Check if adb is installed and available in the system PATH.
    """
    return shutil.which("adb") is not None

def adb_command(serial, *args):
    cmd = ["adb"]
    if serial:
        cmd.extend(["-s", serial])
    cmd.extend(args)
    return cmd

def get_connected_devices():
    if not check_adb():
        return []
    result = subprocess.run(["adb", "devices", "-l"], capture_output=True, text=True)
    devices = []
    for line in result.stdout.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        serial = parts[0]
        status = parts[1] if len(parts) > 1 else "unknown"
        description = " ".join(parts[2:]) if len(parts) > 2 else ""
        devices.append({"serial": serial, "status": status, "description": description})
    return devices

def select_device(preferred_serial=None):
    if preferred_serial:
        return preferred_serial
    devices = [d for d in get_connected_devices() if d["status"] == "device"]
    if not devices:
        ui_print("err", "No authorized adb devices found. Check USB debugging/authorization.")
        return None
    if len(devices) == 1:
        return devices[0]["serial"]
    if HAS_TUI:
        choices = [questionary.Choice(f"{d['serial']} {d['description']}".strip(), value=d["serial"]) for d in devices]
        return questionary.select("Select a device:", choices=choices).ask()
    print("Multiple devices detected:")
    for idx, d in enumerate(devices, start=1):
        desc = f" {d['description']}" if d['description'] else ""
        print(f"  {idx}. {d['serial']}{desc}")
    choice = input("Select device number: ").strip()
    if not choice.isdigit():
        return None
    idx = int(choice) - 1
    return devices[idx]["serial"] if 0 <= idx < len(devices) else None

def get_device_abi(serial):
    try:
        result = subprocess.run(adb_command(serial, "shell", "getprop", "ro.product.cpu.abilist"), capture_output=True, text=True, timeout=10)
        abilist = result.stdout.strip()
        abi = abilist.split(",")[0].strip() if abilist else ""
        if not abi:
            result = subprocess.run(adb_command(serial, "shell", "getprop", "ro.product.cpu.abi"), capture_output=True, text=True, timeout=10)
            abi = result.stdout.strip()
        return abi
    except Exception as e:
        ui_print("err", f"Failed to detect device ABI: {e}")
        return ""

def normalize_abi(value):
    return value.replace("-", "_").lower()

def pick_apk_splits(apk_dir, abi):
    abi_norm = normalize_abi(abi) if abi else ""
    apk_files = [f for f in os.listdir(apk_dir) if f.endswith(".apk")]
    selected = []

    if "base.apk" in apk_files:
        selected.append(os.path.join(apk_dir, "base.apk"))
    else:
        for f in apk_files:
            if not f.startswith("split_config."):
                selected.append(os.path.join(apk_dir, f))
                break

    for f in apk_files:
        if not f.startswith("split_config.") or not f.endswith(".apk"):
            continue
        suffix = f[len("split_config."):-4]
        suffix_norm = normalize_abi(suffix)
        if suffix_norm in KNOWN_ABIS:
            if suffix_norm == abi_norm or suffix_norm == "universal":
                selected.append(os.path.join(apk_dir, f))
        else:
            selected.append(os.path.join(apk_dir, f))

    return selected

def extract_apks_to_temp(apks_path):
    temp_dir = tempfile.mkdtemp(prefix="apks_extract_")
    with zipfile.ZipFile(apks_path, 'r') as zip_ref:
        zip_ref.extractall(temp_dir)
    base_apk = os.path.join(temp_dir, "base.apk")
    if not os.path.exists(base_apk):
        candidates = [f for f in os.listdir(temp_dir) if f.endswith(".apk") and not f.startswith("split_config.")]
        if not candidates:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise FileNotFoundError("base.apk not found in the APKS bundle")
        base_apk = os.path.join(temp_dir, candidates[0])
    return temp_dir, base_apk

def find_objection_output(search_dirs):
    candidates = []
    for base_dir in search_dirs:
        if not base_dir or not os.path.isdir(base_dir):
            continue
        for root, _, files in os.walk(base_dir):
            for name in files:
                if name.endswith(".objection.apk") or ("objection" in name and name.endswith(".apk")):
                    candidates.append(os.path.join(root, name))
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)

def resign_apk_files(apk_files, dry_run=False):
    if not apk_files:
        return True
    if dry_run:
        ui_print("info", f"Dry-run: would re-sign {len(apk_files)} APK(s)")
        return True
    if not check_apksigner():
        ui_print("err", "apksigner is required to re-sign split APKs. Install Android build-tools and retry.")
        return False

    keystore_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug.keystore")
    if not os.path.exists(keystore_path):
        ui_print("err", f"debug.keystore not found at: {keystore_path}")
        return False
    ui_print("warn", "Using bundled debug.keystore for re-signing (development/testing use).")

    for apk_file in apk_files:
        cmd = [
            "apksigner", "sign",
            "--ks", keystore_path,
            "--ks-key-alias", "androiddebugkey",
            "--ks-pass", "pass:android",
            "--key-pass", "pass:android",
            "--v1-signing-enabled", "true",
            "--v2-signing-enabled", "true",
            apk_file
        ]
        rc = stream_command(cmd, label="apksigner")
        if rc != 0:
            ui_print("err", f"Failed to sign APK: {apk_file}")
            return False
    return True

def install_apks_with_adb(package_path, serial=None, dry_run=False):
    """
    Install an APK or APKS bundle using adb.
    For .apks, detects ABI and uses install-multiple. For .apk, uses adb install.
    """
    if dry_run:
        ui_print("info", f"Dry-run: would install from {package_path}")
    if not check_adb():
        ui_print("err", "adb is not installed or not in the system PATH.")
        return
    serial = select_device(serial)
    if not serial:
        return

    lower_path = package_path.lower()
    if lower_path.endswith(".apk"):
        cmd = adb_command(serial, "install", "-r", package_path)
        ui_print("info", f"Running: {' '.join(cmd)}")
        if dry_run:
            ui_print("info", "Dry-run: skipping adb install")
            return
        proc = subprocess.run(cmd, text=True)
        if proc.returncode == 0:
            ui_print("ok", "Install successful!")
        else:
            ui_print("err", "Install failed. See adb output above.")
        return

    if not lower_path.endswith(".apks"):
        ui_print("err", "ADB install supports only .apk or .apks files.")
        return

    abi = get_device_abi(serial)
    if abi:
        ui_print("info", f"Detected device ABI: {abi}")
    else:
        ui_print("warn", "Could not detect device ABI; continuing without --abi.")

    temp_dir = tempfile.mkdtemp(prefix="apks_extract_")
    try:
        with zipfile.ZipFile(package_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        ui_print("step", f"Extracted APKS to: {temp_dir}")

        apk_files = pick_apk_splits(temp_dir, abi)

        if not apk_files:
            ui_print("err", "No APKs found to install.")
            return
        ui_print("info", f"APKs to install: {apk_files}")

        cmd = adb_command(serial, "install-multiple", "-r")
        if abi:
            cmd.extend(["--abi", abi])
        cmd.extend(apk_files)
        ui_print("info", f"Running: {' '.join(cmd)}")
        if dry_run:
            ui_print("info", "Dry-run: skipping adb install-multiple")
            return
        proc = subprocess.run(cmd, text=True)
        if proc.returncode == 0:
            ui_print("ok", "Install successful!")
        else:
            ui_print("err", "Install failed. See adb output above.")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def run_objection_patchapk(source_path, serial=None, arch=None, out_path=None, dry_run=False):
    source_kind = detect_input_kind(source_path)
    if not out_path:
        out_path = default_objection_output(source_path)
    if dry_run:
        ui_print("info", f"Dry-run: would run objection patchapk on {source_path}")
        ui_print("info", f"Dry-run: would write output to {out_path}")
        return out_path
    if not check_objection():
        ui_print("err", "objection is not installed or not in the system PATH.")
        return None

    temp_dirs = []
    actual_source = source_path
    bundle_dir = None
    bundle_kind = source_kind
    output_file = None

    try:
        def stage_extract():
            nonlocal actual_source, bundle_dir, bundle_kind
            if source_kind == "xapk":
                temp_dir = tempfile.mkdtemp(prefix="xapk_to_apks_")
                temp_apks = os.path.join(temp_dir, "converted.apks")
                temp_dirs.append(temp_dir)
                convert_xapk_to_apks(source_path, temp_apks, dry_run=False)
                actual_source = temp_apks
                bundle_kind = "apks"
            if detect_input_kind(actual_source) == "apks":
                temp_dir, base_apk = extract_apks_to_temp(actual_source)
                temp_dirs.append(temp_dir)
                bundle_dir = temp_dir
                actual_source = base_apk
                ui_print("info", f"Using base APK: {actual_source}")

        if not arch:
            if check_adb():
                devices = [d for d in get_connected_devices() if d["status"] == "device"]
                if devices:
                    serial = select_device(serial)
                    if serial:
                        arch = get_device_abi(serial)
                        if arch:
                            ui_print("info", f"Detected device ABI: {arch}")
                else:
                    ui_print("warn", "No adb devices found; running objection without --architecture.")
            else:
                ui_print("warn", "adb not found; running objection without --architecture.")

        def stage_patch():
            nonlocal output_file
            cmd = ["objection", "patchapk", "-s", actual_source]
            if arch:
                cmd.extend(["-a", arch])
            ui_print("info", f"Running command: {' '.join(cmd)}")
            return_code = stream_command(cmd, label="objection")
            ui_print("info", f"objection finished with return code: {return_code}")
            search_dirs = [os.getcwd(), os.path.dirname(actual_source)] + temp_dirs
            output_file = find_objection_output(search_dirs)
            if not output_file:
                raise FileNotFoundError(
                    f"Could not locate patched APK output from objection. Searched in: {', '.join(search_dirs)}"
                )

        def stage_sign():
            if not bundle_dir or bundle_kind != "apks":
                return
            shutil.copy2(output_file, actual_source)
            apk_files = []
            for root, _, files in os.walk(bundle_dir):
                for name in files:
                    if name.endswith(".apk"):
                        apk_files.append(os.path.join(root, name))
            if not resign_apk_files(apk_files, dry_run=dry_run):
                raise RuntimeError("Failed to re-sign split APKs.")

        def stage_compress():
            if not bundle_dir or bundle_kind != "apks":
                return
            out_dir = os.path.dirname(out_path)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            zip_directory(bundle_dir, out_path)
            ui_print("ok", f"Patched APKS saved to: {out_path}")

        stages = []
        if source_kind in {"xapk", "apks"}:
            stages.append(("Extracting APKs", stage_extract))
            stages.append(("Patching base APK", stage_patch))
            stages.append(("Signing APKs", stage_sign))
            stages.append(("Compressing APKs", stage_compress))
        else:
            stages.append(("Patching APK", stage_patch))

        run_stages(stages)

        if bundle_dir and bundle_kind == "apks":
            return out_path

        if output_file != out_path:
            out_dir = os.path.dirname(out_path)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            shutil.copy2(output_file, out_path)
        ui_print("ok", f"Patched APK saved to: {out_path}")
        return out_path
    except Exception as e:
        ui_print("err", f"Failed to run objection: {e}")
        return None
    finally:
        for temp_dir in temp_dirs:
            shutil.rmtree(temp_dir, ignore_errors=True)

def run_tui():
    if not HAS_TUI:
        ui_print("err", "questionary is not installed. Install with: pip install questionary")
        print_help()
        return

    input_file = select_input_file()
    if not input_file:
        return
    input_file = input_file.strip('"')
    input_kind = detect_input_kind(input_file)
    if input_kind == "unknown":
        ui_print("err", "Input file must be .xapk, .apks, or .apk")
        return

    options = [
        questionary.Choice("Convert XAPK to APKS", value="convert"),
        questionary.Choice("Run apk-mitm", value="mit"),
        questionary.Choice("Install APK/APKS (adb)", value="adb"),
        questionary.Choice("Run objection patchapk", value="obj"),
        questionary.Choice("Dry-run (no external commands)", value="dry"),
    ]

    selected = questionary.checkbox("Select actions:", choices=options).ask() or []
    selected = set(selected)
    dry_run = "dry" in selected
    selected.discard("dry")

    if not selected:
        ui_print("warn", "No actions selected.")
        return

    serial = None
    if "adb" in selected:
        serial = select_device(None)

    obj_arch = ""
    if "obj" in selected:
        obj_arch = questionary.text("Objection arch override (blank for auto):").ask().strip()
    obj_out = ""
    if "obj" in selected:
        obj_out = questionary.text("Objection output path (blank for default):").ask().strip()

    input_file = sanitize_filename(input_file, dry_run=dry_run)
    artifacts = []
    state = {
        "input_path": input_file,
        "input_kind": input_kind,
        "converted_apks": None,
        "objection_output": None,
    }
    stages = []

    needs_convert = input_kind == "xapk" and ("convert" in selected or (selected & {"mit", "adb", "obj"}))
    if "convert" in selected and input_kind != "xapk":
        ui_print("warn", "Convert is only valid for .xapk inputs.")
    if needs_convert:
        output_apks = questionary.text("Output APKS (leave blank for default):").ask().strip()
        if not output_apks:
            output_apks = f"{os.path.splitext(input_file)[0]}.apks"
        def convert_stage():
            convert_xapk_to_apks(state["input_path"], output_apks, dry_run=dry_run)
            state["converted_apks"] = output_apks
            artifacts.append(("converted_apks", output_apks))
        stages.append(("Convert XAPK to APKS", convert_stage))

    if "mit" in selected:
        def mit_stage():
            mit_source = state["converted_apks"] or state["input_path"]
            run_apk_mitm(mit_source, dry_run=dry_run)
            artifacts.append(("apk_mitm_source", mit_source))
        stages.append(("Run apk-mitm", mit_stage))
    if "adb" in selected:
        def adb_stage():
            install_source = state["objection_output"] or state["converted_apks"] or state["input_path"]
            input_is_split = state["input_kind"] in {"xapk", "apks"}
            if input_is_split and detect_input_kind(install_source) == "apk":
                ui_print("err", "Split package detected but install source is a single APK. Run objection to generate a .apks bundle before installing.")
                return
            install_apks_with_adb(install_source, serial=serial, dry_run=dry_run)
            artifacts.append(("adb_install_source", install_source))
        stages.append(("Install APK/APKS", adb_stage))
    if "obj" in selected:
        def obj_stage():
            obj_source = state["converted_apks"] or state["input_path"]
            if not obj_out:
                target_output = default_objection_output(obj_source)
            else:
                target_output = obj_out
            result = run_objection_patchapk(obj_source, serial=serial, arch=obj_arch or None, out_path=target_output, dry_run=dry_run)
            if result:
                state["objection_output"] = result
                artifacts.append(("objection_output", result))
        stages.append(("Run objection patchapk", obj_stage))

    print_artifact_summary(state["input_path"], [])
    run_stages(stages)
    print_artifact_summary(state["input_path"], artifacts)

def select_input_file():
    if not HAS_TUI:
        return input("Input file (.xapk, .apks, .apk): ").strip()
    cwd = os.getcwd()
    candidates = [
        f for f in os.listdir(cwd)
        if f.lower().endswith((".xapk", ".apks", ".apk")) and os.path.isfile(os.path.join(cwd, f))
    ]
    choices = [questionary.Choice(f, value=os.path.join(cwd, f)) for f in sorted(candidates)]
    choices.append(questionary.Choice("Enter path...", value="__manual__"))
    selection = questionary.select("Select input file:", choices=choices).ask()
    if selection == "__manual__":
        return questionary.text("Input file (.xapk, .apks, .apk):").ask()
    return selection

def main():
    parser = argparse.ArgumentParser(description="Convert XAPK to APKS and optionally run apk-mitm/objection/adb", add_help=False)
    parser.add_argument("-h", "--help", action="store_true", help="Show help message and exit")
    parser.add_argument("-mit", action="store_true", help="Run apk-mitm after conversion")
    parser.add_argument("-adb", action="store_true", help="Install APK/APKS to device using adb")
    parser.add_argument("-obj", action="store_true", help="Run objection patchapk")
    parser.add_argument("-tui", action="store_true", help="Launch interactive TUI")
    parser.add_argument("--adb-serial", help="Target adb device serial")
    parser.add_argument("--obj-arch", help="Override objection architecture (e.g., arm64-v8a)")
    parser.add_argument("--obj-out", help="Output path for objection patched APK")
    parser.add_argument("--dry-run", action="store_true", help="Show actions without executing external commands")
    parser.add_argument("input_file", nargs="?", help="Path to the input XAPK/APKS/APK file")
    parser.add_argument("output_apks", nargs="?", help="Path to the output APKS file (if converting)")
    args = parser.parse_args()

    if args.help:
        print_help()
        return
    if args.tui or not args.input_file:
        run_tui()
        return

    input_file = sanitize_filename(args.input_file, dry_run=args.dry_run)

    input_kind = detect_input_kind(input_file)
    artifacts = []

    if input_kind == "xapk":
        output_apks = args.output_apks or f"{os.path.splitext(input_file)[0]}.apks"
        try:
            print_artifact_summary(input_file, [])
            convert_xapk_to_apks(input_file, output_apks, dry_run=args.dry_run)
            artifacts.append(("converted_apks", output_apks))
            ui_print("ok", f"Conversion successful. Output file: {output_apks}")
            if args.mit:
                run_apk_mitm(output_apks, dry_run=args.dry_run)
                artifacts.append(("apk_mitm_source", output_apks))
            objection_output = None
            if args.adb and not args.obj:
                install_apks_with_adb(output_apks, serial=args.adb_serial, dry_run=args.dry_run)
                artifacts.append(("adb_install_source", output_apks))
            if args.obj:
                desired_output = args.obj_out or default_objection_output(output_apks)
                objection_output = run_objection_patchapk(output_apks, serial=args.adb_serial, arch=args.obj_arch, out_path=desired_output, dry_run=args.dry_run)
                if objection_output:
                    artifacts.append(("objection_output", objection_output))
            if args.adb and objection_output and detect_input_kind(objection_output) == "apks":
                install_apks_with_adb(objection_output, serial=args.adb_serial, dry_run=args.dry_run)
                artifacts.append(("adb_install_source_after_obj", objection_output))
            elif args.adb and args.obj:
                ui_print("err", SPLIT_INSTALL_ERROR)
            print_artifact_summary(input_file, artifacts)
        except Exception as e:
            ui_print("err", f"Error during conversion: {e}")
    elif input_kind == "apks":
        try:
            print_artifact_summary(input_file, [])
            if args.mit:
                run_apk_mitm(input_file, dry_run=args.dry_run)
                artifacts.append(("apk_mitm_source", input_file))
            objection_output = None
            if args.adb and not args.obj:
                install_apks_with_adb(input_file, serial=args.adb_serial, dry_run=args.dry_run)
                artifacts.append(("adb_install_source", input_file))
            if args.obj:
                desired_output = args.obj_out or default_objection_output(input_file)
                objection_output = run_objection_patchapk(input_file, serial=args.adb_serial, arch=args.obj_arch, out_path=desired_output, dry_run=args.dry_run)
                if objection_output:
                    artifacts.append(("objection_output", objection_output))
            if args.adb and objection_output and detect_input_kind(objection_output) == "apks":
                install_apks_with_adb(objection_output, serial=args.adb_serial, dry_run=args.dry_run)
                artifacts.append(("adb_install_source_after_obj", objection_output))
            elif args.adb and args.obj:
                ui_print("err", SPLIT_INSTALL_ERROR)
            if not args.mit and not args.adb and not args.obj:
                ui_print("warn", "No action specified for .apks file. Use -mit, -adb, or -obj.")
            print_artifact_summary(input_file, artifacts)
        except Exception as e:
            ui_print("err", f"Error: {e}")
    elif input_kind == "apk":
        try:
            print_artifact_summary(input_file, [])
            if args.mit:
                run_apk_mitm(input_file, dry_run=args.dry_run)
                artifacts.append(("apk_mitm_source", input_file))
            objection_output = None
            if args.obj:
                desired_output = args.obj_out or default_objection_output(input_file)
                objection_output = run_objection_patchapk(input_file, serial=args.adb_serial, arch=args.obj_arch, out_path=desired_output, dry_run=args.dry_run)
                if objection_output:
                    artifacts.append(("objection_output", objection_output))
            if args.adb:
                install_target = objection_output or input_file
                install_apks_with_adb(install_target, serial=args.adb_serial, dry_run=args.dry_run)
                artifacts.append(("adb_install_source", install_target))
            if not args.mit and not args.obj and not args.adb:
                ui_print("warn", "No action specified for .apk file. Use -mit or -obj.")
            print_artifact_summary(input_file, artifacts)
        except Exception as e:
            ui_print("err", f"Error: {e}")
    else:
        ui_print("err", "Input file must be .xapk, .apks, or .apk")

if __name__ == "__main__":
    main()
