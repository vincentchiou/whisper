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
from difflib import SequenceMatcher
from io import BytesIO
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_file

try:
    import requests
except ImportError:
    requests = None


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
DEFAULT_INSTALL_PACKAGES = ["flask", "openai-whisper", "yt-dlp", "requests", "silero-vad"]
CUDA_INDEX_CU121 = "https://download.pytorch.org/whl/cu121"
CUDA_INDEX_CU128 = "https://download.pytorch.org/whl/cu128"
WHISPER_MODEL_NAME = "medium"
ADVANCED_SEO_FILENAME = "進階SEO.txt"
DOWNLOAD_FILENAME_LIMIT = 20
OPENAI_STYLE_PROVIDERS = {"openai", "groq", "mistral", "lmstudio"}
GEMINI_STYLE_PROVIDERS = {"aistudio", "google"}
VAD_SAMPLE_RATE = 16000
VAD_MIN_SPEECH_SECONDS = 0.35
VAD_MIN_SPEECH_RATIO = 0.02

LLM_PROVIDER_DEFINITIONS: dict[str, dict[str, Any]] = {
    "ollama": {
        "label": "Ollama（本地）",
        "group": "local",
        "api_style": "ollama",
        "default_base_url": "http://127.0.0.1:11434",
        "needs_api_key": False,
        "api_key_label": "",
        "description": "直接連到本機 Ollama，預設網址可手動改成其他主機或連接埠。",
        "note": "需先啟動 Ollama，並至少拉好一個可用模型。",
    },
    "lmstudio": {
        "label": "LM Studio（本地）",
        "group": "local",
        "api_style": "openai",
        "default_base_url": "http://127.0.0.1:1234/v1",
        "needs_api_key": False,
        "api_key_label": "",
        "description": "使用 LM Studio 的 OpenAI 相容伺服器，預設為本機 1234 連接埠。",
        "note": "請先在 LM Studio 開啟 Local Server，並確認模型可被伺服器看到。",
    },
    "groq": {
        "label": "Groq（API Key）",
        "group": "cloud-freeish",
        "api_style": "openai",
        "default_base_url": "https://api.groq.com/openai/v1",
        "needs_api_key": True,
        "api_key_label": "GROQ API Key",
        "description": "Groq 為 OpenAI 相容 API，可先連通後再從模型清單選擇可用模型。",
        "note": "依您的帳號方案，可能有免費或試用額度限制。",
    },
    "mistral": {
        "label": "Mistral（API Key）",
        "group": "cloud-freeish",
        "api_style": "openai",
        "default_base_url": "https://api.mistral.ai/v1",
        "needs_api_key": True,
        "api_key_label": "Mistral API Key",
        "description": "Mistral 採 chat completions 與 models API，可手動改成代理網址。",
        "note": "依您的帳號方案，可能有免費或試用額度限制。",
    },
    "aistudio": {
        "label": "Google AI Studio（Gemini API）",
        "group": "cloud-freeish",
        "api_style": "gemini",
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta",
        "needs_api_key": True,
        "api_key_label": "AI Studio API Key",
        "description": "使用 Gemini API 端點，適合填入 Google AI Studio 取得的金鑰。",
        "note": "依您的帳號方案，可能有免費或試用額度限制。",
    },
    "google": {
        "label": "Google Gemini API（付費）",
        "group": "cloud-paid",
        "api_style": "gemini",
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta",
        "needs_api_key": True,
        "api_key_label": "Google API Key",
        "description": "與 AI Studio 相同 API 格式，適合填入正式付費方案的 Google API Key。",
        "note": "通常以付費 API 方案使用，請依您的帳單與配額設定為準。",
    },
    "openai": {
        "label": "OpenAI（付費）",
        "group": "cloud-paid",
        "api_style": "openai",
        "default_base_url": "https://api.openai.com/v1",
        "needs_api_key": True,
        "api_key_label": "OpenAI API Key",
        "description": "使用 OpenAI 官方 API，先連通後即可從帳號可用模型中選擇。",
        "note": "通常以付費 API 方案使用，請依您的帳單與配額設定為準。",
    },
}

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
    advanced_seo_text: str | None = None
    advanced_seo_requested: bool = False
    advanced_seo_provider: str | None = None
    advanced_seo_model: str | None = None
    advanced_seo_error: str | None = None
    status_note: str | None = None
    advanced_seo_config: "AdvancedSeoConfig | None" = None
    segment_count: int = 0
    error_msg: str | None = None


@dataclass
class InstallJobState:
    status: str = "running"
    lines: list[str] = field(default_factory=list)


@dataclass
class AdvancedSeoConfig:
    provider: str
    base_url: str
    model: str
    api_key: str | None = None


jobs: dict[str, JobState] = {}
jobs_lock = threading.Lock()

install_jobs: dict[str, InstallJobState] = {}
install_lock = threading.Lock()

_whisper_model = None
_model_lock = threading.Lock()
_silero_vad_model = None
_vad_lock = threading.Lock()
DEVICE = "cpu"
USE_FP16 = False


def set_job_status_note(job_id: str, note: str) -> None:
    with jobs_lock:
        job = jobs.get(job_id)
        if job and job.status == "processing":
            job.status_note = note


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


def get_provider_definition(provider: str) -> dict[str, Any]:
    return LLM_PROVIDER_DEFINITIONS.get(str(provider or "").strip().lower(), {})


def provider_label(provider: str) -> str:
    definition = get_provider_definition(provider)
    return str(definition.get("label") or provider or "未設定")


def list_llm_provider_options() -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for provider, definition in LLM_PROVIDER_DEFINITIONS.items():
        options.append(
            {
                "id": provider,
                "label": definition["label"],
                "group": definition["group"],
                "default_base_url": definition["default_base_url"],
                "needs_api_key": definition["needs_api_key"],
                "api_key_label": definition["api_key_label"],
                "description": definition["description"],
                "note": definition["note"],
                "supports_model_switch": True,
                "auto_load_on_select": provider == "lmstudio",
            }
        )
    return options


def normalize_openai_base_url(base_url: str) -> str:
    cleaned = normalize_text(base_url).rstrip("/")
    if not cleaned:
        return ""
    if cleaned.endswith("/v1"):
        return cleaned
    if "/v1/" in cleaned:
        return cleaned.split("/v1/", 1)[0] + "/v1"
    return cleaned + "/v1"


def normalize_gemini_base_url(base_url: str) -> str:
    cleaned = normalize_text(base_url).rstrip("/")
    if not cleaned:
        return ""
    if cleaned.endswith("/v1beta"):
        return cleaned
    if "/v1beta/" in cleaned:
        return cleaned.split("/v1beta/", 1)[0] + "/v1beta"
    return cleaned + "/v1beta"


def normalize_ollama_base_url(base_url: str) -> str:
    cleaned = normalize_text(base_url).rstrip("/")
    if "/api/" in cleaned:
        return cleaned.split("/api/", 1)[0]
    if cleaned.endswith("/api"):
        return cleaned[:-4]
    return cleaned


def normalize_lmstudio_base_url(base_url: str) -> str:
    cleaned = normalize_text(base_url).rstrip("/")
    if not cleaned:
        return ""
    if cleaned.endswith("/api/v1"):
        cleaned = cleaned[:-7]
    elif "/api/v1/" in cleaned:
        cleaned = cleaned.split("/api/v1/", 1)[0]
    if cleaned.endswith("/api"):
        cleaned = cleaned[:-4]
    if cleaned.endswith("/v1"):
        return cleaned
    if "/v1/" in cleaned:
        return cleaned.split("/v1/", 1)[0] + "/v1"
    return cleaned + "/v1"


def lmstudio_native_base_url(base_url: str) -> str:
    normalized = normalize_lmstudio_base_url(base_url)
    if normalized.endswith("/v1"):
        return normalized[:-2] + "api/v1"
    return normalized.rstrip("/") + "/api/v1"


def normalize_provider_base_url(provider: str, base_url: str | None) -> str:
    definition = get_provider_definition(provider)
    candidate = normalize_text(base_url or "") or str(definition.get("default_base_url", ""))
    provider = str(provider or "").strip().lower()

    if provider == "ollama":
        return normalize_ollama_base_url(candidate)
    if provider == "lmstudio":
        return normalize_lmstudio_base_url(candidate)
    if provider in OPENAI_STYLE_PROVIDERS:
        return normalize_openai_base_url(candidate)
    if provider in GEMINI_STYLE_PROVIDERS:
        return normalize_gemini_base_url(candidate)
    return candidate.rstrip("/")


def normalize_provider_model(provider: str, model: str | None) -> str:
    normalized = normalize_text(model or "")
    if str(provider or "").strip().lower() in GEMINI_STYLE_PROVIDERS:
        return normalized.removeprefix("models/")
    return normalized


def needs_api_key(provider: str) -> bool:
    definition = get_provider_definition(provider)
    return bool(definition.get("needs_api_key"))


def ensure_requests_available() -> None:
    if requests is None:
        raise RuntimeError("目前尚未安裝 requests，請先到「安裝協助」補安裝 requests。")


def extract_advanced_seo_config_from_form(form: Any) -> AdvancedSeoConfig | None:
    enabled = normalize_text(form.get("advanced_seo_enabled", "")).lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return None

    provider = normalize_text(form.get("advanced_seo_provider", "")).lower()
    if provider not in LLM_PROVIDER_DEFINITIONS:
        raise ValueError("進階 SEO 服務商無效，請重新連線後再試一次。")

    base_url = normalize_provider_base_url(provider, form.get("advanced_seo_base_url", ""))
    model = normalize_provider_model(provider, form.get("advanced_seo_model", ""))
    api_key = normalize_text(form.get("advanced_seo_api_key", "")) or None

    if not base_url:
        raise ValueError("進階 SEO 缺少連線網址，請先完成模型連線。")
    if needs_api_key(provider) and not api_key:
        raise ValueError(f"{provider_label(provider)} 需要 API Key，請先填寫後重新連線。")
    if not model:
        raise ValueError("請先連通模型服務並選擇模型，才能產生進階SEO.txt。")

    return AdvancedSeoConfig(
        provider=provider,
        base_url=base_url,
        model=model,
        api_key=api_key,
    )


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

            print(f"[Whisper] 載入 {WHISPER_MODEL_NAME} 模型（device={DEVICE}）...")
            _whisper_model = whisper.load_model(WHISPER_MODEL_NAME, device=DEVICE)
            print("[Whisper] 模型載入完成。")
    return _whisper_model


def silero_vad_installed() -> bool:
    try:
        import silero_vad  # type: ignore

        return silero_vad is not None
    except ImportError:
        return False
    except Exception as exc:
        print(f"[Silero VAD] 載入失敗：{exc}")
        return False


def get_silero_vad_model():
    global _silero_vad_model
    if not silero_vad_installed():
        raise RuntimeError("目前尚未安裝 silero-vad，請先安裝後再啟用 VAD 過濾。")

    with _vad_lock:
        if _silero_vad_model is None:
            from silero_vad import load_silero_vad  # type: ignore

            print("[Silero VAD] 正在載入語音活動偵測模型...")
            _silero_vad_model = load_silero_vad()
            print("[Silero VAD] 模型已載入。")
    return _silero_vad_model


def convert_media_to_vad_wav(file_path: str) -> Path:
    temp_path = UPLOAD_DIR / f"{Path(file_path).stem}_{uuid.uuid4().hex[:8]}_vad.wav"
    subprocess.run(
        [
            shutil.which("ffmpeg") or "ffmpeg",
            "-y",
            "-i",
            file_path,
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(VAD_SAMPLE_RATE),
            "-f",
            "wav",
            str(temp_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return temp_path


def detect_speech_windows(file_path: str) -> list[tuple[float, float]]:
    if not silero_vad_installed():
        return []

    try:
        from silero_vad import get_speech_timestamps, read_audio  # type: ignore

        wav_path = convert_media_to_vad_wav(file_path)
        try:
            model = get_silero_vad_model()
            audio = read_audio(str(wav_path), sampling_rate=VAD_SAMPLE_RATE)
            timestamps = get_speech_timestamps(
                audio,
                model,
                sampling_rate=VAD_SAMPLE_RATE,
                min_silence_duration_ms=400,
                speech_pad_ms=160,
            )
            windows: list[tuple[float, float]] = []
            for item in as_iterable_list(timestamps):
                if not isinstance(item, dict):
                    continue
                start = float(item.get("start", 0.0)) / VAD_SAMPLE_RATE
                end = float(item.get("end", 0.0)) / VAD_SAMPLE_RATE
                if end > start:
                    windows.append((start, end))
            return windows
        finally:
            try:
                if wav_path.exists():
                    wav_path.unlink()
            except OSError:
                pass
    except Exception as exc:
        print(f"[Silero VAD] 偵測失敗，改回一般 Whisper 流程：{exc}")
        return []


def speech_duration_from_windows(windows: list[tuple[float, float]]) -> float:
    return sum(max(0.0, end - start) for start, end in windows)


def has_enough_speech(windows: list[tuple[float, float]], duration: float) -> bool:
    if not windows:
        return False
    speech_seconds = speech_duration_from_windows(windows)
    safe_duration = max(duration, 0.001)
    return speech_seconds >= VAD_MIN_SPEECH_SECONDS and (speech_seconds / safe_duration) >= VAD_MIN_SPEECH_RATIO


def segment_speech_overlap(start: float, end: float, windows: list[tuple[float, float]]) -> float:
    overlap = 0.0
    for win_start, win_end in windows:
        left = max(start, win_start)
        right = min(end, win_end)
        if right > left:
            overlap += right - left
    return overlap


def filter_segments_with_vad(
    segments: list[dict[str, Any]],
    speech_windows: list[tuple[float, float]],
) -> list[dict[str, Any]]:
    if not segments or not speech_windows:
        return segments

    filtered: list[dict[str, Any]] = []
    for segment in segments:
        start = float(segment.get("start", 0.0))
        end = float(segment.get("end", start))
        duration = max(0.01, end - start)
        overlap = segment_speech_overlap(start, end, speech_windows)
        overlap_ratio = overlap / duration
        if overlap >= 0.12 and overlap_ratio >= 0.2:
            filtered.append(segment)
    return filtered


def apply_vad_filter_with_fallback(
    segments: list[dict[str, Any]],
    speech_windows: list[tuple[float, float]],
) -> list[dict[str, Any]]:
    if not segments or not speech_windows:
        return segments

    filtered = filter_segments_with_vad(segments, speech_windows)
    if filtered:
        return filtered

    print("[Silero VAD] 過濾後沒有字幕片段，保留 Whisper 原始結果避免誤判。")
    return segments


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


def compact_keyword_token(text: str, limit: int = 6) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", normalize_text(text))
    if not cleaned:
        return ""
    if re.search(r"[\u4e00-\u9fff]", cleaned):
        return cleaned[:limit]
    return cleaned[: max(4, limit + 2)]


def build_download_base_name(job: "JobState") -> str:
    source_text = clean_transcript_text(job.transcript_text or "")
    seed_title = normalize_text(job.original_title or Path(job.filename).stem)
    keywords = top_keywords(source_text, seed_title, limit=8) if source_text or seed_title else []

    parts: list[str] = []
    for keyword in keywords:
        token = compact_keyword_token(keyword, limit=4)
        if not token:
            continue
        if any(token in existing or existing in token for existing in parts):
            continue
        next_value = "".join(parts) + token
        if len(next_value) > 9:
            break
        parts.append(token)
        if len("".join(parts)) >= 6:
            break

    if not parts:
        fallback = compact_keyword_token(seed_title or source_text or "轉錄", limit=8)
        parts.append(fallback or "轉錄")

    return filename_safe("".join(parts))[:9] or "轉錄"


def build_download_filename(job: "JobState", kind: str) -> str:
    kind = normalize_text(kind).lower()
    base_name = build_download_base_name(job)
    suffix_map = {
        "srt": ("字幕", ".srt"),
        "txt": ("逐字稿", ".txt"),
        "seo": ("SEO", ".txt"),
        "advanced-seo": ("進階SEO", ".txt"),
        "advanced_seo": ("進階SEO", ".txt"),
        "adv-seo": ("進階SEO", ".txt"),
    }
    suffix, extension = suffix_map.get(kind, ("輸出", ".txt"))
    room = max(2, DOWNLOAD_FILENAME_LIMIT - len(suffix) - len(extension))
    short_base = base_name[:room] or "轉錄"
    return f"{short_base}{suffix}{extension}"


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
        "今天介紹", "接著說明", "重點整理", "快速掌握",
        "the", "and", "that", "this", "with", "from", "have", "your", "just", "really",
        "about", "there", "here", "what", "when", "then", "into", "they", "them", "guys",
        "alright", "okay", "cool", "pretty", "stuff", "thing", "these", "those", "me", "are", "front", "at", "is",
    }
    for chunk in ascii_words + chinese_chunks:
        chunk = chunk.strip().strip(".,!?;:()[]{}\"'")
        if "邱文盛" in chunk:
            continue
        if re.search(r"[\u4e00-\u9fff]", chunk) and len(chunk) > 6:
            continue
        if len(chunk) < 2 or chunk.lower() in stop_words or chunk in stop_words:
            continue
        candidates.append(chunk)
    return candidates


def top_keywords(text: str, seed_title: str = "", limit: int = 10) -> list[str]:
    frequency: dict[str, int] = {}
    normalized_source = clean_transcript_text(seed_title + "\n" + text)
    for phrase in extract_candidate_phrases(normalized_source):
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
        candidate = "重點整理" + "、".join(keywords[:3])
    else:
        candidate = fallback

    candidate = candidate.strip("，。！？,.!? ")
    if len(candidate) > 32:
        candidate = candidate[:32].rstrip("，。！？,.!? ") + "…"
    return candidate or fallback


def polish_traditional_punctuation(text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"(?<=[A-Za-z\u4e00-\u9fff]):(?=[A-Za-z\u4e00-\u9fff])", "：", cleaned)
    cleaned = re.sub(r"(?<=[A-Za-z\u4e00-\u9fff]),(?=[A-Za-z\u4e00-\u9fff])", "，", cleaned)
    return cleaned


def shorten_sentence(text: str, max_chars: int = 72) -> str:
    cleaned = clean_transcript_text(text)
    if len(cleaned) <= max_chars:
        return polish_traditional_punctuation(cleaned)
    return polish_traditional_punctuation(cleaned[: max_chars - 1].rstrip("，。！？,.!?；;:： ") + "…")


def build_chapter_description(text: str, fallback: str) -> str:
    cleaned = clean_transcript_text(text)
    keywords = top_keywords(cleaned, "", limit=4)
    chinese_keywords = [item for item in keywords if re.search(r"[\u4e00-\u9fff]", item)]
    english_keywords = [item for item in keywords if re.search(r"[A-Za-z]", item)]
    sentences = sentence_split(cleaned)

    if len(chinese_keywords) >= 2:
        lead = f"本段聚焦{chinese_keywords[0]}與{chinese_keywords[1]}，說明相關概念與操作重點。"
    elif len(chinese_keywords) == 1 and english_keywords:
        lead = f"本段聚焦{chinese_keywords[0]}與{english_keywords[0]}，整理實際應用與重點流程。"
    elif len(english_keywords) >= 2:
        lead = f"本段聚焦{english_keywords[0]}與{english_keywords[1]}，整理實作方向與關鍵觀念。"
    elif keywords:
        lead = f"本段重點圍繞{'、'.join(keywords[:2])}，整理核心內容與延伸重點。"
    else:
        lead = fallback

    if sentences:
        detail_source = shorten_sentence(sentences[0], 46).rstrip("，。！？,.!?；;:：…")
        if re.search(r"[A-Za-z0-9\u4e00-\u9fff]", detail_source):
            detail = f"重點提到{detail_source}。"
            if detail not in lead:
                combined = f"{lead}{detail}"
            else:
                combined = lead
        else:
            combined = lead
    else:
        combined = lead

    return shorten_sentence(combined, 88) or fallback


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
        title = build_chapter_description(chunk_text, f"本段整理重點段落 {len(chapters) + 1} 的核心內容。")
        chapters.append((format_hms(start), title))

    if not chapters or chapters[0][0] != "00:00":
        chapters.insert(0, ("00:00", "影片開始"))

    while len(chapters) < 3 and len(chapters) < len(segments):
        candidate_index = min(len(segments) - 1, len(chapters) * max(1, len(segments) // 3))
        start = float(segments[candidate_index]["start"])
        title = build_chapter_description(
            str(segments[candidate_index]["text"]),
            f"本段整理章節 {len(chapters) + 1} 的核心概念與延伸重點。",
        )
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
    cleaned_text = clean_transcript_text(transcript_text)
    paragraphs = [item.strip() for item in cleaned_text.split("\n\n") if item.strip()]
    if not paragraphs:
        return "這支影片主要分享實際內容與重點觀點，適合整理成可搜尋、可快速理解的 YouTube 說明。", "先看前兩句，就能快速知道這支影片最值得注意的重點。"

    has_chinese = bool(re.search(r"[\u4e00-\u9fff]", cleaned_text))
    keywords = top_keywords(cleaned_text, "", limit=5)

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


def build_summary_and_hook_bullets(transcript_text: str, base_title: str = "") -> list[str]:
    cleaned_text = clean_transcript_text(transcript_text)
    keywords = top_keywords(cleaned_text, base_title, limit=5)
    sentences = sentence_split(cleaned_text)

    focus_keywords = "、".join(keywords[:3]) if keywords else normalize_text(base_title) or "影片主題"
    point_one = shorten_sentence(f"核心重點：內容聚焦{focus_keywords}，適合快速掌握主題方向。", 92)

    if sentences and re.search(r"[A-Za-z0-9\u4e00-\u9fff]", sentences[0]):
        point_two = shorten_sentence(f"重點摘要：{sentences[0]}", 92)
    else:
        point_two = shorten_sentence("重點摘要：影片內容已整理出主要觀念與操作方向。", 92)

    hook_keywords = "、".join(keywords[:2]) if keywords else normalize_text(base_title) or "核心主題"
    point_three = shorten_sentence(f"觀看鉤子：想快速掌握{hook_keywords}與實際做法的人，可先看這份整理。", 92)

    bullets = [point_one, point_two, point_three]
    while sum(len(item) for item in bullets) > 270:
        longest_index = max(range(len(bullets)), key=lambda idx: len(bullets[idx]))
        bullets[longest_index] = shorten_sentence(bullets[longest_index], max(42, len(bullets[longest_index]) - 24))
        if all(len(item) <= 42 for item in bullets):
            break

    return [f"- {item}" for item in bullets if item]


def keyword_to_hashtag(keyword: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff#+-]+", "", normalize_text(keyword).replace(" ", ""))
    return f"#{cleaned}" if cleaned else ""


def build_hashtag_line(keywords: list[str], limit: int = 10) -> str:
    hashtags: list[str] = []
    for keyword in keywords[:limit]:
        tag = keyword_to_hashtag(keyword)
        if tag and tag not in hashtags:
            hashtags.append(tag)
    return ",".join(hashtags) if hashtags else "#Whisper,#字幕轉錄,#YouTube"


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
    summary_bullets = build_summary_and_hook_bullets(transcript_text, base_title)
    chapters = build_chapters(segments, base_title)
    hashtag_line = build_hashtag_line(keywords, limit=10)

    lines = [
        "YouTube SEO 建議內容",
        "====================",
        "",
        "一、建議標題（3個）",
        *[f"{index}. {title}" for index, title in enumerate(title_suggestions, start=1)],
        "",
        "二、內容摘要與鉤子",
        *summary_bullets,
        "",
        "三、關鍵字及標籤分析",
        hashtag_line,
        "",
        "四、章節目錄",
        *[f"{timestamp} {title}" for timestamp, title in chapters],
    ]

    if source_url:
        lines.extend(["", f"原始影片網址：{source_url}"])

    return "\n".join(lines).strip() + "\n"


def build_fallback_advanced_seo_text(
    transcript_text: str,
    segments: list[dict[str, Any]],
    base_title: str,
    source_url: str | None = None,
    reason: str | None = None,
) -> str:
    cleaned_text = clean_transcript_text(transcript_text)
    keywords = top_keywords(cleaned_text, base_title, limit=12)
    title_suggestions = build_title_suggestions(base_title, keywords)
    summary_paragraph = build_summary_paragraph(cleaned_text, base_title, 300)
    summary_bullets = build_summary_and_hook_bullets(cleaned_text, base_title)
    hashtag_line = build_hashtag_line(keywords, limit=10)
    chapters = build_chapters(segments, base_title)

    lines = [
        "進階SEO.txt",
        "====================",
        "",
        "一、建議標題 3 個",
        *[f"{index}. {title}" for index, title in enumerate(title_suggestions, start=1)],
        "",
        "二、內容摘要",
        summary_paragraph,
        "",
        *summary_bullets,
        "",
        "三、關鍵字與標籤",
        hashtag_line,
        "",
        "四、章節目錄",
        *[f"{timestamp} {title}" for timestamp, title in chapters],
    ]

    if source_url:
        lines.extend(["", f"影片來源：{source_url}"])
    if reason:
        lines.extend(["", f"產生備註：本地模型未回傳可用內容，已改用程式規則產生可下載草稿。原因：{reason}"])

    return "\n".join(lines).strip() + "\n"


def chunk_segments_for_context(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not segments:
        return []

    duration = float(segments[-1]["end"])
    target_count = max(3, min(8, math.ceil(duration / 180) + 1))
    chunk_size = max(1, math.ceil(len(segments) / target_count))
    chunks: list[dict[str, Any]] = []

    for index in range(0, len(segments), chunk_size):
        chunk = segments[index:index + chunk_size]
        if not chunk:
            continue

        text = " ".join(str(item["text"]).strip() for item in chunk if str(item["text"]).strip())
        if not text:
            continue

        chunks.append(
            {
                "start": float(chunk[0]["start"]),
                "end": float(chunk[-1]["end"]),
                "text": clean_transcript_text(text),
            }
        )

    return chunks


def build_transcript_excerpt(transcript_text: str, max_chars: int = 4800) -> str:
    cleaned = clean_transcript_text(transcript_text)
    if len(cleaned) <= max_chars:
        return cleaned

    paragraphs = [item.strip() for item in cleaned.split("\n\n") if item.strip()]
    if len(paragraphs) <= 4:
        return cleaned[:max_chars].rstrip() + "…"

    picks: list[str] = []
    indexes = sorted({0, len(paragraphs) // 3, (len(paragraphs) * 2) // 3, len(paragraphs) - 1})
    for index in indexes:
        if 0 <= index < len(paragraphs):
            picks.append(paragraphs[index])

    excerpt = "\n\n".join(picks)
    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars].rstrip() + "…"
    return excerpt


def build_advanced_seo_prompt(
    transcript_text: str,
    segments: list[dict[str, Any]],
    base_title: str,
    source_url: str | None = None,
) -> tuple[str, str]:
    keywords = top_keywords(transcript_text, base_title, limit=12)
    chapters = build_chapters(segments, base_title)
    context_chunks = chunk_segments_for_context(segments)
    summary_bullets = build_summary_and_hook_bullets(transcript_text, base_title)
    hashtag_line = build_hashtag_line(keywords, limit=10)

    chapter_lines: list[str] = []
    for index, chunk in enumerate(context_chunks[:8], start=1):
        fallback = f"本段整理章節 {index} 的核心概念與延伸重點。"
        summary = build_chapter_description(chunk["text"], fallback)
        excerpt = chunk["text"][:220].rstrip()
        if len(chunk["text"]) > 220:
            excerpt += "…"
        chapter_lines.append(
            f"{format_hms(chunk['start'])} {summary}\n"
            f"關鍵摘錄：{excerpt}"
        )

    chapter_seed = "\n\n".join(chapter_lines) if chapter_lines else "無章節素材"
    transcript_excerpt = build_transcript_excerpt(transcript_text)
    chapter_outline = "\n".join(f"{timestamp} {title}" for timestamp, title in chapters)
    keyword_text = "、".join(keywords[:10]) if keywords else "Whisper、字幕轉錄、YouTube"
    title_seed = normalize_text(base_title) or "未提供標題"

    system_prompt = (
        "你是資深的 YouTube SEO 內容編輯與繁體中文文案整理助手。"
        "請根據轉錄內容輸出一份可直接存成純文字檔的進階 SEO 建議稿。"
        "所有內容必須使用繁體中文，不要使用簡體字。"
        "AI、品牌、人名與技術名詞請維持正確英文或既有中文，例如 OpenAI、ChatGPT、Whisper、YouTube、CUDA、NVIDIA、PyTorch、API、LLM、邱文盛。"
        "不要捏造影片中沒有提到的具體事實；資訊不足時要保守描述。"
        "不要輸出 Markdown 程式碼框，不要加上補充提醒、免責聲明或多餘寒暄。"
        "請嚴格只輸出第一到第四段，不要輸出第五段、第六段或其他附錄。"
    )

    user_prompt = (
        "請只輸出下列固定格式的純文字，段落標題名稱請保持一致：\n"
        "進階 YouTube SEO 建議內容\n"
        "========================\n"
        "一、建議標題（3個）\n"
        "1. ...\n"
        "2. ...\n"
        "3. ...\n\n"
        "二、內容摘要與鉤子\n"
        "- ...\n"
        "- ...\n"
        "- ...\n\n"
        "三、關鍵字及標籤分析\n"
        "#關鍵字,#關鍵字,#關鍵字\n\n"
        "四、章節目錄\n"
        "00:00 ...\n\n"
        "整理規則：\n"
        "- 標題要自然、可讀、可搜尋，不要三個都只換少數詞。\n"
        "- 第二段請控制在 300 字內，並以條列式抓出核心重點與觀看鉤子。\n"
        "- 第三段請只輸出關鍵字與標籤分析結果，直接用 #關鍵字,#關鍵字 的方式呈現，不要加額外解說。\n"
        "- 章節目錄請沿用已提供的時間點，並把每段的重要概念整理成 1 到 2 句話說明，不要只放單字。\n"
        "- 關鍵字與 Hashtags 要貼近轉錄內容，不要塞與影片無關的熱門詞。\n"
        "- 如果影片主題包含 AI、模型、API、GPU、CUDA、Whisper、YouTube SEO 等術語，請保留正確拼法。\n\n"
        f"影片標題：{title_seed}\n"
        f"來源網址：{source_url or '未提供'}\n"
        f"關鍵字候選：{keyword_text}\n\n"
        "第二段條列草稿：\n"
        f"{chr(10).join(summary_bullets)}\n\n"
        "第三段 hashtag 草稿：\n"
        f"{hashtag_line}\n\n"
        "章節時間點草稿：\n"
        f"{chapter_outline or '00:00 影片開始'}\n\n"
        "章節內容素材：\n"
        f"{chapter_seed}\n\n"
        "轉錄內容節錄：\n"
        f"{transcript_excerpt}"
    )
    return system_prompt, user_prompt


def build_compact_local_advanced_seo_prompt(
    transcript_text: str,
    segments: list[dict[str, Any]],
    base_title: str,
    source_url: str | None = None,
    *,
    context_reference: str | None = None,
) -> tuple[str, str]:
    keywords = top_keywords(transcript_text, base_title, limit=10)
    chapters = build_chapters(segments, base_title)
    keyword_text = "、".join(keywords[:8]) if keywords else "Whisper、字幕、YouTube、SEO"
    chapter_outline = "\n".join(f"{timestamp} {title}" for timestamp, title in chapters[:6])
    context_body = context_reference or build_transcript_excerpt(transcript_text, max_chars=2200)
    title_seed = normalize_text(base_title) or "影片重點整理"

    system_prompt = (
        "你是繁體中文 YouTube SEO 編輯，請直接輸出最終內容，不要解釋、不要思考過程、不要 Markdown。"
        "請固定輸出這四段：\n"
        "一、建議標題\n"
        "1. ...\n2. ...\n3. ...\n\n"
        "二、內容摘要\n"
        "先寫約 300 字以內的摘要，再用條列列出 3 個核心重點。\n\n"
        "三、關鍵字與標籤\n"
        "只輸出一行 #關鍵字,#關鍵字,...\n\n"
        "四、章節目錄\n"
        "每行格式為 00:00 直接說該段重點，用 1 到 2 句話即可。\n\n"
        "規則：全部使用繁體中文；不要寫第一點、第二點；不要寫「這段在說明什麼」；不要補充提醒。"
    )

    user_prompt = (
        f"主題：{title_seed}\n"
        f"來源：{source_url or '本機檔案'}\n"
        f"關鍵字參考：{keyword_text}\n\n"
        f"章節草稿：\n{chapter_outline or '00:00 影片重點整理'}\n\n"
        f"逐字稿重點：\n{context_body}"
    )
    return system_prompt, user_prompt


def build_advanced_seo_formatter_prompt(draft_text: str) -> tuple[str, str]:
    system_prompt = (
        "你是繁體中文 SEO 排版整理助手。"
        "請把草稿改寫成固定四段，不要解釋、不要 Markdown、不要前言、不要後記。"
        "輸出格式只能是：\n"
        "一、建議標題\n"
        "1. ...\n2. ...\n3. ...\n\n"
        "二、內容摘要\n"
        "先寫約 300 字以內的摘要，再列出 3 個核心重點條列。\n\n"
        "三、關鍵字與標籤\n"
        "只輸出一行 #關鍵字,#關鍵字,...\n\n"
        "四、章節目錄\n"
        "每行格式為 00:00 直接講該段重點，用 1 到 2 句話即可。"
    )
    user_prompt = f"請把以下草稿整理成指定格式，全部使用繁體中文：\n\n{draft_text}"
    return system_prompt, user_prompt


def strip_code_fences(text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^```[\w-]*\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def prune_extra_seo_sections(text: str) -> str:
    cleaned = strip_code_fences(text).replace("\r\n", "\n")
    cleaned = re.sub(r"^三、建議說明區文字\s*$", "三、關鍵字及標籤分析", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(
        r"\n(?:五|六)、[^\n]*\n.*?(?=\n[一二三四五六七八九十]、|\Z)",
        "\n",
        cleaned,
        flags=re.S,
    )
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def content_blocks_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces: list[str] = []
        for item in content:
            if isinstance(item, str):
                pieces.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    pieces.append(text)
        return "\n".join(piece for piece in pieces if piece).strip()
    return ""


def as_iterable_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def response_error_message(response: Any) -> str:
    try:
        data = response.json()
    except Exception:
        text = str(getattr(response, "text", "") or "").strip()
        return text or f"HTTP {getattr(response, 'status_code', '未知錯誤')}"

    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("code") or data)
        if isinstance(error, str):
            return error
        message = data.get("message")
        if isinstance(message, str):
            return message
    return f"HTTP {getattr(response, 'status_code', '未知錯誤')}"


def is_reasonable_text_model(model_id: str) -> bool:
    model = str(model_id or "").strip().lower()
    blocked_tokens = (
        "embedding",
        "moderation",
        "whisper",
        "tts",
        "image",
        "vision-preview",
        "audio-preview",
        "transcribe",
    )
    return bool(model) and not any(token in model for token in blocked_tokens)


def extract_model_ids(model_options: list[dict[str, Any]]) -> list[str]:
    model_ids: list[str] = []
    for item in model_options:
        model_id = normalize_text(item.get("value") or item.get("id") or "")
        if model_id:
            model_ids.append(model_id)
    return model_ids


def pick_default_model(provider: str, requested_model: str, model_options: list[dict[str, Any]]) -> str:
    model_ids = extract_model_ids(model_options)
    if requested_model and requested_model in model_ids:
        return requested_model
    if provider == "lmstudio":
        for item in model_options:
            if item.get("loaded"):
                model_id = normalize_text(item.get("value") or item.get("id") or "")
                if model_id:
                    return model_id
    return model_ids[0] if model_ids else ""


def post_openai_style_chat(
    config: AdvancedSeoConfig,
    system_text: str,
    user_text: str,
    *,
    max_tokens: int,
    temperature: float,
    timeout_seconds: int,
) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"

    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    response = requests.post(
        f"{config.base_url}/chat/completions",
        headers=headers,
        json=payload,
        timeout=timeout_seconds,
    )
    if not response.ok:
        raise RuntimeError(f"{provider_label(config.provider)} 生成失敗：{response_error_message(response)}")
    return response.json()


def extract_openai_style_response(data: dict[str, Any]) -> tuple[str, str, str]:
    choices = as_iterable_list(data.get("choices"))
    choice = choices[0] if choices and isinstance(choices[0], dict) else {}
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    content = content_blocks_to_text(message.get("content")) if isinstance(message, dict) else ""
    reasoning = content_blocks_to_text(message.get("reasoning_content")) if isinstance(message, dict) else ""
    if not reasoning and isinstance(message, dict):
        reasoning_block = message.get("reasoning")
        if isinstance(reasoning_block, dict):
            reasoning = content_blocks_to_text(reasoning_block.get("content"))
    finish_reason = str(choice.get("finish_reason") or "").strip().lower()
    return strip_code_fences(content), strip_code_fences(reasoning), finish_reason


def request_openai_style_text(
    config: AdvancedSeoConfig,
    system_text: str,
    user_text: str,
    *,
    max_tokens: int,
    temperature: float,
    timeout_seconds: int,
) -> str:
    model_id = str(config.model or "").strip().lower()
    use_no_think_hint = (
        config.provider == "lmstudio"
        and any(token in model_id for token in ("reasoning", "think"))
    )
    prepared_user_text = f"/no_think\n{user_text}" if use_no_think_hint and not str(user_text).lstrip().startswith("/no_think") else user_text

    data = post_openai_style_chat(
        config,
        system_text,
        prepared_user_text,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout_seconds=timeout_seconds,
    )
    content, reasoning, finish_reason = extract_openai_style_response(data)
    if content:
        return content

    # Some LM Studio reasoning models may spend the first pass on internal
    # reasoning and omit the final answer. Retry once with stricter wording and
    # a larger token budget so the user still gets a usable result.
    if config.provider == "lmstudio" and reasoning:
        retry_system = (
            f"{system_text}\n\n"
            "請直接輸出最終答案，不要輸出思考過程、分析、草稿、推理內容或額外說明。"
        )
        retry_user = (
            f"{prepared_user_text}\n\n"
            "請直接輸出最終答案，略過思考過程，只保留使用者真正需要的內容。"
        )
        retry_tokens = max(max_tokens, 700)
        if finish_reason == "length":
            retry_tokens = max(retry_tokens, min(max_tokens * 2, 3200))

        retry_data = post_openai_style_chat(
            config,
            retry_system,
            retry_user,
            max_tokens=retry_tokens,
            temperature=min(temperature, 0.2),
            timeout_seconds=max(timeout_seconds, 300),
        )
        retry_content, _, _ = extract_openai_style_response(retry_data)
        if retry_content:
            return retry_content

    raise RuntimeError(f"{provider_label(config.provider)} 沒有回傳可用內容。")


def list_model_options_for_provider(config: AdvancedSeoConfig) -> list[dict[str, Any]]:
    ensure_requests_available()

    provider = config.provider
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"

    if provider == "ollama":
        response = requests.get(f"{config.base_url}/api/tags", timeout=20)
        if not response.ok:
            raise RuntimeError(f"Ollama 連線失敗：{response_error_message(response)}")
        data = response.json()
        options = []
        for item in as_iterable_list(data.get("models")):
            model_id = str(item.get("model") or item.get("name") or "").strip()
            if model_id:
                options.append({"value": model_id, "label": model_id, "loaded": False})
        return sorted(options, key=lambda item: str(item.get("label") or item.get("value") or "").lower())

    if provider == "lmstudio":
        try:
            response = requests.get(f"{lmstudio_native_base_url(config.base_url)}/models", headers=headers, timeout=20)
            if response.ok:
                data = response.json()
                options: list[dict[str, Any]] = []
                for item in as_iterable_list(data.get("models")):
                    if str(item.get("type") or "").strip().lower() != "llm":
                        continue
                    model_id = str(item.get("key") or item.get("id") or "").strip()
                    if not model_id or not is_reasonable_text_model(model_id):
                        continue
                    display_name = str(item.get("display_name") or model_id).strip()
                    loaded = bool(as_iterable_list(item.get("loaded_instances")))
                    options.append(
                        {
                            "value": model_id,
                            "label": f"{display_name}（已載入）" if loaded else display_name,
                            "loaded": loaded,
                            "display_name": display_name,
                        }
                    )
                if options:
                    unique = {str(item["value"]): item for item in options}
                    return sorted(
                        unique.values(),
                        key=lambda item: (not bool(item.get("loaded")), str(item.get("display_name") or item.get("value") or "").lower()),
                    )
        except Exception:
            pass

    if provider in OPENAI_STYLE_PROVIDERS:
        response = requests.get(f"{config.base_url}/models", headers=headers, timeout=20)
        if not response.ok:
            raise RuntimeError(f"{provider_label(provider)} 連線失敗：{response_error_message(response)}")
        data = response.json()
        options = []
        for item in as_iterable_list(data.get("data")):
            model_id = str(item.get("id") or "").strip()
            if is_reasonable_text_model(model_id):
                options.append({"value": model_id, "label": model_id, "loaded": False})
        unique = {str(item["value"]): item for item in options}
        return sorted(unique.values(), key=lambda item: str(item.get("label") or item.get("value") or "").lower())

    if provider in GEMINI_STYLE_PROVIDERS:
        response = requests.get(
            f"{config.base_url}/models",
            params={"key": config.api_key, "pageSize": 1000},
            timeout=20,
        )
        if not response.ok:
            raise RuntimeError(f"{provider_label(provider)} 連線失敗：{response_error_message(response)}")
        data = response.json()
        options = []
        for item in as_iterable_list(data.get("models")):
            methods = item.get("supportedGenerationMethods") or []
            if "generateContent" not in methods:
                continue
            model_name = str(item.get("name") or "").removeprefix("models/").strip()
            if model_name:
                options.append({"value": model_name, "label": model_name, "loaded": False})
        unique = {str(item["value"]): item for item in options}
        return sorted(unique.values(), key=lambda item: str(item.get("label") or item.get("value") or "").lower())

    raise RuntimeError("尚未支援這個模型服務商。")


def list_models_for_provider(config: AdvancedSeoConfig) -> list[str]:
    return extract_model_ids(list_model_options_for_provider(config))


def activate_provider_model(config: AdvancedSeoConfig) -> dict[str, Any]:
    ensure_requests_available()

    if not config.model:
        raise RuntimeError("請先選擇模型，才能套用。")

    if config.provider == "lmstudio":
        headers = {"Content-Type": "application/json"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        response = requests.post(
            f"{lmstudio_native_base_url(config.base_url)}/models/load",
            headers=headers,
            json={"model": config.model, "echo_load_config": True},
            timeout=600,
        )
        if not response.ok:
            raise RuntimeError(f"LM Studio 載入模型失敗：{response_error_message(response)}")
        data = response.json()
        loaded_model = normalize_text(data.get("instance_id") or config.model) or config.model
        load_seconds = data.get("load_time_seconds")
        message = f"LM Studio 已切換並載入 {loaded_model}"
        if isinstance(load_seconds, (int, float)):
            message += f"（約 {load_seconds:.1f} 秒）"
        return {
            "selected_model": config.model,
            "loaded_model": loaded_model,
            "message": message,
            "loaded": True,
        }

    models = list_models_for_provider(config)
    if config.model not in models:
        raise RuntimeError("目前找不到這個模型，請重新連線後再試一次。")
    return {
        "selected_model": config.model,
        "loaded_model": config.model,
        "message": f"已切換為 {provider_label(config.provider)} 的 {config.model}",
        "loaded": False,
    }


def call_openai_style_chat(config: AdvancedSeoConfig, system_prompt: str, user_prompt: str) -> str:
    ensure_requests_available()
    return request_openai_style_text(
        config,
        system_prompt,
        user_prompt,
        max_tokens=1400,
        temperature=0.3,
        timeout_seconds=120,
    )


def call_ollama_chat(config: AdvancedSeoConfig, system_prompt: str, user_prompt: str) -> str:
    ensure_requests_available()
    payload = {
        "model": config.model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "options": {
            "temperature": 0.3,
        },
    }
    response = requests.post(
        f"{config.base_url}/api/chat",
        json=payload,
        timeout=180,
    )
    if not response.ok:
        raise RuntimeError(f"Ollama 生成失敗：{response_error_message(response)}")

    data = response.json()
    message = data.get("message") or {}
    content = content_blocks_to_text(message.get("content")) if isinstance(message, dict) else ""
    if not content and isinstance(message, dict):
        content = str(message.get("content") or "").strip()
    if not content:
        raise RuntimeError("Ollama 沒有回傳可用文字內容。")
    return strip_code_fences(content)


def call_gemini_generate_content(config: AdvancedSeoConfig, system_prompt: str, user_prompt: str) -> str:
    ensure_requests_available()
    model_name = config.model if str(config.model).startswith("models/") else f"models/{config.model}"
    payload = {
        "systemInstruction": {
            "parts": [{"text": system_prompt}],
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 1600,
        },
    }
    response = requests.post(
        f"{config.base_url}/{model_name}:generateContent",
        params={"key": config.api_key},
        json=payload,
        timeout=120,
    )
    if not response.ok:
        raise RuntimeError(f"{provider_label(config.provider)} 生成失敗：{response_error_message(response)}")

    data = response.json()
    candidates = as_iterable_list(data.get("candidates"))
    parts = []
    if candidates and isinstance(candidates[0], dict):
        content = candidates[0].get("content") or {}
        for item in as_iterable_list(content.get("parts")):
            if isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
    content = "\n".join(piece for piece in parts if piece).strip()
    if not content:
        raise RuntimeError(f"{provider_label(config.provider)} 沒有回傳可用文字內容。")
    return strip_code_fences(content)


def generate_advanced_seo_text(
    transcript_text: str,
    segments: list[dict[str, Any]],
    base_title: str,
    source_url: str | None,
    config: AdvancedSeoConfig,
) -> str:
    system_prompt, user_prompt = build_advanced_seo_prompt(
        transcript_text=transcript_text,
        segments=segments,
        base_title=base_title,
        source_url=source_url,
    )

    if config.provider == "ollama":
        content = call_ollama_chat(config, system_prompt, user_prompt)
    elif config.provider in OPENAI_STYLE_PROVIDERS:
        content = call_openai_style_chat(config, system_prompt, user_prompt)
    elif config.provider in GEMINI_STYLE_PROVIDERS:
        content = call_gemini_generate_content(config, system_prompt, user_prompt)
    else:
        raise RuntimeError("尚未支援這個模型服務商。")

    content = prune_extra_seo_sections(content)
    if source_url and "原始影片網址：" not in content:
        content += f"\n\n原始影片網址：{source_url}"
    return content + "\n"


def build_advanced_seo_prompt(
    transcript_text: str,
    segments: list[dict[str, Any]],
    base_title: str,
    source_url: str | None = None,
) -> tuple[str, str]:
    keywords = top_keywords(transcript_text, base_title, limit=12)
    chapters = build_chapters(segments, base_title)
    context_chunks = chunk_segments_for_context(segments)
    summary_bullets = build_summary_and_hook_bullets(transcript_text, base_title)
    hashtag_line = build_hashtag_line(keywords, limit=10)
    baseline_draft = build_seo_text(
        transcript_text=transcript_text,
        segments=segments,
        base_title=base_title,
        source_url=source_url,
    )

    chapter_lines: list[str] = []
    for index, chunk in enumerate(context_chunks[:8], start=1):
        fallback = f"章節 {index} 的內容重點"
        summary = build_chapter_description(chunk["text"], fallback)
        excerpt = chunk["text"][:220].rstrip()
        if len(chunk["text"]) > 220:
            excerpt += "…"
        chapter_lines.append(
            f"{format_hms(chunk['start'])} {summary}\n"
            f"段落摘錄：{excerpt}"
        )

    chapter_seed = "\n\n".join(chapter_lines) if chapter_lines else "暫無章節摘要"
    transcript_excerpt = build_transcript_excerpt(transcript_text)
    chapter_outline = "\n".join(f"{timestamp} {title}" for timestamp, title in chapters)
    keyword_text = "、".join(keywords[:10]) if keywords else "Whisper、字幕轉錄、YouTube"
    title_seed = normalize_text(base_title) or "未命名影片"

    system_prompt = (
        "你是資深的繁體中文 YouTube 內容編輯與 SEO 文案師。"
        "你的工作不是抄逐字稿，也不是把關鍵字排一排，而是先理解影片主題、目標觀眾、痛點、可獲得的價值，再把內容整理成可直接貼到 YouTube 的進階 SEO 稿。"
        "只輸出最後成品，不要解釋你的推理過程。"
        "所有文字一律使用繁體中文。OpenAI、ChatGPT、Whisper、YouTube、SEO、GPU、CUDA、NVIDIA、PyTorch、API、LLM 這些專有名詞必須保持正確英文。"
        "你的文風要像真的內容編輯，不要像機器模板。標題要有角度差異；摘要要抓核心資訊；章節說明要寫出該段實際在談什麼、解決什麼、示範什麼。"
        "不要照抄基礎草稿。若任一行和草稿有超過 12 個連續字相同，就代表重寫失敗。"
        "嚴禁輸出：補充提醒、免責聲明、使用說明、第五段、第六段、Markdown 程式碼框、表格。"
    )

    user_prompt = (
        "請根據下列素材，重寫成真正有可讀性、可上架、較像人類內容編輯完成的進階 SEO 檔。\n"
        "請先在心中完成這四步，但不要把分析過程輸出：\n"
        "1. 判斷這支影片最核心的主題與觀眾想解決的問題。\n"
        "2. 從逐字稿中找出最值得點擊的亮點、方法、結果或提醒。\n"
        "3. 把基礎草稿改寫成更自然、資訊密度更高、但不誇大的版本。\n"
        "4. 讓章節目錄每段都像是『這段到底講了什麼』，而不是只有名詞。\n\n"
        "輸出格式必須完全照下面四段，不可多也不可少：\n"
        "一、建議標題 3 個\n"
        "1. 搜尋型標題...\n"
        "2. 亮點型標題...\n"
        "3. 問題解答型標題...\n\n"
        "二、內容摘要與鉤子\n"
        "- 第一點...\n"
        "- 第二點...\n"
        "- 第三點...\n\n"
        "三、分析關鍵字及標籤\n"
        "#關鍵字,#關鍵字,#關鍵字\n\n"
        "四、章節目錄\n"
        "00:00 這段在說明什麼...\n\n"
        "寫作規則：\n"
        "- 全文只用繁體中文。\n"
        "- 第二段總長控制在 300 字內，必須是條列式，每一點都要有明確資訊，不可空泛。\n"
        "- 第三段只能輸出一行 hashtags，格式固定為 #關鍵字,#關鍵字,...，不要額外解說。\n"
        "- 第四段每個章節都要點出該段的重要概念或結論，可用 1 到 2 句，但不可只列名詞，不可寫成『重點整理』這種空話。\n"
        "- 標題三個方向必須有差異，不要只有換詞。\n"
        "- 可以參考草稿，但不要直接照抄；請主動優化語氣、吸引力與資訊密度。\n"
        "- 不要出現補充提醒、免責聲明、第五段、第六段。\n\n"
        f"原始標題：{title_seed}\n"
        f"來源網址：{source_url or '無'}\n"
        f"關鍵字候選：{keyword_text}\n\n"
        "基礎摘要草稿：\n"
        f"{chr(10).join(summary_bullets)}\n\n"
        "基礎 hashtags 草稿：\n"
        f"{hashtag_line}\n\n"
        "基礎章節草稿：\n"
        f"{chapter_outline or '00:00 影片開場與主題說明'}\n\n"
        "分段內容參考：\n"
        f"{chapter_seed}\n\n"
        "目前的基礎 SEO 初稿（請重寫，不要直接複製）：\n"
        f"{baseline_draft}\n\n"
        "逐字稿節錄：\n"
        f"{transcript_excerpt}"
    )
    return system_prompt, user_prompt


def split_structured_seo_sections(text: str) -> dict[str, str]:
    cleaned = strip_code_fences(text).replace("\r\n", "\n").strip()
    matches = list(re.finditer(r"^(一|二|三|四)、[^\n]+$", cleaned, flags=re.MULTILINE))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(cleaned)
        sections[match.group(1)] = cleaned[start:end].strip()
    return sections


def normalize_advanced_seo_content(content: str) -> str:
    cleaned = prune_extra_seo_sections(content)
    sections = split_structured_seo_sections(cleaned)
    if not sections:
        return cleaned

    title_lines = [line.strip() for line in sections.get("一", "").splitlines() if line.strip()]
    numbered_titles = [line for line in title_lines if re.match(r"^\d+\.\s*", line)]
    if not numbered_titles:
        raw_titles = [line for line in title_lines if line and not line.startswith("建議")]
        numbered_titles = [f"{index}. {line}" for index, line in enumerate(raw_titles[:3], start=1)]
    numbered_titles = numbered_titles[:3]

    summary_lines = [line.strip() for line in sections.get("二", "").splitlines() if line.strip()]
    summary_bullets = [
        re.sub(r"^[-*•]\s*", "", line).strip()
        for line in summary_lines
        if re.match(r"^[-*•]\s*", line)
    ]
    summary_paragraph_parts = [
        line for line in summary_lines
        if not re.match(r"^[-*•]\s*", line)
        and line not in {"核心重點：", "重點：", "摘要："}
    ]
    summary_paragraph = " ".join(summary_paragraph_parts).strip()
    if len(summary_paragraph) > 300:
        summary_paragraph = summary_paragraph[:299].rstrip("，。、；： ") + "。"
    summary_bullets = [f"- {item}" for item in summary_bullets[:3] if item]

    hashtag_matches = re.findall(r"#[0-9A-Za-z\u4e00-\u9fff_+-]+", sections.get("三", ""))
    unique_tags: list[str] = []
    for tag in hashtag_matches:
        if tag not in unique_tags:
            unique_tags.append(tag)
    hashtag_line = ",".join(unique_tags)

    chapter_lines = []
    for raw_line in sections.get("四", "").splitlines():
        line = raw_line.strip()
        if not re.match(r"^\d{2}:\d{2}(?::\d{2})?\s+", line):
            continue
        timestamp, text = line.split(" ", 1)
        text = re.sub(r"^(這段在說明什麼[:：]?\s*|這段在說明[:：]?\s*|本段在介紹[:：]?\s*|本段介紹[:：]?\s*)", "", text).strip()
        chapter_lines.append(f"{timestamp} {text}")

    blocks = [
        "一、建議標題 3 個",
        *numbered_titles,
        "",
        "二、內容摘要",
        summary_paragraph,
        "",
        *summary_bullets,
        "",
        "三、關鍵字與標籤",
        hashtag_line,
        "",
        "四、章節目錄",
        *chapter_lines,
    ]
    return "\n".join(item for item in blocks if item is not None).strip()


def looks_generic_chapter_line(line: str) -> bool:
    text = re.sub(r"^\d{2}:\d{2}(?::\d{2})?\s*", "", normalize_text(line)).strip()
    if not text:
        return True
    generic_phrases = {
        "重點整理",
        "段落重點",
        "內容摘要",
        "重點說明",
        "更多內容",
        "章節重點",
        "觀念整理",
        "延伸說明",
    }
    if text in generic_phrases:
        return True
    keyword_count = len(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{2,}", text))
    has_sentence_tone = bool(re.search(r"[。！？]", text)) or "說明" in text or "介紹" in text or "解析" in text
    return len(text) < 10 or keyword_count < 2 or not has_sentence_tone


def advanced_seo_quality_issues(content: str, baseline_draft: str, expected_chapters: int) -> list[str]:
    cleaned = prune_extra_seo_sections(content)
    sections = split_structured_seo_sections(cleaned)
    issues: list[str] = []

    for key in ("一", "二", "三", "四"):
        if key not in sections:
            issues.append(f"缺少第 {key} 段。")

    title_lines = [line.strip() for line in sections.get("一", "").splitlines() if re.match(r"^\d+\.\s*", line.strip())]
    if len(title_lines) < 3:
        issues.append("建議標題不足 3 個。")

    summary_lines = [line.strip() for line in sections.get("二", "").splitlines() if line.strip().startswith("-")]
    if len(summary_lines) < 3:
        issues.append("內容摘要與鉤子不是完整 3 點條列。")
    summary_char_count = len("".join(line.lstrip("- ").strip() for line in summary_lines))
    if summary_char_count > 300:
        issues.append("內容摘要與鉤子超過 300 字。")

    hashtag_text = re.sub(r"\s+", "", sections.get("三", ""))
    hashtags = [item for item in hashtag_text.split(",") if item]
    if len(hashtags) < 3 or not all(item.startswith("#") for item in hashtags):
        issues.append("關鍵字及標籤沒有正確輸出成 hashtags。")

    chapter_lines = [
        line.strip()
        for line in sections.get("四", "").splitlines()
        if re.match(r"^\d{2}:\d{2}(?::\d{2})?\s+", line.strip())
    ]
    min_chapters = max(3, min(expected_chapters or 3, 5))
    if len(chapter_lines) < min_chapters:
        issues.append("章節目錄數量太少。")
    elif sum(1 for line in chapter_lines if looks_generic_chapter_line(line)) >= max(1, len(chapter_lines) // 2):
        issues.append("章節目錄仍然太像關鍵字拼接，缺少實際內容說明。")

    similarity = SequenceMatcher(
        None,
        re.sub(r"\s+", "", normalize_text(cleaned)),
        re.sub(r"\s+", "", normalize_text(baseline_draft)),
    ).ratio()
    if similarity >= 0.82:
        issues.append("整體內容和基礎草稿太像，沒有真正重寫。")

    if "補充提醒" in cleaned or "五、" in cleaned or "六、" in cleaned:
        issues.append("出現多餘段落或補充提醒。")

    return issues


def build_advanced_seo_retry_prompt(
    original_user_prompt: str,
    first_pass: str,
    issues: list[str],
) -> tuple[str, str]:
    retry_system_prompt = (
        "你現在在做第二輪精修。"
        "上一版太像草稿或章節過於空泛，請整份重寫，不要只修幾個字。"
        "你必須讓這份成品更像人類內容編輯寫出來的版本，保留事實，但提升可讀性、吸引力與內容密度。"
    )
    retry_user_prompt = (
        f"{original_user_prompt}\n\n"
        "上一版不合格，請整份重新輸出。\n"
        "這次必須修正的問題：\n"
        f"{chr(10).join(f'- {issue}' for issue in issues[:8])}\n\n"
        "上一版內容如下，請不要沿用原句：\n"
        f"{first_pass}"
    )
    return retry_system_prompt, retry_user_prompt


def generate_advanced_seo_text(
    transcript_text: str,
    segments: list[dict[str, Any]],
    base_title: str,
    source_url: str | None,
    config: AdvancedSeoConfig,
) -> str:
    system_prompt, user_prompt = build_advanced_seo_prompt(
        transcript_text=transcript_text,
        segments=segments,
        base_title=base_title,
        source_url=source_url,
    )
    baseline_draft = build_seo_text(
        transcript_text=transcript_text,
        segments=segments,
        base_title=base_title,
        source_url=source_url,
    )
    expected_chapters = len(build_chapters(segments, base_title))

    def request_content(system_text: str, user_text: str) -> str:
        if config.provider == "ollama":
            return call_ollama_chat(config, system_text, user_text)
        if config.provider in OPENAI_STYLE_PROVIDERS:
            return call_openai_style_chat(config, system_text, user_text)
        if config.provider in GEMINI_STYLE_PROVIDERS:
            return call_gemini_generate_content(config, system_text, user_text)
        raise RuntimeError("目前不支援這個進階 SEO 提供者。")

    content = prune_extra_seo_sections(request_content(system_prompt, user_prompt))
    quality_issues = advanced_seo_quality_issues(content, baseline_draft, expected_chapters)
    if quality_issues:
        retry_system_prompt, retry_user_prompt = build_advanced_seo_retry_prompt(
            user_prompt,
            content,
            quality_issues,
        )
        content = prune_extra_seo_sections(request_content(retry_system_prompt, retry_user_prompt))

    if source_url and "影片來源：" not in content:
        content += f"\n\n影片來源：{source_url}"
    return content + "\n"


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
    empty_chunk_count = 0

    try:
        for chunk_path, offset in chunks:
            speech_windows = detect_speech_windows(chunk_path)

            result = model.transcribe(
                chunk_path,
                language=None,
                task="transcribe",
                fp16=USE_FP16,
                verbose=False,
            )
            chunk_segments = as_iterable_list(result.get("segments"))
            if speech_windows:
                chunk_segments = apply_vad_filter_with_fallback(chunk_segments, speech_windows)
            if not chunk_segments:
                empty_chunk_count += 1
                continue

            for segment in chunk_segments:
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

    if not combined_segments:
        if empty_chunk_count:
            raise RuntimeError("長影音分段轉錄後沒有辨識到可用語音內容，請確認影片是否有清楚人聲，或改用較短片段再試一次。")
        raise RuntimeError("長影音分段轉錄失敗，沒有取得任何字幕片段。")

    combined_segments.sort(key=lambda item: (float(item["start"]), float(item["end"])))
    return combined_segments


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
) -> tuple[str, str, str, list[dict[str, Any]]]:
    cleaned_segments = clean_segments(segments)
    srt_content = segments_to_srt(cleaned_segments, seg_mode)
    transcript_text = segments_to_transcript_text(cleaned_segments, seg_mode)
    base_title = original_title or Path(filename).stem
    merged_segments = merge_segments(cleaned_segments, seg_mode)
    seo_text = build_seo_text(transcript_text, merged_segments, base_title, source_url)
    return srt_content, transcript_text, seo_text, merged_segments


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
            advanced_seo_config = current.advanced_seo_config

        set_job_status_note(job_id, "正在載入 Whisper 模型，第一次使用可能需要稍候。")
        model = get_whisper_model()
        set_job_status_note(job_id, "Whisper 正在辨識音訊內容。")
        print(f"[Job {job_id[:8]}] 開始轉錄：{file_path}")
        duration = probe_media_duration(file_path) or 0.0
        if duration >= 1200:
            print(f"[Job {job_id[:8]}] 偵測到長影音，改用分段轉錄流程（約 {int(duration)} 秒）。")
            set_job_status_note(job_id, "偵測到長影音，正在分段轉錄並整合時間軸。")
            segments = transcribe_media_in_chunks(model, file_path)
        else:
            speech_windows = detect_speech_windows(file_path)
            result = model.transcribe(
                file_path,
                language=None,
                task="transcribe",
                fp16=USE_FP16,
                verbose=False,
            )
            segments = as_iterable_list(result.get("segments"))
            if speech_windows:
                segments = apply_vad_filter_with_fallback(segments, speech_windows)

        if not segments:
            raise RuntimeError("這段音訊沒有辨識到可用語音內容，請確認檔案是否有聲音、語言是否清楚，或改用較短片段再試一次。")
        set_job_status_note(job_id, "正在整理字幕、轉錄稿與基礎 SEO.txt。")
        srt_content, transcript_text, seo_text, merged_segments = build_job_outputs(
            filename=filename,
            source_type=source_type,
            source_url=source_url,
            original_title=original_title,
            segments=segments,
            seg_mode=seg_mode,
        )

        advanced_seo_text = None
        advanced_seo_error = None
        advanced_provider = advanced_seo_config.provider if advanced_seo_config else None
        advanced_model = advanced_seo_config.model if advanced_seo_config else None

        if advanced_seo_config:
            set_job_status_note(
                job_id,
                f"已完成基礎輸出，正在使用 {provider_label(advanced_seo_config.provider)} 的 {advanced_seo_config.model} 整理進階SEO.txt。",
            )
            try:
                advanced_seo_text = generate_advanced_seo_text(
                    transcript_text=transcript_text,
                    segments=merged_segments,
                    base_title=original_title or Path(filename).stem,
                    source_url=source_url,
                    config=advanced_seo_config,
                )
            except Exception as exc:
                advanced_seo_error = str(exc)
                print(f"[Job {job_id[:8]}] 進階 SEO 生成失敗：{exc}")

        with jobs_lock:
            current = jobs.get(job_id)
            if current and current.status != "cancelled":
                current.status = "done"
                current.srt = srt_content
                current.transcript_text = transcript_text
                current.seo_text = seo_text
                current.advanced_seo_text = advanced_seo_text
                current.advanced_seo_requested = advanced_seo_config is not None
                current.advanced_seo_provider = advanced_provider
                current.advanced_seo_model = advanced_model
                current.advanced_seo_error = advanced_seo_error
                current.segment_count = len(segments)
                if advanced_seo_text:
                    current.status_note = "全部輸出已完成，包含進階SEO.txt。"
                elif advanced_seo_config:
                    current.status_note = "字幕與基礎 SEO 已完成，但進階SEO.txt 生成失敗。"
                else:
                    current.status_note = "字幕、轉錄稿與 SEO.txt 已完成。"

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

    if requests is not None:
        results["requests"] = {
            "ok": True,
            "label": "requests",
            "version": getattr(requests, "__version__", ""),
            "note": "可用於連接本地或雲端模型服務",
        }
    else:
        results["requests"] = {"ok": False, "label": "requests", "version": None, "note": "尚未安裝"}

    try:
        import silero_vad  # type: ignore
    except ImportError:
        results["silero_vad"] = {
            "ok": False,
            "label": "silero-vad",
            "version": None,
            "note": "尚未安裝，VAD 濾波器目前不會生效。",
        }
    except Exception as exc:
        results["silero_vad"] = {
            "ok": False,
            "label": "silero-vad",
            "version": None,
            "note": f"載入失敗，請重新執行 start.bat 修復 PyTorch / torchaudio：{exc}",
        }
    else:
        results["silero_vad"] = {
            "ok": True,
            "label": "silero-vad",
            "version": getattr(silero_vad, "__version__", ""),
            "note": "已啟用 Silero VAD，可過濾無語音或異常片段。",
        }

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
    if not results["requests"]["ok"]:
        missing_pip.append("requests")
    if not results["silero_vad"]["ok"]:
        missing_pip.append("silero-vad")

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
    advanced_seo_config: AdvancedSeoConfig | None = None,
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
            advanced_seo_requested=advanced_seo_config is not None,
            advanced_seo_provider=advanced_seo_config.provider if advanced_seo_config else None,
            advanced_seo_model=advanced_seo_config.model if advanced_seo_config else None,
            status_note="正在排入 Whisper 轉錄工作。",
            advanced_seo_config=advanced_seo_config,
        )

    thread = threading.Thread(target=run_whisper, args=(job_id, file_path, seg_mode), daemon=True)
    thread.start()
    return job_id


setup_ffmpeg()
DEVICE, USE_FP16 = detect_device()


@app.route("/")
def index():
    return send_file(INDEX_FILE)


@app.route("/llm/providers")
def llm_providers():
    return jsonify(
        {
            "providers": list_llm_provider_options(),
            "advanced_seo_filename": ADVANCED_SEO_FILENAME,
        }
    )


@app.route("/llm/connect", methods=["POST"])
def llm_connect():
    data = request.get_json(silent=True) or {}
    provider = normalize_text(data.get("provider", "")).lower()
    if provider not in LLM_PROVIDER_DEFINITIONS:
        return jsonify({"error": "請先選擇有效的模型服務商。"}), 400

    base_url = normalize_provider_base_url(provider, data.get("base_url", ""))
    api_key = normalize_text(data.get("api_key", "")) or None
    model = normalize_provider_model(provider, data.get("model", ""))
    activate_model = normalize_text(data.get("activate_model", "")).lower() in {"1", "true", "yes", "on"}

    if needs_api_key(provider) and not api_key:
        return jsonify({"error": f"{provider_label(provider)} 需要 API Key。"}), 400

    config = AdvancedSeoConfig(
        provider=provider,
        base_url=base_url,
        model=model or "pending",
        api_key=api_key,
    )

    try:
        model_options = list_model_options_for_provider(config)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

    models = extract_model_ids(model_options)
    if not models:
        return jsonify({"error": "已連線成功，但目前讀不到可用模型。請先確認服務端已載入模型。"}), 400

    selected_model = pick_default_model(provider, model, model_options)
    model_message = ""
    loaded_model = ""

    if activate_model and selected_model:
        try:
            applied = activate_provider_model(
                AdvancedSeoConfig(
                    provider=provider,
                    base_url=base_url,
                    model=selected_model,
                    api_key=api_key,
                )
            )
            model_message = str(applied.get("message") or "")
            loaded_model = str(applied.get("loaded_model") or selected_model)
            if provider == "lmstudio":
                refreshed_options = list_model_options_for_provider(
                    AdvancedSeoConfig(
                        provider=provider,
                        base_url=base_url,
                        model=selected_model,
                        api_key=api_key,
                    )
                )
                if refreshed_options:
                    model_options = refreshed_options
                    models = extract_model_ids(model_options)
                    selected_model = pick_default_model(provider, selected_model, model_options)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

    return jsonify(
        {
            "ok": True,
            "provider": provider,
            "provider_label": provider_label(provider),
            "base_url": base_url,
            "selected_model": selected_model,
            "models": models,
            "model_options": model_options,
            "model_message": model_message,
            "loaded_model": loaded_model or selected_model,
            "supports_model_switch": True,
            "auto_load_on_select": provider == "lmstudio",
            "advanced_seo_filename": ADVANCED_SEO_FILENAME,
        }
    )


@app.route("/upload", methods=["POST"])
def upload():
    seg_mode = request.form.get("seg_mode", "standard")
    if seg_mode not in {"fine", "standard", "coarse"}:
        seg_mode = "standard"

    try:
        advanced_seo_config = extract_advanced_seo_config_from_form(request.form)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

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
            advanced_seo_config=advanced_seo_config,
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

    save_path_job_id = str(uuid.uuid4())
    save_path = str(UPLOAD_DIR / f"{save_path_job_id}.{ext}")
    file.save(save_path)
    job_id = create_job(
        filename=file.filename,
        file_path=save_path,
        seg_mode=seg_mode,
        source_type="upload",
        advanced_seo_config=advanced_seo_config,
    )
    print(f"[Upload] 建立工作 {job_id[:8]}，檔案：{file.filename}，模式：{seg_mode}")
    return jsonify({"job_id": job_id})


@app.route("/status/<job_id>")
def status(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)

    if not job:
        return jsonify({"status": "not_found"}), 404

    payload: dict[str, Any] = {"status": job.status, "message": job.status_note}
    if job.status == "done":
        payload.update(
            {
                "srt": job.srt,
                "filename": build_download_filename(job, "srt"),
                "text_filename": build_download_filename(job, "txt"),
                "seo_filename": build_download_filename(job, "seo"),
                "advanced_seo_filename": build_download_filename(job, "advanced-seo") if job.advanced_seo_text else None,
                "advanced_seo_available": bool(job.advanced_seo_text),
                "advanced_seo_requested": job.advanced_seo_requested,
                "advanced_seo_provider": provider_label(job.advanced_seo_provider or "") if job.advanced_seo_provider else None,
                "advanced_seo_model": job.advanced_seo_model,
                "advanced_seo_error": job.advanced_seo_error,
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

    kind = str(kind).lower()

    if kind == "srt" and job.srt:
        filename = build_download_filename(job, "srt")
        content = job.srt
    elif kind == "txt" and job.transcript_text:
        filename = build_download_filename(job, "txt")
        content = job.transcript_text
    elif kind == "seo" and job.seo_text:
        filename = build_download_filename(job, "seo")
        content = job.seo_text
    elif kind in {"advanced-seo", "advanced_seo", "adv-seo"} and job.advanced_seo_text:
        filename = build_download_filename(job, "advanced-seo")
        content = job.advanced_seo_text
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


ADVANCED_SEO_SECTION_TITLES = {
    "一": "建議標題 3 個",
    "二": "內容摘要",
    "三": "關鍵字與標籤",
    "四": "章節目錄",
}

LLM_LONG_CONTEXT_THRESHOLD = 6500
LLM_CONTEXT_CHUNK_CHARS = 1800
LLM_CONTEXT_CHUNK_LIMIT = 8


def build_summary_paragraph(transcript_text: str, base_title: str = "", max_chars: int = 300) -> str:
    cleaned_text = clean_transcript_text(transcript_text)
    sentences = [item.strip() for item in sentence_split(cleaned_text) if item.strip()]
    selected: list[str] = []
    current_length = 0

    for sentence in sentences:
        normalized = polish_traditional_punctuation(sentence.strip())
        if not normalized or len(normalized) < 12:
            continue
        next_length = current_length + len(normalized)
        if selected and next_length > max_chars:
            break
        selected.append(normalized.rstrip("。！？") + "。")
        current_length += len(selected[-1])
        if len(selected) >= 3 and current_length >= 160:
            break

    if not selected:
        keywords = top_keywords(cleaned_text, base_title, limit=4)
        keyword_text = "、".join(keywords[:3]) if keywords else normalize_text(base_title) or "影片重點"
        return shorten_sentence(
            f"這支影片整理了 {keyword_text} 的核心內容，適合延伸成字幕、轉錄稿與 YouTube 內容規劃。",
            max_chars,
        )

    paragraph = "".join(selected)
    if len(paragraph) > max_chars:
        paragraph = paragraph[: max_chars - 1].rstrip("，。、；： ") + "。"
    return paragraph


def build_summary_and_hook_bullets(transcript_text: str, base_title: str = "") -> list[str]:
    cleaned_text = clean_transcript_text(transcript_text)
    keywords = top_keywords(cleaned_text, base_title, limit=6)
    sentences = [item.strip() for item in sentence_split(cleaned_text) if item.strip()]
    bullets: list[str] = []

    if keywords:
        bullets.append(
            shorten_sentence(
                f"聚焦 {'、'.join(keywords[:3])} 等主題，方便後續整理字幕、說明欄與 SEO 內容。",
                70,
            )
        )

    for sentence in sentences:
        normalized = polish_traditional_punctuation(sentence)
        if not normalized or len(normalized) < 10:
            continue
        if any(normalized in existing or existing in normalized for existing in bullets):
            continue
        bullets.append(shorten_sentence(normalized, 72))
        if len(bullets) >= 3:
            break

    if not bullets:
        fallback = normalize_text(base_title) or "影片重點整理"
        bullets = [
            shorten_sentence(f"{fallback} 已整理成可直接延伸使用的轉錄與內容摘要。", 70),
            shorten_sentence("可搭配字幕、章節與關鍵字輸出，方便後續上架與編修。", 70),
        ]

    unique_bullets: list[str] = []
    for bullet in bullets:
        if bullet and bullet not in unique_bullets:
            unique_bullets.append(bullet)
    return [f"- {item}" for item in unique_bullets[:3]]


def build_chapter_description(text: str, fallback: str) -> str:
    cleaned = clean_transcript_text(text)
    sentences = [item.strip() for item in sentence_split(cleaned) if item.strip()]
    keywords = top_keywords(cleaned, "", limit=4)

    for sentence in sentences:
        normalized = polish_traditional_punctuation(sentence)
        normalized = re.sub(r"^(這段|本段|接著|最後|然後|這裡|這邊)(在)?", "", normalized).strip("，。 ")
        if len(normalized) >= 12:
            return shorten_sentence(normalized.rstrip("。！？") + "。", 60)

    if keywords:
        return shorten_sentence(f"{'、'.join(keywords[:3])} 是這個段落的主要重點。", 60)
    return fallback


def build_chapters(segments: list[dict[str, Any]], seed_title: str) -> list[tuple[str, str]]:
    if not segments:
        return [("00:00", "影片開場與主題說明。")]

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
        title = build_chapter_description(chunk_text, f"整理本段第 {len(chapters) + 1} 個重點。")
        chapters.append((format_hms(start), title))

    if not chapters or chapters[0][0] != "00:00":
        chapters.insert(0, ("00:00", "影片開場與主題說明。"))

    unique: list[tuple[str, str]] = []
    seen_times: set[str] = set()
    for timestamp, title in chapters:
        if timestamp in seen_times:
            continue
        seen_times.add(timestamp)
        unique.append((timestamp, title))
    return unique[:8]


def build_seo_text(
    transcript_text: str,
    segments: list[dict[str, Any]],
    base_title: str,
    source_url: str | None = None,
) -> str:
    keywords = top_keywords(transcript_text, base_title, limit=12)
    title_suggestions = build_title_suggestions(base_title, keywords)
    summary_paragraph = build_summary_paragraph(transcript_text, base_title, 300)
    summary_bullets = build_summary_and_hook_bullets(transcript_text, base_title)
    chapters = build_chapters(segments, base_title)
    hashtag_line = build_hashtag_line(keywords, limit=10)

    lines = [
        "YouTube SEO 建議稿",
        "====================",
        "",
        "一、建議標題 3 個",
        *[f"{index}. {title}" for index, title in enumerate(title_suggestions, start=1)],
        "",
        "二、內容摘要",
        summary_paragraph,
        "",
        *summary_bullets,
        "",
        "三、關鍵字與標籤",
        hashtag_line,
        "",
        "四、章節目錄",
        *[f"{timestamp} {title}" for timestamp, title in chapters],
    ]

    if source_url:
        lines.extend(["", f"影片來源：{source_url}"])

    return "\n".join(lines).strip() + "\n"


def split_segments_for_llm(segments: list[dict[str, Any]], max_chars: int = LLM_CONTEXT_CHUNK_CHARS) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    current_segments: list[dict[str, Any]] = []
    current_chars = 0

    for segment in segments:
        text = clean_transcript_text(str(segment.get("text") or ""))
        if not text:
            continue
        extra = len(text) + 1
        if current_segments and current_chars + extra > max_chars:
            chunk_text = " ".join(clean_transcript_text(str(item.get("text") or "")) for item in current_segments).strip()
            chunks.append(
                {
                    "start": float(current_segments[0]["start"]),
                    "end": float(current_segments[-1]["end"]),
                    "text": chunk_text,
                }
            )
            current_segments = []
            current_chars = 0

        current_segments.append(segment)
        current_chars += extra

    if current_segments:
        chunk_text = " ".join(clean_transcript_text(str(item.get("text") or "")) for item in current_segments).strip()
        chunks.append(
            {
                "start": float(current_segments[0]["start"]),
                "end": float(current_segments[-1]["end"]),
                "text": chunk_text,
            }
        )

    if len(chunks) <= LLM_CONTEXT_CHUNK_LIMIT:
        return chunks

    merged: list[dict[str, Any]] = []
    group_size = max(1, math.ceil(len(chunks) / LLM_CONTEXT_CHUNK_LIMIT))
    for index in range(0, len(chunks), group_size):
        group = chunks[index:index + group_size]
        merged.append(
            {
                "start": float(group[0]["start"]),
                "end": float(group[-1]["end"]),
                "text": "\n".join(item["text"] for item in group if item["text"]).strip(),
            }
        )
    return merged[:LLM_CONTEXT_CHUNK_LIMIT]


def request_provider_text(
    config: AdvancedSeoConfig,
    system_text: str,
    user_text: str,
    *,
    max_tokens: int = 1400,
    temperature: float = 0.3,
) -> str:
    ensure_requests_available()

    if config.provider == "ollama":
        payload = {
            "model": config.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_text},
            ],
            "options": {
                "temperature": temperature,
            },
        }
        response = requests.post(
            f"{config.base_url}/api/chat",
            json=payload,
            timeout=300,
        )
        if not response.ok:
            raise RuntimeError(f"Ollama 生成失敗：{response_error_message(response)}")
        data = response.json()
        message = data.get("message") or {}
        content = content_blocks_to_text(message.get("content")) if isinstance(message, dict) else ""
        if not content and isinstance(message, dict):
            content = str(message.get("content") or "").strip()
        if not content:
            raise RuntimeError("Ollama 沒有回傳可用內容。")
        return strip_code_fences(content)

    if config.provider in OPENAI_STYLE_PROVIDERS:
        if config.provider == "lmstudio":
            timeout_seconds = 480 if max_tokens >= 1000 else 300
        else:
            timeout_seconds = 180
        return request_openai_style_text(
            config,
            system_text,
            user_text,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
        )

    if config.provider in GEMINI_STYLE_PROVIDERS:
        model_name = config.model if str(config.model).startswith("models/") else f"models/{config.model}"
        payload = {
            "systemInstruction": {
                "parts": [{"text": system_text}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_text}],
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        response = requests.post(
            f"{config.base_url}/{model_name}:generateContent",
            params={"key": config.api_key},
            json=payload,
            timeout=240,
        )
        if not response.ok:
            raise RuntimeError(f"{provider_label(config.provider)} 生成失敗：{response_error_message(response)}")
        data = response.json()
        candidates = as_iterable_list(data.get("candidates"))
        parts: list[str] = []
        if candidates and isinstance(candidates[0], dict):
            content = candidates[0].get("content") or {}
            for item in as_iterable_list(content.get("parts")):
                if isinstance(item, dict) and item.get("text"):
                    parts.append(str(item["text"]))
        content = "\n".join(piece for piece in parts if piece).strip()
        if not content:
            raise RuntimeError(f"{provider_label(config.provider)} 沒有回傳可用內容。")
        return strip_code_fences(content)

    raise RuntimeError("目前不支援這個進階 SEO 提供者。")


def build_chunk_digest_prompts(
    chunk: dict[str, Any],
    index: int,
    total: int,
    base_title: str,
) -> tuple[str, str]:
    system_prompt = (
        "你是繁體中文內容編輯。請只整理這一段逐字稿的可用重點，不要做整支影片結論。"
        "輸出固定四行：摘要、重點、關鍵字、章節。"
    )
    user_prompt = (
        f"影片標題：{normalize_text(base_title) or '未命名影片'}\n"
        f"目前是第 {index} / {total} 段，時間約 {format_hms(float(chunk['start']))} 到 {format_hms(float(chunk['end']))}。\n\n"
        "請輸出以下格式：\n"
        "摘要：80 到 120 字，直接描述這一段的內容與價值。\n"
        "重點：- ... / - ... 兩點即可。\n"
        "關鍵字：關鍵字1,關鍵字2,關鍵字3\n"
        "章節：一句直接點出段落重點，不要用「這段在說明」「本段介紹」這類字眼。\n\n"
        f"逐字稿：\n{chunk['text']}"
    )
    return system_prompt, user_prompt


def build_long_context_digest(
    transcript_text: str,
    segments: list[dict[str, Any]],
    base_title: str,
    config: AdvancedSeoConfig,
) -> str:
    llm_chunks = split_segments_for_llm(segments)
    digests: list[str] = []

    for index, chunk in enumerate(llm_chunks, start=1):
        system_prompt, user_prompt = build_chunk_digest_prompts(chunk, index, len(llm_chunks), base_title)
        digest = request_provider_text(
            config,
            system_prompt,
            user_prompt,
            max_tokens=500,
            temperature=0.2,
        )
        digests.append(
            f"【第 {index} 段｜{format_hms(float(chunk['start']))} - {format_hms(float(chunk['end']))}】\n{digest.strip()}"
        )

    transcript_excerpt = build_transcript_excerpt(transcript_text, max_chars=1200)
    return "\n\n".join(digests + [f"【補充逐字稿節錄】\n{transcript_excerpt}"]).strip()


def build_advanced_seo_prompt(
    transcript_text: str,
    segments: list[dict[str, Any]],
    base_title: str,
    source_url: str | None = None,
    *,
    context_reference: str | None = None,
) -> tuple[str, str]:
    keywords = top_keywords(transcript_text, base_title, limit=12)
    chapters = build_chapters(segments, base_title)
    summary_paragraph = build_summary_paragraph(transcript_text, base_title, 300)
    summary_bullets = build_summary_and_hook_bullets(transcript_text, base_title)
    hashtag_line = build_hashtag_line(keywords, limit=10)
    baseline_draft = build_seo_text(
        transcript_text=transcript_text,
        segments=segments,
        base_title=base_title,
        source_url=source_url,
    )
    chapter_outline = "\n".join(f"{timestamp} {title}" for timestamp, title in chapters)
    keyword_text = "、".join(keywords[:10]) if keywords else "Whisper、字幕轉錄、YouTube"
    title_seed = normalize_text(base_title) or "未命名影片"
    context_body = context_reference or build_transcript_excerpt(transcript_text, max_chars=4200)

    system_prompt = (
        "你是資深的繁體中文 YouTube 內容編輯與 SEO 文案師。"
        "你要把逐字稿整理成可直接貼上使用的進階 SEO 內容。"
        "全文一律使用繁體中文，但 OpenAI、ChatGPT、Whisper、YouTube、SEO、GPU、CUDA、NVIDIA、PyTorch、API、LLM 等專有名詞必須保持正確英文。"
        "不要照抄草稿，不要輸出補充提醒、免責聲明、第五段、第六段、Markdown 程式碼框或表格。"
        "章節目錄請直接講重點，不要出現「這段在說明什麼」「本段介紹」這種句型。"
    )

    user_prompt = (
        "請根據以下素材，重寫成較像人工內容編輯完成的進階 SEO 檔。\n\n"
        "輸出格式必須完全照下面四段，不可多也不可少：\n"
        "一、建議標題 3 個\n"
        "1. ...\n"
        "2. ...\n"
        "3. ...\n\n"
        "二、內容摘要\n"
        "先寫一段約 300 字的摘要，再用條列式列出核心重點。\n"
        "- ...\n"
        "- ...\n"
        "- ...\n\n"
        "三、關鍵字與標籤\n"
        "#關鍵字,#關鍵字,#關鍵字\n\n"
        "四、章節目錄\n"
        "00:00 直接描述這段的重點內容。\n\n"
        "寫作規則：\n"
        "- 第二段標題固定叫做「內容摘要」，不要寫成「內容摘要與鉤子」。\n"
        "- 第二段開頭先給一段約 300 字的摘要，接著再列出條列重點；不要出現「第一點」「第二點」「第三點」這種文字。\n"
        "- 第三段標題固定叫做「關鍵字與標籤」，內容只能是一行 hashtags。\n"
        "- 第四段請直接講每個章節的重點，不要出現「這段在說明什麼」或類似句型。\n"
        "- 標題三個方向必須有差異，不要只是換詞。\n"
        "- 可以參考草稿，但請重寫成較自然、資訊密度更高的版本。\n\n"
        f"原始標題：{title_seed}\n"
        f"來源網址：{source_url or '無'}\n"
        f"關鍵字候選：{keyword_text}\n\n"
        "基礎摘要草稿：\n"
        f"{summary_paragraph}\n"
        f"{chr(10).join(summary_bullets)}\n\n"
        "基礎 hashtags 草稿：\n"
        f"{hashtag_line}\n\n"
        "基礎章節草稿：\n"
        f"{chapter_outline or '00:00 影片開場與主題說明。'}\n\n"
        "基礎 SEO 初稿（請重寫，不要照抄）：\n"
        f"{baseline_draft}\n\n"
        "內容素材：\n"
        f"{context_body}"
    )
    return system_prompt, user_prompt


def prune_extra_seo_sections(text: str) -> str:
    cleaned = strip_code_fences(text).replace("\r\n", "\n").strip()
    matches = list(re.finditer(r"^(一|二|三|四|五|六)、[^\n]+$", cleaned, flags=re.MULTILINE))
    if not matches:
        cleaned = re.sub(r"(?ms)^補充提醒.*$", "", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    kept_sections: list[str] = []
    for index, match in enumerate(matches):
        key = match.group(1)
        if key not in {"一", "二", "三", "四"}:
            continue
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(cleaned)
        kept_sections.append(cleaned[start:end].strip())
    return "\n\n".join(section for section in kept_sections if section).strip()


def split_structured_seo_sections(text: str) -> dict[str, str]:
    cleaned = strip_code_fences(text).replace("\r\n", "\n").strip()
    matches = list(re.finditer(r"^(一|二|三|四)、[^\n]+$", cleaned, flags=re.MULTILINE))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(cleaned)
        sections[match.group(1)] = cleaned[start:end].strip()
    return sections


def looks_generic_chapter_line(line: str) -> bool:
    text = re.sub(r"^\d{2}:\d{2}(?::\d{2})?\s*", "", normalize_text(line)).strip()
    if not text:
        return True
    if any(token in text for token in ("這段在說明", "本段在說明", "這段在介紹", "本段介紹")):
        return True
    generic_phrases = {
        "重點整理",
        "段落重點",
        "內容摘要",
        "重點說明",
        "更多內容",
        "章節重點",
        "觀念整理",
        "延伸說明",
    }
    if text in generic_phrases:
        return True
    if len(text) < 10:
        return True
    has_sentence_tone = bool(re.search(r"[。！？]", text)) or any(word in text for word in ("說明", "介紹", "解析", "整理", "聚焦", "示範", "比較", "拆解", "統整", "更新"))
    return not has_sentence_tone


def advanced_seo_quality_issues(content: str, baseline_draft: str, expected_chapters: int) -> list[str]:
    cleaned = prune_extra_seo_sections(content)
    sections = split_structured_seo_sections(cleaned)
    issues: list[str] = []

    for key in ("一", "二", "三", "四"):
        if key not in sections:
            issues.append(f"缺少第 {key} 段。")

    title_lines = [line.strip() for line in sections.get("一", "").splitlines() if re.match(r"^\d+\.\s*", line.strip())]
    if len(title_lines) < 3:
        issues.append("建議標題不足 3 個。")

    summary_section = sections.get("二", "")
    summary_lines = [line.strip() for line in summary_section.splitlines() if line.strip()]
    summary_bullets = [line for line in summary_lines if line.startswith("-")]
    summary_paragraph_lines = [line for line in summary_lines if not line.startswith("-")]
    summary_paragraph = " ".join(summary_paragraph_lines)
    if not summary_paragraph:
        issues.append("內容摘要缺少摘要段落。")
    if len(summary_paragraph) > 360:
        issues.append("內容摘要的摘要段落過長。")
    if len(summary_paragraph) < 80:
        issues.append("內容摘要的摘要段落過短。")
    if len(summary_bullets) < 2:
        issues.append("內容摘要缺少核心重點條列。")
    if re.search(r"第[一二三四五六七八九十]點|第一點|第二點|第三點", summary_section):
        issues.append("內容摘要仍出現第一點、第二點這類字眼。")

    hashtag_lines = [line.strip() for line in sections.get("三", "").splitlines() if line.strip()]
    hashtag_text = "".join(hashtag_lines)
    hashtags = [item for item in hashtag_text.split(",") if item]
    if len(hashtag_lines) != 1 or len(hashtags) < 3 or not all(item.startswith("#") for item in hashtags):
        issues.append("關鍵字與標籤沒有正確輸出成單行 hashtags。")

    chapter_lines = [
        line.strip()
        for line in sections.get("四", "").splitlines()
        if re.match(r"^\d{2}:\d{2}(?::\d{2})?\s+", line.strip())
    ]
    min_chapters = max(3, min(expected_chapters or 3, 5))
    if len(chapter_lines) < min_chapters:
        issues.append("章節目錄數量太少。")
    elif sum(1 for line in chapter_lines if looks_generic_chapter_line(line)) >= max(1, len(chapter_lines) // 2):
        issues.append("章節目錄仍然太像模板或關鍵字拼接。")

    similarity = SequenceMatcher(
        None,
        re.sub(r"\s+", "", normalize_text(cleaned)),
        re.sub(r"\s+", "", normalize_text(baseline_draft)),
    ).ratio()
    if similarity >= 0.86:
        issues.append("整體內容和基礎草稿太像，沒有真正重寫。")

    if any(token in cleaned for token in ("補充提醒", "五、", "六、", "內容摘要與鉤子", "這段在說明什麼")):
        issues.append("仍出現不該保留的舊格式。")

    return issues


def build_advanced_seo_retry_prompt(
    original_user_prompt: str,
    first_pass: str,
    issues: list[str],
) -> tuple[str, str]:
    retry_system_prompt = (
        "你現在在做第二輪精修。上一版還保留舊格式或內容太像草稿，請整份重寫。"
        "請讓它更像真的內容編輯寫出的 YouTube SEO 成品。"
    )
    retry_user_prompt = (
        f"{original_user_prompt}\n\n"
        "上一版需要整份重寫，必須修正的問題：\n"
        f"{chr(10).join(f'- {issue}' for issue in issues[:8])}\n\n"
        "上一版內容如下，請不要沿用原句：\n"
        f"{first_pass}"
    )
    return retry_system_prompt, retry_user_prompt


def generate_advanced_seo_text(
    transcript_text: str,
    segments: list[dict[str, Any]],
    base_title: str,
    source_url: str | None,
    config: AdvancedSeoConfig,
) -> str:
    if config.provider == "lmstudio":
        activate_provider_model(config)

    cleaned_transcript = clean_transcript_text(transcript_text)
    context_reference = None
    if len(cleaned_transcript) > LLM_LONG_CONTEXT_THRESHOLD:
        context_reference = build_long_context_digest(
            cleaned_transcript,
            segments,
            base_title,
            config,
        )

    use_compact_local_prompt = config.provider in {"lmstudio", "ollama"}
    if use_compact_local_prompt:
        system_prompt, user_prompt = build_compact_local_advanced_seo_prompt(
            transcript_text=cleaned_transcript,
            segments=segments,
            base_title=base_title,
            source_url=source_url,
            context_reference=context_reference,
        )
        generation_max_tokens = 1200
    else:
        system_prompt, user_prompt = build_advanced_seo_prompt(
            transcript_text=cleaned_transcript,
            segments=segments,
            base_title=base_title,
            source_url=source_url,
            context_reference=context_reference,
        )
        generation_max_tokens = 1800
    baseline_draft = build_seo_text(
        transcript_text=cleaned_transcript,
        segments=segments,
        base_title=base_title,
        source_url=source_url,
    )
    expected_chapters = len(build_chapters(segments, base_title))
    fallback_hashtag_line = build_hashtag_line(top_keywords(cleaned_transcript, base_title, limit=10), limit=10)
    fallback_chapter_lines = [f"{timestamp} {title}" for timestamp, title in build_chapters(segments, base_title)]

    try:
        raw_content = request_provider_text(
            config,
            system_prompt,
            user_prompt,
            max_tokens=generation_max_tokens,
            temperature=0.3,
        )
    except Exception as exc:
        if config.provider in {"lmstudio", "ollama"}:
            print(f"[進階SEO] 本地模型未回傳可用內容，改用規則式草稿：{exc}")
            return build_fallback_advanced_seo_text(
                transcript_text=cleaned_transcript,
                segments=segments,
                base_title=base_title,
                source_url=source_url,
                reason=str(exc),
            )
        raise

    content = normalize_advanced_seo_content(
        raw_content,
        fallback_hashtag_line=fallback_hashtag_line,
        fallback_chapter_lines=fallback_chapter_lines,
    )
    quality_issues = advanced_seo_quality_issues(content, baseline_draft, expected_chapters)
    if quality_issues:
        retry_system_prompt, retry_user_prompt = build_advanced_seo_retry_prompt(
            user_prompt,
            content,
            quality_issues,
        )
        try:
            retry_content = request_provider_text(
                config,
                retry_system_prompt,
                retry_user_prompt,
                max_tokens=generation_max_tokens,
                temperature=0.25,
            )
        except Exception as exc:
            if config.provider in {"lmstudio", "ollama"}:
                print(f"[進階SEO] 本地模型重試失敗，改用規則式草稿：{exc}")
                return build_fallback_advanced_seo_text(
                    transcript_text=cleaned_transcript,
                    segments=segments,
                    base_title=base_title,
                    source_url=source_url,
                    reason=str(exc),
                )
            raise
        content = normalize_advanced_seo_content(
            retry_content,
            fallback_hashtag_line=fallback_hashtag_line,
            fallback_chapter_lines=fallback_chapter_lines,
        )

    final_issues = advanced_seo_quality_issues(content, baseline_draft, expected_chapters)
    if final_issues and use_compact_local_prompt:
        format_system_prompt, format_user_prompt = build_advanced_seo_formatter_prompt(content)
        try:
            formatted_content = request_provider_text(
                config,
                format_system_prompt,
                format_user_prompt,
                max_tokens=min(generation_max_tokens, 900),
                temperature=0.15,
            )
        except Exception as exc:
            print(f"[進階SEO] 本地模型格式化失敗，保留目前內容：{exc}")
            formatted_content = content
        content = normalize_advanced_seo_content(
            formatted_content,
            fallback_hashtag_line=fallback_hashtag_line,
            fallback_chapter_lines=fallback_chapter_lines,
        )

    if source_url and "影片來源：" not in content:
        content += f"\n\n影片來源：{source_url}"
    return content + "\n"


def normalize_advanced_seo_content(
    content: str,
    *,
    fallback_hashtag_line: str = "",
    fallback_chapter_lines: list[str] | None = None,
) -> str:
    cleaned = prune_extra_seo_sections(content)
    sections = split_structured_seo_sections(cleaned)
    if not sections:
        cleaned = re.sub(r"內容摘要與鉤子", "內容摘要", cleaned)
        cleaned = re.sub(r"分析關鍵字及標籤", "關鍵字與標籤", cleaned)
        cleaned = re.sub(r"^(這段在說明什麼[:：]\s*|本段在說明[:：]\s*|這段主要在說[:：]\s*)", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"^(第[一二三四五六七八九十0-9]+點[:：]\s*)", "", cleaned, flags=re.MULTILINE)
        return cleaned.strip()

    title_lines = [line.strip() for line in sections.get("一", "").splitlines() if line.strip()]
    numbered_titles = [line for line in title_lines if re.match(r"^\d+\.\s*", line)]
    if not numbered_titles:
        raw_titles = [line for line in title_lines if line and "建議標題" not in line]
        numbered_titles = [f"{index}. {line}" for index, line in enumerate(raw_titles[:3], start=1)]
    numbered_titles = numbered_titles[:3]

    summary_lines = [line.strip() for line in sections.get("二", "").splitlines() if line.strip()]
    summary_paragraph_parts: list[str] = []
    summary_bullets: list[str] = []
    for line in summary_lines:
        if re.match(r"^[-*‧•]\s*", line):
            bullet = re.sub(r"^[-*‧•]\s*", "", line).strip()
            bullet = re.sub(r"^(第[一二三四五六七八九十0-9]+點[:：]\s*|重點[:：]\s*)", "", bullet)
            if bullet:
                summary_bullets.append(bullet)
            continue
        if line not in {"核心重點：", "重點：", "內容摘要："}:
            summary_paragraph_parts.append(line)
    summary_paragraph = " ".join(summary_paragraph_parts).strip()
    if len(summary_paragraph) > 300:
        summary_paragraph = summary_paragraph[:299].rstrip("，、。；：,.!? ") + "。"
    summary_bullets = [f"- {item}" for item in summary_bullets[:3] if item]

    hashtag_matches = re.findall(r"#[0-9A-Za-z\u4e00-\u9fff_+-]+", sections.get("三", ""))
    unique_tags: list[str] = []
    for tag in hashtag_matches:
        if tag not in unique_tags:
            unique_tags.append(tag)
    hashtag_line = ",".join(unique_tags)
    if not hashtag_line:
        hashtag_line = normalize_text(fallback_hashtag_line) or "#Whisper,#字幕轉錄,#YouTube"

    chapter_lines: list[str] = []
    for raw_line in sections.get("四", "").splitlines():
        line = raw_line.strip()
        if not re.match(r"^\d{2}:\d{2}(?::\d{2})?\s+", line):
            continue
        timestamp, _, body = line.partition(" ")
        body = re.sub(r"^(這段在說明什麼[:：]\s*|本段在說明[:：]\s*|這段主要在說[:：]\s*)", "", body).strip()
        if body:
            chapter_lines.append(f"{timestamp} {body}")
    if not chapter_lines:
        chapter_lines = [line.strip() for line in (fallback_chapter_lines or []) if line and line.strip()]

    result_lines = [
        "一、建議標題 3 個",
        *numbered_titles,
        "",
        "二、內容摘要",
        summary_paragraph,
        "",
        *summary_bullets,
        "",
        "三、關鍵字與標籤",
        hashtag_line,
        "",
        "四、章節目錄",
        *chapter_lines,
    ]
    return "\n".join(line for line in result_lines if line is not None).strip()


if __name__ == "__main__":
    print("=" * 42)
    print("  Whisper 字幕神器啟動中")
    print("  服務位置：http://localhost:5000")
    print("=" * 42)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
