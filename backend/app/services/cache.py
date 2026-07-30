import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path


_DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache"


def _cache_dir() -> Path:
    path = Path(os.environ.get("CACHE_DIR") or _DEFAULT_CACHE_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def make_key(text: str, language: str, voice_id: str, speed: float) -> str:
    """Stable SHA-256 cache key. Language MUST be in the hash to prevent
    cross-language collisions on identical text+voice+speed inputs."""
    canonical = "\x00".join([text, language, voice_id, str(speed)])
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class CacheEntry:
    audio: bytes
    meta: dict


def exists(key: str) -> bool:
    d = _cache_dir()
    return (d / f"{key}.mp3").exists() and (d / f"{key}.json").exists()


def get(key: str) -> CacheEntry | None:
    d = _cache_dir()
    mp3_path = d / f"{key}.mp3"
    json_path = d / f"{key}.json"
    if not mp3_path.exists() or not json_path.exists():
        return None
    audio = mp3_path.read_bytes()
    meta = json.loads(json_path.read_text())
    return CacheEntry(audio=audio, meta=meta)


def put(key: str, audio: bytes, meta: dict) -> None:
    d = _cache_dir()
    (d / f"{key}.mp3").write_bytes(audio)
    (d / f"{key}.json").write_text(json.dumps(meta))
