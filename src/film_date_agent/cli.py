"""FilmDateStamp Agent CLI インターフェース。"""
from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__
from .capabilities import build_capabilities, human_summary
from .engine import ENGINE_DIR, FONTS_DIR, engine_file_sha256, load as load_engine
from .errors import (
    EXIT_ENGINE,
    EXIT_INPUT,
    EXIT_OK,
    EXIT_OUTPUT_EXISTS,
    EXIT_USAGE,
    AgentError,
)
from .presets import (
    create_preset,
    get_builtin_presets,
    list_all_presets,
    load_favorites,
    resolve_preset,
    set_user_favorite,
    user_config_dir,
    user_favorites_file,
)
from .runner import apply as run_apply, batch as run_batch


def _emit(report: Dict[str, Any], as_json: bool, human: Optional[str] = None) -> None:
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif human is not None:
        print(human)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))


def _fail(err: AgentError, as_json: bool) -> int:
    if as_json:
        print(json.dumps(err.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"エラー: {err.message}", file=sys.stderr)
        candidates = err.extra.get("candidates")
        if candidates:
            print(f"利用可能な候補: {', '.join(candidates)}", file=sys.stderr)
    return err.exit_code


def _wants_json(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "json", False))


def cmd_apply(args: argparse.Namespace) -> int:
    as_json = _wants_json(args)
    show_time_val: Optional[bool] = None
    if getattr(args, "show_time", False):
        show_time_val = True
    elif getattr(args, "no_time", False):
        show_time_val = False

    try:
        report = run_apply(
            args.input,
            preset=args.preset,
            output=args.output,
            save_mask=args.save_mask,
            date=args.date,
            at=args.at,
            date_format=args.format,
            show_time=show_time_val,
            font_type=args.font,
            preset_color=args.color,
            exposure_intensity=args.intensity,
            core_glow=args.glow,
            halation=args.halation,
            position=args.position,
            font_scale=args.scale,
            margin=args.margin,
            irregularity=args.irregularity,
            seed=args.seed,
            dry_run=args.dry_run,
            overwrite=args.overwrite,
        )
    except AgentError as e:
        return _fail(e, as_json)

    prefix = "（dry-run）" if report.get("dry_run") else ""
    mask_info = f" / マスク: {report['mask_output']}" if report.get("mask_output") else ""
    human = (
        f"{prefix}日付スタンプを焼き付けました: {report['output']}\n"
        f"プリセット: {report['preset_resolved']} / 日付表示: \"{report['date_text']}\"（{report['date_source']}）{mask_info}"
    )
    _emit(report, as_json, human)
    return EXIT_OK


def cmd_batch(args: argparse.Namespace) -> int:
    as_json = _wants_json(args)
    show_time_val: Optional[bool] = None
    if getattr(args, "show_time", False):
        show_time_val = True
    elif getattr(args, "no_time", False):
        show_time_val = False

    try:
        report, code = run_batch(
            args.input_dir,
            args.output_dir,
            preset=args.preset,
            date=args.date,
            at=args.at,
            date_format=args.format,
            show_time=show_time_val,
            font_type=args.font,
            preset_color=args.color,
            font_scale=args.scale,
            position=args.position,
            overwrite=args.overwrite,
            recursive=args.recursive,
        )
    except AgentError as e:
        return _fail(e, as_json)

    human = (
        f"一括処理完了: 成功 {report['success']} 件 / 失敗 {report['failed']} 件 / "
        f"合計 {report['total']} 件（プリセット: {report['preset_resolved']}）"
    )
    _emit(report, as_json, human)
    return code


def cmd_presets(args: argparse.Namespace) -> int:
    as_json = _wants_json(args)
    try:
        if args.presets_cmd == "list":
            all_presets = list_all_presets()
            fav = load_favorites()
            items = []
            for disp_name, s, cfg, src, p in all_presets:
                items.append({
                    "name": disp_name,
                    "slug": s,
                    "source": src,
                    "color": cfg.get("preset_color"),
                    "font": cfg.get("font_type"),
                    "show_time": cfg.get("show_time", False),
                    "file": str(p) if p else None,
                })
            report = {"ok": True, "favorite": fav.get("favorite"), "presets": items}
            human_lines = [
                f"- {i['name']} [slug: {i['slug']}]（{i['color']} / {i['font']} / 時刻:{'ON' if i['show_time'] else 'OFF'} / {i['source']}）"
                for i in items
            ]
            human = "\n".join(human_lines) + f"\n\n現在のお気に入り（既定）: {fav.get('favorite')}"
            _emit(report, as_json, human)
            return EXIT_OK

        if args.presets_cmd == "show":
            resolved = resolve_preset(args.name)
            report = {
                "ok": True,
                "requested": args.name,
                "name": resolved.name,
                "slug": resolved.slug,
                "source": resolved.source,
                "file": str(resolved.file_path) if resolved.file_path else None,
                "config": resolved.config_dict,
            }
            _emit(report, as_json)
            return EXIT_OK

        if args.presets_cmd == "set-favorite":
            dest = set_user_favorite(args.name)
            resolved = resolve_preset(args.name)
            report = {"ok": True, "favorite": resolved.slug, "file": str(dest)}
            _emit(report, as_json, f"お気に入りを '{resolved.name}' ({resolved.slug}) に設定しました: {dest}")
            return EXIT_OK

        if args.presets_cmd == "create":
            params = {}
            if args.color:
                params["preset_color"] = args.color
            if args.font:
                params["font_type"] = args.font
            if args.intensity is not None:
                params["exposure_intensity"] = args.intensity
            if args.glow is not None:
                params["core_glow"] = args.glow
            if args.halation is not None:
                params["halation"] = args.halation
            if args.position:
                params["position"] = args.position
            if args.scale is not None:
                params["font_scale"] = args.scale
            if args.margin is not None:
                params["margin"] = args.margin
            if getattr(args, "show_time", False):
                params["show_time"] = True
            elif getattr(args, "no_time", False):
                params["show_time"] = False
            if args.date:
                params["date_string"] = args.date
            if args.format:
                params["date_format"] = args.format

            report = create_preset(
                name=args.name,
                params=params,
                base_name=args.base,
                favorite=args.favorite,
                overwrite=args.overwrite,
            )
            human = f"プリセットを作成しました: {report['name']} ({report['slug']}) -> {report['file']}"
            if report.get("favorite"):
                human += "（お気に入りに設定しました）"
            _emit(report, as_json, human)
            return EXIT_OK

    except AgentError as e:
        return _fail(e, as_json)

    return EXIT_USAGE


def cmd_capabilities(args: argparse.Namespace) -> int:
    caps = build_capabilities()
    _emit(caps, _wants_json(args), human_summary(caps))
    return EXIT_OK


def cmd_doctor(args: argparse.Namespace) -> int:
    as_json = _wants_json(args)
    checks: List[Dict[str, Any]] = []

    # 1. Python バージョン
    py_ok = sys.version_info >= (3, 10)
    checks.append({
        "name": "python",
        "ok": py_ok,
        "detail": f"Python {platform.python_version()} (3.10+ required)",
    })

    # 2. NumPy
    try:
        import numpy as np
        checks.append({"name": "numpy", "ok": True, "detail": f"v{np.__version__}"})
    except ImportError as e:
        checks.append({"name": "numpy", "ok": False, "detail": str(e)})

    # 3. Pillow
    try:
        import PIL
        checks.append({"name": "pillow", "ok": True, "detail": f"v{PIL.__version__}"})
    except ImportError as e:
        checks.append({"name": "pillow", "ok": False, "detail": str(e)})

    # 4. エンジンファイルの整合性
    manifest_path = Path(__file__).resolve().parent / "data" / "engine_hashes.json"
    hashes: Dict[str, str] = {}
    if manifest_path.is_file():
        try:
            hashes = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    engine_ok = True
    engine_details = []
    for rel_path, expected_hash in hashes.items():
        actual_file = ENGINE_DIR / rel_path
        actual_hash = engine_file_sha256(actual_file)
        if actual_hash != expected_hash:
            engine_ok = False
            engine_details.append(f"{rel_path}: mismatch (got {actual_hash[:8]}..., expected {expected_hash[:8]}...)")

    checks.append({
        "name": "engine_integrity",
        "ok": engine_ok,
        "detail": f"{len(hashes)} files verified" if engine_ok else "; ".join(engine_details),
    })

    # 5. TrueType フォントの存在
    film_config, _ = load_engine()
    font_missing = []
    for font_display, font_entry in film_config.FONT_MAP.items():
        font_filename = font_entry[0] if isinstance(font_entry, (list, tuple)) else str(font_entry)
        font_path = FONTS_DIR / font_filename
        if not font_path.is_file():
            font_missing.append(font_filename)

    checks.append({
        "name": "fonts",
        "ok": len(font_missing) == 0,
        "detail": f"All {len(film_config.FONT_MAP)} fonts present" if not font_missing else f"Missing: {font_missing}",
    })

    # 6. お気に入り設定
    fav = load_favorites()
    fav_name = fav.get("favorite")
    fav_ok = False
    try:
        resolved_fav = resolve_preset(fav_name)
        fav_ok = True
        fav_detail = f"'{resolved_fav.name}' ({resolved_fav.slug})"
    except Exception as e:
        fav_detail = f"Failed to resolve favorite '{fav_name}': {e}"

    checks.append({
        "name": "favorite_preset",
        "ok": fav_ok,
        "detail": fav_detail,
    })

    all_ok = all(c["ok"] for c in checks)
    report = {
        "ok": all_ok,
        "version": __version__,
        "checks": checks,
    }

    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        status_line = "全項目が正常です！準備完了。" if all_ok else "一部のチェックで警告またはエラーが発生しています。"
        lines = [f"FilmDateStamp Agent v{__version__} 診断レポート:", ""]
        for c in checks:
            mark = "[OK]" if c["ok"] else "[NG]"
            lines.append(f"  {mark:<5} {c['name']:<18}: {c['detail']}")
        lines.append("")
        lines.append(status_line)
        print("\n".join(lines))

    return EXIT_OK if all_ok else EXIT_ENGINE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="film-date-agent",
        description="FilmDateStamp Agent - フィルム物理光学露光日付スタンプ CLI",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # -------------------------------------------------------------------------
    # apply サブコマンド
    # -------------------------------------------------------------------------
    p_apply = subparsers.add_parser("apply", help="単一画像に日付スタンプを焼き付ける")
    p_apply.add_argument("input", help="処理対象の画像ファイルパス")
    p_apply.add_argument("-o", "--output", help="出力ファイルパス（省略時は連番で自動命名）")
    p_apply.add_argument("-p", "--preset", default="favorite", help="スタイルプリセット（既定: favorite）")
    p_apply.add_argument("--save-mask", help="発光アルファマスクを保存する画像パス（省略時はマスク未保存）")
    p_apply.add_argument("-d", "--date", help="日付指定（'photo': EXIF撮影日時, 'auto': 現在, 'random': レトロ乱数, または直接指定）")
    p_apply.add_argument("--at", help="指定日時（ISO形式: 1998-12-24 または 2026-11-05T14:30）")
    p_apply.add_argument("--format", help="日付フォーマット（'YY MM DD, MM DD 'YY, DD.MM.YY, YYYY-MM-DD 等）")
    p_apply.add_argument("--show-time", action="store_true", help="時刻（HH:MM）を表示する")
    p_apply.add_argument("--no-time", action="store_true", help="時刻（HH:MM）を非表示にする")
    p_apply.add_argument("--color", help="発光色（Amber Classic, Quartz Red, Fuji Orange, Cyber Green 等）")
    p_apply.add_argument("--font", help="発光フォント（80s 7セグ, 写ルンですドット, 70s活字, 液晶等幅 等）")
    p_apply.add_argument("--intensity", type=float, help="露光強度 (0.0〜2.0)")
    p_apply.add_argument("--glow", type=float, help="フィラメント芯グロー (0.0〜2.0)")
    p_apply.add_argument("--halation", type=float, help="ハレーション拡散 (0.0〜3.0)")
    p_apply.add_argument("--scale", type=float, help="フォント倍率 (0.5〜2.5)")
    p_apply.add_argument("--margin", type=float, help="余白比率 (0.0〜3.0)")
    p_apply.add_argument("--position", choices=["bottom_right", "bottom_left", "top_right", "top_left"], help="配置位置")
    p_apply.add_argument("--irregularity", type=float, help="素子個体差・圧板ゆらぎ (0.0〜2.0)")
    p_apply.add_argument("--seed", type=int, help="乱数シード")
    p_apply.add_argument("--dry-run", action="store_true", help="描画せずに設定と出力パスを検証")
    p_apply.add_argument("--overwrite", action="store_true", help="既存の出力ファイルを上書き")
    p_apply.add_argument("--json", action="store_true", help="結果をJSONで出力")
    p_apply.set_defaults(func=cmd_apply)

    # -------------------------------------------------------------------------
    # batch サブコマンド
    # -------------------------------------------------------------------------
    p_batch = subparsers.add_parser("batch", help="フォルダ内の画像に一括で日付スタンプを焼き付ける")
    p_batch.add_argument("input_dir", help="入力ディレクトリ")
    p_batch.add_argument("output_dir", help="出力ディレクトリ")
    p_batch.add_argument("-p", "--preset", default="favorite", help="スタイルプリセット（既定: favorite）")
    p_batch.add_argument("-d", "--date", help="日付指定（'photo': 各画像のEXIF撮影日時, 'auto', 'random', または固定文字列）")
    p_batch.add_argument("--at", help="指定日時（ISO形式）")
    p_batch.add_argument("--format", help="日付フォーマット")
    p_batch.add_argument("--show-time", action="store_true", help="時刻（HH:MM）を表示")
    p_batch.add_argument("--no-time", action="store_true", help="時刻（HH:MM）を非表示")
    p_batch.add_argument("--color", help="発光色")
    p_batch.add_argument("--font", help="発光フォント")
    p_batch.add_argument("--scale", type=float, help="フォント倍率")
    p_batch.add_argument("--position", choices=["bottom_right", "bottom_left", "top_right", "top_left"], help="配置位置")
    p_batch.add_argument("-r", "--recursive", action="store_true", help="サブフォルダも再帰的に処理")
    p_batch.add_argument("--overwrite", action="store_true", help="既存ファイルを上書き")
    p_batch.add_argument("--json", action="store_true", help="結果をJSONで出力")
    p_batch.set_defaults(func=cmd_batch)

    # -------------------------------------------------------------------------
    # presets サブコマンド
    # -------------------------------------------------------------------------
    p_presets = subparsers.add_parser("presets", help="プリセットの確認・作成・お気に入り設定")
    presets_sub = p_presets.add_subparsers(dest="presets_cmd", required=True)

    # presets list
    p_p_list = presets_sub.add_parser("list", help="利用可能なプリセット一覧")
    p_p_list.add_argument("--json", action="store_true", help="結果をJSONで出力")

    # presets show
    p_p_show = presets_sub.add_parser("show", help="プリセットの詳細設定を表示")
    p_p_show.add_argument("name", help="プリセット名またはスラグ")
    p_p_show.add_argument("--json", action="store_true", help="結果をJSONで出力")

    # presets set-favorite
    p_p_fav = presets_sub.add_parser("set-favorite", help="既定のお気に入りプリセットを設定")
    p_p_fav.add_argument("name", help="お気に入りにするプリセット名またはスラグ")
    p_p_fav.add_argument("--json", action="store_true", help="結果をJSONで出力")

    # presets create
    p_p_create = presets_sub.add_parser("create", help="新しいプリセットを作成")
    p_p_create.add_argument("name", help="作成するプリセット名")
    p_p_create.add_argument("--base", help="土台にする既存プリセット名")
    p_p_create.add_argument("--favorite", action="store_true", help="同時に既定のお気に入りに設定")
    p_p_create.add_argument("--overwrite", action="store_true", help="既存プリセットを上書き")
    p_p_create.add_argument("--color", help="発光色")
    p_p_create.add_argument("--font", help="フォント種類")
    p_p_create.add_argument("--intensity", type=float, help="露光強度")
    p_p_create.add_argument("--glow", type=float, help="中心芯グロー")
    p_p_create.add_argument("--halation", type=float, help="ハレーション拡散")
    p_p_create.add_argument("--scale", type=float, help="フォント倍率")
    p_p_create.add_argument("--margin", type=float, help="余白比率")
    p_p_create.add_argument("--position", choices=["bottom_right", "bottom_left", "top_right", "top_left"])
    p_p_create.add_argument("--show-time", action="store_true")
    p_p_create.add_argument("--no-time", action="store_true")
    p_p_create.add_argument("--date", help="既定の日付文字列")
    p_p_create.add_argument("--format", help="日付フォーマット")
    p_p_create.add_argument("--json", action="store_true", help="結果をJSONで出力")

    p_presets.set_defaults(func=cmd_presets)

    # -------------------------------------------------------------------------
    # capabilities サブコマンド
    # -------------------------------------------------------------------------
    p_caps = subparsers.add_parser("capabilities", help="対応フォント・カラー・プリセット等の一覧カタログ")
    p_caps.add_argument("--json", action="store_true", help="結果をJSONで出力")
    p_caps.set_defaults(func=cmd_capabilities)

    # -------------------------------------------------------------------------
    # doctor サブコマンド
    # -------------------------------------------------------------------------
    p_doc = subparsers.add_parser("doctor", help="環境・依存ライブラリ・フォント・エンジン整合性の診断")
    p_doc.add_argument("--json", action="store_true", help="結果をJSONで出力")
    p_doc.set_defaults(func=cmd_doctor)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    func = getattr(args, "func", None)
    if func:
        code = func(args)
        sys.exit(code)
    parser.print_help()
    sys.exit(EXIT_USAGE)


if __name__ == "__main__":
    main()

