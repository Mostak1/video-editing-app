# Smart Video Clip Agent

A multi-interface video automation application built with Python, PySide6, FastAPI, and FFmpeg. The project supports two modes of operation:
1. **Standalone Desktop GUI Application**: Runs entirely as a local desktop window.
2. **Web UI + Local Agent Service (Option 2)**: Access a hosted or local web dashboard in your browser while a background local agent handles FFmpeg operations and file dialogue requests natively on your PC.

---

## Onboarding Setup Wizard Flow

When a user visits the hosted video editing website:

1. **Auto-check**: The Web UI automatically attempts to establish a background connection with the Local Agent on `http://127.0.0.1:8765/health`.
2. **Automatic Redirect**: If the Local Agent is active and both **FFmpeg** and **FFprobe** are detected in the system's PATH, the Setup Wizard is bypassed and the user is redirected straight to the **Video Editing Dashboard** in 1.5 seconds.
3. **Onboarding Guidance**: If the agent is offline or dependencies are missing, the UI presents an interactive **Setup Wizard**:
   - Instructions on how to download/install Python and FFmpeg.
   - Script run commands to start the local agent.
   - An interactive **Verification Checklist** checking for:
     - `Local Agent Status` (Online/Offline)
     - `FFmpeg Binary` (Detected/Missing)
     - `FFprobe Binary` (Detected/Missing)
   - A **"Verify & Start Editing"** check button that runs real-time diagnostic checks and redirects immediately upon success.

---

## Architecture Overview

```
[ Web UI Dashboard ] (Browser)
        │
        ▼ (HTTP / CORS)
[ Local Agent Service ] (Runs on local PC: http://127.0.0.1:8765)
        │
        ▼ (Subprocess calls)
[ Local FFmpeg Engine ]
        │
        ▼
[ Final Output Folder ]
```

---

## Prerequisites

Before running either interface, make sure you have the following installed:

1. **Python 3.9+**
2. **FFmpeg & FFprobe** (must be available in your system's PATH)

### Installing FFmpeg

#### 🔹 Windows
1. Download the build package from [Gyan.dev](https://www.gyan.dev/ffmpeg/builds/) (`ffmpeg-git-essentials.7z`).
2. Extract the files (e.g., to `C:\ffmpeg`).
3. Add `C:\ffmpeg\bin` to your system environment variables PATH.
4. Restart your terminal.

#### 🔹 macOS
```bash
brew install ffmpeg
```

#### 🔹 Linux (Debian/Ubuntu)
```bash
sudo apt update
sudo apt install ffmpeg
```

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd /var/www/html/smart-video-agent
   ```

2. **Create and activate a virtual environment:**
   * **Windows:**
     ```powershell
     python -m venv .venv
     .venv\Scripts\activate
     ```
   * **macOS / Linux:**
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

3. **Install the dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

---

## How to Run

### Option 1: Standalone Desktop GUI
If you want to use the classic PySide6 desktop interface directly:
```bash
python video_agent_app.py
```

### Option 2: Web UI + Local Agent (Recommended Setup)
1. **Launch the Local Agent:**
   ```bash
   python local_agent.py
   ```
   This opens a small agent window showing the server status and logs. The FastAPI server starts in the background on `http://127.0.0.1:8765`.

2. **Open the Web UI:**
   - Click the **"Open Web UI"** button directly on the agent's desktop window.
   - Or open `web_ui/index.html` in any web browser or visit `http://127.0.0.1:8765/` directly.
   - If hosted, visit the hosted URL (the website will run the setup checks automatically).

3. **Start rendering:**
   - Select your CSV, source video, options, and click **"Start Render"**. Progress and logs will stream in real-time on your browser dashboard.
