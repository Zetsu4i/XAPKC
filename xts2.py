#!/usr/bin/env python3
import os
import re
import shutil
import zipfile
import json
import time
import subprocess
import shlex
import argparse
import tempfile
from colorama import init, Fore, Style

# Initialize colorama for colored output
init(autoreset=True)

def sanitize_filename(filepath):
    """
    Sanitize the filename by replacing disallowed characters with underscores.
    Allowed characters: letters, digits, underscore, hyphen and dot.
    Renames the file if needed.
    """
    path, filename = os.path.split(filepath)
    sanitized_filename = re.sub(r'[^A-Za-z0-9_.-]', '_', filename)
    new_filepath = os.path.join(path, sanitized_filename)
    
    if filepath != new_filepath:
        try:
            shutil.move(filepath, new_filepath)
            print(f"File renamed: {filename} -> {sanitized_filename}")
        except Exception as e:
            print(f"{Fore.RED}Error renaming file: {e}{Style.RESET_ALL}")
            return filepath  # Return original path if renaming fails
    
    return new_filepath

def convert_xapk_to_apks(xapk_path, output_apks_path):
    """
    Convert an XAPK file to an APKS file:
      1. Extract the XAPK archive.
      2. Sanitize extracted filenames.
      3. Read manifest.json to process APK files.
      4. Rename base APK to "base.apk" and split APKs to "split_config.<suffix>.apk".
      5. Create metadata files (meta.sai_v1.json and meta.sai_v2.json).
      6. Package the processed files into a new .apks archive.
    """
    # Create temporary directories for extraction and building the APKS package
    work_dir = tempfile.mkdtemp(prefix="xapk_extract_")
    apks_build_dir = tempfile.mkdtemp(prefix="apks_build_")
    backup_size = 0

    try:
        # Extract the XAPK (ZIP file)
        with zipfile.ZipFile(xapk_path, 'r') as zip_ref:
            zip_ref.extractall(work_dir)
        print(f"Extracted XAPK to temporary directory: {work_dir}")

        # (Optional) You can implement a recursive walk to sanitize all filenames if needed.
        print("Sanitized extracted file names (if any renaming was necessary).")

        # Locate and read manifest.json
        manifest_path = os.path.join(work_dir, "manifest.json")
        if not os.path.exists(manifest_path):
            raise FileNotFoundError("manifest.json not found in the XAPK.")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        # Copy the icon file if it exists
        icon_name = manifest.get("icon")
        if icon_name:
            icon_src = os.path.join(work_dir, icon_name)
            if os.path.exists(icon_src):
                shutil.copy(icon_src, os.path.join(apks_build_dir, icon_name))

        # Process APK files listed in the manifest's split_apks field
        split_apks = manifest.get("split_apks", [])
        for entry in split_apks:
            file_name = entry.get("file")
            apk_id = entry.get("id")
            if not file_name or not apk_id:
                continue
            src_file = os.path.join(work_dir, file_name)
            if not os.path.exists(src_file):
                print(f"{Fore.YELLOW}Warning: {file_name} not found; skipping.{Style.RESET_ALL}")
                continue
            backup_size += os.path.getsize(src_file)

            # Determine destination file name based on apk_id
            if apk_id == "base":
                dest_name = "base.apk"
            elif apk_id.startswith("config."):
                suffix = apk_id.split("config.", 1)[-1]
                dest_name = f"split_config.{suffix}.apk"
            else:
                dest_name = file_name
            dest_path = os.path.join(apks_build_dir, dest_name)
            shutil.copy(src_file, dest_path)
            print(f"Copied and renamed {file_name} as {dest_name}")

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

        # Package the contents into the final APKS archive
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
    Execute the apk-mitm command on the given APKS file.
    Displays the output in real time.
    """
    if not check_apk_mitm():
        print(f"{Fore.RED}Error: apk-mitm is not installed or not in the system PATH.{Style.RESET_ALL}")
        return

    print("\nLaunching apk-mitm on the APKS file...\n")
    # shlex.quote 
    # APK_MITM_PATH = r"C:\Users\MYounes\AppData\Roaming\npm\apk-mitm"  
    # cmd = f'"{APK_MITM_PATH}" "{apks_path}"'
    cmd = ["apk-mitm", apks_path]  # to avoid quoting issues
    subprocess.run(cmd, shell=True)
    cmd = f"apk-mitm {shlex.quote(apks_path)}"
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    print(f"Running command: {cmd}")
    # try:
    #     process = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    # except Exception as e:
    #     print(f"{Fore.RED}Failed to start apk-mitm: {e}{Style.RESET_ALL}")
    #     return

    # Read and print output in real time
    while True:
        line = process.stdout.readline()
        if not line:
            break
        print(line, end="")
    process.wait()
    print(f"\napk-mitm finished with return code: {process.returncode}")

def print_help():
    """
    Display the help message with available commands and usage examples.
    """
    help_text = f"""
{Fore.CYAN}Interactive XAPK Converter and apk-mitm Runner{Style.RESET_ALL}

This script can:
  • Convert an XAPK file to a valid APKS file.
  • Convert an XAPK file to APKS and then run the apk-mitm command.
  • Run apk-mitm directly on an existing APKS file.
  • Sanitize filenames by replacing special characters with underscores (_).

Usage examples:
  {Fore.GREEN}$ python {os.path.basename(__file__)} <input_xapk_file> [<output_apks_file>]{Style.RESET_ALL}
    (Converts XAPK to APKS without running apk-mitm)
  {Fore.GREEN}$ python {os.path.basename(__file__)} -mit <input_xapk_file> [<output_apks_file>]{Style.RESET_ALL}
    (Converts XAPK to APKS and then runs apk-mitm)
  {Fore.GREEN}$ python {os.path.basename(__file__)} <input_apks_file>{Style.RESET_ALL}
    (Runs apk-mitm on an existing APKS file)
"""
    print(help_text)

def check_apk_mitm():
    """
    Check if apk-mitm is installed and available in the system PATH.
    """
    return shutil.which("apk-mitm") is not None

def main():
    parser = argparse.ArgumentParser(description="Convert XAPK to APKS and optionally run apk-mitm", add_help=False)
    parser.add_argument("-h", "--help", action="store_true", help="Show help message and exit")
    parser.add_argument("-mit", action="store_true", help="Run apk-mitm after conversion")
    parser.add_argument("input_file", nargs="?", help="Path to the input XAPK or APKS file")
    parser.add_argument("output_apks", nargs="?", help="Path to the output APKS file (if converting)")
    args = parser.parse_args()

    if args.help or not args.input_file:
        print_help()
        return

    input_file = sanitize_filename(args.input_file)
    
    # If the input file is an XAPK, convert it; if it's an APKS, run apk-mitm on it.
    if input_file.lower().endswith('.xapk'):
        output_apks = args.output_apks or f"{os.path.splitext(input_file)[0]}.apks"
        try:
            convert_xapk_to_apks(input_file, output_apks)
            print(f"\n{Fore.GREEN}Conversion successful. Output file: {output_apks}{Style.RESET_ALL}")
            if args.mit:
                run_apk_mitm(output_apks)
        except Exception as e:
            print(f"{Fore.RED}Error during conversion: {e}{Style.RESET_ALL}")
    elif input_file.lower().endswith('.apks'):
        try:
            run_apk_mitm(input_file)
        except Exception as e:
            print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}Error: Input file must be either .xapk or .apks{Style.RESET_ALL}")

if __name__ == "__main__":
    main()
