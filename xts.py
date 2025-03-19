import os
import zipfile
import shutil
import json
import time
import tempfile
import argparse

def convert_xapk_to_apks(xapk_path, output_apks_path):
    # Create a temporary working directory
    work_dir = tempfile.mkdtemp(prefix="xapk_extract_")
    try:
        # Extract the XAPK (which is a ZIP archive)
        with zipfile.ZipFile(xapk_path, 'r') as zip_ref:
            zip_ref.extractall(work_dir)
        print(f"Extracted XAPK to {work_dir}")

        # Locate and read manifest.json
        manifest_path = os.path.join(work_dir, "manifest.json")
        if not os.path.exists(manifest_path):
            raise FileNotFoundError("manifest.json not found in the XAPK.")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        
        # Prepare a new directory for the APKS file structure
        apks_dir = tempfile.mkdtemp(prefix="apks_build_")
        
        # Copy the icon file if it exists (as referenced in manifest)
        icon_name = manifest.get("icon")
        if icon_name:
            icon_src = os.path.join(work_dir, icon_name)
            if os.path.exists(icon_src):
                shutil.copy(icon_src, os.path.join(apks_dir, icon_name))
        
        # Process split_apks from manifest
        # manifest["split_apks"] is expected to be a list of dicts like:
        # { "file": "net.xblacky.wallx.apk", "id": "base" } etc.
        split_apks = manifest.get("split_apks", [])
        backup_size = 0  # We'll compute backup size from the files we include
        for entry in split_apks:
            file_name = entry.get("file")
            apk_id = entry.get("id")
            if not file_name or not apk_id:
                continue
            src_file = os.path.join(work_dir, file_name)
            if not os.path.exists(src_file):
                print(f"Warning: {file_name} not found in the XAPK; skipping.")
                continue
            # Compute file size for backup_components later
            backup_size += os.path.getsize(src_file)
            # Determine destination file name
            if apk_id == "base":
                dest_name = "base.apk"
            elif apk_id.startswith("config."):
                # Remove the "config." prefix for the naming convention
                suffix = apk_id.split("config.", 1)[-1]
                dest_name = f"split_config.{suffix}.apk"
            else:
                # Fallback: use original name
                dest_name = file_name
            dest_path = os.path.join(apks_dir, dest_name)
            shutil.copy(src_file, dest_path)
            print(f"Copied {file_name} as {dest_name}")

        # Create metadata JSON files using the manifest data
        # Use current time in milliseconds as export_timestamp
        export_timestamp = int(time.time() * 1000)
        label = manifest.get("name", "")
        package_name = manifest.get("package_name", "")
        version_code = int(manifest.get("version_code", 0))
        version_name = manifest.get("version_name", "")
        min_sdk = int(manifest.get("min_sdk_version", 0))
        target_sdk = int(manifest.get("target_sdk_version", 0))
        
        # meta.sai_v1.json content
        meta_v1 = {
            "export_timestamp": export_timestamp,
            "label": label,
            "package": package_name,
            "version_code": version_code,
            "version_name": version_name
        }
        
        # meta.sai_v2.json content
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
        
        # Write meta files to the output directory
        meta_v1_path = os.path.join(apks_dir, "meta.sai_v1.json")
        meta_v2_path = os.path.join(apks_dir, "meta.sai_v2.json")
        with open(meta_v1_path, "w", encoding="utf-8") as f:
            json.dump(meta_v1, f, separators=(',', ':'))
        with open(meta_v2_path, "w", encoding="utf-8") as f:
            json.dump(meta_v2, f, separators=(',', ':'))
        
        print("Created metadata files.")
        
        # Create the final APKS archive
        with zipfile.ZipFile(output_apks_path, "w", zipfile.ZIP_DEFLATED) as apks_zip:
            # Add all files from apks_dir into the zip archive (at the root)
            for root, _, files in os.walk(apks_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, apks_dir)
                    apks_zip.write(file_path, arcname)
        print(f"APKS file created: {output_apks_path}")
        
    finally:
        # Clean up temporary directories
        shutil.rmtree(work_dir, ignore_errors=True)
        shutil.rmtree(apks_dir, ignore_errors=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert XAPK to APKS format")
    parser.add_argument("xapk_file", help="Path to the input XAPK file")
    # parser.add_argument("output_apks", help="Path for the output APKS file (should end with .apks)")
    args = parser.parse_args()
    
    convert_xapk_to_apks(args.xapk_file, args.xapk_file+".apks")
