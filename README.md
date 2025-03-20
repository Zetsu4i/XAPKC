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

out of curosity i wanted to explore the dark side of the android world, I spent a considerable amount of time searching for a tool that could easily convert XAPK files to APKS format and integrate with APK-MITM. Unable to find a suitable solution, I decided to create this tool to make the process easier for myself and future adventurers in the Android security testing world.


## Requirements

- Python 3.x
- colorama
- APK-MITM (optional)

## Usage 

```
xapkc.py [-mit] [input_file] [output_apks]
```
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

