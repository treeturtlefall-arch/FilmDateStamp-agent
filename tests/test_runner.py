from pathlib import Path
import pytest
from film_date_agent.runner import apply, batch
from film_date_agent.errors import AgentError


def test_apply_dry_run(sample_image: Path):
    rep = apply(sample_image, dry_run=True)
    assert rep["ok"] is True
    assert rep["dry_run"] is True
    assert "Japanese Snap (Disposable)" in rep["preset_resolved"]


def test_apply_render(sample_image: Path, tmp_path: Path):
    dest = tmp_path / "out.png"
    rep = apply(
        sample_image,
        output=str(dest),
        preset="japanese-snap-disposable",
        date="'98 12 24",
        show_time=False,
    )
    assert rep["ok"] is True
    assert dest.is_file()
    assert rep["date_text"] == "'98 12 24"


def test_apply_with_mask(sample_image: Path, tmp_path: Path):
    dest = tmp_path / "out.png"
    mask_dest = tmp_path / "mask.png"
    rep = apply(
        sample_image,
        output=str(dest),
        save_mask=str(mask_dest),
        date="1999-07-20",
    )
    assert rep["ok"] is True
    assert dest.is_file()
    assert mask_dest.is_file()
    assert "mask_output" in rep


def test_apply_overwrite_protection(sample_image: Path, tmp_path: Path):
    dest = tmp_path / "out.png"
    apply(sample_image, output=str(dest))

    # overwrite なしだとエラー
    with pytest.raises(AgentError) as exc:
        apply(sample_image, output=str(dest), overwrite=False)
    assert exc.value.code == "output_exists"

    # overwrite ありなら成功
    rep = apply(sample_image, output=str(dest), overwrite=True)
    assert rep["ok"] is True


def test_batch_processing(tmp_path: Path, sample_image: Path):
    in_dir = tmp_path / "batch_in"
    out_dir = tmp_path / "batch_out"
    in_dir.mkdir()

    # 2枚コピー
    (in_dir / "img1.png").write_bytes(sample_image.read_bytes())
    (in_dir / "img2.png").write_bytes(sample_image.read_bytes())

    rep, code = batch(in_dir, out_dir, preset="japanese-tokyo-90s")
    assert code == 0
    assert rep["total"] == 2
    assert rep["success"] == 2
    assert rep["failed"] == 0
