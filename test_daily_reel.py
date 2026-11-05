"""오늘의 1게임 릴스와 인스타 댓글 답글 검증."""

import datetime
import subprocess

import daily_reel as dr
import ig_comments as ic
import lotto_gen as g

KST = g.KST
FRI, SAT = datetime.date(2026, 11, 6), datetime.date(2026, 11, 7)


def test_josa():
    assert dr.josa("가우스") == "가" and dr.josa("오일러") == "가" and dr.josa("아르키메데스") == "가"
    assert dr.josa("파스칼") == "이"


def test_today_game_matches_genius_card_numbers():
    l1, l2, how, nums, draw_no = dr.today_game("genius", FRI)
    gi = g.GENIUSES[FRI.weekday()]
    assert nums == list(g.genius_games(gi["id"], draw_no)[0])   # 카드·스레드와 같은 A게임
    assert gi["name"] in l1 and str(draw_no) in l2 and how.endswith("1게임")


def test_weekend_uses_band_numbers():
    _, _, _, nums, _ = dr.today_game("band", SAT)
    assert len(nums) == 6 and nums == sorted(nums)


def test_build_is_reel_spec(tmp_path):
    out, nums, _ = dr.build("genius", FRI, tmp_path / "r.mp4")
    info = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height:format=duration",
                           "-of", "default=nw=1", str(out)], capture_output=True, text=True).stdout
    assert "width=1080" in info and "height=1920" in info
    dur = float([l for l in info.splitlines() if l.startswith("duration=")][0].split("=")[1])
    assert abs(dur - dr.total_sec()) < 0.5


def at(d, h=13):
    return datetime.datetime(2026, 11, d, h, 0, tzinfo=KST)


def state_with(*keys):
    return {"published": {k: {"media_id": f"m-{k}"} for k in keys}}


def test_targets_only_number_reels_recent():
    st = state_with("genius-2026-11-06", "replay-2026-11-06", "genius-2026-11-01", "band-2026-11-07")
    keys = [k for k, _, _ in ic.targets(st, at(8))]
    assert keys == ["genius-2026-11-06", "band-2026-11-07"]


def test_replies_once_skips_me_and_already_answered():
    st = state_with("genius-2026-11-06")
    comments = {"data": [
        {"id": "c1", "username": "kim", "text": "kim"},
        {"id": "c2", "username": "gzclab", "text": "내 댓글"},
        {"id": "c3", "username": "lee", "text": "lee", "replies": {"data": [{"username": "gzclab"}]}},
    ]}
    sent = []
    fetch = lambda path, params, token: comments
    send = lambda path, params, token: sent.append((path, params["message"])) or {"id": "r1"}
    ic.run(st, at(6), "t", print, fetch, send)
    ic.run(st, at(6, 14), "t", print, fetch, send)          # 두 번 돌아도 한 번만 답한다
    assert [p for p, _ in sent] == ["c1/replies"]
    assert sent[0][1].startswith("@kim 1249회 네 1게임")


def test_missing_permission_notifies_once_and_stops_for_the_day():
    st = state_with("genius-2026-11-06")
    notes = []

    def fetch(path, params, token):
        raise RuntimeError("403 permission")
    ic.run(st, at(6), "t", notes.append, fetch, None)
    ic.run(st, at(6, 14), "t", notes.append, fetch, None)
    assert len(notes) == 1 and st["comments"]["blocked_day"] == "2026-11-06"


def test_caps():
    st = state_with("genius-2026-11-06")
    comments = {"data": [{"id": f"c{i}", "username": f"u{i}", "text": "x"} for i in range(30)]}
    sent = []
    ic.run(st, at(6), "t", print, lambda *a: comments, lambda p, q, t: sent.append(p) or {"id": "r"})
    assert len(sent) == ic.RUN_CAP


def test_daily_caption_fits_and_asks_comment():
    import instagram_publish as ip
    cap = ip.daily_caption("genius", FRI)
    assert len(cap) <= ip.CAPTION_LIMIT and "댓글에 닉네임" in cap and "팔로우" in cap
    assert cap.count("#") <= 5
