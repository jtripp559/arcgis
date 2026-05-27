@echo off
setlocal
echo Beginning file transfer routine

REM Default values
set "DEFAULT_LINUX_USER=jtripp"
set "DEFAULT_LINUX_HOST=org-app9"
set "DEFAULT_LINUX_DIR=/home/jtripp/scripts/output/"
set "DEFAULT_WINDOWS_DIR=\\org-app2\D$\GenericArcGISDataDir\"

REM Prompt the user for input with default values
set /p LINUX_USER="Enter the Linux username [DEFAULT: %DEFAULT_LINUX_USER%]: " 
if "%LINUX_USER%"=="" set LINUX_USER=%DEFAULT_LINUX_USER%

set /p LINUX_HOST="Enter the Linux host (IP or hostname) [DEFAULT: %DEFAULT_LINUX_HOST%]: "
if "%LINUX_HOST%"=="" set LINUX_HOST=%DEFAULT_LINUX_HOST%

set /p LINUX_DIR="Enter the directory on the Linux server [DEFAULT: %DEFAULT_LINUX_DIR%]: "
if "%LINUX_DIR%"=="" set LINUX_DIR=%DEFAULT_LINUX_DIR%

set /p WINDOWS_DIR="Enter the directory on the Windows server [DEFAULT: %DEFAULT_WINDOWS_DIR%]: "
if "%WINDOWS_DIR%"=="" set WINDOWS_DIR=%DEFAULT_WINDOWS_DIR%

set /p FROM_FILE_NAME="Enter the file name to copy: "
if "%FROM_FILE_NAME%"=="" (
    echo *** FILE NAME IS REQUIRED. *** Try again.
    set /p FROM_FILE_NAME="Enter the file name to copy: "
    if "%FROM_FILE_NAME%"=="" (
        echo No file name entered. Operation cancelled.
        pause
        exit /b 1
    )
)

set /p TO_FILE_NAME="Enter the name to save the file as [DEFAULT: %FROM_FILE_NAME%]: "
if "%TO_FILE_NAME%"=="" set TO_FILE_NAME=%FROM_FILE_NAME%

set /p COPY_FROM_LINUX="Are you copying *** FROM *** %LINUX_HOST%? (y/n): "

REM Ensure DIRs end with a slash
if not "%LINUX_DIR:~-1%"=="/" set "LINUX_DIR=%LINUX_DIR%/"
if not "%WINDOWS_DIR:~-1%"=="\" set "WINDOWS_DIR=%WINDOWS_DIR%\"

if /i "%COPY_FROM_LINUX%"=="n" (
    set "FROM_DIR=%WINDOWS_DIR%"
    set "TO_DIR=%LINUX_DIR%"
) else (
    set "FROM_DIR=%LINUX_DIR%"
    set "TO_DIR=%WINDOWS_DIR%"
)

REM Construct the full file paths
set "FROM_FILE_PATH=%FROM_DIR%%FROM_FILE_NAME%"
set "TO_FILE_PATH=%TO_DIR%%TO_FILE_NAME%"

REM Display the entered information
echo.
echo Linux Username: %LINUX_USER%
echo Linux Host: %LINUX_HOST%
echo Linux Directory: %LINUX_DIR%
echo Windows Directory: %WINDOWS_DIR%
echo.
echo From File Path: %FROM_FILE_PATH%
echo To File Path: %TO_FILE_PATH%
echo.
echo.

REM Confirm the details with the user
set /p CONFIRM="Are these details correct? (y/n): "
if /i not "%CONFIRM%"=="y" (
    echo Operation cancelled.
    pause
    exit /b 1
)

REM Use scp to copy the file
echo.
echo Copying file...
if /i "%COPY_FROM_LINUX%"=="n" (
    scp %FROM_FILE_PATH% %LINUX_USER%@%LINUX_HOST%:%TO_FILE_PATH%
) else (
    scp %LINUX_USER%@%LINUX_HOST%:%FROM_FILE_PATH% %TO_FILE_PATH%
)

REM Check if the copy was successful
if %errorlevel% neq 0 (
    echo File transfer failed.
    pause
    exit /b %errorlevel%
) else (
    echo File transfer successful.

    REM Verify the file transfer by calculating checksums

    echo Comparing checksums for verification...
    ssh %LINUX_USER%@%LINUX_HOST% "md5sum %FROM_FILE_PATH%" > linux_checksum.txt
    if %errorlevel% neq 0 (
        echo Failed to calculate checksum on Linux.
        pause
        exit /b %errorlevel%
    )
    :: Extract the checksum value
    set /p LINUX_CHECKSUM=<linux_checksum.txt
    set LINUX_CHECKSUM=%LINUX_CHECKSUM:~0,32%
    :: remove the temporary file
    del linux_checksum.txt

    :: Calculate checksum on Windows
    certutil -hashfile %TO_FILE_PATH% MD5 > windows_checksum.txt
    if %errorlevel% neq 0 (
        echo Failed to calculate checksum on Windows.
        pause
        exit /b %errorlevel%
    )
    :: Extract the checksum value
    for /f "tokens=1,2 delims=: " %%a in (windows_checksum.txt) do (
        if "%%a"=="MD5" set WINDOWS_CHECKSUM=%%b
    )
    :: remove the temporary file
    del windows_checksum.txt

    :: Compare checksums
    if /i "%LINUX_CHECKSUM%"=="%WINDOWS_CHECKSUM%" (
        echo Checksums match. File transfer verified.
    ) else (
        echo Checksums do not match. File transfer may be corrupted.
        pause
        exit /b 1
    )
)

REM Open the TO_DIR in Windows Explorer
explorer %TO_DIR%

endlocal

pause