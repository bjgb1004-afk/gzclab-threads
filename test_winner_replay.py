"""1등 번호 되짚어보기 검증.

이 기능에서 제일 비싼 실수는 **자기 회차를 안 빼는 것**이다. 넣으면 금액의 100%가
거기서 나와(2026-10-28 실측) "1등 번호는 22억"이라는 거짓이 되고, 그건 댓글 한 줄에
반박당한다. 그래서 그 선을 테스트로 묶어 둔다.
"""

import datetime

import band_picks as bp
import cards as C
import replay as rp

DRAWS = rp.fetch_draws()


def test_pick_is_stable_for_a_day():
    """같은 날이면 인스타·스레드·앱이 모두 같은 회차를 내야 한다."""
    a = rp.pick_winner("2026-10-29", DRAWS)
    b = rp.pick_winner("2026-10-29", DRAWS)
    assert a["no"] == b["no"]


def test_pick_changes_daily_without_repeats():
    days = [f"2026-11-{d:02d}" for d in range(1, 31)]
    nos = [rp.pick_winner(x, DRAWS)["no"] for x in days]
    assert len(set(nos)) == len(nos), "한 달 안에 같은 회차가 또 나오면 안 된다"


def test_own_draw_is_excluded():
    """핵심. 자기 회차가 들어가면 1등이 찍히고 금액이 억 단위가 된다."""
    for day in ("2026-10-29", "2026-11-05", "2026-12-01"):
        w = rp.winner_replay(day, DRAWS)
        assert 1 not in w["res"]["by_rank"], f"{w['draw_no']}회가 자기 자신을 세고 있다"
        assert w["res"]["draws"] == len(DRAWS) - 1 or w["res"]["draws"] < len(DRAWS)


def test_own_prize_is_reported_separately():
    """그 회차 당첨금과 나머지 합계는 따로 있어야 한다 — 합치면 그게 거짓말이다."""
    w = rp.winner_replay("2026-10-29", DRAWS)
    assert w["own_prize"] > 100_000_000          # 1등은 억 단위
    assert w["res"]["gross"] < 10_000_000        # 나머지는 만원 단위
    assert w["own_prize"] != w["res"]["gross"]


def test_numbers_match_the_actual_winning_draw():
    w = rp.winner_replay("2026-10-29", DRAWS)
    real = next(d for d in DRAWS if d["no"] == w["draw_no"])
    assert w["numbers"] == sorted(real["numbers"])


# ---------- 스레드 글 ----------

def test_thread_post_shape():
    post = bp.build_winner("2026-10-29", DRAWS)
    assert post["id"] == "winner-2026-10-29"
    assert post["slot"] == "winner"
    # 댓글로 번호를 받아 돌려주는 구조라야 이 글에 답글이 붙는다
    assert post["reply_mode"] == "replay"
    assert len(post["text"]) <= bp.LIMIT


def test_thread_post_shows_both_numbers():
    """그 회차 금액과 나머지 합계가 둘 다 본문에 있어야 한다."""
    post = bp.build_winner("2026-10-29", DRAWS)
    w = rp.winner_replay("2026-10-29", DRAWS)
    assert f"{w['own_prize'] / 100000000:.1f}억원" in post["text"]
    assert rp.won(w["res"]["gross"]) in post["text"]
    assert "1등 번호라고 특별한 게 아님" in post["text"]


def test_thread_post_big_number_is_labelled_as_that_draw():
    """첫 줄은 그 회차 당첨금(훅). 바로 뒤에 '이 회차를 빼고'로 나머지 성적을 따로 보여야 한다."""
    t = bp.build_winner("2026-10-29", DRAWS)["text"]
    lines = t.splitlines()
    assert "억" in lines[0] and "그 회차" in lines[0]
    assert "이 회차를 빼고" in t
    assert t.index("억") < t.index("이 회차를 빼고") < t.index("다 합쳐")


def test_winner_runs_daily_in_its_window():
    KST = datetime.timezone(datetime.timedelta(hours=9))
    at = lambda h, m, d=29: datetime.datetime(2026, 10, d, h, m, tzinfo=KST)
    assert bp.due(at(14, 5)) == []
    assert "winner" in bp.due(at(14, 7))
    assert bp.due(at(18, 0)) == []
    # 토요일엔 번호대 글이 제 시각에 따로 나간다
    assert "band" in bp.due(at(10, 7, d=31))


# ---------- 인스타 ----------

def test_instagram_card_and_hook_use_same_draw():
    day = datetime.date(2026, 10, 29)
    hook, sub = C.slide_hook("replay", day, DRAWS)
    w = rp.winner_replay(day.isoformat(), DRAWS)
    assert str(w["draw_no"]) in hook
    assert sub == "지난 회차 1등 번호"


def test_instagram_caption_separates_the_two_numbers():
    import instagram_publish as ip
    _name, cap = ip.build("replay", datetime.date(2026, 10, 29))
    w = rp.winner_replay("2026-10-29", DRAWS)
    assert f"{w['own_prize'] / 100000000:.1f}억원" in cap
    assert "그 회차를 빼면 아무 번호랑 성적이 같습니다" in cap
    assert len(cap) <= ip.CAPTION_LIMIT
