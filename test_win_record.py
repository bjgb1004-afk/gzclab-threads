"""누적 당첨 실적(win_totals / win_line / grade_hook)과 흐름 정리 글 얹기 검증.

이 기능의 위험은 과장이다. 숫자가 틀리는 것보다 "번호가 잘 맞는다"로 읽히는 게 더 나쁘다
— 번호는 닉네임 시드 무작위 조합이다. 그래서 문구 자체를 테스트로 묶어 둔다.
"""

import json
import pathlib
import tempfile

import lotto_picks as lp
import lotto_stats as ls


def sandbox(picks=None):
    tmp = pathlib.Path(tempfile.mkdtemp())
    lp.PICKS = tmp / "picks.json"
    lp.PICKS.write_text(json.dumps(picks or {}, ensure_ascii=False), encoding="utf-8")
    return lp.PICKS


def week(games, ranks):
    return {"days": {}, "stats": {"grade_result": {"games": games, "ranks": ranks}}}


# ---------- 집계 ----------

def test_win_totals_sums_across_draws():
    sandbox({"1245": week(181, {"4": 1, "5": 6}),
             "1246": week(83, {"5": 1}),
             "1247": week(68, {"5": 2})})
    assert lp.win_totals() == {"draws": 3, "games": 332, "ranks": {4: 1, 5: 9}}


def test_win_totals_ignores_weeks_without_result():
    sandbox({"1245": week(10, {"5": 1}), "1246": {"days": {}, "stats": {"post_id": "x"}}})
    assert lp.win_totals()["draws"] == 1


def test_save_grade_result_shape():
    p = sandbox()
    lp.save_grade_result(1248, [0] * 68, {5: [1, 1], 4: [1]})
    got = json.loads(p.read_text(encoding="utf-8"))["1248"]["stats"]["grade_result"]
    assert got == {"games": 68, "ranks": {"4": 1, "5": 2}}


# ---------- 실적 한 줄 ----------

def test_win_line_none_without_wins():
    """없는 성과를 쓰지 않는다. 당첨이 0이면 줄 자체를 넣지 않는다."""
    sandbox({"1245": week(181, {})})
    assert lp.win_line() is None
    sandbox({})
    assert lp.win_line() is None


def test_win_line_does_not_lead_with_the_better_prize():
    """10명 중 9명이 5등인데 4등 상금(5만원)을 앞세우면 평균 수익을 10배로 오해시킨다.
    문구에서 상금 액수는 아예 쓰지 않기로 했다(2026-10-26)."""
    sandbox({"1245": week(181, {"4": 1, "5": 6}), "1246": week(151, {"5": 3})})
    line = lp.win_line()
    assert "5만원" not in line and "5천원" not in line


def test_win_line_does_not_hide_denominator():
    """전체 게임 수가 없으면 당첨률을 숨기는 글이 된다."""
    sandbox({"1245": week(181, {"5": 6})})
    line = lp.win_line()
    assert "181게임 중" in line and "6명 당첨" in line


def test_win_line_never_claims_better_odds():
    """번호는 닉네임 시드 조합이고 실측상 무작위와 차이가 없다. 확률 주장은 거짓이 된다."""
    sandbox({"1245": week(181, {"5": 6})})
    line = lp.win_line()
    for banned in ("확률", "적중률", "잘 맞", "올라", "유리"):
        assert banned not in line, banned


# ---------- 채점 글 첫 줄 ----------

def test_grade_hook_leads_with_best_rank():
    assert lp.grade_hook(1245, [0] * 181, {4: [1], 5: [1] * 6}) == (
        "스레드 댓글로 받아간 번호에서 4등 나왔습니다. (1245회, 181게임 중)")


def test_grade_hook_counts_when_several():
    assert "5등 2명 나왔습니다" in lp.grade_hook(1247, [0] * 68, {5: [1, 1]})


def test_grade_hook_is_honest_when_nothing_won():
    """꽝인 주에 당첨을 꾸며내지 않는다. 그게 '전부 채점함' 약속의 근거다."""
    hook = lp.grade_hook(1248, [0] * 50, {})
    assert "전부 꽝" in hook and "숨기지 않고" in hook


# ---------- 흐름 정리 글에 얹기 ----------

def _stats():
    """lotto_stats.analyze()의 실제 출력 모양(2026-10-26, 1247회 기준)."""
    return {"last": 1247, "latest": [8, 14, 21, 22, 42, 45], "carry_rate": 64,
            "carry_avg": 0.83, "hot": [[13, 5], [16, 3], [18, 3]],
            "cold_recent": [3, 6, 12, 15, 17, 29, 30, 35, 37, 39, 40],
            "longest": [17, 21], "follow": {"from": 8, "to": 4, "rate": 20, "gap": 2},
            "band": [[11, 20], 27], "sum": [[121, 140], 26],
            "odd_even": ["3:3", 33], "no_consec": 48, "filter_pass": 72, "total": 1247}


def test_build_post_includes_extra():
    text = ls.build_post(_stats(), extra="실적 한 줄")
    assert "실적 한 줄" in text and len(text) <= ls.LIMIT


def test_build_post_without_extra_unchanged():
    text = ls.build_post(_stats())
    assert text.startswith("1248회 로또 흐름 정리")
    assert len(text) <= ls.LIMIT


def test_build_post_drops_cold_line_before_extra():
    """자리가 모자라면 통계 한 줄을 버리고 실적을 남긴다 — 실제 당첨자가 더 값지다."""
    extra = "실" * 60  # cold 줄을 빼면 들어가는 크기
    s = _stats()
    s["cold_recent"] = list(range(1, 46))  # 이 줄이 혼자 100자가 넘는다
    text = ls.build_post(s, extra=extra)
    assert extra in text
    assert "한 번도 안 나온" not in text
    assert len(text) <= ls.LIMIT


def test_build_post_has_no_double_blank_when_extra_dropped():
    """실적 줄을 뺄 때 앞의 빈 줄까지 빠져야 한다."""
    text = ls.build_post(_stats(), extra="실" * 400)
    assert "\n\n\n" not in text


def test_build_post_drops_extra_as_last_resort():
    s = _stats()
    text = ls.build_post(s, extra="실" * 400)
    assert "실" * 400 not in text
    assert len(text) <= ls.LIMIT


# ---------- 실제 데이터 ----------

def test_real_picks_has_backfilled_record():
    """발행된 채점 글 3편의 숫자가 picks.json에 들어가 있어야 실적 줄이 0이 아니다."""
    import importlib
    importlib.reload(lp)
    t = lp.win_totals()
    assert t["draws"] >= 3, t
    assert t["ranks"].get(4) == 1 and t["ranks"].get(5, 0) >= 9, t
    assert lp.win_line() is not None


# ---------- 당첨자 본인에게 알리기 ----------

def reply_sandbox(picks=None):
    """publish를 가짜로 바꾸고 (본문, 답글대상) 목록을 모은다."""
    import publish
    path = sandbox(picks)
    calls = {"posts": [], "telegram": []}
    publish.TOKEN = "x"
    publish.publish = lambda text, reply_to=None: (
        calls["posts"].append((text, reply_to)) or f"r{len(calls['posts'])}")
    publish.telegram = lambda text: calls["telegram"].append(text)
    return path, calls


WIN = [4, 5, 25, 28, 32, 42]
BONUS = 12


def entry(name, nums, rid):
    return {"name": name, "numbers": nums, "reply_id": rid}


def test_comment_entries_keeps_reply_id():
    """당첨자 자리에 답글을 달려면 내 답글의 id가 필요하다."""
    items = [{"id": "A1", "username": "gzclab",
              "text": "chulsoo아 1247회 네 조합 뽑아왔어!\n04 05 25 28 32 42\n\n닉네임으로"},
             {"id": "B1", "username": "someone", "text": "나도 줘"}]
    got = lp.comment_entries(items)
    assert got == [{"name": "chulsoo", "numbers": WIN, "reply_id": "A1"}]
    # 기존 집계 경로는 2-튜플 그대로여야 한다
    assert lp.comment_games(items) == [("chulsoo", WIN)]


def test_reply_to_winners_only_replies_to_winners():
    _p, calls = reply_sandbox()
    entries = [entry("win5", [4, 5, 25, 1, 2, 3], "A"),      # 3개 일치 = 5등
               entry("nope", [1, 2, 3, 6, 7, 8], "B"),        # 꽝
               entry("win4", [4, 5, 25, 28, 1, 2], "C")]      # 4개 일치 = 4등
    assert lp.reply_to_winners(1247, entries, WIN, BONUS) == 2
    targets = {rid for _t, rid in calls["posts"]}
    assert targets == {"A", "C"}
    assert "B" not in targets


def test_reply_to_winners_is_idempotent():
    """같은 사람에게 두 번 보내면 그게 제일 빠른 차단 사유다."""
    p, calls = reply_sandbox()
    entries = [entry("win5", [4, 5, 25, 1, 2, 3], "A")]
    assert lp.reply_to_winners(1247, entries, WIN, BONUS) == 1
    assert lp.reply_to_winners(1247, entries, WIN, BONUS) == 0
    assert len(calls["posts"]) == 1
    # 보낸 기록이 picks.json에 남아야 다음 실행이 안 보낸다
    saved = json.loads(p.read_text(encoding="utf-8"))["1247"]["stats"]["winner_replies"]
    assert saved == ["A"]


def test_reply_to_winners_skips_entries_without_reply_id():
    _p, calls = reply_sandbox()
    assert lp.reply_to_winners(1247, [entry("x", [4, 5, 25, 1, 2, 3], None)], WIN, BONUS) == 0
    assert not calls["posts"]


def test_reply_to_winners_respects_cap():
    """파싱이 틀어져 수백 건이 나가는 일을 막는 안전장치."""
    _p, calls = reply_sandbox()
    entries = [entry(f"u{i}", [4, 5, 25, 1, 2, 3], f"R{i}") for i in range(40)]
    sent = lp.reply_to_winners(1247, entries, WIN, BONUS)
    assert sent == lp.WINNER_REPLY_CAP == 20
    assert len(calls["posts"]) == 20


def test_reply_to_winners_one_failure_does_not_block_rest():
    import publish
    p, calls = reply_sandbox()
    real = publish.publish

    def flaky(text, reply_to=None):
        if reply_to == "A":
            raise RuntimeError("일시 오류")
        return real(text, reply_to)

    publish.publish = flaky
    entries = [entry("a", [4, 5, 25, 1, 2, 3], "A"), entry("b", [4, 5, 25, 1, 2, 3], "B")]
    assert lp.reply_to_winners(1247, entries, WIN, BONUS) == 1
    # 실패한 사람은 기록에 안 들어가 다음 실행이 다시 시도한다
    saved = json.loads(p.read_text(encoding="utf-8"))["1247"]["stats"]["winner_replies"]
    assert saved == ["B"]


def test_winner_reply_tells_how_to_collect():
    """당첨된 걸 알려주면서 받는 방법을 빼면 알려준 의미가 없다."""
    low = lp.winner_reply("철수", 1247, 5, 3)
    assert "5등이야" in low and "5천원" in low and "판매점" in low and "1년" in low
    mid = lp.winner_reply("철수", 1247, 4, 4)
    assert "5만원" in mid and "판매점" in mid
    high = lp.winner_reply("철수", 1247, 2, 5)
    assert "농협은행" in high and "신분증" in high
    # 1~3등 상금은 회차마다 달라 액수를 쓰지 않는다
    assert "원" not in high.replace("신분증", "").replace("농협은행", "").split("지급")[0][20:]


def test_run_grade_sends_winner_replies():
    import publish
    p, calls = reply_sandbox()
    lp.QUEUE = p.with_name("queue.json")
    lp.save(lp.QUEUE, [{"id": "picks-1247-stats", "post_id": "S", "status": "published"}])
    lp.fetch_winning = lambda draw: (WIN, BONUS)
    lp.conversation_all = lambda m, t: [
        {"id": "A", "username": "gzclab", "text": "win아 1247회 네 조합 뽑아왔어!\n04 05 25 01 02 03\n\n닉"},
        {"id": "B", "username": "gzclab", "text": "lose아 1247회 네 조합 뽑아왔어!\n01 02 03 06 07 08\n\n닉"},
    ]
    assert lp.run_grade(at_now(), dry=False, draw_no=1247) == 0
    # 채점 글 1건 + 링크 답글 없음 + 당첨자 답글 1건
    assert any(rid == "A" and "5등이야" in t for t, rid in calls["posts"])
    assert not any(rid == "B" for _t, rid in calls["posts"])


def at_now():
    import datetime
    return datetime.datetime(2026, 10, 26, 10, 7, tzinfo=lp.g.KST)
