"""フィルム日付スタンプの合成実行モジュール。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from PIL import Image, ImageOps

from . import __version__
from .engine import load as load_engine
from .errors import (
    EXIT_ENGINE,
    EXIT_INPUT,
    EXIT_OK,
    EXIT_OUTPUT_EXISTS,
    EXIT_USAGE,
    AgentError,
)
from .exif import get_photo_datetime
from .presets import ResolvedPreset, resolve_preset

DATA_UPSTREAM = Path(__file__).resolve().parent / "data" / "upstream.json"

SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"
}


def _engine_info() -> Dict[str, Any]:
    try:
        info = json.loads(DATA_UPSTREAM.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        info = {}
    return {
        "engine": info.get("repo", "FilmDateStamp"),
        "snapshot": info.get("snapshot", "2026-11-05"),
        "agent_version": __version__,
    }


def _validate_input(path: Path) -> None:
    if not path.exists():
        raise AgentError("input_not_found", EXIT_INPUT, f"入力ファイルが見つかりません: {path}")
    if not path.is_file():
        raise AgentError("input_not_file", EXIT_INPUT, f"入力パスはファイルである必要があります: {path}")
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise AgentError(
            "unsupported_format",
            EXIT_INPUT,
            f"未対応の画像形式です: {path.suffix}（対応: {', '.join(sorted(SUPPORTED_EXTENSIONS))}）",
        )


def _resolve_unique_output(input_path: Path, output: Optional[str], overwrite: bool) -> Path:
    """出力パスを解決する。未指定時は連番で一意のファイル名を決定する。"""
    if output:
        dest = Path(output).expanduser()
        if dest.is_dir():
            dest = dest / f"{input_path.stem}_stamped{input_path.suffix}"
        if dest.exists() and not overwrite:
            raise AgentError(
                "output_exists",
                EXIT_OUTPUT_EXISTS,
                f"出力先が既に存在します: {dest}（上書きする場合は --overwrite を指定してください）",
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        return dest

    # 未指定時: input_dir / {stem}_stamped.{ext}
    parent = input_path.parent
    suffix = input_path.suffix if input_path.suffix.lower() in SUPPORTED_EXTENSIONS else ".png"
    base_name = f"{input_path.stem}_stamped"

    candidate = parent / f"{base_name}{suffix}"
    if not candidate.exists() or overwrite:
        return candidate

    idx = 1
    while True:
        candidate = parent / f"{base_name}_{idx}{suffix}"
        if not candidate.exists():
            return candidate
        idx += 1


def parse_at_datetime(value: str) -> datetime:
    """--at の ISO 形式（例: '2026-11-05T14:30'）を解釈する。"""
    text = value.strip().replace(" ", "T", 1)
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        raise AgentError(
            "invalid_at",
            EXIT_USAGE,
            f"--at の形式が不正です: {value}（例: 2026-11-05T14:30 または 1998-12-24）",
        )


def resolve_date_input(
    date_arg: Optional[str],
    at_arg: Optional[str],
    preset_cfg: Dict[str, Any],
    input_path: Path,
    date_format: str,
    show_time: bool,
    seed: Optional[int] = None,
) -> Tuple[str, str]:
    """
    日付文字列と検出ソースを解決する。
    戻り値: (描画用date_string, date_source)
    """
    film_config, _ = load_engine()

    # 1. --at 指定時
    if at_arg:
        dt = parse_at_datetime(at_arg)
        date_text = film_config.format_datetime(dt, date_format, show_time)
        return date_text, "at_argument"

    # 2. --date 指定時
    raw_date = date_arg.strip() if date_arg else None

    # 明示的に "photo" または "exif" が指定された場合
    if raw_date and raw_date.lower() in ("photo", "exif", "camera"):
        dt, source = get_photo_datetime(input_path)
        if dt:
            return film_config.format_datetime(dt, date_format, show_time), f"photo_{source}"
        # 撮影日時が取れない場合はファイル更新日時または現在時刻
        now = datetime.now()
        return film_config.format_datetime(now, date_format, show_time), "fallback_now"

    # "auto", "today", "now"
    if raw_date and raw_date.lower() in ("auto", "today", "now"):
        now = datetime.now()
        return film_config.format_datetime(now, date_format, show_time), "auto_now"

    # "random"
    if raw_date and raw_date.lower() == "random":
        dt = film_config.generate_random_vintage_datetime(seed=seed)
        return film_config.format_datetime(dt, date_format, show_time), "random_vintage"

    # 任意の日付文字列が明示指定された場合
    if raw_date:
        return raw_date, "custom_string"

    # 3. 指定が無い場合はプリセットの設定をベースにする
    preset_date = preset_cfg.get("date_string", "'98 12 24")
    p_lower = str(preset_date).strip().lower()

    if p_lower in ("auto", "today", "now"):
        now = datetime.now()
        return film_config.format_datetime(now, date_format, show_time), "preset_auto"
    if p_lower == "random":
        dt = film_config.generate_random_vintage_datetime(seed=seed)
        return film_config.format_datetime(dt, date_format, show_time), "preset_random"
    if p_lower in ("photo", "exif"):
        dt, source = get_photo_datetime(input_path)
        if dt:
            return film_config.format_datetime(dt, date_format, show_time), f"preset_{source}"
        now = datetime.now()
        return film_config.format_datetime(now, date_format, show_time), "preset_fallback_now"

    return preset_date, "preset_default"


def apply(
    input_file: Union[str, Path],
    *,
    preset: Optional[str] = "favorite",
    output: Optional[str] = None,
    save_mask: Optional[str] = None,
    date: Optional[str] = None,
    at: Optional[str] = None,
    date_format: Optional[str] = None,
    show_time: Optional[bool] = None,
    font_type: Optional[str] = None,
    preset_color: Optional[str] = None,
    exposure_intensity: Optional[float] = None,
    core_glow: Optional[float] = None,
    halation: Optional[float] = None,
    position: Optional[str] = None,
    font_scale: Optional[float] = None,
    margin: Optional[float] = None,
    irregularity: Optional[float] = None,
    seed: Optional[int] = None,
    dry_run: bool = False,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """単一画像に対して物理感光日付スタンプを焼き付ける。"""
    film_config, film_stamp = load_engine()

    input_path = Path(input_file).expanduser().resolve()
    _validate_input(input_path)
    dest_path = _resolve_unique_output(input_path, output, overwrite)

    mask_dest_path: Optional[Path] = None
    if save_mask:
        m_path = Path(save_mask).expanduser().resolve()
        if m_path.exists() and not overwrite:
            raise AgentError(
                "mask_output_exists",
                EXIT_OUTPUT_EXISTS,
                f"マスク出力先が既に存在します: {m_path}（上書き時は --overwrite を指定）",
            )
        m_path.parent.mkdir(parents=True, exist_ok=True)
        mask_dest_path = m_path

    # プリセット解決
    resolved = resolve_preset(preset)
    cfg_dict = dict(resolved.config_dict)

    # パラメータ決定（引数でのオーバーライド）
    final_fmt = date_format or cfg_dict.get("date_format", "'YY MM DD")
    final_show_time = show_time if show_time is not None else cfg_dict.get("show_time", False)

    final_date_str, date_src = resolve_date_input(
        date_arg=date,
        at_arg=at,
        preset_cfg=cfg_dict,
        input_path=input_path,
        date_format=final_fmt,
        show_time=final_show_time,
        seed=seed,
    )

    # DateStampConfig の組み立て
    config = film_config.DateStampConfig(
        style_preset="Custom",
        date_string=final_date_str,
        date_format=final_fmt,
        show_time=final_show_time,
        font_type=font_type or cfg_dict.get("font_type", "FDS7_Strict_Compact (80s -7°)"),
        preset_color=preset_color or cfg_dict.get("preset_color", "Amber Classic"),
        exposure_intensity=exposure_intensity if exposure_intensity is not None else cfg_dict.get("exposure_intensity", 1.0),
        core_glow=core_glow if core_glow is not None else cfg_dict.get("core_glow", 1.0),
        halation=halation if halation is not None else cfg_dict.get("halation", 1.0),
        position=position or cfg_dict.get("position", "bottom_right"),
        font_scale=font_scale if font_scale is not None else cfg_dict.get("font_scale", 1.0),
        margin=margin if margin is not None else cfg_dict.get("margin", 1.15),
        irregularity=irregularity if irregularity is not None else cfg_dict.get("irregularity", 1.0),
    )

    # 画像読み込み
    try:
        with Image.open(input_path) as raw_img:
            # EXIF Orientation を自動補正
            img = ImageOps.exif_transpose(raw_img)
            width, height = img.size
            if img.mode != "RGB":
                img = img.convert("RGB")
            # float32 [H, W, C] 0.0〜1.0
            img_np = np.asarray(img, dtype=np.float32) / 255.0
    except Exception as e:
        raise AgentError("image_read_failed", EXIT_INPUT, f"画像を開けませんでした: {input_path} ({e})")

    # dry-run の場合は描画をスキップ
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "input": str(input_path),
            "output": str(dest_path),
            "preset": preset,
            "preset_resolved": resolved.name,
            "date_text": final_date_str,
            "date_source": date_src,
            "width": width,
            "height": height,
            "config": {
                "font_type": config.font_type,
                "preset_color": config.preset_color,
                "exposure_intensity": config.exposure_intensity,
                "core_glow": config.core_glow,
                "halation": config.halation,
                "position": config.position,
                "font_scale": config.font_scale,
                "margin": config.margin,
                "show_time": config.show_time,
            },
            "engine": _engine_info(),
        }

    # 描画実行
    try:
        result_np, mask_np, rendered_text = film_stamp.render_film_date_stamp(
            image=img_np,
            config=config,
            seed=seed,
            return_details=True,
        )
    except Exception as e:
        raise AgentError("render_failed", EXIT_ENGINE, f"日付スタンプ描画中にエラーが発生しました: {e}")

    # 結果保存
    try:
        out_uint8 = np.clip(result_np * 255.0, 0.0, 255.0).astype(np.uint8)
        out_img = Image.fromarray(out_uint8, mode="RGB")
        out_img.save(dest_path)
    except Exception as e:
        raise AgentError("image_save_failed", EXIT_ENGINE, f"結果画像の保存に失敗しました: {dest_path} ({e})")

    # マスク保存（指定時）
    if mask_dest_path:
        try:
            mask_uint8 = np.clip(mask_np * 255.0, 0.0, 255.0).astype(np.uint8)
            mask_img = Image.fromarray(mask_uint8, mode="L")
            mask_img.save(mask_dest_path)
        except Exception as e:
            raise AgentError("mask_save_failed", EXIT_ENGINE, f"マスク画像の保存に失敗しました: {mask_dest_path} ({e})")

    report: Dict[str, Any] = {
        "ok": True,
        "input": str(input_path),
        "output": str(dest_path),
        "preset": preset,
        "preset_resolved": resolved.name,
        "date_text": rendered_text,
        "date_source": date_src,
        "width": width,
        "height": height,
        "config": {
            "font_type": config.font_type,
            "preset_color": config.preset_color,
            "exposure_intensity": config.exposure_intensity,
            "core_glow": config.core_glow,
            "halation": config.halation,
            "position": config.position,
            "font_scale": config.font_scale,
            "margin": config.margin,
            "show_time": config.show_time,
        },
        "engine": _engine_info(),
    }
    if mask_dest_path:
        report["mask_output"] = str(mask_dest_path)

    return report


def batch(
    input_dir: Union[str, Path],
    output_dir: Union[str, Path],
    *,
    preset: Optional[str] = "favorite",
    date: Optional[str] = None,
    at: Optional[str] = None,
    date_format: Optional[str] = None,
    show_time: Optional[bool] = None,
    font_type: Optional[str] = None,
    preset_color: Optional[str] = None,
    font_scale: Optional[float] = None,
    position: Optional[str] = None,
    overwrite: bool = False,
    recursive: bool = False,
) -> Tuple[Dict[str, Any], int]:
    """ディレクトリ内の全画像に一括で日付スタンプを焼き付ける。"""
    in_path = Path(input_dir).expanduser().resolve()
    out_path = Path(output_dir).expanduser().resolve()

    if not in_path.is_dir():
        raise AgentError("input_dir_not_found", EXIT_INPUT, f"入力ディレクトリが見つかりません: {in_path}")

    out_path.mkdir(parents=True, exist_ok=True)

    pattern = "**/*" if recursive else "*"
    all_files = [p for p in in_path.glob(pattern) if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS]

    if not all_files:
        raise AgentError("no_images_found", EXIT_INPUT, f"対象画像ファイルが見つかりません: {in_path}")

    items: List[Dict[str, Any]] = []
    success_count = 0
    failed_count = 0

    for file_path in sorted(all_files):
        # 出力ファイル名
        rel = file_path.relative_to(in_path)
        dest_file = out_path / rel.parent / f"{file_path.stem}_stamped{file_path.suffix}"
        dest_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            rep = apply(
                file_path,
                preset=preset,
                output=str(dest_file),
                date=date,
                at=at,
                date_format=date_format,
                show_time=show_time,
                font_type=font_type,
                preset_color=preset_color,
                font_scale=font_scale,
                position=position,
                overwrite=overwrite,
            )
            items.append({
                "file": str(file_path),
                "output": rep["output"],
                "date_text": rep["date_text"],
                "status": "success",
            })
            success_count += 1
        except Exception as e:
            items.append({
                "file": str(file_path),
                "error": str(e),
                "status": "failed",
            })
            failed_count += 1

    overall_code = EXIT_OK if failed_count == 0 else EXIT_ENGINE
    resolved = resolve_preset(preset)

    report = {
        "ok": failed_count == 0,
        "input_dir": str(in_path),
        "output_dir": str(out_path),
        "total": len(all_files),
        "success": success_count,
        "failed": failed_count,
        "preset_resolved": resolved.name,
        "items": items,
        "engine": _engine_info(),
    }
    return report, overall_code
