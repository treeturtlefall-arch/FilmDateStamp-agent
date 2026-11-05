"""プリセットおよびお気に入りの名前解決モジュール。"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .engine import load as load_engine
from .errors import EXIT_USAGE, AgentError

PACKAGE_DIR = Path(__file__).resolve().parent
DATA_DIR = PACKAGE_DIR / "data"
REPO_PRESETS_DIR = PACKAGE_DIR.parents[1] / "presets"
REPO_FAVORITES = PACKAGE_DIR.parents[1] / "favorites.json"

FAVORITE_WORDS = ("favorite", "お気に入り", "いつもの", "default")


def slugify(text: str) -> str:
    """プリセット名を比較用のスラグ形式（小文字・ハイフン区切り）に変換する。"""
    s = text.strip().lower()
    s = re.sub(r"[\s_()]+", "-", s)
    s = re.sub(r"[^a-z0-9\-]", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def user_config_dir() -> Path:
    override = os.environ.get("FILM_DATE_AGENT_CONFIG_DIR")
    if override:
        return Path(override)
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "film-date-agent"


def user_presets_dir() -> Path:
    return user_config_dir() / "presets"


def user_favorites_file() -> Path:
    return user_config_dir() / "favorites.json"


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise AgentError("invalid_json", EXIT_USAGE, f"JSON を読めません: {path}: {e}")
    if not isinstance(data, dict):
        raise AgentError("invalid_json", EXIT_USAGE, f"JSON の最上位はオブジェクトである必要があります: {path}")
    return data


@dataclass
class ResolvedPreset:
    name: str                       # 元のプリセット名（表示用）
    slug: str                       # スラグ化名（キー）
    config_dict: Dict[str, Any]     # DateStampConfig互換の辞書
    source: str                     # "builtin", "repo", "user", "file"
    file_path: Optional[Path] = None


def get_builtin_presets() -> Dict[str, Dict[str, Any]]:
    """組み込みスタイルプリセット（12種）を取得する。"""
    film_config, _ = load_engine()
    presets: Dict[str, Dict[str, Any]] = {}
    for name, params in film_config.STYLE_PRESETS.items():
        if name != "Custom" and params is not None:
            presets[name] = dict(params)
    return presets


def list_all_presets() -> List[Tuple[str, str, Dict[str, Any], str, Optional[Path]]]:
    """
    全プリセット（組み込み + リポジトリ同梱 + ユーザー）の一覧を返す。
    返り値: (表示名, スラグ名, 設定辞書, 出典, ファイルパス)
    重複時は ユーザー > リポジトリ > 組み込み の順で上書き。
    """
    result_map: Dict[str, Tuple[str, str, Dict[str, Any], str, Optional[Path]]] = {}

    # 1. 組み込みプリセット
    for name, params in get_builtin_presets().items():
        s = slugify(name)
        result_map[s] = (name, s, params, "builtin", None)

    # 2. リポジトリ同梱 presets/
    if REPO_PRESETS_DIR.is_dir():
        for p in sorted(REPO_PRESETS_DIR.glob("*.json")):
            try:
                data = _read_json(p)
                s = slugify(p.stem)
                disp_name = data.get("name", p.stem)
                result_map[s] = (disp_name, s, data, "repo", p)
            except Exception:
                continue

    # 3. ユーザープリセット
    up = user_presets_dir()
    if up.is_dir():
        for p in sorted(up.glob("*.json")):
            try:
                data = _read_json(p)
                s = slugify(p.stem)
                disp_name = data.get("name", p.stem)
                result_map[s] = (disp_name, s, data, "user", p)
            except Exception:
                continue

    return sorted(result_map.values(), key=lambda x: x[1])


def preset_candidates() -> List[str]:
    """CLI候補表示用のスラグ名一覧を返す。"""
    return [item[1] for item in list_all_presets()]


def load_favorites() -> dict:
    """お気に入り設定ファイルを読み込む。"""
    for p in (user_favorites_file(), DATA_DIR / "favorites.json", REPO_FAVORITES):
        if p.is_file():
            try:
                data = _read_json(p)
                return {
                    "favorite": data.get("favorite") or "japanese-tokyo-90s",
                    "aliases": data.get("aliases") or {},
                    "_file": str(p),
                }
            except Exception:
                pass
    return {
        "favorite": "japanese-tokyo-90s",
        "aliases": {},
        "_file": None,
    }


def resolve_preset_name(requested: Optional[str]) -> str:
    """
    指定文字列またはお気に入りから実プリセットスラグを解決する。
    None または空文字列、お気に入りワードの場合は favorite を返す。
    """
    fav = load_favorites()
    if not requested or requested.strip().lower() in FAVORITE_WORDS:
        return str(fav.get("favorite") or "japanese-tokyo-90s")

    req_slug = slugify(requested)

    # 別名辞書で解決
    aliases = fav.get("aliases") or {}
    for alias_key, target in aliases.items():
        if slugify(alias_key) == req_slug or alias_key == requested:
            return slugify(target)

    # 直接スラグ一致
    all_presets = list_all_presets()
    slug_map = {item[1]: item[1] for item in all_presets}
    if req_slug in slug_map:
        return req_slug

    # 原名（大文字小文字無視）一致
    name_map = {slugify(item[0]): item[1] for item in all_presets}
    if req_slug in name_map:
        return name_map[req_slug]

    # 部分一致探索（例: "tokyo" -> "japanese-tokyo-90s"）
    matches = [s for s in slug_map if req_slug in s]
    if len(matches) == 1:
        return matches[0]

    return requested


def resolve_preset(preset_spec: Optional[str]) -> ResolvedPreset:
    """
    プリセット指定（名前、スラグ、ファイルパス、お気に入り）から
    ResolvedPreset を生成する。見つからない場合は AgentError を投げる。
    """
    # 1. 直接の JSON ファイルパス指定の場合
    if preset_spec and (Path(preset_spec).is_file() or preset_spec.endswith(".json")):
        p = Path(preset_spec)
        if not p.is_file():
            raise AgentError(
                "preset_file_not_found",
                EXIT_USAGE,
                f"指定されたプリセットファイルが見つかりません: {preset_spec}",
            )
        data = _read_json(p)
        return ResolvedPreset(
            name=data.get("name", p.stem),
            slug=slugify(p.stem),
            config_dict=data,
            source="file",
            file_path=p,
        )

    # 2. 名前解決
    target_slug = resolve_preset_name(preset_spec)

    for disp_name, s, cfg, src, path in list_all_presets():
        if s == target_slug:
            return ResolvedPreset(
                name=disp_name,
                slug=s,
                config_dict=cfg,
                source=src,
                file_path=path,
            )

    raise AgentError(
        "preset_not_found",
        EXIT_USAGE,
        f"プリセットが見つかりません: '{preset_spec}'",
        candidates=preset_candidates(),
    )


def set_user_favorite(target_name: str) -> Path:
    """ユーザーのお気に入りを指定プリセットに設定する。"""
    resolved = resolve_preset(target_name)
    cfg_dir = user_config_dir()
    cfg_dir.mkdir(parents=True, exist_ok=True)
    fav_file = user_favorites_file()

    cur = {}
    if fav_file.is_file():
        try:
            cur = _read_json(fav_file)
        except Exception:
            pass

    cur["favorite"] = resolved.slug
    fav_file.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
    return fav_file


def create_preset(
    name: str,
    params: Dict[str, Any],
    base_name: Optional[str] = None,
    favorite: bool = False,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """新規ユーザープリセットを保存する。"""
    slug = slugify(name)
    if not slug:
        raise AgentError("invalid_name", EXIT_USAGE, "有効なプリセット名を指定してください")

    target_dir = user_presets_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / f"{slug}.json"

    if dest.is_file() and not overwrite:
        raise AgentError(
            "preset_exists",
            EXIT_USAGE,
            f"プリセット '{slug}' は既に存在します。上書きする場合は --overwrite を指定してください: {dest}",
        )

    base_config: Dict[str, Any] = {}
    if base_name:
        resolved_base = resolve_preset(base_name)
        base_config = dict(resolved_base.config_dict)

    final_config = dict(base_config)
    final_config.update(params)
    final_config["name"] = name

    dest.write_text(json.dumps(final_config, ensure_ascii=False, indent=2), encoding="utf-8")

    if favorite:
        set_user_favorite(slug)

    return {
        "ok": True,
        "name": name,
        "slug": slug,
        "file": str(dest),
        "favorite": favorite,
        "config": final_config,
    }
