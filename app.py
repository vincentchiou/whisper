from __future__ import annotations

import gc
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import unicodedata
import uuid
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_file


# 中文註解：專案根目錄與暫存資料夾。
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
INDEX_FILE = BASE_DIR / "index.html"
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {"mp3", "mp4", "wav", "m4a", "ogg", "webm"}
MAX_CONTENT_LENGTH = 500 * 1024 * 1024
PYTORCH_WINDOWS_PYTHON_MIN = (3, 9)
PYTORCH_WINDOWS_PYTHON_MAX = (3, 12)
PYTORCH_PIP_PACKAGES = {"openai-whisper", "whisper", "torch", "torchvision", "torchaudio"}
DEFAULT_INSTALL_PACKAGES = ["flask", "openai-whisper", "yt-dlp"]
CUDA_INDEX_CU121 = "https://download.pytorch.org/whl/cu121"
CUDA_INDEX_CU128 = "https://download.pytorch.org/whl/cu128"

app = Flask(__name__, static_folder=".", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH


@dataclass
class JobState:
    status: str
    filename: str
    file_path: str | None = None
    source_type: str = "upload"
    source_url: str | None = None
    original_title: str | None = None
    srt: str | None = None
    transcript_text: str | None = None
    seo_text: str | None = None
    segment_count: int = 0
    error_msg: str | None = None


@dataclass
class InstallJobState:
    status: str = "running"
    lines: list[str] = field(default_factory=list)


jobs: dict[str, JobState] = {}
jobs_lock = threading.Lock()

install_jobs: dict[str, InstallJobState] = {}
install_lock = threading.Lock()

_whisper_model = None
_model_lock = threading.Lock()
DEVICE = "cpu"
USE_FP16 = False


def python_version_text() -> str:
    return ".".join(str(part) for part in sys.version_info[:3])


def is_pytorch_python_supported() -> bool:
    major_minor = sys.version_info[:2]
    if os.name == "nt":
        return PYTORCH_WINDOWS_PYTHON_MIN <= major_minor <= PYTORCH_WINDOWS_PYTHON_MAX
    return major_minor >= PYTORCH_WINDOWS_PYTHON_MIN


def python_support_blocker() -> str | None:
    if is_pytorch_python_supported():
        return None

    if os.name == "nt":
        return (
            f"目前使用 Python {python_version_text()}。Windows 版 PyTorch 官方 wheel 支援 Python 3.9～3.12，"
            "建議改用 Python 3.11 或 3.12 後重新執行 start.bat。"
        )

    return f"目前使用 Python {python_version_text()}，請改用 Python 3.9 以上。"


def package_base_name(package: str) -> str:
    name = str(package).strip().lower().replace("_", "-")
    name = name.split("[", 1)[0]
    for separator in ("==", ">=", "<=", "~=", "!=", ">", "<"):
        name = name.split(separator, 1)[0]
    return name.strip()


def packages_need_pytorch(packages: list[str]) -> bool:
    return any(package_base_name(item) in PYTORCH_PIP_PACKAGES for item in packages)


def version_tuple(version: str | None) -> tuple[int, int]:
    parts: list[int] = []
    for chunk in str(version or "").split("."):
        if not chunk.isdigit():
            break
        parts.append(int(chunk))
        if len(parts) == 2:
            break
    while len(parts) < 2:
        parts.append(0)
    return parts[0], parts[1]


def capability_text(capability: tuple[int, int] | None) -> str:
    if not capability:
        return "未知"
    return f"sm_{capability[0]}{capability[1]}"


def looks_like_rtx50(gpu_name: str | None) -> bool:
    text = str(gpu_name or "").upper().replace(" ", "")
    return any(token in text for token in ("RTX50", "RTX5060", "RTX5070", "RTX5080", "RTX5090"))


def recommend_cuda_index(
    capability: tuple[int, int] | None = None,
    nvcc_version: str | None = None,
    gpu_name: str | None = None,
) -> str:
    if (capability and capability >= (12, 0)) or looks_like_rtx50(gpu_name):
        return CUDA_INDEX_CU128
    if str(nvcc_version or "").startswith("11.8"):
        return "https://download.pytorch.org/whl/cu118"
    if str(nvcc_version or "").startswith("11"):
        return "https://download.pytorch.org/whl/cu117"
    return CUDA_INDEX_CU121


def ffmpeg_candidates() -> list[str]:
    candidates = [
        r"C:\ffmpeg\bin",
        r"C:\Program Files\ffmpeg\bin",
    ]
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        for app_name in ("CapCut", "JianyingPro"):
            app_root = Path(local_app_data) / app_name / "Apps"
            if app_root.is_dir():
                for version_dir in sorted(app_root.iterdir(), reverse=True):
                    if version_dir.is_dir():
                        candidates.append(str(version_dir))
    return candidates


def setup_ffmpeg() -> None:
    if shutil.which("ffmpeg"):
        return

    for candidate in ffmpeg_candidates():
        if (Path(candidate) / "ffmpeg.exe").is_file():
            os.environ["PATH"] = candidate + os.pathsep + os.environ.get("PATH", "")
            print(f"[ffmpeg] 使用路徑：{candidate}")
            return

    print("[ffmpeg] 找不到 ffmpeg，轉錄或 YouTube 抽音時可能失敗。")


def detect_device() -> tuple[str, bool]:
    try:
        import torch

        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            total = torch.cuda.get_device_properties(0).total_memory / 1024**3
            print(f"[GPU] 偵測到 {gpu_name}，VRAM {total:.1f} GB，預設使用 GPU。")
            return "cuda", True
    except Exception as exc:
        print(f"[GPU] 偵測 CUDA 失敗：{exc}")

    print("[CPU] 未偵測到可用 GPU，改用 CPU。")
    return "cpu", False


def inspect_torch_cuda(test_tensor: bool = True) -> dict[str, Any]:
    info: dict[str, Any] = {
        "torch_installed": False,
        "torch_version": None,
        "torch_cuda": None,
        "cuda_available": False,
        "cuda_usable": False,
        "gpu_name": None,
        "gpu_count": 0,
        "capability": None,
        "cuda_issue": None,
        "cuda_warnings": [],
    }

    try:
        import torch
    except ImportError:
        info["cuda_issue"] = "尚未安裝 PyTorch。"
        return info

    info["torch_installed"] = True
    info["torch_version"] = getattr(torch, "__version__", None)
    info["torch_cuda"] = getattr(torch.version, "cuda", None)
    info["cuda_available"] = torch.cuda.is_available()

    if not torch.cuda.is_available():
        info["cuda_issue"] = "PyTorch 目前偵測不到可用 CUDA。"
        return info

    try:
        props = torch.cuda.get_device_properties(0)
        capability = torch.cuda.get_device_capability(0)
        info["gpu_name"] = props.name
        info["gpu_count"] = torch.cuda.device_count()
        info["capability"] = capability

        runtime_version = version_tuple(info["torch_cuda"])
        if capability >= (12, 0) and runtime_version < (12, 8):
            info["cuda_issue"] = (
                f"{info['gpu_name']} 是 {capability_text(capability)}，需要 CUDA 12.8 版 PyTorch；"
                f"目前安裝的是 CUDA {info['torch_cuda'] or '未知'}。"
            )
            return info

        if test_tensor:
            torch.empty(1, device="cuda")
            torch.cuda.synchronize()

        info["cuda_usable"] = True
    except Exception as exc:
        info["cuda_issue"] = f"CUDA 偵測失敗：{exc}"

    return info


def get_whisper_model():
    global _whisper_model
    with _model_lock:
        if _whisper_model is None:
            import whisper

            print(f"[Whisper] 載入 medium 模型（device={DEVICE}）...")
            _whisper_model = whisper.load_model("medium", device=DEVICE)
            print("[Whisper] 模型載入完成。")
    return _whisper_model


def fmt_time(seconds: float) -> str:
    milliseconds = int(round((seconds % 1) * 1000))
    whole = int(seconds)
    sec = whole % 60
    minute = (whole // 60) % 60
    hour = whole // 3600
    return f"{hour:02d}:{minute:02d}:{sec:02d},{milliseconds:03d}"


def format_hms(seconds: float) -> str:
    whole = max(0, int(seconds))
    sec = whole % 60
    minute = (whole // 60) % 60
    hour = whole // 3600
    if hour > 0:
        return f"{hour:02d}:{minute:02d}:{sec:02d}"
    return f"{minute:02d}:{sec:02d}"


def merge_segments(segments: list[dict[str, Any]], mode: str = "standard") -> list[dict[str, Any]]:
    if mode == "fine" or not segments:
        return segments

    if mode == "coarse":
        max_chars, max_sec, max_gap = 70, 10.0, 2.0
    else:
        max_chars, max_sec, max_gap = 40, 6.0, 1.5

    break_punct = {"。", "！", "？", ".", "!", "?", "，", ","}
    merged: list[dict[str, Any]] = []
    current = {
        "start": segments[0]["start"],
        "end": segments[0]["end"],
        "text": str(segments[0]["text"]).strip(),
    }

    for segment in segments[1:]:
        text = str(segment["text"]).strip()
        if not text:
            continue

        gap = float(segment["start"]) - float(current["end"])
        combined = (str(current["text"]) + " " + text).strip()
        combined_duration = float(segment["end"]) - float(current["start"])
        ends_break = bool(current["text"]) and str(current["text"])[-1] in break_punct

        can_merge = (
            gap <= max_gap
            and len(combined) <= max_chars
            and combined_duration <= max_sec
            and not ends_break
        )

        if can_merge:
            current["text"] = combined
            current["end"] = segment["end"]
        else:
            merged.append(current)
            current = {"start": segment["start"], "end": segment["end"], "text": text}

    merged.append(current)
    return merged


def segments_to_srt(segments: list[dict[str, Any]], mode: str = "standard") -> str:
    merged = merge_segments(segments, mode)
    blocks: list[str] = []
    for index, segment in enumerate(merged, start=1):
        text = str(segment["text"]).strip()
        if not text:
            continue
        blocks.append(
            f"{index}\n"
            f"{fmt_time(float(segment['start']))} --> {fmt_time(float(segment['end']))}\n"
            f"{text}\n"
        )
    return "\n".join(blocks)


def clean_spacing(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    text = re.sub(r"\s+([，。！？；：,.!?;:])", r"\1", text)
    return text


def clean_transcript_text(text: str) -> str:
    cleaned = normalize_text(text)
    cleaned = clean_spacing(cleaned)

    glossary_patterns = [
        (r"\bopen[\s.-]*ai\b", "OpenAI"),
        (r"\bchat[\s.-]*gpt\b", "ChatGPT"),
        (r"\bwhisper\b", "Whisper"),
        (r"\byou[\s.-]*tube\b", "YouTube"),
        (r"\byt[\s.-]*dlp\b", "yt-dlp"),
        (r"\bseo\b", "SEO"),
        (r"\bgpu\b", "GPU"),
        (r"\bcuda\b", "CUDA"),
        (r"\bnvidia\b", "NVIDIA"),
        (r"\bpy[\s.-]*torch\b", "PyTorch"),
        (r"\bapi\b", "API"),
        (r"\bllm\b", "LLM"),
        (r"\ba[\s.-]*i\b", "AI"),
    ]

    for pattern, replacement in glossary_patterns:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

    replacements = {
        "秋文盛": "邱文盛",
        "邱文勝": "邱文盛",
        "邱文圣": "邱文盛",
        "邱文聖": "邱文盛",
        "丘文盛": "邱文盛",
        "秋文勝": "邱文盛",
        "秋文圣": "邱文盛",
        "秋文聖": "邱文盛",
    }

    for wrong, correct in replacements.items():
        pattern = re.compile(re.escape(wrong), re.IGNORECASE)
        cleaned = pattern.sub(correct, cleaned)

    cleaned = re.sub(r"(嗯|呃|這個|那個)(\s+\1){1,}", r"\1", cleaned)
    cleaned = re.sub(r"([，。！？,.!?])\1+", r"\1", cleaned)
    cleaned = re.sub(r"\b([A-Z])\s+([A-Z])\b", r"\1\2", cleaned)
    return cleaned.strip()


def clean_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned_segments: list[dict[str, Any]] = []
    for segment in segments:
        cleaned_segments.append(
            {
                "start": float(segment["start"]),
                "end": float(segment["end"]),
                "text": clean_transcript_text(segment.get("text", "")),
            }
        )
    return cleaned_segments


def sentence_split(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?])\s+|[\r\n]+", text)
    return [part.strip() for part in parts if part and part.strip()]


def segments_to_transcript_text(segments: list[dict[str, Any]], mode: str = "standard") -> str:
    merged = merge_segments(segments, mode)
    if not merged:
        return ""

    paragraphs: list[str] = []
    current_lines: list[str] = []
    current_chars = 0
    paragraph_start = float(merged[0]["start"])

    for segment in merged:
        text = str(segment["text"]).strip()
        if not text:
            continue

        duration = float(segment["end"]) - paragraph_start
        current_lines.append(text)
        current_chars += len(text)

        should_break = (
            current_chars >= 120
            or duration >= 45
            or text.endswith(("。", "！", "？", ".", "!", "?"))
        )

        if should_break:
            paragraphs.append(clean_transcript_text(" ".join(current_lines).strip()))
            current_lines = []
            current_chars = 0
            paragraph_start = float(segment["end"])

    if current_lines:
        paragraphs.append(clean_transcript_text(" ".join(current_lines).strip()))

    return "\n\n".join(paragraphs)


def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKC", str(text or "")).strip()


def filename_safe(text: str) -> str:
    safe = re.sub(r'[\\/:*?"<>|]+', "_", normalize_text(text))
    safe = re.sub(r"\s+", " ", safe).strip(" ._")
    return safe or "transcript"


def is_youtube_url(url: str) -> bool:
    text = normalize_text(url).lower()
    return "youtube.com/" in text or "youtu.be/" in text


def import_yt_dlp():
    import yt_dlp  # type: ignore

    return yt_dlp


def download_youtube_media(job_id: str, youtube_url: str) -> tuple[str, str]:
    yt_dlp = import_yt_dlp()

    output_template = str(UPLOAD_DIR / f"{job_id}.%(ext)s")
    options = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": False,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(youtube_url, download=True)
        if info is None:
            raise RuntimeError("無法取得 YouTube 影片資訊。")

        requested = info.get("requested_downloads") or []
        file_path = None
        if requested:
            file_path = requested[0].get("filepath")
        if not file_path:
            file_path = ydl.prepare_filename(info)
        if not file_path or not os.path.exists(file_path):
            raise RuntimeError("YouTube 影片下載完成，但找不到媒體檔案。")

        title = normalize_text(info.get("title") or "YouTube影片")
        return file_path, title


def extract_candidate_phrases(text: str) -> list[str]:
    normalized = normalize_text(text)
    ascii_words = re.findall(r"[A-Za-z0-9][A-Za-z0-9+#&._-]{1,24}", normalized)
    chinese_chunks = re.findall(r"[\u4e00-\u9fff]{2,12}", normalized)

    candidates: list[str] = []
    stop_words = {
        "我們", "你們", "這個", "那個", "以及", "因為", "如果", "所以", "可以", "影片", "內容", "今天",
        "the", "and", "that", "this", "with", "from", "have", "your", "just", "really",
        "about", "there", "here", "what", "when", "then", "into", "they", "them", "guys",
        "alright", "okay", "cool", "pretty", "stuff", "thing",
    }
    for chunk in ascii_words + chinese_chunks:
        chunk = chunk.strip().strip(".,!?;:()[]{}\"'")
        if len(chunk) < 2 or chunk.lower() in stop_words or chunk in stop_words:
            continue
        candidates.append(chunk)
    return candidates


def top_keywords(text: str, seed_title: str = "", limit: int = 10) -> list[str]:
    frequency: dict[str, int] = {}
    for phrase in extract_candidate_phrases(seed_title + "\n" + text):
        frequency[phrase] = frequency.get(phrase, 0) + 1

    sorted_items = sorted(
        frequency.items(),
        key=lambda item: (-item[1], -len(item[0]), item[0]),
    )

    keywords: list[str] = []
    for phrase, _count in sorted_items:
        if any(phrase in existing or existing in phrase for existing in keywords):
            continue
        keywords.append(phrase)
        if len(keywords) >= limit:
            break

    return keywords


def summarize_chapter_text(text: str, fallback: str) -> str:
    cleaned = clean_transcript_text(text)
    keywords = top_keywords(cleaned, "", limit=5)
    chinese_keywords = [item for item in keywords if re.search(r"[\u4e00-\u9fff]", item)]
    english_keywords = [item for item in keywords if re.search(r"[A-Za-z]", item)]

    if len(chinese_keywords) >= 3:
        candidate = f"聚焦{chinese_keywords[0]}、{chinese_keywords[1]}與{chinese_keywords[2]}"
    elif len(chinese_keywords) == 2:
        candidate = f"說明{chinese_keywords[0]}與{chinese_keywords[1]}"
    elif len(chinese_keywords) == 1 and len(english_keywords) >= 1:
        candidate = f"整理{chinese_keywords[0]}與{english_keywords[0]}"
    elif len(english_keywords) >= 3:
        candidate = "重點涵蓋" + "、".join(english_keywords[:3])
    elif len(english_keywords) == 2:
        candidate = "說明" + "與".join(english_keywords[:2])
    elif keywords:
        candidate = "重點：" + "、".join(keywords[:3])
    else:
        candidate = fallback

    candidate = candidate.strip("，。！？,.!? ")
    if len(candidate) > 32:
        candidate = candidate[:32].rstrip("，。！？,.!? ") + "…"
    return candidate or fallback


def build_chapters(segments: list[dict[str, Any]], seed_title: str) -> list[tuple[str, str]]:
    if not segments:
        return [("00:00", "影片開始")]

    duration = float(segments[-1]["end"])
    target_count = max(3, min(8, math.ceil(duration / 180) + 1))
    chunk_size = max(1, math.ceil(len(segments) / target_count))
    chapters: list[tuple[str, str]] = []

    for index in range(0, len(segments), chunk_size):
        chunk = segments[index:index + chunk_size]
        if not chunk:
            continue

        start = float(chunk[0]["start"])
        if chapters and start - _chapter_seconds(chapters[-1][0]) < 10:
            continue

        chunk_text = " ".join(str(item["text"]).strip() for item in chunk if str(item["text"]).strip())
        title = summarize_chapter_text(chunk_text, f"重點段落 {len(chapters) + 1}")
        chapters.append((format_hms(start), title))

    if not chapters or chapters[0][0] != "00:00":
        chapters.insert(0, ("00:00", "影片開始"))

    while len(chapters) < 3 and len(chapters) < len(segments):
        candidate_index = min(len(segments) - 1, len(chapters) * max(1, len(segments) // 3))
        start = float(segments[candidate_index]["start"])
        title = summarize_chapter_text(str(segments[candidate_index]["text"]), f"章節 {len(chapters) + 1}")
        chapters.append((format_hms(start), title))

    unique: list[tuple[str, str]] = []
    seen_times: set[str] = set()
    for timestamp, title in chapters:
        if timestamp in seen_times:
            continue
        seen_times.add(timestamp)
        unique.append((timestamp, title))

    return unique[:8]


def _chapter_seconds(timestamp: str) -> int:
    parts = [int(item) for item in timestamp.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 0


def build_summary_and_hook(transcript_text: str) -> tuple[str, str]:
    paragraphs = [item.strip() for item in transcript_text.split("\n\n") if item.strip()]
    if not paragraphs:
        return "這支影片主要分享實際內容與重點觀點，適合整理成可搜尋、可快速理解的 YouTube 說明。", "先看前兩句，就能快速知道這支影片最值得注意的重點。"

    has_chinese = bool(re.search(r"[\u4e00-\u9fff]", transcript_text))
    keywords = top_keywords(transcript_text, "", limit=5)

    if not has_chinese and keywords:
        keyword_text = "、".join(keywords[:3])
        summary = f"這段內容主要圍繞 {keyword_text} 等重點展開，適合整理成容易搜尋與理解的影片說明。"
        hook = f"影片一開始就帶出 {keyword_text} 等核心內容，適合作為吸引觀眾繼續看下去的開場鉤子。"
        return summary, hook

    summary_sentences: list[str] = []
    for paragraph in paragraphs[:2]:
        summary_sentences.extend(sentence_split(paragraph)[:2])

    summary = " ".join(summary_sentences[:3]).strip()
    if not summary:
        summary = paragraphs[0][:180]

    hook_source = sentence_split(paragraphs[0])
    hook_text = hook_source[0] if hook_source else paragraphs[0][:80]
    hook = f"你會在這支影片裡快速掌握：{hook_text}"
    return summary, hook


def build_title_suggestions(base_title: str, keywords: list[str]) -> list[str]:
    cleaned_title = normalize_text(base_title) or "這支影片"
    top = keywords[:4]
    key_a = top[0] if len(top) > 0 else cleaned_title
    key_b = top[1] if len(top) > 1 else "完整重點"
    key_c = top[2] if len(top) > 2 else "實用整理"

    suggestions = [
        f"{cleaned_title}｜{key_a}重點一次看懂",
        f"{key_a}怎麼做？{cleaned_title}完整整理與重點摘要",
        f"{cleaned_title}｜{key_b}、{key_c}與章節懶人包",
    ]

    unique: list[str] = []
    for item in suggestions:
        if item not in unique:
            unique.append(item)
    return unique


def build_seo_text(
    transcript_text: str,
    segments: list[dict[str, Any]],
    base_title: str,
    source_url: str | None = None,
) -> str:
    keywords = top_keywords(transcript_text, base_title, limit=12)
    title_suggestions = build_title_suggestions(base_title, keywords)
    summary, hook = build_summary_and_hook(transcript_text)
    chapters = build_chapters(segments, base_title)
    hashtag_keywords = [keyword.replace(" ", "") for keyword in keywords[:8]]

    description_block = "\n".join(
        [
            summary,
            "",
            hook,
        ]
    ).strip()

    lines = [
        "YouTube SEO 建議內容",
        "====================",
        "",
        "一、建議標題（3個）",
        *[f"{index}. {title}" for index, title in enumerate(title_suggestions, start=1)],
        "",
        "二、內容摘要與鉤子",
        f"摘要：{summary}",
        f"鉤子：{hook}",
        "",
        "三、建議說明區文字",
        description_block,
        "",
        "四、章節目錄",
        *[f"{timestamp} {title}" for timestamp, title in chapters],
        "",
        "五、內容關鍵字",
        "、".join(keywords[:10]) if keywords else "Whisper、字幕轉錄、YouTube",
        "",
        "六、建議標籤 / Hashtags",
        " ".join(f"#{item}" for item in hashtag_keywords) if hashtag_keywords else "#Whisper #字幕 #YouTube",
    ]

    if source_url:
        lines.extend(["", f"原始影片網址：{source_url}"])

    return "\n".join(lines).strip() + "\n"


def probe_media_duration(file_path: str) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                file_path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return None


def split_media_for_transcription(file_path: str, segment_seconds: int = 1200) -> tuple[list[tuple[str, float]], Path]:
    temp_dir = UPLOAD_DIR / f"{Path(file_path).stem}_chunks"
    temp_dir.mkdir(exist_ok=True)
    output_pattern = str(temp_dir / "chunk_%03d.wav")

    command = [
        shutil.which("ffmpeg") or "ffmpeg",
        "-y",
        "-i",
        file_path,
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "segment",
        "-segment_time",
        str(segment_seconds),
        "-reset_timestamps",
        "1",
        output_pattern,
    ]

    subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )

    chunk_files = sorted(temp_dir.glob("chunk_*.wav"))
    if not chunk_files:
        raise RuntimeError("音訊分段失敗，找不到可供轉錄的片段。")

    chunks: list[tuple[str, float]] = []
    offset = 0.0
    for chunk_path in chunk_files:
        chunks.append((str(chunk_path), offset))
        duration = probe_media_duration(str(chunk_path))
        offset += duration if duration else float(segment_seconds)
    return chunks, temp_dir


def transcribe_media_in_chunks(model: Any, file_path: str) -> list[dict[str, Any]]:
    chunks, temp_dir = split_media_for_transcription(file_path)
    combined_segments: list[dict[str, Any]] = []

    try:
        for chunk_path, offset in chunks:
            result = model.transcribe(
                chunk_path,
                language=None,
                task="transcribe",
                fp16=USE_FP16,
                verbose=False,
            )
            for segment in result.get("segments", []):
                combined_segments.append(
                    {
                        "start": float(segment["start"]) + offset,
                        "end": float(segment["end"]) + offset,
                        "text": segment.get("text", ""),
                    }
                )
    finally:
        for chunk_path, _offset in chunks:
            try:
                if os.path.exists(chunk_path):
                    os.remove(chunk_path)
            except OSError:
                pass
        try:
            temp_dir.rmdir()
        except OSError:
            pass


def append_install_line(install_id: str, line: str) -> None:
    with install_lock:
        install_jobs[install_id].lines.append(line)


def set_install_status(install_id: str, status: str, message: str | None = None) -> None:
    with install_lock:
        install_jobs[install_id].status = status
        if message:
            install_jobs[install_id].lines.append("")
            install_jobs[install_id].lines.append(message)


def run_install_command(
    install_id: str,
    command: list[str],
    success_message: str,
    finish_success: bool = True,
) -> bool:
    append_install_line(install_id, f">>> {' '.join(command)}")
    append_install_line(install_id, "安裝中，首次下載可能需要一段時間，請耐心等待。")
    append_install_line(install_id, "")

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.rstrip()
            if line:
                append_install_line(install_id, line)

        process.wait()
        if process.returncode == 0:
            if finish_success:
                set_install_status(install_id, "done", success_message)
            return True

        set_install_status(install_id, "error", f"安裝失敗，錯誤代碼：{process.returncode}")
        return False
    except Exception as exc:
        set_install_status(install_id, "error", f"安裝時發生例外：{exc}")
        return False


def run_cuda_torch_install(install_id: str, command: list[str]) -> None:
    if not run_install_command(install_id, command, "CUDA 版 PyTorch 安裝完成，請重新啟動 start.bat。", False):
        return

    append_install_line(install_id, "")
    append_install_line(install_id, "正在確認 PyTorch CUDA 狀態...")
    verify_command = [
        sys.executable,
        "-c",
        (
            "import torch; "
            "print('PyTorch 版本：' + str(torch.__version__)); "
            "print('PyTorch 內建 CUDA：' + str(torch.version.cuda)); "
            "print('CUDA 可用：' + str(torch.cuda.is_available())); "
            "cc=torch.cuda.get_device_capability(0) if torch.cuda.is_available() else (0,0); "
            "print('顯卡架構：sm_%d%d' % cc); "
            "cv=tuple(int(x) for x in (torch.version.cuda or '0.0').split('.')[:2]); "
            "ok=torch.cuda.is_available() and not (cc >= (12,0) and cv < (12,8)); "
            "torch.empty(1, device='cuda') if ok else None; "
            "torch.cuda.synchronize() if ok else None; "
            "raise SystemExit(0 if ok else 2)"
        ),
    ]

    try:
        verifier = subprocess.run(
            verify_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if verifier.stdout:
            for raw_line in verifier.stdout.splitlines():
                if raw_line.strip():
                    append_install_line(install_id, raw_line.strip())

        if verifier.returncode != 0:
            set_install_status(
                install_id,
                "error",
                "PyTorch 已安裝，但 CUDA 測試未通過。RTX 50 系列請安裝 CUDA 12.8 版 PyTorch；若仍失敗，請更新 NVIDIA 驅動或先改用 CPU。",
            )
            return
    except Exception as exc:
        set_install_status(install_id, "error", f"CUDA 驗證時發生例外：{exc}")
        return

    set_install_status(install_id, "done", "CUDA 版 PyTorch 安裝工作完成，請重新啟動 start.bat。")


def build_job_outputs(
    filename: str,
    source_type: str,
    source_url: str | None,
    original_title: str | None,
    segments: list[dict[str, Any]],
    seg_mode: str,
) -> tuple[str, str, str]:
    cleaned_segments = clean_segments(segments)
    srt_content = segments_to_srt(cleaned_segments, seg_mode)
    transcript_text = segments_to_transcript_text(cleaned_segments, seg_mode)
    base_title = original_title or Path(filename).stem
    seo_text = build_seo_text(transcript_text, merge_segments(cleaned_segments, seg_mode), base_title, source_url)
    return srt_content, transcript_text, seo_text


def run_whisper(job_id: str, file_path: str, seg_mode: str) -> None:
    try:
        with jobs_lock:
            current = jobs.get(job_id)
            if not current or current.status == "cancelled":
                return
            source_type = current.source_type
            source_url = current.source_url
            original_title = current.original_title
            filename = current.filename

        model = get_whisper_model()
        print(f"[Job {job_id[:8]}] 開始轉錄：{file_path}")
        duration = probe_media_duration(file_path) or 0.0
        if duration >= 1200:
            print(f"[Job {job_id[:8]}] 偵測到長影音，改用分段轉錄流程（約 {int(duration)} 秒）。")
            segments = transcribe_media_in_chunks(model, file_path)
        else:
            result = model.transcribe(
                file_path,
                language=None,
                task="transcribe",
                fp16=USE_FP16,
                verbose=False,
            )
            segments = result.get("segments", [])
        srt_content, transcript_text, seo_text = build_job_outputs(
            filename=filename,
            source_type=source_type,
            source_url=source_url,
            original_title=original_title,
            segments=segments,
            seg_mode=seg_mode,
        )

        with jobs_lock:
            current = jobs.get(job_id)
            if current and current.status != "cancelled":
                current.status = "done"
                current.srt = srt_content
                current.transcript_text = transcript_text
                current.seo_text = seo_text
                current.segment_count = len(segments)

        print(f"[Job {job_id[:8]}] 轉錄完成。")
    except Exception as exc:
        with jobs_lock:
            current = jobs.get(job_id)
            if current:
                current.status = "error"
                current.error_msg = str(exc)
        print(f"[Job {job_id[:8]}] 轉錄失敗：{exc}")
    finally:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except OSError:
            pass


def find_python_for_frontend() -> str:
    return sys.executable


def build_env_check() -> dict[str, Any]:
    python_blocker = python_support_blocker()
    results: dict[str, Any] = {
        "python": {
            "ok": python_blocker is None,
            "label": "Python",
            "version": sys.version.split()[0],
            "note": find_python_for_frontend() if python_blocker is None else f"{find_python_for_frontend()}｜{python_blocker}",
        }
    }

    try:
        import flask

        results["flask"] = {
            "ok": True,
            "label": "Flask",
            "version": getattr(flask, "__version__", ""),
            "note": "",
        }
    except ImportError:
        results["flask"] = {"ok": False, "label": "Flask", "version": None, "note": "尚未安裝"}

    try:
        import whisper

        results["whisper"] = {
            "ok": True,
            "label": "openai-whisper",
            "version": getattr(whisper, "__version__", ""),
            "note": "",
        }
    except ImportError:
        results["whisper"] = {"ok": False, "label": "openai-whisper", "version": None, "note": "尚未安裝"}

    try:
        import yt_dlp

        yt_version = getattr(yt_dlp, "__version__", None)
        if not yt_version:
            yt_version_module = getattr(yt_dlp, "version", None)
            yt_version = getattr(yt_version_module, "__version__", "") if yt_version_module else ""
        results["yt_dlp"] = {
            "ok": True,
            "label": "yt-dlp",
            "version": yt_version,
            "note": "可用於下載 YouTube 影片音訊",
        }
    except ImportError:
        results["yt_dlp"] = {"ok": False, "label": "yt-dlp", "version": None, "note": "尚未安裝"}

    torch_info = inspect_torch_cuda()
    if torch_info.get("torch_installed"):
        if torch_info.get("cuda_usable"):
            torch_note = "CUDA 可用"
        elif torch_info.get("cuda_available"):
            torch_note = torch_info.get("cuda_issue") or "偵測到 GPU，但 PyTorch CUDA 版本不相容"
        else:
            torch_note = "目前使用 CPU"
        results["torch"] = {
            "ok": True,
            "label": "PyTorch",
            "version": torch_info.get("torch_version", ""),
            "note": torch_note,
        }
    else:
        results["torch"] = {"ok": False, "label": "PyTorch", "version": None, "note": "尚未安裝"}

    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        results["ffmpeg"] = {"ok": True, "label": "ffmpeg", "version": None, "note": ffmpeg_path}
    else:
        discovered = None
        for candidate in ffmpeg_candidates():
            if (Path(candidate) / "ffmpeg.exe").is_file():
                discovered = candidate
                break
        if discovered:
            results["ffmpeg"] = {"ok": True, "label": "ffmpeg", "version": None, "note": f"已找到：{discovered}"}
        else:
            results["ffmpeg"] = {"ok": False, "label": "ffmpeg", "version": None, "note": "尚未找到 ffmpeg"}

    missing_pip = []
    if not results["flask"]["ok"]:
        missing_pip.append("flask")
    if not results["whisper"]["ok"]:
        missing_pip.append("openai-whisper")
    if not results["yt_dlp"]["ok"]:
        missing_pip.append("yt-dlp")

    results["missing_pip"] = missing_pip
    results["python_supported"] = python_blocker is None
    results["python_blocker"] = python_blocker
    return results


def create_job(
    filename: str,
    file_path: str,
    seg_mode: str,
    source_type: str,
    source_url: str | None = None,
    original_title: str | None = None,
) -> str:
    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = JobState(
            status="processing",
            filename=filename,
            file_path=file_path,
            source_type=source_type,
            source_url=source_url,
            original_title=original_title,
        )

    thread = threading.Thread(target=run_whisper, args=(job_id, file_path, seg_mode), daemon=True)
    thread.start()
    return job_id


setup_ffmpeg()
DEVICE, USE_FP16 = detect_device()


@app.route("/")
def index():
    return send_file(INDEX_FILE)


@app.route("/upload", methods=["POST"])
def upload():
    seg_mode = request.form.get("seg_mode", "standard")
    if seg_mode not in {"fine", "standard", "coarse"}:
        seg_mode = "standard"

    youtube_url = normalize_text(request.form.get("youtube_url", ""))
    if youtube_url:
        if not is_youtube_url(youtube_url):
            return jsonify({"error": "請輸入有效的 YouTube 影片網址。"}), 400

        try:
            file_path, title = download_youtube_media(str(uuid.uuid4()), youtube_url)
        except ImportError:
            return jsonify({"error": "目前尚未安裝 yt-dlp，請先到「安裝協助」補安裝。"}), 400
        except Exception as exc:
            return jsonify({"error": f"YouTube 影片下載失敗：{exc}"}), 400

        filename = f"{filename_safe(title)}{Path(file_path).suffix}"
        job_id = create_job(
            filename=filename,
            file_path=file_path,
            seg_mode=seg_mode,
            source_type="youtube",
            source_url=youtube_url,
            original_title=title,
        )
        print(f"[YouTube] 建立工作 {job_id[:8]}，標題：{title}")
        return jsonify({"job_id": job_id})

    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "請先選擇音訊、影片檔，或輸入 YouTube 網址。"}), 400

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        return jsonify({"error": f"不支援的檔案格式：{ext}。請使用 {allowed}。"}), 400

    job_id = str(uuid.uuid4())
    save_path = str(UPLOAD_DIR / f"{job_id}.{ext}")
    file.save(save_path)

    with jobs_lock:
        jobs[job_id] = JobState(
            status="processing",
            filename=file.filename,
            file_path=save_path,
            source_type="upload",
        )

    thread = threading.Thread(target=run_whisper, args=(job_id, save_path, seg_mode), daemon=True)
    thread.start()
    print(f"[Upload] 建立工作 {job_id[:8]}，檔案：{file.filename}，模式：{seg_mode}")
    return jsonify({"job_id": job_id})


@app.route("/status/<job_id>")
def status(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)

    if not job:
        return jsonify({"status": "not_found"}), 404

    payload: dict[str, Any] = {"status": job.status}
    if job.status == "done":
        base_name = filename_safe(Path(job.filename).stem or "transcript")
        payload.update(
            {
                "srt": job.srt,
                "filename": base_name + ".srt",
                "text_filename": base_name + ".txt",
                "seo_filename": "SEO.txt",
                "segment_count": job.segment_count,
                "source_type": job.source_type,
                "source_url": job.source_url,
                "original_title": job.original_title or Path(job.filename).stem,
            }
        )
    elif job.status == "error":
        payload["error_msg"] = job.error_msg

    return jsonify(payload)


@app.route("/download/<job_id>")
def download_default(job_id: str):
    return download_file(job_id, "srt")


@app.route("/download/<job_id>/<kind>")
def download_file(job_id: str, kind: str):
    with jobs_lock:
        job = jobs.get(job_id)

    if not job or job.status != "done":
        return "找不到可下載的轉錄結果。", 404

    base_name = filename_safe(Path(job.filename).stem or "transcript")
    kind = str(kind).lower()

    if kind == "srt" and job.srt:
        filename = base_name + ".srt"
        content = job.srt
    elif kind == "txt" and job.transcript_text:
        filename = base_name + ".txt"
        content = job.transcript_text
    elif kind == "seo" and job.seo_text:
        filename = "SEO.txt"
        content = job.seo_text
    else:
        return "找不到指定的輸出檔案。", 404

    buffer = BytesIO(content.encode("utf-8-sig"))
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype="text/plain; charset=utf-8",
        as_attachment=True,
        download_name=filename,
    )


@app.route("/cancel/<job_id>", methods=["POST"])
def cancel(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if job and job.status == "processing":
            job.status = "cancelled"
            job.error_msg = "使用者已取消轉錄。"
    return jsonify({"ok": True})


@app.route("/unload-model", methods=["POST"])
def unload_model():
    global _whisper_model

    freed = False
    with _model_lock:
        if _whisper_model is not None:
            _whisper_model = None
            freed = True

    gc.collect()
    message = "目前沒有已載入的模型。"
    if freed:
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                message = "模型已卸載，GPU VRAM 已釋放。"
            else:
                message = "模型已卸載，記憶體已釋放。"
        except Exception:
            message = "模型已卸載。"

    return jsonify({"ok": True, "msg": message})


@app.route("/device-info")
def device_info():
    info: dict[str, Any] = {
        "device": DEVICE,
        "fp16": USE_FP16,
        "model_loaded": _whisper_model is not None,
    }

    cuda_info = inspect_torch_cuda(test_tensor=False)
    info.update(cuda_info)

    if cuda_info.get("cuda_available"):
        try:
            import torch

            props = torch.cuda.get_device_properties(0)
            info["gpu_total"] = round(props.total_memory / 1024**3, 1)
            info["gpu_used"] = round(torch.cuda.memory_allocated(0) / 1024**3, 2)
        except Exception:
            pass

    return jsonify(info)


@app.route("/set-device", methods=["POST"])
def set_device():
    global DEVICE, USE_FP16, _whisper_model

    target = (request.get_json(silent=True) or {}).get("device", "cpu")
    if target not in {"cpu", "cuda"}:
        return jsonify({"error": "device 必須為 cpu 或 cuda。"}), 400

    try:
        import torch
    except ImportError:
        return jsonify({"error": "找不到 torch，請先安裝 PyTorch。"}), 500

    if target == "cuda":
        cuda_info = inspect_torch_cuda()
        if not cuda_info.get("cuda_usable"):
            return jsonify({"error": cuda_info.get("cuda_issue") or "目前偵測不到可用的 CUDA GPU。"}), 400

    with _model_lock:
        _whisper_model = None

    gc.collect()
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass

    DEVICE = target
    USE_FP16 = target == "cuda"
    print(f"[Device] 切換到 {DEVICE.upper()}。")
    return jsonify({"ok": True, "device": DEVICE})


@app.route("/cuda-diagnose")
def cuda_diagnose():
    python_blocker = python_support_blocker()
    cuda_info = inspect_torch_cuda()
    result: dict[str, Any] = {
        "python_version": python_version_text(),
        "python_executable": find_python_for_frontend(),
        "python_supported": python_blocker is None,
        "cuda_install_supported": python_blocker is None,
        "cuda_install_blocker": python_blocker,
    }
    result.update(cuda_info)

    if shutil.which("nvcc"):
        try:
            output = subprocess.check_output(["nvcc", "--version"], text=True, stderr=subprocess.STDOUT)
            match = re.search(r"release\s+([\d.]+)", output)
            result["nvcc_version"] = match.group(1) if match else output.strip().splitlines()[-1]
        except Exception as exc:
            result["nvcc_version"] = str(exc)
    else:
        result["nvcc_version"] = None

    if shutil.which("nvidia-smi"):
        try:
            output = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
                text=True,
                stderr=subprocess.STDOUT,
            )
            result["nvidia_smi"] = output.strip()
        except Exception:
            result["nvidia_smi"] = None
    else:
        result["nvidia_smi"] = None

    result["recommended_index"] = recommend_cuda_index(
        capability=result.get("capability"),
        nvcc_version=result.get("nvcc_version"),
        gpu_name=result.get("gpu_name"),
    )
    return jsonify(result)


@app.route("/install-cuda-torch", methods=["POST"])
def install_cuda_torch():
    data = request.get_json(silent=True) or {}
    index_url = data.get("index_url", CUDA_INDEX_CU128)

    python_blocker = python_support_blocker()
    if python_blocker:
        return jsonify({"error": python_blocker}), 400

    install_id = str(uuid.uuid4())
    with install_lock:
        install_jobs[install_id] = InstallJobState()

    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "torch",
        "torchvision",
        "torchaudio",
        "--index-url",
        index_url,
        "--upgrade",
        "--progress-bar",
        "off",
    ]
    threading.Thread(target=run_cuda_torch_install, args=(install_id, command), daemon=True).start()
    return jsonify({"install_id": install_id})


@app.route("/env-check")
def env_check():
    return jsonify(build_env_check())


@app.route("/install", methods=["POST"])
def install_packages():
    data = request.get_json(silent=True) or {}
    packages = data.get("packages", DEFAULT_INSTALL_PACKAGES)
    if not isinstance(packages, list) or not packages:
        packages = DEFAULT_INSTALL_PACKAGES

    packages = [str(item) for item in packages]
    python_blocker = python_support_blocker()
    if python_blocker and packages_need_pytorch(packages):
        return jsonify({"error": python_blocker}), 400

    install_id = str(uuid.uuid4())
    with install_lock:
        install_jobs[install_id] = InstallJobState()

    command = [sys.executable, "-m", "pip", "install", *packages, "--progress-bar", "off"]
    threading.Thread(
        target=run_install_command,
        args=(install_id, command, "套件安裝完成，請重新執行 start.bat。"),
        daemon=True,
    ).start()
    return jsonify({"install_id": install_id})


@app.route("/install-status/<install_id>")
def install_status(install_id: str):
    with install_lock:
        job = install_jobs.get(install_id)
    if not job:
        return jsonify({"status": "not_found"}), 404
    return jsonify({"status": job.status, "lines": job.lines})


if __name__ == "__main__":
    print("=" * 42)
    print("  Whisper 字幕神器啟動中")
    print("  服務位置：http://localhost:5000")
    print("=" * 42)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
