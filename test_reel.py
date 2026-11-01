"""reel.py 검증. ffmpeg를 실제로 돌리는 건 selftest 하나뿐이고 나머지는 순수 함수다."""

import datetime
import pathlib
import tempfile

from PIL import Image

import subprocess

import cards as C
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


def test_hook_time_follows_text_length():
    """글자가 많으면 훅이 길어져야 한다. 고정 3초였을 때 유저가 못 읽었다(2026-11-01)."""
    짧 = reel.hook_sec("번호 공개", None)
    긺 = reel.hook_sec("485회 1등 번호, 그 회차에 15.0억원 나왔습니다",
                       "이 회차를 빼고 나머지 985회에 돌려보면?")
    assert 짧 == reel.HOOK_MIN, "짧은 훅도 최소 시간은 준다"
    assert 긺 > 짧 * 1.5, f"긴 훅이 안 길어졌다: {긺}"
    assert (len("485회 1등 번호, 그 회차에 15.0억원 나왔습니다")
            + len("이 회차를 빼고 나머지 985회에 돌려보면?")) / 긺 <= 7.0, "초당 7자를 넘기면 못 읽는다"


def test_body_always_outlasts_hook(monkeypatch):
    """바탕 영상이 짧아도 훅을 자르지 않는다 — 배속을 낮춰서 채운다."""
    seen = {}
    monkeypatch.setattr(reel, "_duration", lambda p: 3.0)   # 아주 짧은 클립
    monkeypatch.setattr(reel, "build", lambda *a, **k: seen.update(k) or "x.mp4")
    reel.build_for("band", datetime.date(2026, 11, 2))
    hs = reel.hook_sec(*C.slide_hook("band", datetime.date(2026, 11, 2), None))
    assert seen["body_sec"] >= hs, f"훅 {hs}s인데 화면은 {seen['body_sec']}s뿐"
    assert seen["speed"] < 1.0, "짧은 클립은 느리게 틀어야 채워진다"


def test_build_for_names_missing_footage():
    """build()의 가드보다 _duration이 먼저 불린다. 거기서 빈 출력을 float()에 넘기면
    "could not convert string to float" 만 남아 원인을 못 찾는다(2026-10-30 사고)."""
    try:
        reel._duration("없는파일.mp4")
    except FileNotFoundError as e:
        assert "없는파일" in str(e)
    else:
        raise AssertionError("없는 바탕 영상은 경로를 들고 죽어야 한다")


def test_footage_is_committed():
    """러너는 저장소를 받아서 돈다 — 바탕 영상이 커밋돼 있지 않으면 릴스가 매번 실패한다."""
    tracked = subprocess.run(["git", "ls-files", "assets/footage"],
                             capture_output=True, text=True, cwd=reel.HERE).stdout.split()
    for kind in reel.PROFILE:
        assert f"assets/footage/{kind}.mp4" in tracked, f"{kind}.mp4 미커밋"


def test_available_lists_footage(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        (d / "genius.mp4").write_bytes(b"x")
        monkeypatch.setattr(reel, "FOOTAGE", d)
        assert [p.name for p in reel.available()] == ["genius.mp4"]


def test_available_empty_when_no_folder(monkeypatch):
    monkeypatch.setattr(reel, "FOOTAGE", pathlib.Path("/존재하지않는경로"))
    assert reel.available() == []
