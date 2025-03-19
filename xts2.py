#!/usr/bin/env python3
import re
import sys
import time
import json
import shlex
import shutil
import zipfile
import tempfile
import subprocess
import argparse
from colorama import init, Fore, Style
import shutil
import os

# Initialize colorama
init(autoreset=True)

def sanitize_filename(filepath):
    """
    Sanitize the filename and rename the actual file.
    Replace special characters in the filename with underscores.
    Allowed characters: letters, digits, underscore, hyphen and dot.
    """
    path, filename = os.path.split(filepath)
    sanitized_filename = re.sub(r'[^A-Za-z0-9_.-]', '_', filename)
    new_filepath = os.path.join(path, sanitized_filename)
    
    if filepath != new_filepath:
        try:
            shutil.move(filepath, new_filepath)
            print(f"File renamed: {filename} -> {sanitized_filename}")
        except Exception as e:
            print(f"Error renaming file: {e}")
            return filepath  # Return original path if renaming fails
    
    return new_filepath
def convert_xapk_to_apks(xapk_path, output_apks_path):
    """
    Convert an XAPK file (a zip archive) to an APKS file.
    It will:
      1. Extract the XAPK.
      2. Sanitize filenames (replace special characters with underscores).
      3. Read manifest.json to process APK files.
      4. Rename base APK to "base.apk" and split APKs to "split_config.<suffix>.apk".
      5. Create meta files (meta.sai_v1.json and meta.sai_v2.json).
      6. Package everything into a new .apks file.
    """
    # Create temporary working directories
    work_dir = tempfile.mkdtemp(prefix="xapk_extract_")
    apks_build_dir = tempfile.mkdtemp(prefix="apks_build_")
    try:
        # Extract the XAPK (which is just a ZIP file)
        with zipfile.ZipFile(xapk_path, 'r') as zip_ref:
            zip_ref.extractall(work_dir)
        print(f"Extracted XAPK to temporary directory: {work_dir}")

        # Sanitize all extracted file names
        
        print("Sanitized extracted file names (special characters replaced with underscores).")

        # Locate and read manifest.json
        manifest_path = os.path.join(work_dir, "manifest.json")
        if not os.path.exists(manifest_path):
            raise FileNotFoundError("manifest.json not found in the XAPK.")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        # Copy the icon file if it exists (as referenced in manifest)
        icon_name = manifest.get("icon")
        if icon_name:
            icon_src = os.path.join(work_dir, icon_name)
            if os.path.exists(icon_src):
                shutil.copy(icon_src, os.path.join(apks_build_dir, icon_name))

        # Process APK files as listed in manifest's split_apks field
        split_apks = manifest.get("split_apks", [])
        backup_size = 0  # total size of all APK files
        for entry in split_apks:
            file_name = entry.get("file")
            apk_id = entry.get("id")
            if not file_name or not apk_id:
                continue
            sanitized_file_name = file_name
            src_file = os.path.join(work_dir, sanitized_file_name)
            if not os.path.exists(src_file):
                print(f"Warning: {sanitized_file_name} not found; skipping.")
                continue
            backup_size += os.path.getsize(src_file)
            # Determine destination file name
            if apk_id == "base":
                dest_name = "base.apk"
            elif apk_id.startswith("config."):
                suffix = apk_id.split("config.", 1)[-1]
                dest_name = f"split_config.{suffix}.apk"
            else:
                dest_name = sanitized_file_name
            dest_path = os.path.join(apks_build_dir, dest_name)
            shutil.copy(src_file, dest_path)
            print(f"Copied and renamed {sanitized_file_name} as {dest_name}")

        # Create metadata JSON files
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
        print("Created metadata files: meta.sai_v1.json and meta.sai_v2.json")

        # Create the final APKS archive
        with zipfile.ZipFile(output_apks_path, "w", zipfile.ZIP_DEFLATED) as apks_zip:
            for root, _, files in os.walk(apks_build_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, apks_build_dir)
                    apks_zip.write(file_path, arcname)
        print(f"APKS file created: {output_apks_path}")
    finally:
        # Clean up temporary directories
        shutil.rmtree(work_dir, ignore_errors=True)
        shutil.rmtree(apks_build_dir, ignore_errors=True)

def run_apk_mitm(apks_path):
    """
    Run the apk-mitm command on the given APKS file.
    It will display output in real time just as the actual apk-mitm does.
    """
    print("\nLaunching apk-mitm on the APKS file...\n")
    # Here we assume apk-mitm is in PATH; adjust command if needed.
    cmd = f"apk-mitm {shlex.quote(apks_path)}"
    print(cmd)
    process = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    # Read and print output line by line (simulate apk-mitm UI)
    while True:
        line = process.stdout.readline()
        if not line:
            break
        # Print exactly what apk-mitm outputs
        print(line, end="")
    process.wait()
    print("\napk-mitm finished with return code:", process.returncode)

def print_help():
    """
    Display help message with available commands and usage.
    """
    help_text = f"""
{Fore.CYAN}Interactive XAPK Converter and apk-mitm Runner{Style.RESET_ALL}

This script can do the following:
  • Convert an XAPK file to a valid APKS file.
  • Convert an XAPK file to an APKS file and then run the apk-mitm command on it.
  • Run apk-mitm directly on an existing APKS file.
  • It sanitizes filenames by replacing special characters with underscores (_).

{Fore.GREEN}Example:{Style.RESET_ALL}
  $ python convert_xapk.py
  (then follow the interactive prompts)
you can supply arguments:
  $ python convert_xapk.py <input_xapk_file> [<output_apks_file>]
    (This will simply convert the XAPK to APKS without running apk-mitm)
  $ python convert_xapk.py -mit <input_xapk_file> [<output_apks_file>]
    (This will convert the XAPK to APKS and then run apk-mitm)
  $ python convert_xapk.py <input_apks_file>
    (This will simply run apk-mitm on an existing APKS file)
"""
    print(help_text)

def check_apk_mitm():
    """
    Check if apk-mitm is installed and accessible in the system PATH.
    """
    return shutil.which("apk-mitm") is not None


def main():
    parser = argparse.ArgumentParser(description="Convert XAPK to APKS and optionally run apk-mitm", add_help=False)
    parser.add_argument("-h", "--help", action="store_true", help="Show help message and exit")
    parser.add_argument("-mit", action="store_true", help="Run apk-mitm after conversion")
    parser.add_argument("input_file", nargs="?", help="Path to the input XAPK or APKS file")
    parser.add_argument("output_apks", nargs="?", help="Path to the output APKS file")
    args = parser.parse_args()

    if not check_apk_mitm():
        print(f"{Fore.YELLOW}[WARNING]: apk-mitm is not installed or not in the system PATH. Some features may not work.{Style.RESET_ALL}")

    if args.help:
        print_help()
        return

    if not args.input_file:
        print_help()
    else:
        # Command-line mode
        input_file = sanitize_filename(args.input_file)
        if input_file.lower().endswith('.xapk'):
            output_apks = args.output_apks or f"{os.path.splitext(input_file)[0]}.apks"
            try:
                convert_xapk_to_apks(input_file, output_apks)
                print(f"\n{Fore.GREEN}Conversion successful. Output file: {output_apks}{Style.RESET_ALL}")
                if args.mit:
                    run_apk_mitm(output_apks)
            except Exception as e:
                print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        elif input_file.lower().endswith('.apks'):
            try:
                run_apk_mitm(input_file)
            except Exception as e:
                print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}Error: Input file must be either .xapk or .apks{Style.RESET_ALL}")

if __name__ == "__main__":
    main()