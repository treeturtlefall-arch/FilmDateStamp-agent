"""
FilmDateStamp - コア光学露光レンダリングエンジン (v2.0)
NumPy + Pillow ベースで、フィルム乳剤へのH&D非線形分光感光・3階層有機ゆらぎ・ハイライト感光余力合成をシミュレートする。
外部依存（scipy / torch 等）を一切排し、高速かつ完全スタンドアロンで動作する。
"""
import os
import math
import re
from functools import lru_cache
from typing import Tuple, Optional, Union
import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:
    from .film_config import (
        DateStampConfig,
        resolve_date_text,
        PHYSICAL_SPECTRA,
        FONT_MAP,
    )
except (ImportError, ValueError):
    from film_config import (
        DateStampConfig,
        resolve_date_text,
        PHYSICAL_SPECTRA,
        FONT_MAP,
    )

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(MODULE_DIR, "fonts")


# ==============================================================================
# 色空間変換 (sRGB <-> Linear RGB)
# ==============================================================================
def srgb_to_linear(srgb: np.ndarray) -> np.ndarray:
    """sRGB (0.0〜1.0) を物理リニア輝度空間へ変換"""
    srgb = np.clip(srgb, 0.0, 1.0)
    return np.where(
        srgb <= 0.04045,
        srgb / 12.92,
        np.power((srgb + 0.055) / 1.055, 2.4),
    ).astype(np.float32)


def linear_to_srgb(linear: np.ndarray) -> np.ndarray:
    """物理リニア輝度空間 (0.0〜1.0) を sRGB へ変換"""
    linear = np.clip(linear, 0.0, 1.0)
    return np.where(
        linear <= 0.0031308,
        linear * 12.92,
        1.055 * np.power(linear, 1.0 / 2.4) - 0.055,
    ).astype(np.float32)


# ==============================================================================
# 物理フィルタ・ノイズ合成関数群（純粋 NumPy / Pillow 実装）
# ==============================================================================
def fft_gaussian_blur(
    arr: np.ndarray,
    sigma: float,
    sigma_minor: Optional[float] = None,
    angle_deg: float = 0.0,
    shift_xy: Tuple[float, float] = (0.0, 0.0),
) -> np.ndarray:
    """
    FFT による高速ガウシアンブラー。
    - sigma_minor 指定で楕円（異方性）カーネル、angle_deg でその主軸を回転
    - shift_xy でサブピクセル精度の平行移動（圧板浮き・レンズ傾斜による滲みオフセット）
    """
    if sigma_minor is None:
        sigma_minor = sigma
    smax = max(sigma, sigma_minor)
    if smax < 0.05 and abs(shift_xy[0]) < 1e-3 and abs(shift_xy[1]) < 1e-3:
        return arr.astype(np.float32, copy=True)

    pad = int(math.ceil(3.5 * smax + abs(shift_xy[0]) + abs(shift_xy[1]))) + 2
    a = np.pad(arr.astype(np.float32), pad, mode="constant")
    h, w = a.shape

    fy = np.fft.fftfreq(h).astype(np.float32)[:, None]
    fx = np.fft.rfftfreq(w).astype(np.float32)[None, :]
    th = math.radians(angle_deg)
    u = fx * math.cos(th) + fy * math.sin(th)
    v = -fx * math.sin(th) + fy * math.cos(th)
    tf = np.exp(-2.0 * math.pi ** 2 * (sigma ** 2 * u ** 2 + sigma_minor ** 2 * v ** 2))
    if shift_xy[0] != 0.0 or shift_xy[1] != 0.0:
        tf = tf * np.exp(-2j * math.pi * (fx * shift_xy[0] + fy * shift_xy[1]))

    out = np.fft.irfft2(np.fft.rfft2(a) * tf, s=a.shape)
    return np.maximum(out[pad:-pad, pad:-pad], 0.0).astype(np.float32)


def approx_inner_distance(binary: np.ndarray, max_iter: int = 96) -> np.ndarray:
    """
    反復モルフォロジー収縮による近似距離変換（八角形メトリック）。
    文字ストローク内部の中心尾根（LEDホットスポット）を scipy 非依存で高速に抽出。
    """
    dist = np.zeros(binary.shape, dtype=np.float32)
    cur = binary.astype(bool).copy()
    for i in range(max_iter):
        if not cur.any():
            break
        dist += cur
        p = np.pad(cur, 1, constant_values=False)
        er = p[1:-1, 1:-1] & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
        if i % 2 == 1:
            er &= p[:-2, :-2] & p[:-2, 2:] & p[2:, :-2] & p[2:, 2:]
        cur = er
    return dist


def value_noise(rng: np.random.Generator, shape: Tuple[int, int], cell_y: float, cell_x: Optional[float] = None) -> np.ndarray:
    """格子乱数を Bicubic 補間した滑らかな空間ゆらぎ（平均0・標準偏差1に正規化）"""
    h, w = shape
    cell_x = cell_y if cell_x is None else cell_x
    cell_y = max(1.0, float(cell_y))
    cell_x = max(1.0, float(cell_x))
    gh = int(math.ceil(h / cell_y)) + 4
    gw = int(math.ceil(w / cell_x)) + 4
    grid = rng.standard_normal((gh, gw)).astype(np.float32)
    up_w, up_h = int(math.ceil(gw * cell_x)), int(math.ceil(gh * cell_y))
    up = np.asarray(Image.fromarray(grid).resize((up_w, up_h), Image.BICUBIC), dtype=np.float32)
    oy = int(cell_y + rng.random() * cell_y)
    ox = int(cell_x + rng.random() * cell_x)
    out = up[oy:oy + h, ox:ox + w]
    std = float(out.std())
    return ((out - out.mean()) / std).astype(np.float32) if std > 1e-6 else np.zeros(shape, np.float32)


def fbm_noise(rng: np.random.Generator, shape: Tuple[int, int], cell: float, octaves: int = 3, gain: float = 0.5) -> np.ndarray:
    """多オクターブの雲状ノイズ（Fractal Brownian Motion）"""
    acc = np.zeros(shape, dtype=np.float32)
    amp, total = 1.0, 0.0
    for i in range(octaves):
        acc += value_noise(rng, shape, cell / (2 ** i)) * amp
        total += amp
        amp *= gain
    acc /= total
    std = float(acc.std())
    return (acc / std).astype(np.float32) if std > 1e-6 else acc


def bilinear_warp(field: np.ndarray, dx: np.ndarray, dy: np.ndarray) -> np.ndarray:
    """変位場 (dx, dy) によるドメインワープ（波打ち再サンプリング）"""
    h, w = field.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    sx = np.clip(xx + dx, 0.0, w - 1.001)
    sy = np.clip(yy + dy, 0.0, h - 1.001)
    x0 = sx.astype(np.int32)
    y0 = sy.astype(np.int32)
    fx = sx - x0
    fy = sy - y0
    a = field[y0, x0]
    b = field[y0, x0 + 1]
    c = field[y0 + 1, x0]
    d = field[y0 + 1, x0 + 1]
    return (a * (1 - fx) * (1 - fy) + b * fx * (1 - fy) + c * (1 - fx) * fy + d * fx * fy).astype(np.float32)


# ==============================================================================
# フォント・レイアウト管理
# ==============================================================================
@lru_cache(maxsize=16)
def get_font_file_and_shear(font_type: str) -> Tuple[str, float]:
    """フォントファイルパスとシアー傾斜角度（度数）を返す"""
    if font_type in FONT_MAP:
        filename, shear_deg = FONT_MAP[font_type]
    else:
        filename, shear_deg = "FDS7Strict-Compact.ttf", 0.0

    font_path = os.path.join(FONTS_DIR, filename)
    if not os.path.exists(font_path):
        alt_path = os.path.join(MODULE_DIR, filename)
        if os.path.exists(alt_path):
            font_path = alt_path

    return font_path, shear_deg


@lru_cache(maxsize=32)
def get_cached_truetype_font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    """TrueTypeフォントインスタンスのLRUキャッシュ取得"""
    try:
        return ImageFont.truetype(font_path, size)
    except Exception:
        return ImageFont.load_default()


def apply_shear_tilt(img: Image.Image, shear_deg: float) -> Image.Image:
    """画像を右傾斜（イタリック調）にアフィン変換する"""
    if abs(shear_deg) < 0.01:
        return img

    w, h = img.size
    shear_factor = math.tan(math.radians(shear_deg))
    offset_x = int(math.ceil(h * shear_factor))
    new_w = w + offset_x
    matrix = (1, shear_factor, -shear_factor * h, 0, 1, 0)

    transformed = img.transform(
        (new_w, h),
        Image.AFFINE,
        matrix,
        resample=Image.BILINEAR
    )
    return transformed


def calculate_stamp_position(
    img_w: int,
    img_h: int,
    stamp_w: int,
    stamp_h: int,
    position: str,
    margin_x_px: int,
    margin_y_px: int,
) -> Tuple[int, int]:
    """配置指定に従ってスタンプ描画の左上座標 (pos_x, pos_y) を計算"""
    pos_key = position.lower().strip()

    if pos_key == "bottom_left":
        pos_x = margin_x_px
        pos_y = img_h - stamp_h - margin_y_px
    elif pos_key == "top_right":
        pos_x = img_w - stamp_w - margin_x_px
        pos_y = margin_y_px
    elif pos_key == "top_left":
        pos_x = margin_x_px
        pos_y = margin_y_px
    else:
        # デフォルト: bottom_right
        pos_x = img_w - stamp_w - margin_x_px
        pos_y = img_h - stamp_h - margin_y_px

    return pos_x, pos_y


_FONT_NORM_CACHE = {}
_REF_TARGET_W = 360.0
_REF_TARGET_H = 65.0


def get_font_visual_norm_factor(font_path: str) -> float:
    """
    フォントごとの内部メトリクス差を吸収し、どのフォントを選んでも
    同じ font_scale で同じ視覚サイズになるよう正規化係数を算出する。
    """
    if font_path in _FONT_NORM_CACHE:
        return _FONT_NORM_CACHE[font_path]

    try:
        ref_font = get_cached_truetype_font(font_path, 100)
        basename = os.path.basename(font_path)
        if basename.startswith("FDS7Strict") or basename.startswith("FDSDotStrict"):
            # FDS7Strict / FDSDotStrict は実機スリム比率 (W/H=0.50〜0.537) をそのまま保持し、
            # 横幅引き伸ばしによる巨大化を防ぐため高さ基準 (cap height -> 65px) で正規化する
            bbox = ref_font.getbbox("88 88 88")
            h = max(1.0, float(bbox[3] - bbox[1]))
            norm_factor = _REF_TARGET_H / h
        else:
            bbox = ref_font.getbbox("88 88 88")
            w = max(1.0, float(bbox[2] - bbox[0]))
            h = max(1.0, float(bbox[3] - bbox[1]))
            norm_factor = ((_REF_TARGET_W / w) ** 0.75) * ((_REF_TARGET_H / h) ** 0.25)
            norm_factor = max(0.4, min(2.5, norm_factor))
    except Exception:
        norm_factor = 1.0

    _FONT_NORM_CACHE[font_path] = norm_factor
    return norm_factor


@lru_cache(maxsize=16)
def render_date_mask_cached(
    text: str,
    font_path: str,
    font_size: int,
    shear_deg: float = 0.0,
) -> Tuple[Image.Image, int, int]:
    """
    指定文字列のグレースケールマスク画像（Lモード）をキャッシュ生成する内部関数。
    """
    safe_text = re.sub(r'[\r\n\t]+', ' ', text).strip() if text else " "
    norm_factor = get_font_visual_norm_factor(font_path)
    effective_font_size = max(10, int(round(font_size * norm_factor)))
    font = get_cached_truetype_font(font_path, effective_font_size)

    dummy_img = Image.new("L", (1, 1), 0)
    dummy_draw = ImageDraw.Draw(dummy_img)
    bbox = dummy_draw.textbbox((0, 0), safe_text, font=font, anchor="lt")
    raw_w = max(1, bbox[2] - bbox[0])
    raw_h = max(1, bbox[3] - bbox[1])

    pad_y = max(4, int(effective_font_size * 0.4))
    pad_x = max(4, int(effective_font_size * 0.4))
    canvas_w = raw_w + pad_x * 2
    canvas_h = raw_h + pad_y * 2

    mask = Image.new("L", (canvas_w, canvas_h), 0)
    draw = ImageDraw.Draw(mask)
    draw.text((pad_x - bbox[0], pad_y - bbox[1]), safe_text, fill=255, font=font, anchor="lt")

    if abs(shear_deg) > 0.01:
        mask = apply_shear_tilt(mask, shear_deg)

    tight_bbox = mask.getbbox()
    if tight_bbox is not None:
        mask = mask.crop(tight_bbox)

    text_w, text_h = mask.size
    return mask, max(1, text_w), max(1, text_h)


def render_date_mask(
    text: str,
    font_path: str,
    font_size: int,
    shear_deg: float = 0.0,
) -> Tuple[Image.Image, int, int]:
    """後方互換用公開インターフェース"""
    mask, w, h = render_date_mask_cached(text, font_path, font_size, shear_deg)
    return mask.copy(), w, h


# ==============================================================================
# v2.0 光学露光マップ生成エンジン（H&D分光飽和・3階層有機ゆらぎ）
# ==============================================================================
@lru_cache(maxsize=16)
def generate_light_map_cached_v2(
    date_text: str,
    font_path: str,
    base_font_size: int,
    shear_deg: float,
    preset_color: str,
    exposure_intensity: float,
    core_glow: float,
    halation: float,
    irregularity: float = 1.0,
    grain: float = 1.0,
    seed: int = 0,
) -> Tuple[np.ndarray, int, int, int]:
    """
    v2.0 光学計算エンジン:
    1. 近似距離変換による LED セグメント発光尾根（Hotspot）
    2. Macro ゆらぎ（文字・セグメント単位の光量差＋レンズ周辺減光）
    3. 多重 PSF 散乱（異方性・サブピクセルオフセット付き）
    4. Meso ゆらぎ（圧板密着ムラ＋ハレーション輪郭の波打ち）
    5. Micro ゆらぎ（銀塩グレイン＋現像色素雲による裾野ちぎれ）
    6. H&D 分光感光モデル（赤→橙→黄→白の連続ブリーチ）
    戻り値: (light_lin_rgb, text_w, text_h, blur_pad)
    """
    mask_core, text_w, text_h = render_date_mask_cached(
        text=date_text,
        font_path=font_path,
        font_size=base_font_size,
        shear_deg=shear_deg,
    )

    fs = float(base_font_size)
    blur_pad = max(16, int(fs * 2.2))
    padded_w = mask_core.width + blur_pad * 2
    padded_h = mask_core.height + blur_pad * 2

    padded_mask = Image.new("L", (padded_w, padded_h), 0)
    padded_mask.paste(mask_core, (blur_pad, blur_pad))
    raw = np.asarray(padded_mask, dtype=np.float32) / 255.0
    H, W = raw.shape

    irr = max(0.0, float(irregularity))
    hal = max(0.01, float(halation))
    E0 = float(exposure_intensity)
    cg = float(core_glow)

    # 決定論的シード乱数生成器
    rng_macro = np.random.default_rng([int(seed) & 0xFFFFFFFF, 1])
    rng_meso = np.random.default_rng([int(seed) & 0xFFFFFFFF, 2])
    rng_micro = np.random.default_rng([int(seed) & 0xFFFFFFFF, 3])

    # ---- Step 1: LED 発光尾根 ----
    inside = raw > 0.30
    dist = approx_inner_distance(inside)
    dist = fft_gaussian_blur(dist, max(0.5, fs * 0.012)) * inside
    dmax = max(1.0, float(np.percentile(dist[inside], 92))) if inside.any() else 1.0
    ridge = np.power(np.clip(dist / dmax, 0.0, 1.25), 1.15)

    # ---- Step 2: ① Macro ゆらぎ ----
    if irr > 0:
        n_char = value_noise(rng_macro, (H, W), cell_y=fs * 4.0, cell_x=fs * 0.55)
        n_seg = value_noise(rng_macro, (H, W), fs * 0.22)
        ang = rng_macro.uniform(0, 2 * math.pi)
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        lens = math.cos(ang) * (xx - W / 2) / (W / 2) + math.sin(ang) * (yy - H / 2) / (H / 2)
        gain = np.clip(1.0 + irr * (0.09 * n_char + 0.06 * n_seg + 0.07 * lens), 0.55, 1.45)
    else:
        gain = np.ones((H, W), np.float32)

    slit = fft_gaussian_blur(raw, max(0.35, fs * 0.022))
    hot = ridge * gain
    source = (0.45 * slit * gain + 1.15 * hot * cg) * E0

    # ---- Step 3: 多重 PSF 散乱 ----
    psf_core = fft_gaussian_blur(hot, max(0.45, fs * 0.025))
    psf_narrow = fft_gaussian_blur(source, max(0.75, fs * 0.052))

    if irr > 0:
        aniso = 1.0 + irr * 0.16 * rng_meso.uniform(0.4, 1.0)
        hal_angle = rng_meso.uniform(0.0, 180.0)
        sh_ang = rng_meso.uniform(0, 2 * math.pi)
        sh_mag = irr * fs * 0.035
        shift = (math.cos(sh_ang) * sh_mag, math.sin(sh_ang) * sh_mag)
    else:
        aniso, hal_angle, shift = 1.0, 0.0, (0.0, 0.0)

    sig_mid = max(1.4, fs * 0.12 * math.sqrt(hal))
    sig_wide = max(2.8, fs * 0.27 * hal)
    sig_veil = max(5.5, fs * 0.58 * hal)

    # 3重ハレーション散乱（mid, wide, veil）を周波数領域（FFT空間）で1つの伝達関数に合成して高速化
    smax_all = max(sig_mid * aniso, sig_wide * aniso, sig_veil * aniso)
    sh_max = abs(shift[0] * 1.8) + abs(shift[1] * 1.8)
    pad = int(math.ceil(3.5 * smax_all + sh_max)) + 2
    padded_source = np.pad(source.astype(np.float32), pad, mode="constant")
    ph, pw = padded_source.shape

    fy = np.fft.fftfreq(ph).astype(np.float32)[:, None]
    fx = np.fft.rfftfreq(pw).astype(np.float32)[None, :]
    th = math.radians(hal_angle)
    u = fx * math.cos(th) + fy * math.sin(th)
    v = -fx * math.sin(th) + fy * math.cos(th)

    def calc_halo_tf(sig: float, scale: float) -> np.ndarray:
        s_maj = sig * aniso
        s_min = sig / aniso
        shx, shy = shift[0] * scale, shift[1] * scale
        tf = np.exp(-2.0 * math.pi ** 2 * (s_maj ** 2 * u ** 2 + s_min ** 2 * v ** 2))
        if shx != 0.0 or shy != 0.0:
            tf = tf * np.exp(-2j * math.pi * (fx * shx + fy * shy))
        return tf

    tf_halo = (
        0.30 * calc_halo_tf(sig_mid, 0.4)
        + 0.17 * calc_halo_tf(sig_wide, 1.0)
        + 0.07 * calc_halo_tf(sig_veil, 1.8)
    ) * hal

    f_source = np.fft.rfft2(padded_source)
    out_halo = np.fft.irfft2(f_source * tf_halo, s=padded_source.shape)
    halo = np.maximum(out_halo[pad:-pad, pad:-pad], 0.0).astype(np.float32)

    # ---- Step 4: ② Meso ゆらぎ ----
    if irr > 0:
        cloud = fbm_noise(rng_meso, (H, W), fs * 1.4, octaves=2, gain=0.4)
        halo = halo * np.clip(1.0 + irr * 0.14 * cloud, 0.5, 1.5)
        wx = fbm_noise(rng_meso, (H, W), fs * 1.2, octaves=2) * (irr * fs * 0.055)
        wy = fbm_noise(rng_meso, (H, W), fs * 1.2, octaves=2) * (irr * fs * 0.055)
        halo = bilinear_warp(halo, wx, wy)
        psf_narrow = bilinear_warp(psf_narrow, wx * 0.3, wy * 0.3)

    core_E = (0.85 * hot * raw + 0.55 * psf_core) * cg * E0
    body_E = (0.50 * slit * gain + 0.65 * psf_narrow) * E0

    # ---- Step 5: ③ Micro ゆらぎ ----
    total = core_E + body_E + halo
    mod = np.ones((H, W), np.float32)
    if grain > 0:
        fine = rng_micro.standard_normal((H, W)).astype(np.float32)
        clump = value_noise(rng_micro, (H, W), 2.2)
        grain_field = 0.55 * fine + 0.45 * clump
        env = np.clip(total * 2.2, 0.0, 1.0) * np.exp(-core_E * 1.6)
        mod *= 1.0 + 0.22 * float(grain) * grain_field * env
    if irr > 0:
        dye = value_noise(rng_micro, (H, W), 1.8)
        tail = np.exp(-total * 6.0) * np.clip(total * 8.0, 0.0, 1.0)
        mod *= np.clip(1.0 + irr * 0.20 * dye * tail, 0.6, 1.4)

    # ---- Step 6: H&D 分光感光 ----
    spec = PHYSICAL_SPECTRA.get(preset_color, PHYSICAL_SPECTRA["Amber Classic"])
    s_r, s_g, s_b = spec["sens"]
    k_r, k_g, k_b = spec["scatter"]
    bleach = np.power(np.clip(core_E, 0.0, 2.5), 1.5) * 1.35

    E_r = ((core_E + body_E) * s_r + halo * s_r * k_r * 1.35 + bleach) * mod
    E_g = ((core_E * 1.2 + body_E * 0.85) * s_g + halo * s_g * k_g * 0.70 + bleach * 0.95) * mod
    E_b = ((core_E * 1.8 + body_E * 0.25) * s_b + halo * s_b * k_b * 0.20 + bleach * 0.65) * mod
    E_rgb = np.maximum(np.stack([E_r, E_g, E_b], axis=-1), 0.0)

    light_lin = 1.0 - np.exp(-np.power(E_rgb, 1.15))
    light_lin *= np.asarray(spec["tint"], dtype=np.float32)[None, None, :]

    return light_lin.astype(np.float32), text_w, text_h, blur_pad


# ==============================================================================
# 公開インターフェース
# ==============================================================================
def render_film_date_stamp(
    image: Union[Image.Image, np.ndarray],
    config: Optional[DateStampConfig] = None,
    seed: Optional[int] = None,
    return_details: bool = False,
    **kwargs
) -> Union[Image.Image, np.ndarray, Tuple[Union[Image.Image, np.ndarray], np.ndarray, str]]:
    """
    ベース画像に対してフィルム日付スタンプを光学的に露光・焼き付け合成する (v2.0)。

    Parameters:
        image: PIL.Image または NumPy配列 [H, W, C] (float32 0..1 or uint8 0..255)
        config: DateStampConfig インスタンス（省略時はデフォルト）
        seed: random_vintage および有機ゆらぎ用の乱数シード
        return_details: True の場合、(result_image, mask_np [H, W], date_text) のタプルを返す
        **kwargs: config を上書きする個別パラメータ
    """
    if config is None:
        config = DateStampConfig()
        if "style_preset" in kwargs:
            config.style_preset = kwargs["style_preset"]
        config.apply_style_preset_if_set()

    # kwargs による動的オーバーライド
    for k, v in kwargs.items():
        if hasattr(config, k) and v is not None:
            setattr(config, k, v)

    # 入力の型判定
    is_numpy = isinstance(image, np.ndarray)
    orig_channels = 3
    alpha_channel = None

    if is_numpy:
        np_input = image
        if np_input.ndim == 2:
            np_input = np_input[:, :, None]

        orig_channels = np_input.shape[2]

        if np_input.dtype == np.uint8:
            base_full = np_input.astype(np.float32) / 255.0
        else:
            base_full = np.clip(np_input.astype(np.float32), 0.0, 1.0)

        if orig_channels == 4:
            base_rgb = base_full[:, :, :3].copy()
            alpha_channel = base_full[:, :, 3:4].copy()
        elif orig_channels == 1:
            base_rgb = np.repeat(base_full, 3, axis=2).copy()
        else:
            base_rgb = base_full[:, :, :3].copy()

        h, w = base_rgb.shape[:2]
    else:
        pil_img = image.convert("RGB")
        w, h = pil_img.size
        base_rgb = np.array(pil_img, dtype=np.float32) / 255.0

    s = min(w, h)

    # 1. 日付文字列の解決
    date_text = resolve_date_text(config, seed=seed)

    # 2. フォントとシアー設定
    font_path, shear_deg = get_font_file_and_shear(config.font_type)

    base_font_size = max(10, int(s * 0.040 * config.font_scale))

    # 3. v2 光学露光マップの取得 (リニア RGB [H, W, 3])
    eff_seed = seed if seed is not None else 0
    light_lin, text_w, text_h, blur_pad = generate_light_map_cached_v2(
        date_text=date_text,
        font_path=font_path,
        base_font_size=base_font_size,
        shear_deg=round(shear_deg, 2),
        preset_color=config.preset_color,
        exposure_intensity=round(float(config.exposure_intensity), 3),
        core_glow=round(float(config.core_glow), 3),
        halation=round(float(config.halation), 3),
        irregularity=round(float(config.irregularity), 2),
        grain=1.0,
        seed=eff_seed,
    )

    stamp_h, stamp_w = light_lin.shape[:2]

    # 4. 配置計算（単一マージンスケール）
    margin_x_px = int(s * 0.05 * config.margin)
    margin_y_px = int(s * 0.04 * config.margin)

    text_pos_x, text_pos_y = calculate_stamp_position(
        img_w=w,
        img_h=h,
        stamp_w=text_w,
        stamp_h=text_h,
        position=config.position,
        margin_x_px=margin_x_px,
        margin_y_px=margin_y_px,
    )

    origin_x = text_pos_x - blur_pad
    origin_y = text_pos_y - blur_pad

    dst_x1 = max(0, origin_x)
    dst_y1 = max(0, origin_y)
    dst_x2 = min(w, origin_x + stamp_w)
    dst_y2 = min(h, origin_y + stamp_h)

    src_x1 = max(0, -(origin_x))
    src_y1 = max(0, -(origin_y))
    src_x2 = src_x1 + (dst_x2 - dst_x1)
    src_y2 = src_y1 + (dst_y2 - dst_y1)

    mask_out = np.zeros((h, w), dtype=np.float32)

    if dst_x2 > dst_x1 and dst_y2 > dst_y1 and src_x2 > src_x1 and src_y2 > src_y1:
        sub_base_srgb = base_rgb[dst_y1:dst_y2, dst_x1:dst_x2]
        sub_light_lin = light_lin[src_y1:src_y2, src_x1:src_x2]

        # 5. リニア空間での乳剤感光余力＋フィルム肩特性合成 (Optical Burn-in)
        sub_base_lin = srgb_to_linear(sub_base_srgb)
        luma = (
            0.2126 * sub_base_lin[..., 0:1]
            + 0.7152 * sub_base_lin[..., 1:2]
            + 0.0722 * sub_base_lin[..., 2:3]
        )
        # 背景が明るいほど乳剤の感光余力（headroom）が小さくなり、文字が溶け込んで埋もれる
        headroom = np.clip(1.0 - np.power(luma, 1.35) * 0.72, 0.12, 1.0)
        eff_light = sub_light_lin * headroom

        raw_sum = sub_base_lin + eff_light * 1.18
        compressed = 1.0 - np.exp(-raw_sum * 1.20) * (1.0 - sub_base_lin * np.exp(-eff_light * 2.0))
        t = np.clip((raw_sum - 0.45) / 0.75, 0.0, 1.0)
        combined_lin = np.clip(raw_sum * (1.0 - t) + compressed * t, 0.0, 1.0)

        base_rgb[dst_y1:dst_y2, dst_x1:dst_x2] = linear_to_srgb(combined_lin)

        # マスク領域の抽出（光量の最大チャンネル）
        sub_mask = np.clip(np.max(sub_light_lin, axis=-1), 0.0, 1.0)
        mask_out[dst_y1:dst_y2, dst_x1:dst_x2] = sub_mask

    # 出力形式の復元
    if is_numpy:
        if orig_channels == 4:
            result = np.concatenate([base_rgb, alpha_channel], axis=-1)
        elif orig_channels == 1:
            luma = (0.2126 * base_rgb[:, :, 0] + 0.7152 * base_rgb[:, :, 1] + 0.0722 * base_rgb[:, :, 2])[:, :, None]
            result = luma
        else:
            result = base_rgb

        if np_input.dtype == np.uint8:
            final_img = (result * 255.0).astype(np.uint8)
        else:
            final_img = result
    else:
        final_img = Image.fromarray((base_rgb * 255.0 + 0.5).astype(np.uint8))

    if return_details:
        return final_img, mask_out, date_text
    return final_img
