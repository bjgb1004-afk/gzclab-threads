"""reel.py 검증. ffmpeg를 실제로 돌리는 건 selftest 하나뿐이고 나머지는 순수 함수다."""

import datetime
import pathlib
import tempfile

from PIL import Image

import reel


def test_reel_name_is_stable():
    day = datetime.date(2026, 10, 28)
    assert reel.reel_name("replay", day) == "reel-replay-2026-10-28"


def test_hook_png_is_transparent_9x16():
    """글자 뒤에만 막을 깔고 나머지는 비어 있어야 영상이 비친다."""
    with tempfile.TemporaryDirectory() as td:
        p = reel.hook_png("훅 문장입니다", "보조", pathlib.Path(td) / "h.png")
        im = Image.open(p)
        assert im.size == (reel.RW, reel.RH)
        assert im.mode == "RGBA"
        # 맨 아래쪽은 완전 투명이어야 한다
        assert im.getpixel((reel.RW // 2, reel.RH - 40))[3] == 0
        # 훅이 놓인 자리는 막이 깔려 불투명하다
        assert im.getpixel((reel.RW // 2, 300))[3] > 0


def test_hook_png_shrinks_long_text():
    """긴 훅을 그대로 그리면 화면을 넘어간다. 줄 수가 많아지면 글자를 줄인다."""
    long_hook = "아주 긴 훅 문장을 " * 12
    with tempfile.TemporaryDirectory() as td:
        p = reel.hook_png(long_hook, None, pathlib.Path(td) / "h.png")
        im = Image.open(p)
        assert im.size == (reel.RW, reel.RH)


def test_build_rejects_missing_footage():
    try:
        reel.build("없는파일.mp4", "훅", None, "/tmp/x.mp4")
    except FileNotFoundError as e:
        assert "없는파일" in str(e)
    else:
        raise AssertionError("없는 바탕 영상은 바로 알려야 한다")


def test_available_lists_footage(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        (d / "genius.mp4").write_bytes(b"x")
        monkeypatch.setattr(reel, "FOOTAGE", d)
        assert [p.name for p in reel.available()] == ["genius.mp4"]


def test_available_empty_when_no_folder(monkeypatch):
    monkeypatch.setattr(reel, "FOOTAGE", pathlib.Path("/존재하지않는경로"))
    assert reel.available() == []
