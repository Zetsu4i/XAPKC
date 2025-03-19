@echo off
setlocal enabledelayedexpansion

:: Configure ANSI escape codes for colors
for /f %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
set "GREEN=%ESC%[92m"
set "YELLOW=%ESC%[93m"
set "RED=%ESC%[91m"
set "CYAN=%ESC%[96m"
set "RESET=%ESC%[0m"

:: Check input parameter
if "%~1"=="" (
    echo %RED%Error: No input file specified!%RESET%
    echo Usage: %~nx0 [input.xapk|apks|apk]
    exit /b 1
)

:: Sanitize filename
set "INPUT_FILE=%~f1"
set "EXT=%~x1"
set "BASE_NAME=%~n1"
set "BASE_NAME=%BASE_NAME: =_%"
set "BASE_NAME=%BASE_NAME:'=%"
set "BASE_NAME=%BASE_NAME:´=%"
set "BASE_NAME=%BASE_NAME:`=%"
set "BASE_NAME=%BASE_NAME:^=%"
set "BASE_NAME=%BASE_NAME:&=_%"
set "BASE_NAME=%BASE_NAME:(=_%"
set "BASE_NAME=%BASE_NAME:)=_%"
set "BASE_NAME=%BASE_NAME:[=_%"
set "BASE_NAME=%BASE_NAME:]=_%"
set "BASE_NAME=%BASE_NAME:!=_%"
set "BASE_NAME=%BASE_NAME:@=_%"
set "BASE_NAME=%BASE_NAME:#=_%"
set "BASE_NAME=%BASE_NAME:$=_%"
set "BASE_NAME=%BASE_NAME:%%=_%"
set "BASE_NAME=%BASE_NAME:+=_%"
set "BASE_NAME=%BASE_NAME:}=_%"
set "BASE_NAME=%BASE_NAME:{=_%"
set "BASE_NAME=%BASE_NAME:;=_%"
set "BASE_NAME=%BASE_NAME:^|=_%"
set "BASE_NAME=%BASE_NAME:?=_%"

:: Initialize variables
set "OUTPUT_DIR=%~dp0%BASE_NAME%-patched"
set "TEMPDIR=%TEMP%\%BASE_NAME%-%RANDOM%-%TIME::=-%"
set "KEYSTORE=debug.keystore"
set "ORIG_EXT=%EXT%"
set "IS_BUNDLE=0"

:: Check required tools
call :CHECK_TOOLS || exit /b 1

:: Determine file type
if /i "%EXT%" == ".xapk" set "IS_BUNDLE=1"
if /i "%EXT%" == ".apks" set "IS_BUNDLE=1"

:: Main processing logic
if %IS_BUNDLE% equ 1 (
    call :PROCESS_BUNDLE || exit /b 1
) else (
    call :PROCESS_SINGLE || exit /b 1
)

call :CLEANUP || exit /b 1

echo %CYAN%═══════════════════════════════════════════════════%RESET%
echo %GREEN%Successfully patched file!%RESET%
echo %GREEN%Goo and Show some love for  %CYAN%Zetsu4i %RESET% Now!!%RESET%
echo %YELLOW%Output: %OUTPUT_DIR% %RESET%
echo %CYAN%═══════════════════════════════════════════════════%RESET%

timeout 5 >nul
exit /b 0

:: Check if required tools are available
:CHECK_TOOLS
echo %YELLOW%[ ] Checking required tools...%RESET%

where apk-mitm >nul 2>&1 || (
    echo %RED%Error: apk-mitm not found in PATH!%RESET%
    exit /b 1
)

where apksigner >nul 2>&1 || (
    echo %RED%Error: apksigner not found in PATH!%RESET%
    exit /b 1
)
where node >nul 2>&1 || (
    echo %RED%Warrinig: NodeJs not found in PATH!%RESET%
)
echo %GREEN%✓ All tools verified%RESET%
exit /b 0

:: Process XAPK bundle
:PROCESS_BUNDLE
echo %YELLOW%[1/6] Processing %ORIG_EXT% bundle...%RESET%

:: Check if the input file exists
if not exist "%INPUT_FILE%" (
    echo %RED%Error: Input file does not exist!%RESET%
    exit /b 1
)

:: Create temp directory
if not exist "%TEMPDIR%" mkdir "%TEMPDIR%" || (
    echo %RED%Error: Failed to create temp directory!%RESET%
    exit /b 1
)

:: Copy input file to temp directory
copy "%INPUT_FILE%" "%TEMPDIR%\%BASE_NAME%.zip" >nul || (
    echo %RED%Error: Failed to prepare bundle file!%RESET%
    exit /b 1
)

call :UNZIP || exit /b 1
call :FIND_BASE_APK || exit /b 1
call :CREATE_KEYSTORE || exit /b 1
call :PATCH_APK || exit /b 1
call :SIGN_APKS || exit /b 1
call :REPACKAGE_BUNDLE || exit /b 1
exit /b 0

:: Process single APK
:PROCESS_SINGLE
echo %YELLOW%[1/4] Processing single APK...%RESET%

:: Create temp directory
if not exist "%TEMPDIR%" mkdir "%TEMPDIR%" || (
    echo %RED%Error: Failed to create temp directory!%RESET%
    exit /b 1
)

:: Copy APK file to temp directory
copy "%INPUT_FILE%" "%TEMPDIR%\%BASE_NAME%.apk" >nul || (
    echo %RED%Error: Failed to copy APK!%RESET%
    exit /b 1
)

call :CREATE_KEYSTORE || exit /b 1
call :PATCH_SINGLE || exit /b 1
call :SIGN_SINGLE || exit /b 1
call :MOVE_OUTPUT || exit /b 1
exit /b 0

:: Unzip the bundle
:UNZIP
echo %YELLOW%[2/6] Extracting bundle...%RESET%
pushd "%TEMPDIR%"
powershell -command "Expand-Archive -Path '%BASE_NAME%.zip' -DestinationPath ."
if exist "%BASE_NAME%.zip" del "%BASE_NAME%.zip"
echo %GREEN%✓ Extraction successful%RESET%
popd
exit /b 0

:: Find the base APK name from manifest.json
:FIND_BASE_APK
echo %YELLOW%[3/6] Finding base APK name...%RESET%
set "BASE_APK="
:: Attempt to read manifest.json and extract base APK name
pushd "%TEMPDIR%"
if exist "manifest.json" (
    echo %YELLOW%[1.1] Reading manifest.json to find base APK...%RESET%
    for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "((Get-Content 'manifest.json' -Raw | ConvertFrom-Json).split_apks | Where-Object { $_.id -eq 'base' }).file"`) do (
        set "BASE_APK=%%A"
    )
    echo %GREEN%✓ Found base APK: %BASE_APK%%RESET%
) else (
    echo %YELLOW%manifest.json not found, using default base APK: %BASE_APK%%RESET%
)
popd

call :CREATE_KEYSTORE || exit /b 1
call :PATCH_APK || exit /b 1
call :SIGN_APKS || exit /b 1
call :REPACKAGE_BUNDLE || exit /b 1
exit /b 0

:: Create keystore for signing
:CREATE_KEYSTORE
echo %YELLOW%[4/6] Generating debug keystore...%RESET%
if exist "%KEYSTORE%" del "%KEYSTORE%"
keytool -genkey -v -keystore "%KEYSTORE%" -storepass android -alias androiddebugkey -keypass android -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Android Debug, OU=Mobile, O=Android, C=US" || (
    echo %RED%Error: Keystore generation failed!%RESET%
    exit /b 1
)
echo %GREEN%✓ Keystore created%RESET%
exit /b 0

:: Patch APK
:PATCH_APK
echo %YELLOW%[5/6] Patching base APK...%RESET%
pushd "%TEMPDIR%"
if exist "%BASE_APK%" (
    apk-mitm "%BASE_APK%"
    if not exist "%BASE_APK%-patched.apk" (
        echo %RED%Error: APK patching failed!%RESET%
        exit /b 1
    )
    del "%BASE_APK%"
    ren "%BASE_APK%-patched.apk" "%BASE_APK%"
    echo %GREEN%✓ APK successfully patched%RESET%
    popd
    exit /b 0
)
echo %RED%Error: %BASE_APK% not found in bundle!%RESET%
exit /b 1

:: Sign APK files
:SIGN_APKS
echo %YELLOW%[6/6] Signing APK files...%RESET%
pushd "%TEMPDIR%"
set "SIGN_ERROR=0"
for %%f in (*.apk) do (
    echo Signing %%~nf...
    apksigner sign --ks "..\%KEYSTORE%" --ks-pass pass:android "%%f"
    if !ERRORLEVEL! neq 0 set "SIGN_ERROR=1"
)
popd
if %SIGN_ERROR% equ 1 (
    echo %RED%Error: Failed to sign one or more APKs!%RESET%
    exit /b 1
)
echo %GREEN%✓ All APKs signed%RESET%
exit /b 0

:: Repackage the bundle after patching
:REPACKAGE_BUNDLE
echo %YELLOW%[7/6] Creating patched %ORIG_EXT%...%RESET%
if exist "%OUTPUT_DIR%" (
    echo %YELLOW%Warning: Output directory exists - overwriting contents!%RESET%
    rmdir /s /q "%OUTPUT_DIR%"
)
mkdir "%OUTPUT_DIR%"
pushd "%TEMPDIR%"
powershell -command "Compress-Archive -Path '*' -DestinationPath 'bundle.zip' -Force"
ren "bundle.zip" "%BASE_NAME%-patched%ORIG_EXT%"
popd
move "%TEMPDIR%\%BASE_NAME%-patched%ORIG_EXT%" "%OUTPUT_DIR%\" >nul && (
    echo %GREEN%✓ Bundle repackaged successfully%RESET%
    exit /b 0
)
echo %RED%Error: Failed to create patched bundle!%RESET%
exit /b 1

:: Patch single APK
:PATCH_SINGLE
echo %YELLOW%[2/4] Patching APK...%RESET%
pushd "%TEMPDIR%"
apk-mitm "%BASE_NAME%.apk"
if not exist "%BASE_NAME%-patched.apk" (
    echo %RED%Error: APK patching failed!%RESET%
    exit /b 1
)
del "%BASE_NAME%.apk"
echo %GREEN%✓ APK successfully patched%RESET%
popd
exit /b 0

:: Sign single APK
:SIGN_SINGLE
echo %YELLOW%[3/4] Signing APK...%RESET%
pushd "%TEMPDIR%"
apksigner sign --ks "..\%KEYSTORE%" --ks-pass pass:android "%BASE_NAME%-patched.apk" || (
    echo %RED%Error: Failed to sign APK!%RESET%
    exit /b 1
)
echo %GREEN%✓ APK signed successfully%RESET%
popd
exit /b 0

:: Move output to the final location
:MOVE_OUTPUT
echo %YELLOW%[4/4] Finalizing...%RESET%
if exist "%OUTPUT_DIR%" (
    echo %YELLOW%Warning: Output directory exists - overwriting contents!%RESET%
    rmdir /s /q "%OUTPUT_DIR%"
)
mkdir "%OUTPUT_DIR%"
move "%TEMPDIR%\%BASE_NAME%-patched.apk" "%OUTPUT_DIR%\" >nul && (
    echo %GREEN%✓ Patched APK ready%RESET%
    exit /b 0
)
echo %RED%Error: Failed to move output file!%RESET%
exit /b 1

:: Cleanup temporary files
:CLEANUP
echo %YELLOW%Cleaning up temporary files...%RESET%
::if exist "%TEMPDIR%" rmdir /s /q "%TEMPDIR%"
::if exist "%KEYSTORE%" del "%KEYSTORE%"
echo %GREEN%✓ Cleanup complete%RESET%
exit /b 0
