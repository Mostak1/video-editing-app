# Smart Video Clip Agent

A multi-interface video automation application built with Python, PySide6, FastAPI, and FFmpeg. The project supports two modes of operation:
1. **Standalone Desktop GUI Application**: Runs entirely as a local desktop window.
2. **Web UI + Local Agent Service**: Access a hosted or local web dashboard in your browser while a background local agent handles FFmpeg operations and file dialogue requests natively on your PC.

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

### Key Modules:
- `render_engine.py`: The core video-processing library containing the FFmpeg/FFprobe logic (split clips, cut silences, remove black screens, stitch clips).
- `video_agent_app.py`: Standalone desktop PySide6 GUI wrapper.
- `local_agent.py`: A native PySide6 app that starts a background FastAPI web server on port `8765`. It handles API requests from the browser (Web UI) and triggers native OS file dialogs when requested.
- `web_ui/index.html`: The web dashboard frontend. Features glassmorphism UI, a real-time console log stream, progress bars, and status updates.

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

### Option 2: Web UI + Local Agent (Recommended)
This splits the interface into a modern browser-based web dashboard and a local engine service:

1. **Launch the Local Agent:**
   ```bash
   python local_agent.py
   ```
   This will open a small agent window showing the server status and logs. The FastAPI server starts in the background on `http://127.0.0.1:8765`.

2. **Open the Web UI:**
   - Click the **"Open Web UI"** button directly on the agent's desktop window.
   - Alternatively, open `web_ui/index.html` in any web browser or visit `http://127.0.0.1:8765/` directly.

3. **Start rendering:**
   - The Web UI will automatically detect the local agent.
   - Click the **"Browse"** buttons in the browser. This will trigger native file/folder pickers on your desktop to retrieve the absolute paths.
   - Select your CSV, source video, options, and click **"Start Render"**. Progress and logs will stream in real-time on your browser dashboard.

---

## CSV File Schema Format

For CSV-driven modes, construct your CSV with the following headers:

| Headers (Any of the following) | Description |
| :--- | :--- |
| `ID` / `No` / `Serial` | Unique identifier for each clip |
| `Final title` / `Title` / `Name` | Output filename of the clip |
| `Source time range` / `Time range` / `Range` | Timestamp range to keep or cut (e.g. `00:01:20 - 00:02:10`) |

### Example
```csv
ID,Title,Time range
1,Intro,00:00:00 - 00:01:30
2,Deep Dive,00:01:30 - 00:08:45
```

---

## Agent Process Modes

- **Create many short clips from CSV ranges**: Splices the video into individual files per row.
- **Remove CSV ranges**: Cuts the timestamp ranges out, stitching the remaining content.
- **Auto remove black screen parts**: Automatically finds and deletes black screen intervals.
- **Auto remove silent parts**: Automatically scans the audio, finds silences, and removes them.
- **Auto remove black and silent parts**: Performs both checks and yields a polished, continuous video.
