import sys
import queue
import uuid
import threading
import webbrowser
from pathlib import Path
from typing import Optional, List

from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
)

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
import uvicorn

# Global Dialog Request Queue for communication between FastAPI threads and PySide6 main GUI thread
dialog_requests = queue.Queue()

# Thread-safe global state for the rendering job
job_state = {
    "status": "idle",       # "idle", "running", "finished", "failed", "cancelled"
    "progress": 0,
    "total": 0,
    "logs": [],
    "last_error": None,
    "cancelled": False,
}
job_lock = threading.Lock()

# ----------------- FastAPI Setup -----------------
app = FastAPI(title="Smart Video Agent Local Service")

# Enable CORS for any web client connecting locally
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class JobConfig(BaseModel):
    csv_path: Optional[str] = None
    video_path: str
    outro_path: Optional[str] = None
    output_dir: str
    normalize_output: bool
    work_mode: str

# Signal holder to send logs from FastAPI thread to PySide GUI log box
class AgentSignaler(QObject):
    log_signal = Signal(str)

signaler = AgentSignaler()

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "app": "smart-video-agent-local-service",
        "job_status": job_state["status"]
    }

@app.post("/choose-file")
def choose_file(file_type: str = Query("all", description="Type of file: 'csv', 'video', or 'outro'")):
    res_queue = queue.Queue()
    dialog_requests.put(("file", file_type, res_queue))
    # Block FastAPI request handler until Qt main thread selects file and pushes result
    path = res_queue.get()
    return {"path": path}

@app.post("/choose-folder")
def choose_folder():
    res_queue = queue.Queue()
    dialog_requests.put(("folder", "", res_queue))
    path = res_queue.get()
    return {"path": path}

def run_job_thread(config: JobConfig):
    global job_state
    
    try:
        def log_cb(msg):
            with job_lock:
                job_state["logs"].append(msg)
            signaler.log_signal.emit(msg)

        def progress_cb(curr, tot):
            with job_lock:
                job_state["progress"] = curr
                job_state["total"] = tot

        def cancel_check():
            with job_lock:
                return job_state["cancelled"]

        from render_engine import execute_video_job
        
        csv_path = Path(config.csv_path) if config.csv_path else None
        video_path = Path(config.video_path)
        outro_path = Path(config.outro_path) if config.outro_path else None
        output_dir = Path(config.output_dir)

        res = execute_video_job(
            csv_path=csv_path,
            video_path=video_path,
            outro_path=outro_path,
            output_dir=output_dir,
            normalize_output=config.normalize_output,
            work_mode=config.work_mode,
            log_cb=log_cb,
            progress_cb=progress_cb,
            cancel_check_cb=cancel_check
        )
        
        with job_lock:
            if job_state["cancelled"]:
                job_state["status"] = "cancelled"
                log_cb("Job was cancelled by the user.")
            else:
                job_state["status"] = "finished"
                log_cb(f"Job finished successfully! Saved to: {res}")
    except Exception as e:
        import traceback
        err_msg = str(e)
        with job_lock:
            job_state["status"] = "failed"
            job_state["last_error"] = err_msg
            job_state["logs"].append(f"ERROR: {err_msg}")
        signaler.log_signal.emit(f"ERROR: {err_msg}")

@app.post("/start-job")
def start_job(config: JobConfig):
    global job_state
    with job_lock:
        if job_state["status"] == "running":
            raise HTTPException(status_code=400, detail="A rendering job is already running.")
        
        # Reset state
        job_state["status"] = "running"
        job_state["progress"] = 0
        job_state["total"] = 0
        job_state["logs"] = []
        job_state["last_error"] = None
        job_state["cancelled"] = False

    signaler.log_signal.emit("----- Started New Web UI Render Job -----")
    signaler.log_signal.emit(f"Mode: {config.work_mode}")
    signaler.log_signal.emit(f"Video: {config.video_path}")
    signaler.log_signal.emit(f"Output: {config.output_dir}")

    t = threading.Thread(target=run_job_thread, args=(config,), daemon=True)
    t.start()
    return {"status": "started"}

@app.post("/cancel-job")
def cancel_job():
    global job_state
    with job_lock:
        if job_state["status"] == "running":
            job_state["cancelled"] = True
            signaler.log_signal.emit("Cancellation requested...")
            return {"status": "cancelling"}
        return {"status": "not_running"}

@app.get("/job-status")
def get_job_status(offset: int = 0):
    with job_lock:
        all_logs = list(job_state["logs"])
        sliced_logs = all_logs[offset:]
        return {
            "status": job_state["status"],
            "progress": job_state["progress"],
            "total": job_state["total"],
            "last_error": job_state["last_error"],
            "new_logs": sliced_logs,
            "next_offset": len(all_logs)
        }

@app.get("/")
def serve_web_ui():
    web_ui_path = Path(__file__).parent / "web_ui" / "index.html"
    if web_ui_path.exists():
        return FileResponse(web_ui_path)
    return HTMLResponse(
        """
        <html>
            <body style="background:#111827; color:#E5E7EB; font-family: sans-serif; text-align:center; padding-top:100px;">
                <h1>Smart Video Agent Local Service Running</h1>
                <p>Status: Healthy</p>
                <p>Web UI folder not found. Please create the <code>web_ui/index.html</code> file.</p>
            </body>
        </html>
        """
    )


# ----------------- Uvicorn Runner -----------------
class WebServerThread(threading.Thread):
    def __init__(self, host="127.0.0.1", port=8765):
        super().__init__()
        self.host = host
        self.port = port
        self.daemon = True

    def run(self):
        # Disable uvicorn log pollution to stdout if needed, or leave defaults
        uvicorn.run(app, host=self.host, port=self.port, log_level="warning")


# ----------------- PySide6 Desktop GUI -----------------
class LocalAgentWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Smart Video Agent - Local Agent")
        self.setMinimumSize(600, 400)
        
        self.build_ui()
        self.apply_style()

        # Connect log signals to update the UI text area
        signaler.log_signal.connect(self.add_log)

        # QTimer to periodically check for native dialog requests from FastAPI
        self.dialog_timer = QTimer(self)
        self.dialog_timer.timeout.connect(self.process_dialog_requests)
        self.dialog_timer.start(50)  # Check every 50ms

    def build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header Info
        header_label = QLabel("Smart Video Agent - Local Agent")
        header_label.setObjectName("HeaderTitle")
        layout.addWidget(header_label)

        status_desc = QLabel("This background agent allows the hosted Web UI to communicate with your local FFmpeg.")
        status_desc.setObjectName("HeaderSub")
        layout.addWidget(status_desc)

        # Info Box (Server Status, URL)
        info_layout = QHBoxLayout()
        self.server_url_label = QLabel("Server Running at: <b>http://127.0.0.1:8765</b>")
        self.server_url_label.setObjectName("UrlLabel")
        info_layout.addWidget(self.server_url_label)
        
        self.open_ui_btn = QPushButton("Open Web UI")
        self.open_ui_btn.clicked.connect(self.open_web_ui)
        info_layout.addWidget(self.open_ui_btn)
        
        layout.addLayout(info_layout)

        # Log box
        log_title = QLabel("Agent Logs:")
        layout.addWidget(log_title)
        
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setPlaceholderText("Logs from local operations and incoming API requests will show here...")
        layout.addWidget(self.log_box)

        self.add_log("Agent started locally.")
        self.add_log("Listening on HTTP http://127.0.0.1:8765")

    def apply_style(self):
        self.setStyleSheet(
            """
            QWidget {
                background: #111827;
                color: #E5E7EB;
                font-size: 13px;
                font-family: 'Inter', -apple-system, sans-serif;
            }

            QLabel#HeaderTitle {
                font-size: 20px;
                font-weight: 700;
                color: #FFFFFF;
                margin-top: 5px;
            }

            QLabel#HeaderSub {
                color: #9CA3AF;
                font-size: 13px;
                margin-bottom: 5px;
            }

            QLabel#UrlLabel {
                background: #1F2937;
                border: 1px solid #374151;
                border-radius: 8px;
                padding: 10px;
                color: #10B981;
            }

            QTextEdit {
                background: #1F2937;
                border: 1px solid #374151;
                border-radius: 8px;
                padding: 10px;
                color: #F3F4F6;
                font-family: monospace;
            }

            QPushButton {
                background: #2563EB;
                border: none;
                border-radius: 8px;
                padding: 10px 18px;
                color: white;
                font-weight: 600;
            }

            QPushButton:hover {
                background: #1D4ED8;
            }
            """
        )

    def add_log(self, message: str):
        self.log_box.append(message)
        # Scroll to bottom
        self.log_box.ensureCursorVisible()

    def open_web_ui(self):
        webbrowser.open("http://127.0.0.1:8765/")

    def process_dialog_requests(self):
        while not dialog_requests.empty():
            dialog_type, file_type, res_queue = dialog_requests.get()
            path = ""
            
            try:
                if dialog_type == "file":
                    if file_type == "csv":
                        filter_str = "CSV Files (*.csv);;All Files (*)"
                        title = "Select CSV File"
                    elif file_type in ("video", "outro"):
                        filter_str = "Video Files (*.mp4 *.mov *.mkv *.avi *.webm);;All Files (*)"
                        title = f"Select {file_type.capitalize()} Video"
                    else:
                        filter_str = "All Files (*)"
                        title = "Select File"
                    
                    self.add_log(f"Spawning native file dialog: {title}")
                    path, _ = QFileDialog.getOpenFileName(self, title, "", filter_str)
                    
                elif dialog_type == "folder":
                    self.add_log("Spawning native folder dialog")
                    path = QFileDialog.getExistingDirectory(self, "Select Output Folder", "")
            except Exception as e:
                self.add_log(f"Error in dialog processing: {e}")
                path = ""
                
            res_queue.put(path)
            self.add_log(f"Selected path: {path if path else 'None'}")


def main():
    # 1. Start the FastAPI Web Server Thread
    server_thread = WebServerThread(host="127.0.0.1", port=8765)
    server_thread.start()

    # 2. Run the Qt Desktop GUI Application
    app_qt = QApplication(sys.argv)
    window = LocalAgentWindow()
    window.show()
    
    sys.exit(app_qt.exec())

if __name__ == "__main__":
    main()
