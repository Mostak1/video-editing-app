@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ===================================================
echo     Smart Video Agent - Windows Auto Setup
echo ===================================================
echo.

:: 1. Check Python
echo [*] Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Python not found. Downloading Python 3.11 installer...
    curl -L -o python_installer.exe https://www.python.org/ftp/python/3.11.5/python-3.11.5-amd64.exe
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to download Python. Please install it manually from https://python.org/
        pause
        exit /b
    )
    echo [*] Installing Python silently (User-only, adds to PATH)... Please wait...
    start /wait python_installer.exe /quiet PrependPath=1 InstallAllUsers=0 Include_test=0 Include_pip=1
    del python_installer.exe
    
    :: Refresh PATH for the current batch session
    set "PATH=%USERPROFILE%\AppData\Local\Programs\Python\Python311\;%USERPROFILE%\AppData\Local\Programs\Python\Python311\Scripts\;%PATH%"
    
    :: Verify again
    python --version >nul 2>&1
    if !errorlevel! neq 0 (
        echo [ERROR] Python installation succeeded but could not be located in PATH. Please restart this setup script.
        pause
        exit /b
    )
    echo [✓] Python installed successfully.
) else (
    echo [✓] Python is already installed.
)

:: 2. Check FFmpeg
echo.
echo [*] Checking FFmpeg installation...
if exist "ffmpeg.exe" (
    echo [✓] FFmpeg is already present in project directory.
) else (
    ffmpeg -version >nul 2>&1
    if !errorlevel! eq 0 (
        echo [✓] FFmpeg is already available globally in system PATH.
    ) else (
        echo [!] FFmpeg not found. Downloading pre-compiled FFmpeg binaries...
        :: Downloading static essentials release zip
        curl -L -o ffmpeg.zip https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
        if !errorlevel! neq 0 (
            echo [ERROR] Failed to download FFmpeg. Please download it manually.
            pause
            exit /b
        )
        echo [*] Extracting FFmpeg... This may take a minute...
        powershell -Command "Expand-Archive -Path ffmpeg.zip -DestinationPath temp_ffmpeg -Force"
        
        :: Find and copy the executables to the root directory
        echo [*] Configuring FFmpeg binaries in project folder...
        for /r temp_ffmpeg %%f in (ffmpeg.exe ffprobe.exe) do (
            if exist "%%f" copy /y "%%f" . >nul
        )
        
        :: Cleanup
        del ffmpeg.zip
        rmdir /s /q temp_ffmpeg
        
        if not exist "ffmpeg.exe" (
            echo [ERROR] Failed to extract FFmpeg. Please place ffmpeg.exe in this folder manually.
            pause
            exit /b
        )
        echo [✓] FFmpeg configured locally in project folder.
    )
)

:: 3. Create virtual environment
echo.
echo [*] Creating Python Virtual Environment (.venv)...
python -m venv .venv
if !errorlevel! neq 0 (
    echo [ERROR] Failed to create virtual environment.
    pause
    exit /b
)

:: 4. Install dependencies
echo.
echo [*] Installing required Python packages...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
if !errorlevel! neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b
)
echo [✓] Dependencies installed.

echo.
echo ===================================================
echo [✓] SETUP COMPLETE SUCCESSFULLY!
echo ===================================================
echo You can now run the agent by double-clicking run_agent.bat
echo.
pause
start run_agent.bat
exit
