"""
FilmDateStamp - 設定データクラス・カラープリセット・日付パーサー
"""
from dataclasses import dataclass
import datetime
import random
import re
from typing import Dict, Tuple, Optional

# プリセットカラーパレット定義 (Core, Body, Halation)
# ※ Cyber Green は飛び道具・特殊用途としての位置づけを明確にするため末尾に配置
COLOR_PRESETS: Dict[str, Dict[str, Tuple[int, int, int]]] = {
    "Amber Classic": {
        "core": (255, 255, 210),
        "body": (255, 130, 20),
        "halation": (240, 45, 0),
    },
    "Quartz Red": {
        "core": (255, 230, 220),
        "body": (255, 40, 20),
        "halation": (200, 10, 0),
    },
    "Fuji Orange": {
        "core": (255, 250, 190),
        "body": (255, 115, 20),
        "halation": (250, 60, 10),
    },
    "Golden Yellow": {
        "core": (255, 255, 240),
        "body": (255, 185, 30),
        "halation": (240, 110, 0),
    },
    "Bulb Warm Ivory": {
        "core": (255, 250, 232),
        "body": (255, 242, 204),
        "halation": (255, 214, 138),
    },
    "Paper White (Monochrome)": {
        "core": (248, 246, 240),
        "body": (245, 242, 234),
        "halation": (235, 232, 224),
    },
    # 特殊・空想（Fiction / Speculative）カラーパレット
    "Cyber Green": {
        "core": (230, 255, 230),
        "body": (40, 255, 80),
        "halation": (0, 180, 40),
    },
    "Neo Pink": {
        "core": (255, 235, 248),
        "body": (255, 70, 170),
        "halation": (230, 25, 115),
    },
    "Crimson Red": {
        "core": (255, 235, 225),
        "body": (235, 25, 35),
        "halation": (185, 5, 15),
    },
}

# 物理分光感度・散乱波長特性（H&D 非線形感光モデル用）
# sens: (R, G, B 各チャンネルの感光速度)
# scatter: (R, G, B 各チャンネルの長波長散乱比率)
# tint: (高エネルギー飽和時の微小バイアス)
PHYSICAL_SPECTRA: Dict[str, Dict[str, Tuple[float, float, float]]] = {
    "Amber Classic": {
        "sens": (3.20, 0.95, 0.38),
        "scatter": (1.00, 0.24, 0.02),
        "tint": (1.00, 0.98, 0.85),
    },
    "Quartz Red": {
        "sens": (3.60, 0.32, 0.18),
        "scatter": (1.00, 0.06, 0.01),
        "tint": (1.00, 0.90, 0.84),
    },
    "Fuji Orange": {
        "sens": (3.40, 0.82, 0.30),
        "scatter": (1.00, 0.28, 0.02),
        "tint": (1.00, 0.97, 0.80),
    },
    "Golden Yellow": {
        "sens": (3.00, 1.55, 0.45),
        "scatter": (1.00, 0.45, 0.04),
        "tint": (1.00, 0.99, 0.90),
    },
    "Bulb Warm Ivory": {
        "sens": (3.20, 2.65, 1.38),
        "scatter": (1.00, 0.72, 0.26),
        "tint": (1.00, 0.949, 0.800),
    },
    "Paper White (Monochrome)": {
        "sens": (2.90, 2.86, 2.75),
        "scatter": (0.85, 0.84, 0.80),
        "tint": (0.973, 0.965, 0.941),
    },
    # 特殊・空想分光特性
    "Cyber Green": {
        "sens": (0.32, 3.20, 0.65),
        "scatter": (0.05, 1.00, 0.22),
        "tint": (0.90, 1.00, 0.92),
    },
    "Neo Pink": {
        "sens": (3.00, 0.40, 2.40),
        "scatter": (1.00, 0.15, 0.65),
        "tint": (1.00, 0.90, 0.98),
    },
    "Crimson Red": {
        "sens": (3.60, 0.25, 0.18),
        "scatter": (1.00, 0.06, 0.01),
        "tint": (1.00, 0.88, 0.85),
    },
}

SUPPORTED_DATE_FORMATS = [
    "'YY MM DD",
    "YY MM DD",
    "MM DD 'YY",
    "DD MM 'YY",
    "DD.MM.YY",
    "YY-MM-DD",
    "YY.MM.DD",
    "YYYY MM DD",
    "YYYY-MM-DD",
]

SUPPORTED_POSITIONS = [
    "bottom_right",
    "bottom_left",
    "top_right",
    "top_left",
]

# 厳選フォント定義 (フォントファイル名, シアー傾斜角度)
# 自社製実機仕様4種 ＋ 液晶等幅1種 ＋ 空想・シミュレーティブ3種
FONT_MAP: Dict[str, Tuple[str, float]] = {
    # 実機エミュレート
    "FDS7_Strict_Compact (80s -7°)": ("FDS7Strict-Compact.ttf", 0.0),
    "FDS7_Strict_SLR (80s 0°)": ("FDS7Strict-SLR.ttf", 0.0),
    "FDS_Dot_Strict (90s Dot Matrix)": ("FDSDotStrict-Regular.ttf", 0.0),
    "FDS_Mechanical_70s (70s Mechanical)": ("FDSMechanical70s-Regular.ttf", 0.0),
    "ShareTechMono (LCD Digital)": ("ShareTechMono-Regular.ttf", 0.0),
    # 空想・シミュレーティブ（Fiction / Speculative）
    "Michroma (Cyber Telemetry)": ("Michroma-Regular.ttf", 0.0),
    "MochiyPopOne (Y2K Pop)": ("MochiyPopOne-Regular.ttf", 0.0),
    "EagleLake (Arcane Script)": ("EagleLake-Regular.ttf", 0.0),
}

SUPPORTED_FONTS = list(FONT_MAP.keys())
SUPPORTED_COLORS = list(COLOR_PRESETS.keys())

# スタイル一括プリセット定義（地域・時代・文化ベース）
STYLE_PRESETS: Dict[str, Optional[Dict[str, object]]] = {
    "Custom": None,
    "Japanese Tokyo 90s": {
        "date_string": "'98 12 24",
        "date_format": "'YY MM DD",
        "show_time": False,
        "font_type": "FDS7_Strict_Compact (80s -7°)",
        "preset_color": "Amber Classic",
        "exposure_intensity": 1.00,
        "core_glow": 1.00,
        "halation": 1.00,
        "position": "bottom_right",
        "font_scale": 1.00,
        "margin": 1.15,
    },
    "Japanese Snap (Disposable)": {
        "date_string": "'98 12 24 18:30",
        "date_format": "'YY MM DD",
        "show_time": True,
        "font_type": "FDS_Dot_Strict (90s Dot Matrix)",
        "preset_color": "Fuji Orange",
        "exposure_intensity": 1.00,
        "core_glow": 0.50,
        "halation": 1.00,
        "position": "bottom_right",
        "font_scale": 1.20,
        "margin": 1.50,
    },
    "American West Coast": {
        "date_string": "12 24 '98",
        "date_format": "MM DD 'YY",
        "show_time": False,
        "font_type": "FDS7_Strict_Compact (80s -7°)",
        "preset_color": "Golden Yellow",
        "exposure_intensity": 1.00,
        "core_glow": 0.85,
        "halation": 1.00,
        "position": "bottom_right",
        "font_scale": 1.00,
        "margin": 1.15,
    },
    "American 80s (Red Quartz)": {
        "date_string": "12 24 '88",
        "date_format": "MM DD 'YY",
        "show_time": False,
        "font_type": "FDS7_Strict_SLR (80s 0°)",
        "preset_color": "Quartz Red",
        "exposure_intensity": 1.10,
        "core_glow": 1.00,
        "halation": 1.30,
        "position": "bottom_right",
        "font_scale": 1.00,
        "margin": 1.15,
    },
    "European Classic (Paris/Berlin)": {
        "date_string": "24.12.98",
        "date_format": "DD.MM.YY",
        "show_time": False,
        "font_type": "FDS7_Strict_SLR (80s 0°)",
        "preset_color": "Amber Classic",
        "exposure_intensity": 0.90,
        "core_glow": 0.70,
        "halation": 0.80,
        "position": "bottom_right",
        "font_scale": 0.95,
        "margin": 1.15,
    },
    "Y2K Digicam (Early 2000s)": {
        "date_string": "'03 08 15 14:20",
        "date_format": "'YY MM DD",
        "show_time": True,
        "font_type": "ShareTechMono (LCD Digital)",
        "preset_color": "Golden Yellow",
        "exposure_intensity": 1.05,
        "core_glow": 0.60,
        "halation": 0.90,
        "position": "bottom_right",
        "font_scale": 1.15,
        "margin": 1.40,
    },
    "Compact Fine Dot (Minimal)": {
        "date_string": "'99 07 20 16:45",
        "date_format": "'YY MM DD",
        "show_time": True,
        "font_type": "FDS_Dot_Strict (90s Dot Matrix)",
        "preset_color": "Fuji Orange",
        "exposure_intensity": 1.00,
        "core_glow": 0.40,
        "halation": 0.90,
        "position": "bottom_right",
        "font_scale": 1.10,
        "margin": 1.50,
    },
    "Monochrome 70s (Canodate E)": {
        "date_string": "74 12 25",
        "date_format": "YY MM DD",
        "show_time": False,
        "font_type": "FDS_Mechanical_70s (70s Mechanical)",
        "preset_color": "Paper White (Monochrome)",
        "exposure_intensity": 1.00,
        "core_glow": 0.50,
        "halation": 0.60,
        "position": "bottom_right",
        "font_scale": 1.00,
        "margin": 1.15,
    },
    "Vintage 70s Color (Datematic)": {
        "date_string": "'74 12 25",
        "date_format": "'YY MM DD",
        "show_time": False,
        "font_type": "FDS_Mechanical_70s (70s Mechanical)",
        "preset_color": "Bulb Warm Ivory",
        "exposure_intensity": 1.05,
        "core_glow": 0.70,
        "halation": 0.85,
        "position": "bottom_right",
        "font_scale": 1.00,
        "margin": 1.15,
    },
    # 空想・シミュレーティブ（Fiction / Speculative）プリセット
    "Cyber Telemetry (80s Sci-Fi)": {
        "date_string": "'98 12 24 23:59:59",
        "date_format": "'YY MM DD",
        "show_time": True,
        "font_type": "Michroma (Cyber Telemetry)",
        "preset_color": "Cyber Green",
        "exposure_intensity": 1.35,
        "core_glow": 1.20,
        "halation": 1.45,
        "position": "bottom_right",
        "font_scale": 1.05,
        "margin": 0.90,
    },
    "Y2K Pop (Heisei Fancy)": {
        "date_string": "'98 12 24 18:30",
        "date_format": "'YY MM DD",
        "show_time": True,
        "font_type": "MochiyPopOne (Y2K Pop)",
        "preset_color": "Neo Pink",
        "exposure_intensity": 1.05,
        "core_glow": 0.50,
        "halation": 0.75,
        "position": "bottom_right",
        "font_scale": 1.15,
        "margin": 0.90,
    },
    "Arcane Occult (Crimson Script)": {
        "date_string": "'98 12 24",
        "date_format": "'YY MM DD",
        "show_time": False,
        "font_type": "EagleLake (Arcane Script)",
        "preset_color": "Crimson Red",
        "exposure_intensity": 1.05,
        "core_glow": 0.40,
        "halation": 0.60,
        "position": "bottom_right",
        "font_scale": 1.50,
        "margin": 0.85,
    },
}


@dataclass
class DateStampConfig:
    """フィルム日付スタンプの設定データクラス"""
    style_preset: str = "Custom"
    date_string: str = "'98 12 24"
    date_format: str = "'YY MM DD"
    show_time: bool = False
    font_type: str = "FDS7_Strict_Compact (80s -7°)"
    preset_color: str = "Amber Classic"
    exposure_intensity: float = 1.0
    core_glow: float = 1.0
    halation: float = 1.0
    position: str = "bottom_right"
    font_scale: float = 1.0
    margin: float = 1.0
    irregularity: float = 1.0  # 有機的ゆらぎ強度 (0.0=均一, 1.0=実機相当, 2.0=誇張)

    def apply_style_preset_if_set(self):
        """style_preset が選択されている場合、対応するパラメータを適用"""
        if self.style_preset and self.style_preset in STYLE_PRESETS:
            preset_values = STYLE_PRESETS[self.style_preset]
            if preset_values:
                for k, v in preset_values.items():
                    if hasattr(self, k):
                        setattr(self, k, v)

    def get_color_palette(self) -> Dict[str, Tuple[int, int, int]]:
        """選択されたカラープリセットの辞書を取得"""
        if self.preset_color in COLOR_PRESETS:
            return COLOR_PRESETS[self.preset_color]
        return COLOR_PRESETS["Amber Classic"]


def format_datetime(dt: datetime.datetime, format_str: str, show_time: bool = False) -> str:
    """指定された日付フォーマットに従って日時候補文字列を生成"""
    yy = f"{dt.year % 100:02d}"
    yyyy = f"{dt.year:04d}"
    mm = f"{dt.month:02d}"
    dd = f"{dt.day:02d}"
    hh = f"{dt.hour:02d}"
    minute = f"{dt.minute:02d}"

    if format_str == "'YY MM DD":
        base = f"'{yy} {mm} {dd}"
    elif format_str == "YY MM DD":
        base = f"{yy} {mm} {dd}"
    elif format_str == "MM DD 'YY":
        base = f"{mm} {dd} '{yy}"
    elif format_str == "DD MM 'YY":
        base = f"{dd} {mm} '{yy}"
    elif format_str == "DD.MM.YY":
        base = f"{dd}.{mm}.{yy}"
    elif format_str == "YY-MM-DD":
        base = f"{yy}-{mm}-{dd}"
    elif format_str == "YY.MM.DD":
        base = f"{yy}.{mm}.{dd}"
    elif format_str == "YYYY MM DD":
        base = f"{yyyy} {mm} {dd}"
    elif format_str == "YYYY-MM-DD":
        base = f"{yyyy}-{mm}-{dd}"
    else:
        base = f"'{yy} {mm} {dd}"

    if show_time:
        return f"{base} {hh}:{minute}"
    return base


def generate_random_vintage_datetime(
    start_year: int = 1985,
    end_year: int = 2005,
    seed: Optional[int] = None,
) -> datetime.datetime:
    """1985〜2005年のランダムな日時を生成"""
    start_dt = datetime.datetime(start_year, 1, 1, 0, 0, 0)
    end_dt = datetime.datetime(end_year, 12, 31, 23, 59, 59)
    total_seconds = int((end_dt - start_dt).total_seconds())

    if seed is not None:
        rng = random.Random(seed)
        random_sec = rng.randint(0, total_seconds)
    else:
        random_sec = random.randint(0, total_seconds)

    return start_dt + datetime.timedelta(seconds=random_sec)


def resolve_date_text(config: DateStampConfig, seed: Optional[int] = None) -> str:
    """
    設定に基づいて実際に描画する文字列を決定・解決する。
    - "auto", "today", "now": 現在日時の自動生成
    - "random": ヴィンテージランダム日時の自動生成
    - その他: ユーザー入力文字列（改行正規化、時刻トリム/補完適用）
    """
    raw_text = config.date_string if config.date_string is not None else "'98 12 24"
    text_clean = re.sub(r'[\r\n\t]+', ' ', raw_text).strip()
    key = text_clean.lower()

    if key in ("auto", "today", "now"):
        now = datetime.datetime.now()
        return format_datetime(now, config.date_format, show_time=config.show_time)

    if key == "random":
        dt = generate_random_vintage_datetime(seed=seed)
        return format_datetime(dt, config.date_format, show_time=config.show_time)

    # ユーザー指定の直接カスタム文字列
    if not text_clean:
        text_clean = "'98 12 24"
    if len(text_clean) > 64:
        text_clean = text_clean[:64]

    # 末尾の時刻（例: ' 18:30', ' 09:15', ' 23:59:59'）を検出
    time_match = re.search(r'\s+(\d{1,2}:\d{2}(?::\d{2})?)$', text_clean)

    if config.show_time:
        if not time_match:
            # show_time が True なのに時刻がない場合はデフォルト "18:30" を付加
            text_clean = f"{text_clean} 18:30"
    else:
        if time_match:
            # show_time が False なのに時刻が含まれている場合は除去
            text_clean = text_clean[:time_match.start()]

    return text_clean
