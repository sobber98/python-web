from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


OFFICIAL_INDEX = "https://pypi.org/simple"


@dataclass(frozen=True)
class PipMirrorPreset:
    key: str
    label: str
    url: str


PIP_MIRROR_PRESETS: list[PipMirrorPreset] = [
    PipMirrorPreset("official", "PyPI 官方源", OFFICIAL_INDEX),
    PipMirrorPreset("tsinghua", "清华大学", "https://pypi.tuna.tsinghua.edu.cn/simple"),
    PipMirrorPreset("aliyun", "阿里云", "https://mirrors.aliyun.com/pypi/simple"),
    PipMirrorPreset("tencent", "腾讯云", "https://mirrors.cloud.tencent.com/pypi/simple"),
    PipMirrorPreset("ustc", "中国科学技术大学", "https://pypi.mirrors.ustc.edu.cn/simple"),
    PipMirrorPreset("custom", "自定义", ""),
]

_PRESET_BY_KEY = {preset.key: preset for preset in PIP_MIRROR_PRESETS}


def get_preset(key: str) -> PipMirrorPreset | None:
    return _PRESET_BY_KEY.get(key)


def normalize_mirror_url(url: str) -> str:
    return url.strip().rstrip("/")


def validate_mirror_url(url: str) -> tuple[bool, str]:
    raw = (url or "").strip()
    if not raw:
        return False, "自定义镜像源 URL 不能为空。"
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        return False, "镜像源 URL 必须以 http:// 或 https:// 开头。"
    if not parsed.netloc:
        return False, "镜像源 URL 缺少主机名。"
    return True, ""


def build_pip_index_args(url: str) -> list[str]:
    clean = normalize_mirror_url(url)
    if not clean:
        return []
    args = ["-i", clean]
    parsed = urlparse(clean)
    if parsed.scheme == "http" and parsed.netloc:
        args.extend(["--trusted-host", parsed.netloc])
    return args


def selector_url(selector: str, custom_url: str) -> str:
    if selector == "custom":
        return normalize_mirror_url(custom_url)
    preset = _PRESET_BY_KEY.get(selector)
    return preset.url if preset else ""