# Smart Video Clip Agent

A desktop GUI application built with PySide6 and FFmpeg to automate video editing tasks. The application can split a long video into multiple clips based on CSV timestamp ranges, cut out silent or black screen sections automatically, combine clips, or append outro templates.

---

## Prerequisites

Before running the application, make sure you have the following installed on your system:

1. **Python 3.9+**
2. **FFmpeg & FFprobe** (must be added to your system's PATH environment variable)

### How to Install FFmpeg on Any PC

#### 🔹 Windows
1. Download the latest release from [Gyan.dev](https://www.gyan.dev/ffmpeg/builds/) (choose `ffmpeg-git-essentials.7z`).
2. Extract the downloaded archive (e.g., to `C:\ffmpeg`).
3. Add the `bin` folder (e.g., `C:\ffmpeg\bin`) to your system environment variables PATH:
   * Press `Win + R`, type `sysdm.cpl`, and hit Enter.
   * Go to **Advanced** tab > **Environment Variables**.
   * Under **System variables**, select **Path** and click **Edit**.
   * Click **New** and paste the path to your extracted `bin` folder.
   * Click **OK** to save and restart your terminal.

#### 🔹 macOS
Using [Homebrew](https://brew.sh/):
```bash
brew install ffmpeg
```

#### 🔹 Linux (Debian/Ubuntu)
```bash
sudo apt update
sudo apt install ffmpeg
```

---

## Setup & Running the Application

Follow these steps to run the application on your computer:

### Step 1: Clone or navigate to the project folder
Open your terminal (or Command Prompt / PowerShell on Windows) and run:
```bash
cd path/to/smart-video-agent
```

### Step 2: Create a virtual environment (Recommended)
This keeps dependencies isolated for the project.

* **On Windows (PowerShell / Command Prompt):**
  ```powershell
  python -m venv .venv
  .venv\Scripts\activate
  ```

* **On macOS / Linux:**
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

### Step 3: Install dependencies
Install the required Python packages:
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Run the Application
Start the graphical interface:
```bash
python video_agent_app.py
```

---

## CSV File Schema Format

When using CSV mode, the file must be comma-separated (`.csv`) and contain the following column headers (case-insensitive):

| Column Headers (Use one of each group) | Example Values | Description |
| :--- | :--- | :--- |
| `ID` / `No` / `Serial` | `1`, `clip_01` | Unique identifier for the clip |
| `Final title` / `Title` / `Name` | `Introduction to PySide6` | Name of the output video clip |
| `Source time range` / `Time range` / `Range` | `00:01:12 - 00:02:05` | Timestamp range to keep or cut |

### Example CSV Content
```csv
ID,Title,Time range
1,Intro Scene,00:00:00 - 00:01:30
2,Code Walkthrough,00:01:30 - 00:10:45
3,Outro & Summary,00:10:45 - 00:12:00
```

---

## Agent Modes

* **Create many short clips from CSV ranges**: Splits the source video into separate video files for each row defined in the CSV.
* **Remove CSV ranges and create one polished video**: Cuts out the listed CSV time ranges and stitches the remaining parts together into a single polished output video.
* **Auto remove black screen parts**: Automatically detects black screens in the source video and cuts them out.
* **Auto remove silent parts**: Automatically scans the video's audio track, finds silences, and removes them.
* **Auto remove black and silent parts**: Performs both checks and yields a polished, continuous video without silence or blank screens.
