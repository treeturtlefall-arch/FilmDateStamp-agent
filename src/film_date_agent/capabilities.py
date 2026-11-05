"""FilmDateStamp 能力カタログモジュール。"""
from __future__ import annotations

from typing import Dict, Any
from .engine import load as load_engine
from .presets import load_favorites, resolve_preset, list_all_presets


def build_capabilities() -> Dict[str, Any]:
    film_config, _ = load_engine()
    fav = load_favorites()

    try:
        resolved = resolve_preset("favorite")
        current_fav = {
            "name": resolved.name,
            "slug": resolved.slug,
            "config": resolved.config_dict,
        }
    except Exception as e:
        current_fav = {"favorite": fav.get("favorite"), "error": str(e)}

    preset_items = []
    for disp_name, s, cfg, src, _ in list_all_presets():
        preset_items.append({
            "name": disp_name,
            "slug": s,
            "source": src,
            "color": cfg.get("preset_color"),
            "font": cfg.get("font_type"),
            "format": cfg.get("date_format"),
            "show_time": cfg.get("show_time", False),
        })

    return {
        "ok": True,
        "summary": "フィルム写真の感光乳剤に焼き付けられるクォーツデート（日付スタンプ）の物理光学露光をシミュレートする",
        "axes": {
            "preset_color": {
                "label": "発光色（分光特性）",
                "choices": list(film_config.COLOR_PRESETS.keys()),
            },
            "font_type": {
                "label": "発光素子タイポグラフィ（自社製TrueType中心・全8種）",
                "choices": list(film_config.SUPPORTED_FONTS),
            },
            "date_format": {
                "label": "日付順・区切りフォーマット",
                "choices": list(film_config.SUPPORTED_DATE_FORMATS),
            },
            "position": {
                "label": "焼き付け位置",
                "choices": list(film_config.SUPPORTED_POSITIONS),
            },
            "exposure_intensity": {
                "label": "露光強度（光子の量）",
                "range": [0.0, 2.0],
                "default": 1.0,
            },
            "core_glow": {
                "label": "中心フィラメント芯の白飛び強度",
                "range": [0.0, 2.0],
                "default": 1.0,
            },
            "halation": {
                "label": "多重スケールPSFハレーション拡散",
                "range": [0.0, 3.0],
                "default": 1.0,
            },
            "font_scale": {
                "label": "フォント倍率（視覚サイズ自動正規化済み）",
                "range": [0.5, 2.5],
                "default": 1.0,
            },
            "margin": {
                "label": "端からの余白マージン比率",
                "range": [0.0, 3.0],
                "default": 1.0,
            },
            "irregularity": {
                "label": "素子個体差・圧板ゆらぎ",
                "range": [0.0, 2.0],
                "default": 1.0,
            },
            "date_modes": {
                "photo": "写真のEXIF撮影日時（DateTimeOriginal）を自動反映",
                "auto": "実行時の現在日時を自動反映",
                "random": "1985〜2005年のヴィンテージランダム日時を生成",
                "fixed": "指定した任意の日付文字列をそのまま焼き付け",
            },
            "show_time": {
                "label": "時刻表示トグル（HH:MM）",
                "type": "boolean",
                "default": False,
            },
        },
        "presets": {
            "count": len(preset_items),
            "items": preset_items,
            "current_favorite": current_fav,
        },
    }


def human_summary(caps: Dict[str, Any]) -> str:
    axes = caps["axes"]
    lines = [
        caps["summary"] + "。",
        "",
        "🌟 変えられる要素（軸）:",
        f"- 発光色（{len(axes['preset_color']['choices'])}種）: {' / '.join(axes['preset_color']['choices'])}",
        f"- フォント（{len(axes['font_type']['choices'])}種）: 80s 7セグ（-7°/直立）、90s ドットマトリクス、70s 機械式活字、液晶等幅、SF映画テレメトリ、平成レトロ丸文字、古文書スクリプト",
        f"- 日付指定: photo（EXIF撮影日時）、auto（現在時刻）、random（80-00sランダム）、または任意文字列",
        f"- 時刻トグル: --show-time で時分（HH:MM）の表示をワンクリック切り替え",
        f"- スタイルプリセット（{caps['presets']['count']}種）: 90年代東京スナップ、写ルンです風、西海岸ロードトリップ、80sモーテル赤LED、欧州クラシック、初期コンデジ、70s機械式活字 等",
        f"- 光学微調整: 露光強度、中心芯ブリーチ、ハレーション拡散、サイズ倍率、マージン、有機的ゆらぎ",
        "",
        f"現在の既定プリセット（お気に入り）: {caps['presets']['current_favorite'].get('name', 'japanese-tokyo-90s')}",
    ]
    return "\n".join(lines)
