from __future__ import annotations

import json
from pathlib import Path
from PIL import Image

from film_date_agent.engine import ENGINE_DIR, engine_file_sha256
from film_date_agent.runner import apply


def test_engine_files_unmodified():
    """同梱エンジンファイルがマニフェストの SHA-256 と完全一致する（改変なし担保）。"""
    manifest_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "film_date_agent"
        / "data"
        / "engine_hashes.json"
    )
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest) >= 10

    for name, expected_hash in manifest.items():
        actual_file = ENGINE_DIR / name
        assert actual_file.is_file(), f"Missing file: {name}"
        actual_hash = engine_file_sha256(actual_file)
        assert actual_hash == expected_hash, f"Hash mismatch in {name}"


def test_apply_deterministic_with_seed(sample_image: Path, tmp_path: Path):
    """同一シード・固定日時での描画結果がバイト単位で完全一致する（再現性担保）。"""
    out_a = tmp_path / "out_a.png"
    out_b = tmp_path / "out_b.png"

    apply(
        sample_image,
        output=str(out_a),
        preset="japanese-tokyo-90s",
        date="'98 12 24",
        seed=42,
    )
    apply(
        sample_image,
        output=str(out_b),
        preset="japanese-tokyo-90s",
        date="'98 12 24",
        seed=42,
    )

    bytes_a = out_a.read_bytes()
    bytes_b = out_b.read_bytes()
    assert bytes_a == bytes_b


def test_mask_dimensions_and_levels(sample_image: Path, tmp_path: Path):
    """マスク画像が元画像と同一サイズで生成され、正しい輝度レンジを持つ。"""
    out = tmp_path / "out.png"
    mask = tmp_path / "mask.png"

    apply(
        sample_image,
        output=str(out),
        save_mask=str(mask),
        preset="american-80s-red-quartz",
        date="12 24 '88",
    )

    img = Image.open(out)
    m = Image.open(mask)

    assert img.size == m.size
    extrema = m.getextrema()
    # マスクに発光領域（>0）と暗部（=0）が含まれていること
    assert extrema[0] == 0
    assert extrema[1] > 0
