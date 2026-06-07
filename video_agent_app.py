import csv
import re
import shutil
import subprocess
import sys
import tempfile
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

TIME_RE = re.compile(r"\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?")
BLACK_RE = re.compile(r"black_start:(?P<start>\d+(?:\.\d+)?).*black_end:(?P<end>\d+(?:\.\d+)?)")
SILENCE_START_RE = re.compile(r"silence_start:\s*(?P<start>\d+(?:\.\d+)?)")
SILENCE_END_RE = re.compile(r"silence_end:\s*(?P<end>\d+(?:\.\d+)?)")

VF = (
    "scale=1920:1080:force_original_aspect_ratio=decrease,"
    "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,"
    "setsar=1,format=yuv420p"
)


def normalize_key(key: str) -> str:
    return re.sub(r"\s+", " ", str(key).strip().lower())


def get_column(row: dict, *names: str) -> str:
    normalized = {normalize_key(k): v for k, v in row.items()}
    for name in names:
        value = normalized.get(normalize_key(name))
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def parse_time_to_seconds(value: str) -> float:
    parts = value.strip().split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    if len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    raise ValueError(f"Invalid time: {value}")


def seconds_to_time(seconds: float) -> str:
    h = int(seconds // 3600)
    seconds -= h * 3600
    m = int(seconds // 60)
    seconds -= m * 60
    return f"{h:02d}:{m:02d}:{seconds:06.3f}"


def parse_time_range(value: str):
    times = TIME_RE.findall(str(value))
    if len(times) < 2:
        raise ValueError(f"Could not read start and end time: {value}")

    start = parse_time_to_seconds(times[0])
    end = parse_time_to_seconds(times[1])

    if end <= start:
        raise ValueError(f"End time must be after start time: {value}")

    return start, end, end - start


def safe_filename(text: str, max_len: int = 150) -> str:
    text = str(text).strip()
    text = re.sub(r'[<>:"/\\|?*\x00-\x1F]+', "_", text)
    text = re.sub(r"\s+", " ", text)
    text = text.strip(" ._")
    return (text or "clip")[:max_len]


def read_jobs(csv_path: Path):
    jobs = []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for index, row in enumerate(reader, start=1):
            clip_id = get_column(row, "ID", "No", "Serial") or str(index)
            title = get_column(row, "Final title", "Title", "Name") or f"Clip {index}"
            time_range = get_column(row, "Source time range", "Time range", "Range")

            if not time_range:
                raise ValueError(f"Row {index}: Source time range missing")

            start, end, duration = parse_time_range(time_range)

            jobs.append(
                {
                    "id": clip_id,
                    "title": title,
                    "time_range": time_range,
                    "start": start,
                    "end": end,
                    "duration": duration,
                }
            )

    if not jobs:
        raise ValueError("CSV has no valid rows")

    return jobs


def run_command(cmd):
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "FFmpeg command failed")


def detect_black_ranges(ffmpeg: str, input_video: Path, min_duration: float = 0.5):
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-i",
        str(input_video),
        "-vf",
        f"blackdetect=d={min_duration}:pix_th=0.10",
        "-an",
        "-f",
        "null",
        "-",
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Could not detect black ranges")

    jobs = []
    for index, match in enumerate(BLACK_RE.finditer(result.stderr), start=1):
        start = float(match.group("start"))
        end = float(match.group("end"))
        if end <= start:
            continue

        jobs.append(
            {
                "id": f"black_{index}",
                "title": f"Black screen {index}",
                "time_range": f"{seconds_to_time(start)} - {seconds_to_time(end)}",
                "start": start,
                "end": end,
                "duration": end - start,
            }
        )

    return jobs


def detect_silence_ranges(
    ffmpeg: str,
    ffprobe: str,
    input_video: Path,
    min_duration: float = 1.0,
    noise_level: str = "-35dB",
):
    if not has_audio(ffprobe, input_video):
        raise RuntimeError("This video has no audio stream, so silence cannot be detected.")

    cmd = [
        ffmpeg,
        "-hide_banner",
        "-i",
        str(input_video),
        "-af",
        f"silencedetect=noise={noise_level}:d={min_duration}",
        "-f",
        "null",
        "-",
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Could not detect silence ranges")

    jobs = []
    open_start = None

    for line in result.stderr.splitlines():
        start_match = SILENCE_START_RE.search(line)
        if start_match:
            open_start = float(start_match.group("start"))
            continue

        end_match = SILENCE_END_RE.search(line)
        if end_match and open_start is not None:
            end = float(end_match.group("end"))
            if end > open_start:
                index = len(jobs) + 1
                jobs.append(
                    {
                        "id": f"silence_{index}",
                        "title": f"Silence {index}",
                        "time_range": f"{seconds_to_time(open_start)} - {seconds_to_time(end)}",
                        "start": open_start,
                        "end": end,
                        "duration": end - open_start,
                    }
                )
            open_start = None

    return jobs


def merge_remove_jobs(jobs: list[dict], label: str = "Remove") -> list[dict]:
    ranges = sorted((job["start"], job["end"]) for job in jobs)
    merged = []

    for start, end in ranges:
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)

    remove_jobs = []
    for index, (start, end) in enumerate(merged, start=1):
        remove_jobs.append(
            {
                "id": f"{label.lower()}_{index}",
                "title": f"{label} {index}",
                "time_range": f"{seconds_to_time(start)} - {seconds_to_time(end)}",
                "start": start,
                "end": end,
                "duration": end - start,
            }
        )

    return remove_jobs


def has_audio(ffprobe: str, path: Path) -> bool:
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "default=nw=1:nk=1",
        str(path),
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    return bool(result.stdout.strip())


def get_duration(ffprobe: str, path: Path) -> float:
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nw=1:nk=1",
        str(path),
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"Could not read duration: {path}")

    return float(result.stdout.strip())


def parse_fps(value: str) -> float:
    if "/" in value:
        top, bottom = value.split("/", 1)
        bottom_value = float(bottom)
        if bottom_value:
            return float(top) / bottom_value
    return float(value)


def get_video_profile(ffprobe: str, path: Path) -> dict:
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate",
        "-of",
        "csv=p=0",
        str(path),
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"Could not read video profile: {path}")

    width, height, fps_text = result.stdout.strip().split(",")
    return {
        "width": int(width),
        "height": int(height),
        "fps": parse_fps(fps_text),
        "has_audio": has_audio(ffprobe, path),
    }


def render_standard_clip(
    ffmpeg: str,
    ffprobe: str,
    input_video: Path,
    output_video: Path,
    start: float,
    duration: float,
):
    start_time = seconds_to_time(start)
    duration_text = f"{duration:.3f}"

    if has_audio(ffprobe, input_video):
        cmd = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            start_time,
            "-i",
            str(input_video),
            "-t",
            duration_text,
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-vf",
            VF,
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output_video),
        ]
    else:
        cmd = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            start_time,
            "-i",
            str(input_video),
            "-f",
            "lavfi",
            "-t",
            duration_text,
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t",
            duration_text,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-vf",
            VF,
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_video),
        ]

    run_command(cmd)


def render_original_clip(
    ffmpeg: str,
    input_video: Path,
    output_video: Path,
    start: float,
    duration: float,
):
    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        seconds_to_time(start),
        "-i",
        str(input_video),
        "-t",
        f"{duration:.3f}",
        "-map",
        "0",
        "-c",
        "copy",
        "-avoid_negative_ts",
        "make_zero",
        str(output_video),
    ]

    run_command(cmd)


def render_standard_full(
    ffmpeg: str,
    ffprobe: str,
    input_video: Path,
    output_video: Path,
):
    if has_audio(ffprobe, input_video):
        cmd = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(input_video),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-vf",
            VF,
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output_video),
        ]
    else:
        duration_text = f"{get_duration(ffprobe, input_video):.3f}"

        cmd = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(input_video),
            "-f",
            "lavfi",
            "-t",
            duration_text,
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-vf",
            VF,
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_video),
        ]

    run_command(cmd)


def render_outro_like_source(
    ffmpeg: str,
    ffprobe: str,
    source_video: Path,
    outro_video: Path,
    output_video: Path,
):
    profile = get_video_profile(ffprobe, source_video)
    width = profile["width"]
    height = profile["height"]
    fps = f"{profile['fps']:.3f}"
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"setsar=1,format=yuv420p"
    )

    if profile["has_audio"]:
        if has_audio(ffprobe, outro_video):
            cmd = [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(outro_video),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0",
                "-vf",
                vf,
                "-r",
                fps,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-c:a",
                "aac",
                "-ar",
                "44100",
                "-ac",
                "2",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                str(output_video),
            ]
        else:
            duration_text = f"{get_duration(ffprobe, outro_video):.3f}"
            cmd = [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(outro_video),
                "-f",
                "lavfi",
                "-t",
                duration_text,
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-vf",
                vf,
                "-r",
                fps,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-c:a",
                "aac",
                "-ar",
                "44100",
                "-ac",
                "2",
                "-b:a",
                "192k",
                "-shortest",
                "-movflags",
                "+faststart",
                str(output_video),
            ]
    else:
        cmd = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(outro_video),
            "-map",
            "0:v:0",
            "-vf",
            vf,
            "-r",
            fps,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-movflags",
            "+faststart",
            str(output_video),
        ]

    run_command(cmd)


def concat_two_videos(ffmpeg: str, first: Path, second: Path, output: Path):
    list_file = output.with_suffix(".concat.txt")

    list_file.write_text(
        f"file '{first.resolve()}'\nfile '{second.resolve()}'\n",
        encoding="utf-8",
    )

    try:
        cmd = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(output),
        ]

        run_command(cmd)
    finally:
        list_file.unlink(missing_ok=True)


def concat_many_videos(ffmpeg: str, videos: list[Path], output: Path):
    list_file = output.with_suffix(".concat.txt")
    list_file.write_text(
        "".join(f"file '{video.resolve()}'\n" for video in videos),
        encoding="utf-8",
    )

    try:
        cmd = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(output),
        ]

        run_command(cmd)
    finally:
        list_file.unlink(missing_ok=True)


def build_keep_ranges(remove_jobs: list[dict], source_duration: float):
    remove_ranges = sorted((job["start"], job["end"]) for job in remove_jobs)
    keep_ranges = []
    cursor = 0.0

    for start, end in remove_ranges:
        start = max(0.0, min(start, source_duration))
        end = max(0.0, min(end, source_duration))

        if end <= cursor:
            continue

        if start > cursor:
            keep_ranges.append((cursor, start, start - cursor))

        cursor = max(cursor, end)

    if cursor < source_duration:
        keep_ranges.append((cursor, source_duration, source_duration - cursor))

    return [item for item in keep_ranges if item[2] > 0.05]


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
        self.csv_path = Path(csv_path)
        self.video_path = Path(video_path)
        self.outro_path = Path(outro_path) if outro_path else None
        self.output_dir = Path(output_dir)
        self.normalize_output = normalize_output
        self.work_mode = work_mode

    def run(self):
        try:
            ffmpeg = shutil.which("ffmpeg")
            ffprobe = shutil.which("ffprobe")

            if not ffmpeg or not ffprobe:
                raise RuntimeError("ffmpeg/ffprobe not found. Please install FFmpeg first.")

            if self.work_mode == "auto_black":
                self.log.emit("Detecting black screen ranges automatically...")
                jobs = detect_black_ranges(ffmpeg, self.video_path)
                if not jobs:
                    raise RuntimeError("No black screen ranges found in the video.")
                self.log.emit(f"Detected {len(jobs)} black screen ranges.")
            elif self.work_mode == "auto_silence":
                self.log.emit("Detecting silent ranges automatically...")
                jobs = detect_silence_ranges(ffmpeg, ffprobe, self.video_path)
                if not jobs:
                    raise RuntimeError("No silent ranges found in the video.")
                self.log.emit(f"Detected {len(jobs)} silent ranges.")
            elif self.work_mode == "auto_black_silence":
                self.log.emit("Detecting black screen and silent ranges automatically...")
                black_jobs = detect_black_ranges(ffmpeg, self.video_path)
                silence_jobs = detect_silence_ranges(ffmpeg, ffprobe, self.video_path)
                jobs = merge_remove_jobs(black_jobs + silence_jobs, "Auto remove")
                if not jobs:
                    raise RuntimeError("No black screen or silent ranges found in the video.")
                self.log.emit(
                    f"Detected {len(black_jobs)} black ranges and {len(silence_jobs)} silent ranges."
                )
                self.log.emit(f"Merged into {len(jobs)} remove ranges.")
            else:
                jobs = read_jobs(self.csv_path)

            self.output_dir.mkdir(parents=True, exist_ok=True)

            self.log.emit(f"Agent found {len(jobs)} clips in CSV.")
            if self.normalize_output:
                self.log.emit("Output format: 1920x1080, 30fps, H.264 + AAC")
            else:
                self.log.emit("Output format: original video/audio streams")

            with tempfile.TemporaryDirectory(prefix="video_agent_") as temp_name:
                temp_dir = Path(temp_name)
                outro_video = None

                if self.normalize_output and self.outro_path and self.outro_path.exists():
                    self.log.emit("Preparing outro video once...")
                    outro_video = temp_dir / "outro_standard.mp4"
                    render_standard_full(ffmpeg, ffprobe, self.outro_path, outro_video)
                    self.log.emit("Outro ready.")
                elif self.outro_path and self.outro_path.exists():
                    self.log.emit("Preparing outro video to match original main video...")
                    outro_video = temp_dir / f"outro_original_match{self.video_path.suffix or '.mp4'}"
                    render_outro_like_source(
                        ffmpeg,
                        ffprobe,
                        self.video_path,
                        self.outro_path,
                        outro_video,
                    )
                    self.log.emit("Outro matched to original video profile.")

                success = 0

                if self.work_mode in (
                    "remove_ranges",
                    "auto_black",
                    "auto_silence",
                    "auto_black_silence",
                ):
                    source_duration = get_duration(ffprobe, self.video_path)
                    keep_ranges = build_keep_ranges(jobs, source_duration)

                    if not keep_ranges:
                        raise RuntimeError("CSV ranges remove korar por kono video part baki thakbe na.")

                    output_suffix = ".mp4" if self.normalize_output else self.video_path.suffix
                    final_path = self.output_dir / f"polished_{safe_filename(self.video_path.stem)}{output_suffix or '.mp4'}"
                    concat_parts = []

                    if self.work_mode == "auto_black":
                        self.log.emit(f"Auto black mode: cutting out {len(jobs)} black ranges.")
                    elif self.work_mode == "auto_silence":
                        self.log.emit(f"Auto silence mode: cutting out {len(jobs)} silent ranges.")
                    elif self.work_mode == "auto_black_silence":
                        self.log.emit(f"Auto polish mode: cutting out {len(jobs)} merged ranges.")
                    else:
                        self.log.emit(f"Remove mode: cutting out {len(jobs)} ranges.")
                    self.log.emit(f"Keeping {len(keep_ranges)} remaining video parts.")

                    for i, (start, _end, duration) in enumerate(keep_ranges, start=1):
                        temp_clip = temp_dir / f"keep_{i:04d}{output_suffix or '.mp4'}"
                        self.log.emit(f"[{i}/{len(keep_ranges)}] Keeping: {seconds_to_time(start)} for {duration:.3f}s")

                        if self.normalize_output:
                            render_standard_clip(
                                ffmpeg,
                                ffprobe,
                                self.video_path,
                                temp_clip,
                                start,
                                duration,
                            )
                        else:
                            render_original_clip(
                                ffmpeg,
                                self.video_path,
                                temp_clip,
                                start,
                                duration,
                            )

                        concat_parts.append(temp_clip)
                        self.progress.emit(i, len(keep_ranges))

                    if outro_video:
                        concat_parts.append(outro_video)

                    concat_many_videos(ffmpeg, concat_parts, final_path)
                    self.log.emit(f"Saved: {final_path.name}")
                    self.finished_ok.emit(f"Done. Created polished video:\n{final_path}")
                    return

                for i, job in enumerate(jobs, start=1):
                    base = safe_filename(f"{job['id']}_{job['title']}")
                    output_suffix = ".mp4" if self.normalize_output else self.video_path.suffix
                    final_path = self.output_dir / f"{base}{output_suffix or '.mp4'}"
                    temp_clip = temp_dir / f"clip_{i:04d}{output_suffix or '.mp4'}"

                    self.log.emit(f"[{i}/{len(jobs)}] Cutting: {job['title']}")

                    if self.normalize_output:
                        render_standard_clip(
                            ffmpeg,
                            ffprobe,
                            self.video_path,
                            temp_clip,
                            job["start"],
                            job["duration"],
                        )
                    else:
                        render_original_clip(
                            ffmpeg,
                            self.video_path,
                            temp_clip,
                            job["start"],
                            job["duration"],
                        )

                    if outro_video:
                        concat_two_videos(ffmpeg, temp_clip, outro_video, final_path)
                    else:
                        shutil.move(str(temp_clip), str(final_path))

                    success += 1
                    self.progress.emit(i, len(jobs))
                    self.log.emit(f"Saved: {final_path.name}")

            self.finished_ok.emit(f"Done. Created {success} videos in:\n{self.output_dir}")

        except Exception as e:
            self.failed.emit(str(e))


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
