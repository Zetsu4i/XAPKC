# XAPK Converter and APK-MITM Runner 
##### (XAPC) in short for XAPK Converter.
A powerful Python tool to convert XAPK files to APKS format and optionally run APK-MITM.

## Description

This script is designed to simplify the process of converting XAPK files to APKS format and optionally running the APK-MITM tool. It was created to fill a gap in the available tools for Android app developers and security researchers.

Key features:
- Convert XAPK files to valid APKS format
- Optionally run APK-MITM on the converted APKS file
- Run APK-MITM directly on existing APKS files
- Sanitize filenames by replacing special characters with underscores

## Why I Created This Tool

i wanted to try few things this morning, and I found myself facing a challenge: the lack of a streamlined tool for converting XAPK files to APKS format. XAPK files are commonly used in Android app development, but they are not directly compatible with some Android tools. This tool addresses this gap by providing a simple and efficient solution for converting XAPK files to APKS format.

This project was born out of the need to simplify and expedite the process of working with XAPK files and conducting security analysis. By combining file conversion capabilities with APK-MITM integration, this tool aims to enhance productivity and facilitate more efficient Android application testing and research.

## Requirements

- Python 3.x
- colorama
- APK-MITM (optional)

## Usage 

### Commands

- `<input_xapk_file>`: Path to the input XAPK file.
- `<output_apks_file>` (optional): Path for the output APKS file (should end with .apks).
- `-mit`: Run apk-mitm after converting the XAPK to APKS.
### Example

1. Convert XAPK to APKS and run apk-mitm: 
```
python xapkc.py -mit <input_xapk_file> [<output_apks_file>]
```

2. Convert XAPK to APKS without running apk-mitm:
```
python xapkc.py <input_xapk_file> [<output_apks_file>]
```

3. Cleans the apk file name and run apk-mitm directly on an existing APKS file:
```
python xapkc.py -mit <input_apks_file> (optional: <output_apks_file>)
```
`<input_apks_file> must be (apk,apks,xapk)`

For detailed usage instructions and examples, please refer to the script's help message by running:

```
python xapkc.py
```

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Disclaimer

This script is provided as-is, without any warranty. Use at your own risk. The author is not responsible for any misuse or damage caused by this script. Always ensure you have the necessary permissions before running any script or modifying Android applications.

## Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](../../issues) if you want to contribute.

## Support

If you need help or have any questions, please create an issue in the repository.

Happy coding and happy Android app exploration!

