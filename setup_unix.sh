#!/bin/bash

# Exit on error
set -e

echo "==================================================="
echo "     Smart Video Agent - Unix Auto Setup"
echo "==================================================="
echo ""

# Determine OS
OS_TYPE="$(uname -s)"
echo "[*] Operating System: $OS_TYPE"

# 1. Check Python3
echo "[*] Checking Python3 installation..."
if ! command -v python3 &> /dev/null; then
    echo "[!] Python3 not found."
    if [ "$OS_TYPE" = "Darwin" ]; then
        echo "[*] macOS detected. Installing Python3 via Homebrew..."
        if ! command -v brew &> /dev/null; then
            echo "[ERROR] Homebrew is not installed. Please install Homebrew first from https://brew.sh/"
            exit 1
        fi
        brew install python
    else
        echo "[*] Linux detected. Please install Python3 using your package manager (e.g., sudo apt install python3)."
        exit 1
    fi
else
    echo "[✓] Python3 is installed."
fi

# 2. Check FFmpeg
echo ""
echo "[*] Checking FFmpeg installation..."
if command -v ffmpeg &> /dev/null; then
    echo "[✓] FFmpeg is already installed."
else
    echo "[!] FFmpeg not found. Attempting installation..."
    if [ "$OS_TYPE" = "Darwin" ]; then
        if ! command -v brew &> /dev/null; then
            echo "[ERROR] Homebrew is not installed. Please install Homebrew first to automate FFmpeg setup, or install FFmpeg manually."
            exit 1
        fi
        echo "[*] Installing FFmpeg via Homebrew..."
        brew install ffmpeg
    else
        # Linux
        if command -v apt-get &> /dev/null; then
            echo "[*] Debian/Ubuntu detected. Installing FFmpeg..."
            sudo apt-get update && sudo apt-get install -y ffmpeg
        elif command -v dnf &> /dev/null; then
            echo "[*] Fedora detected. Installing FFmpeg..."
            sudo dnf install -y ffmpeg
        elif command -v pacman &> /dev/null; then
            echo "[*] Arch Linux detected. Installing FFmpeg..."
            sudo pacman -S --noconfirm ffmpeg
        else
            echo "[ERROR] Unsupported Linux distribution. Please install FFmpeg manually using your package manager."
            exit 1
        fi
    fi
fi

# 3. Create virtual environment
echo ""
echo "[*] Creating Python Virtual Environment (.venv)..."
python3 -m venv .venv

# 4. Install dependencies
echo ""
echo "[*] Installing required Python packages..."
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "==================================================="
echo "[✓] SETUP COMPLETED SUCCESSFULLY!"
echo "==================================================="
echo "You can now run the agent by running: ./run_agent.sh"
echo ""

# Set execution permissions on run script
chmod +x run_agent.sh || true
./run_agent.sh
