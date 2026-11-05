import pytest
from pathlib import Path
from PIL import Image

@pytest.fixture
def sample_image(tmp_path: Path) -> Path:
    """単体テスト用の単色RGB画像を作成する。"""
    p = tmp_path / "sample.png"
    img = Image.new("RGB", (640, 480), color=(50, 70, 90))
    img.save(p)
    return p
