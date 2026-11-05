from pathlib import Path
from PIL import Image
from film_date_agent.exif import get_photo_datetime, _parse_exif_date


def test_parse_exif_date():
    dt = _parse_exif_date("2003:10:02 17:49:15")
    assert dt is not None
    assert dt.year == 2003
    assert dt.month == 10
    assert dt.day == 2
    assert dt.hour == 17
    assert dt.minute == 49


def test_fallback_file_mtime(tmp_path: Path):
    p = tmp_path / "plain.png"
    img = Image.new("RGB", (100, 100), color="white")
    img.save(p)
    dt, source = get_photo_datetime(p)
    assert dt is not None
    assert source == "file_mtime"


def test_real_exif_photo():
    real_photo = Path("tests/data/DSC00004.JPG")
    if real_photo.is_file():
        dt, source = get_photo_datetime(real_photo)
        assert dt is not None
        assert dt.year == 2003
        assert dt.month == 10
        assert dt.day == 2
        assert "exif" in source
