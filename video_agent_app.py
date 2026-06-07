import sys
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from render_engine import execute_video_job


class VideoWorker(QThread):
    log = Signal(str)
    progress = Signal(int, int)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        csv_path: str,
        video_path: str,
        outro_path: str,
        output_dir: str,
        normalize_output: bool,
        work_mode: str,
    ):
        super().__init__()
        self.csv_path = Path(csv_path) if csv_path else None
        self.video_path = Path(video_path)
        self.outro_path = Path(outro_path) if outro_path else None
        self.output_dir = Path(output_dir)
        self.normalize_output = normalize_output
        self.work_mode = work_mode
        self._cancelled = False

    def run(self):
        try:
            def log_cb(msg):
                self.log.emit(msg)

            def progress_cb(curr, tot):
                self.progress.emit(curr, tot)

            def cancel_check():
                return self._cancelled

            res = execute_video_job(
                csv_path=self.csv_path,
                video_path=self.video_path,
                outro_path=self.outro_path,
                output_dir=self.output_dir,
                normalize_output=self.normalize_output,
                work_mode=self.work_mode,
                log_cb=log_cb,
                progress_cb=progress_cb,
                cancel_check_cb=cancel_check,
            )
            if self._cancelled:
                self.log.emit("Job was cancelled by user.")
            else:
                self.finished_ok.emit(f"Successfully processed video task!\nSaved to: {res}")
        except Exception as e:
            self.failed.emit(str(e))

    def cancel(self):
        self._cancelled = True


class VideoAgentApp(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.setWindowTitle("Smart Video Clip Agent")
        self.setMinimumSize(850, 560)
        self.build_ui()
        self.apply_style()

    def build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(14)

        title = QLabel("Smart Video Clip Agent")
        title.setObjectName("Title")

        subtitle = QLabel(
            "CSV ranges দিয়ে short clips বা polished full video তৈরি করুন"
        )
        subtitle.setObjectName("Subtitle")

        root.addWidget(title)
        root.addWidget(subtitle)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)

        self.csv_input = QLineEdit()
        self.video_input = QLineEdit()
        self.outro_input = QLineEdit()
        self.output_input = QLineEdit()
        self.normalize_checkbox = QCheckBox("Normalize output: 1920x1080, 30fps, H.264 + AAC")
        self.normalize_checkbox.setChecked(True)
        self.mode_select = QComboBox()
        self.mode_select.addItem("Create many short clips from CSV ranges", "clips")
        self.mode_select.addItem("Remove CSV ranges and create one polished video", "remove_ranges")
        self.mode_select.addItem("Auto remove black screen parts into one polished video", "auto_black")
        self.mode_select.addItem("Auto remove silent parts into one polished video", "auto_silence")
        self.mode_select.addItem("Auto remove black and silent parts into one polished video", "auto_black_silence")

        self.add_file_row(grid, 0, "Script CSV", self.csv_input, self.choose_csv)
        self.add_file_row(grid, 1, "Main long video", self.video_input, self.choose_video)
        self.add_file_row(grid, 2, "Outro video optional", self.outro_input, self.choose_outro)
        self.add_folder_row(grid, 3, "Final output folder", self.output_input, self.choose_output)
        grid.addWidget(QLabel("Agent mode"), 4, 0)
        grid.addWidget(self.mode_select, 4, 1, 1, 2)
        grid.addWidget(QLabel("Output mode"), 5, 0)
        grid.addWidget(self.normalize_checkbox, 5, 1, 1, 2)

        root.addLayout(grid)

        self.start_btn = QPushButton("Start Agent")
        self.start_btn.clicked.connect(self.start_agent)

        self.progress = QProgressBar()
        self.progress.setValue(0)

        action_row = QHBoxLayout()
        action_row.addWidget(self.start_btn)
        action_row.addWidget(self.progress)

        root.addLayout(action_row)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setPlaceholderText("Agent logs will appear here...")

        root.addWidget(self.log_box)

    def add_file_row(self, grid, row, label_text, line_edit, handler):
        label = QLabel(label_text)
        button = QPushButton("Browse")
        button.clicked.connect(handler)

        grid.addWidget(label, row, 0)
        grid.addWidget(line_edit, row, 1)
        grid.addWidget(button, row, 2)

    def add_folder_row(self, grid, row, label_text, line_edit, handler):
        label = QLabel(label_text)
        button = QPushButton("Select")
        button.clicked.connect(handler)

        grid.addWidget(label, row, 0)
        grid.addWidget(line_edit, row, 1)
        grid.addWidget(button, row, 2)

    def choose_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose CSV",
            "",
            "CSV Files (*.csv);;All Files (*)",
        )
        if path:
            self.csv_input.setText(path)

    def choose_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose video",
            "",
            "Video Files (*.mp4 *.mov *.mkv *.avi *.webm);;All Files (*)",
        )
        if path:
            self.video_input.setText(path)

    def choose_outro(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose outro video",
            "",
            "Video Files (*.mp4 *.mov *.mkv *.avi *.webm);;All Files (*)",
        )
        if path:
            self.outro_input.setText(path)

    def choose_output(self):
        path = QFileDialog.getExistingDirectory(self, "Choose output folder")
        if path:
            self.output_input.setText(path)

    def start_agent(self):
        csv_path = self.csv_input.text().strip()
        video_path = self.video_input.text().strip()
        outro_path = self.outro_input.text().strip()
        output_dir = self.output_input.text().strip()
        normalize_output = self.normalize_checkbox.isChecked()
        work_mode = self.mode_select.currentData()

        if work_mode not in ("auto_black", "auto_silence", "auto_black_silence") and (
            not csv_path or not Path(csv_path).exists()
        ):
            QMessageBox.warning(self, "Missing CSV", "Please select a valid CSV file.")
            return

        if not video_path or not Path(video_path).exists():
            QMessageBox.warning(self, "Missing video", "Please select a valid main video file.")
            return

        if outro_path and not Path(outro_path).exists():
            QMessageBox.warning(self, "Invalid outro", "Outro path is invalid.")
            return

        if not output_dir:
            QMessageBox.warning(self, "Missing folder", "Please select an output folder.")
            return

        self.log_box.clear()
        self.progress.setValue(0)
        self.start_btn.setEnabled(False)

        self.worker = VideoWorker(
            csv_path,
            video_path,
            outro_path,
            output_dir,
            normalize_output,
            work_mode,
        )
        self.worker.log.connect(self.add_log)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished_ok.connect(self.agent_done)
        self.worker.failed.connect(self.agent_failed)
        self.worker.start()

    def add_log(self, text):
        self.log_box.append(text)

    def update_progress(self, current, total):
        self.progress.setMaximum(total)
        self.progress.setValue(current)

    def agent_done(self, message):
        self.start_btn.setEnabled(True)
        QMessageBox.information(self, "Done", message)
        self.add_log(message)

    def agent_failed(self, message):
        self.start_btn.setEnabled(True)
        QMessageBox.critical(self, "Agent failed", message)
        self.add_log("ERROR: " + message)

    def apply_style(self):
        self.setStyleSheet(
            """
            QWidget {
                background: #111827;
                color: #E5E7EB;
                font-size: 14px;
            }

            QLabel#Title {
                font-size: 28px;
                font-weight: 700;
                color: #FFFFFF;
            }

            QLabel#Subtitle {
                color: #9CA3AF;
                font-size: 14px;
                margin-bottom: 10px;
            }

            QLineEdit, QTextEdit, QComboBox {
                background: #1F2937;
                border: 1px solid #374151;
                border-radius: 10px;
                padding: 9px;
                color: #F9FAFB;
            }

            QCheckBox {
                spacing: 8px;
            }

            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }

            QPushButton {
                background: #2563EB;
                border: none;
                border-radius: 10px;
                padding: 10px 16px;
                color: white;
                font-weight: 600;
            }

            QPushButton:hover {
                background: #1D4ED8;
            }

            QPushButton:disabled {
                background: #4B5563;
            }

            QProgressBar {
                border: 1px solid #374151;
                border-radius: 8px;
                background: #1F2937;
                height: 22px;
                text-align: center;
            }

            QProgressBar::chunk {
                background: #22C55E;
                border-radius: 8px;
            }
            """
        )


def main():
    app = QApplication(sys.argv)
    window = VideoAgentApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
