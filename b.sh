#!/bin/bash

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
INPUT_APKS=""
OUTPUT_DIR="output"
TEMPDIR=$(mktemp -d -t xapk-XXXXXXXXXX)

# Cleanup function
cleanup() {
    if [ -d "$TEMPDIR" ]; then
        rm -rf "$TEMPDIR"
        echo -e "${BLUE}[INFO]${NC} Cleaned up temporary directory"
    fi
}

# Error handler
error_exit() {
    echo -e "${RED}[ERROR]${NC} $1"
    cleanup
    exit 1
}

# Check dependencies
check_deps() {
    local deps=("unzip" "zip " "apk-mitm" "apksigner" "keytool" "adb")
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &> /dev/null; then
            error_exit "Required tool missing: $dep"
        fi
    done
}

# Interactive file selection
select_apks() {
    echo -e "${YELLOW}[?]${NC} Enter path to .apks file (or drag & drop it here):"
    read -r INPUT_APKS
    INPUT_APKS=$(echo "$INPUT_APKS" | tr -d '\n' | xargs) # Remove newlines and spaces
    
    if [ ! -f "$INPUT_APKS" ]; then
        error_exit "File not found: $INPUT_APKS"
    fi
}

# Main process
main() {
    clear
    echo -e "${GREEN}[XAPK Patcher]${NC}"
    echo -e "${BLUE}----------------------------------------${NC}"
    
    check_deps
    select_apks
    
    # Unzip APKS
    echo -e "\n${BLUE}[1/5]${NC} Unzipping ${YELLOW}$INPUT_APKS${NC}"
    unzip -q "$INPUT_APKS" -d "$TEMPDIR" || error_exit "Failed to unzip APKS file"
    
    # Create keystore
    echo -e "\n${BLUE}[2/5]${NC} Creating debug keystore"
    if [ -f "debug.keystore" ]; then
        echo -e "${YELLOW}[!]${NC} Existing debug.keyst found found, overwriting..."
    fi
    
    keytool -genkey -v -keystore debug.keystore -storepass android -alias androiddebugkey \
        -keypass android -keyalg RSA -keysize 2048 -validity 10000 \
        -dname "cn=Unknown, ou=Unknown, o=Unknown, c=Unknown" || error_exit "Keystore creation failed"
    
    # Process APKs
    echo -e "\n${BLUE}[3/5]${NC} Processing APKs"
    cd "$TEMPDIR" || error_exit "Failed to enter temporary directory"
    
    if [ ! -f "base.ap"" ]; then
        error_exit "base.apk not found in the package"
    fi
    
    echo -e "${BLUE}[+]${NC} Running apk-mitm on base.apk"
    apk-mitm base.apk || error_exit "apk-mitm failed"
    rm base.apk
    mv base-patched.apk base.apk
    
    # Sign APKs
    echo -e "\n${BLUE}[4/5]${NC} Signing APKs"
    for apk in *.apk; do
        echo -e "${BLUE}[+]${NC} Signing $apk"
        apksigner sign --ks ../debug.keystore --ks-pass pass:android "$apk" || error_exit "Failed to sign $apk"
    done
    
    # Package XAPK
    echo -e "\n${BLUE}[5/5]${NC} Packaging XAPK"
    cd .. || error_exit "Failed to return to root directory"
    mkdir -p "$OUTPUT_DIR"
    OUTPUT_FILE="$OUTPUT_DIR/$(basename "${INPUT_APKS%.*}-patched.xapk")"
    zip -qjr "$OUTPUT_FILE" "$TEMPDIR"/*
    
    echo -e "\n${GREEN}[SUCCESS]${NC} Patched XAPK created: ${YELLOW}$OUTPUT_FILE${NC}"
    
    # ADB install prompt
    echo -e "\n${YELLOW}[?]${NC} Would you like to install the patched XAPK on a connected device? (y/n)"
    read -r INSTALL_CHOICE
    if [[ "$INSTALL_CHOICE" =~ [yY] ]]; then
        echo -e "${BLUE}[+]${NC} Checking connected devices..."
        adb devices | grep -w device || error_exit "No devices connected"
        echo -e "${BLUE}[+]${NC} Installing..."
        adb install-multiple "$OUTPUT_FILE" || error_exit "Installation failed"
        echo -e "${GREEN}[SUCCESS]${NC} Installation complete!"
    fi
    
    cleanup
}

# Run main function
main
