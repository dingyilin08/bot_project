# -*- coding: utf-8 -*-
"""GM 永久权限与全局图片模式的 YAML 持久化。"""

import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_SHARED_LOG_DIR = Path("/opt/qq-rpg/shared/logs")


def _default_state_path() -> Path:
    """生产环境放入跨发布共享目录，本地开发则放在项目根目录。"""
    configured = os.getenv("GM_STATE_FILE")
    if configured:
        configured_path = Path(configured)
        if configured_path.is_absolute():
            return configured_path
        # 兼容早期配置的相对路径，避免它在 /releases/<版本> 下失去写权限。
        if PRODUCTION_SHARED_LOG_DIR.is_dir():
            return PRODUCTION_SHARED_LOG_DIR / configured_path.name
        return PROJECT_ROOT / configured_path
    if PRODUCTION_SHARED_LOG_DIR.is_dir():
        return PRODUCTION_SHARED_LOG_DIR / "gm_state.yaml"
    return PROJECT_ROOT / "gm_state.yaml"


STATE_PATH = _default_state_path()
_LOCK = threading.RLock()
_DEFAULT_STATE = {"version": 1, "admins": [], "image_mode_enabled": True}


class GMStateError(Exception):
    pass


def _normalize(data) -> dict:
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise GMStateError("GM 状态文件格式错误。")
    admins = []
    for value in data.get("admins", []):
        try:
            uid = int(value)
            if uid > 0 and uid not in admins:
                admins.append(uid)
        except (TypeError, ValueError):
            continue
    return {
        "version": 1,
        "admins": sorted(admins),
        "image_mode_enabled": bool(data.get("image_mode_enabled", True)),
        "updated_at": data.get("updated_at"),
    }


def load_state() -> dict:
    with _LOCK:
        if not STATE_PATH.exists():
            return dict(_DEFAULT_STATE)
        try:
            return _normalize(yaml.safe_load(STATE_PATH.read_text(encoding="utf-8")))
        except (OSError, yaml.YAMLError) as exc:
            raise GMStateError(f"无法读取 GM 状态文件：{exc}") from exc


def _save_state(state: dict) -> None:
    normalized = _normalize(state)
    normalized["updated_at"] = datetime.now(timezone.utc).isoformat()
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = STATE_PATH.with_suffix(STATE_PATH.suffix + ".tmp")
    try:
        temp_path.write_text(
            yaml.safe_dump(normalized, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        os.replace(temp_path, STATE_PATH)
        try:
            os.chmod(STATE_PATH, 0o600)
        except OSError:
            pass
    except OSError as exc:
        raise GMStateError(f"无法保存 GM 状态文件：{exc}") from exc


def is_admin(uid: int) -> bool:
    try:
        return int(uid) in load_state()["admins"]
    except (TypeError, ValueError):
        return False


def get_admin_uids() -> tuple:
    """返回当前永久管理员 UID，用于需要归属系统管理员的玩法初始化。"""
    try:
        return tuple(load_state()["admins"])
    except GMStateError:
        return ()


def grant_admin(uid: int) -> bool:
    uid = int(uid)
    if uid <= 0:
        raise GMStateError("管理员 UID 无效。")
    with _LOCK:
        state = load_state()
        if uid in state["admins"]:
            return False
        state["admins"].append(uid)
        _save_state(state)
        return True


def get_image_mode() -> bool:
    return bool(load_state()["image_mode_enabled"])


def set_image_mode(enabled: bool) -> bool:
    with _LOCK:
        state = load_state()
        changed = state["image_mode_enabled"] != bool(enabled)
        state["image_mode_enabled"] = bool(enabled)
        _save_state(state)
        return changed
