"""plan3 の auth.py と同一内容の複製(共有機構がないため)。変更時は両方を更新する。"""
from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

import jwt
from fastapi import HTTPException, Request

_CACHE_TTL_SECONDS = 60
_cache_lock = Lock()
_cache: tuple[float, int, dict] | None = None


@dataclass(frozen=True)
class Principal:
    user_id: str
    email: str
    groups: list[str]
    is_eval: bool = False


def decode_user_jwt(token: str) -> dict:
    """Open WebUI が発行した HS256 JWT を検証する。"""
    secret = os.environ.get("USER_JWT_SECRET", "")
    if not secret:
        raise HTTPException(status_code=500, detail="USER_JWT_SECRET が未設定です")
    try:
        return jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            issuer="open-webui",
            options={"require": ["sub", "email", "exp"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="転送ユーザー JWT が不正です") from exc


def load_group_config() -> dict:
    """groups.json を mtime 追跡付きで最大 60 秒キャッシュする。"""
    global _cache
    path = Path(os.getenv("GROUPS_CONFIG", "/app/auth/groups.json"))
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"グループ設定を読めません: {path}") from exc

    now = time.monotonic()
    with _cache_lock:
        if _cache and now - _cache[0] < _CACHE_TTL_SECONDS and _cache[1] == mtime_ns:
            return _cache[2]
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=500, detail=f"グループ設定が不正です: {path}") from exc
        if not isinstance(config.get("groups"), list) or not isinstance(config.get("users"), dict):
            raise HTTPException(status_code=500, detail="groups.json の形式が不正です")
        _cache = (now, mtime_ns, config)
        return config


def all_groups() -> list[str]:
    return sorted({str(group) for group in load_group_config()["groups"] if group})


def resolve_groups(email: str) -> list[str]:
    config = load_group_config()
    allowed = set(all_groups())
    groups = sorted({str(group) for group in config["users"].get(email, []) if group in allowed})
    if not groups:
        raise HTTPException(status_code=403, detail="許可グループがありません")
    return groups


async def require_principal(request: Request) -> Principal:
    authorization = request.headers.get("Authorization", "")
    eval_token = os.environ.get("EVAL_TOKEN", "")
    if authorization.startswith("Bearer ") and eval_token:
        supplied = authorization.removeprefix("Bearer ").strip()
        if secrets.compare_digest(supplied, eval_token):
            return Principal(user_id="evaluation", email="evaluation@local", groups=all_groups(), is_eval=True)

    token = request.headers.get("X-OpenWebUI-User-Jwt", "")
    if not token:
        raise HTTPException(status_code=401, detail="署名付きユーザー JWT が必要です")
    claims = decode_user_jwt(token)
    email = str(claims["email"])
    return Principal(
        user_id=str(claims["sub"]),
        email=email,
        groups=resolve_groups(email),
    )
