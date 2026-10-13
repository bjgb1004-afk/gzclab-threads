"""lotto_picks 자체 점검. `python test_lotto_picks.py`. 네트워크 없이 한 주를 통째로 돌려본다."""

import datetime
import functools
import json
import pathlib
import shutil
import tempfile

import auto_reply
import lotto_gen as g
import lotto_picks as lp
import lotto_stats
import publish
import recipes

KST = g.KST
HERE = pathlib.Path(__file__).parent


def at(y, m, d, hh, mm=7):
    return datetime.datetime(y, m, d, hh, mm, tzinfo=KST)


def sandbox():
    """임시 폴더에 빈 picks.json·큐·comment_picks를 두고, 발행·알림·당첨번호 조회를 가짜로 바꾼다."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    lp.PICKS = tmp / "picks.json"
    lp.QUEUE = tmp / "queue.json"
    lp.QUEUE.write_text("[]", encoding="utf-8")
    lp.COMMENT_PICKS = tmp / "comment_picks.json"
    shutil.copy(HERE / "district_replies.json", tmp / "district_replies.json")
    lp.REPLIES = tmp / "district_replies.json"

    calls = {"posts": [], "telegram": []}

    def fake_publish(text, reply_to=None):
        calls["posts"].append((text, reply_to))
        return f"id-{len(calls['posts'])}"

    publish.publish = fake_publish
    publish.telegram = lambda text: calls["telegram"].append(text)
    lp.history_or_none = lambda dry=False: offline_history()  # 네트워크 금지
    return calls


@functools.lru_cache(maxsize=1)
def offline_history():
    """네트워크 없이 전체 당첨 이력. 저장된 캐시를 쓴다. [(회차, 번호6개)...] 오름차순."""
    rows = json.loads((HERE / "draws_cache.json").read_text(encoding="utf-8"))
    return sorted((x["no"], sorted(x["numbers"])) for x in rows)


def seed_comment_picks(draw_no, entries):
    """[(recipe_id, numbers), ...]를 그 회차 댓글 번호로 기록한다."""
    picks = [
        {"draw": draw_no, "recipe": rid, "username": f"u{i}", "numbers": nums,
         "reply_id": f"seed-{i}"}
        for i, (rid, nums) in enumerate(entries)
    ]
    lp.COMMENT_PICKS.write_text(json.dumps(picks, ensure_ascii=False), encoding="utf-8")


# 1244회(2026-10-03 추첨)의 당첨번호를 가정한다. 월요일 A게임과 4개 겹치게 골랐다.
WIN = ([3, 18, 19, 27, 40, 44], 38)


def test_all_posts_fit_the_limit_for_two_years():
    """월~금 분석법 글 내용은 history만의 함수(회차엔 안 움직임) — 회차 몇 개로 글자수만 본다."""
    history = offline_history()
    for draw in (1244, 1300, 9999):
        for day in lp.DAYS:
            text, games, meta = lp.build_daily(draw, day, history)
            assert len(text) <= lp.LIMIT, (draw, day, len(text))
            if meta["kind"] == "method":
                # 번호는 본문에 없고 댓글 답글로만 나간다
                assert games == [] and "댓글 남기면" in text
            else:
                assert "구 이름 남겨줘" in text
                assert len(games) == 5


def test_saturday_stores_rotate_and_are_real_top_stores():
    stores = lp.top_stores()
    assert len(stores) >= 20
    assert all(s["wins"] >= lp.STORE_MIN_WINS for s in stores)
    a = lp.weekly_stores(1244, stores)
    b = lp.weekly_stores(1245, stores)
    assert len({s["name"] for s in a}) == 5
    assert a != b


def test_full_week():
    calls = sandbox()
    lp.fetch_winning = lambda draw: WIN if draw == 1244 else None

    # 월~토 00:07 이후(20시 판매 마감). 일요일에는 아무것도 안 올라간다.
    for day in range(28, 31):
        assert lp.run_auto(at(2026, 9, day, 23), dry=False) == 0
    for day in range(1, 3):
        assert lp.run_auto(at(2026, 10, day, 23), dry=False) == 0
    assert lp.run_auto(at(2026, 10, 3, 17), dry=False) == 0
    bodies = [t for t, reply in calls["posts"] if reply is None]
    assert len(bodies) == 6, len(bodies)
    assert "월요일의 분석: 아르키메데스" in bodies[0]
    assert "금요일의 분석: 가우시안" in bodies[4]
    assert "토요일은 명당 번호" in bodies[5]
    for t in bodies[:5]:
        assert "댓글 남기면" in t  # 번호 없이 분석 과정만, 번호는 댓글 답글로
    # 번호 글마다 앱 링크 답글 (월~토 6일)
    link_replies = [t for t, reply in calls["posts"] if reply and lp.LINK in t]
    assert len(link_replies) == 6, len(link_replies)

    # 같은 날 백업 cron이 또 돌아도 중복 발행하지 않는다.
    before = len(calls["posts"])
    lp.run_auto(at(2026, 10, 3, 19, 37), dry=False)
    assert len(calls["posts"]) == before

    # 토 21:37 채점. 이 주엔 분석법 댓글 번호가 하나도 없다(auto_reply를 안 돌렸다) → 순위 없음.
    assert lp.run_auto(at(2026, 10, 3, 21, 37), dry=False) == 0
    picks = json.loads(lp.PICKS.read_text(encoding="utf-8"))
    week = picks["1244"]
    assert week["result"]["numbers"] == WIN[0]
    assert week["days"]["mon"]["games"] == [] and "score" not in week["days"]["mon"]
    assert week["recipe_result"]["winners"] == []
    result_text = [t for t, reply in calls["posts"] if reply is None][-1]
    assert result_text.startswith("[1244회 결과] 03 18 19 27 40 44 + 보너스 38")
    assert "토요일 명당 5게임" in result_text
    assert "분석법 댓글 번호가 없어서" in result_text
    assert len(result_text) <= lp.LIMIT

    # 명당 글 + 분석법 5개 글 전부에 채점 답글(분석법은 "집계할 게 없음")
    day_ids = {d["post_id"] for d in week["days"].values()}
    scored = [t for t, reply in calls["posts"] if reply in day_ids and "채점" in t]
    assert len(scored) == 6, scored
    store_scored = [t for t in scored if "게임)" in t]
    assert len(store_scored) == 1 and "최고" in store_scored[0] and "일치" in store_scored[0]
    assert sum("집계할 게 없음" in t for t in scored) == 5

    # 다시 돌아도 아무것도 더 안 올린다.
    before = len(calls["posts"])
    lp.run_auto(at(2026, 10, 4, 7, 37), dry=False)
    assert len(calls["posts"]) == before

    # 모든 글이 큐에 기록돼 자동답글·인사이트 대상이 된다.
    queue = json.loads(lp.QUEUE.read_text(encoding="utf-8"))
    ids = [p["id"] for p in queue]
    assert ids == [f"picks-1244-{d}" for d in lp.DAYS] + ["picks-1244-result"], ids
    # 월~금 글은 전부 댓글마다 그 분석법 번호 1게임을 답으로 달아야 한다
    for day, rid in zip(lp.DAYS[:5], recipes.ORDER):
        entry = next(p for p in queue if p["id"] == f"picks-1244-{day}")
        assert entry["reply_mode"] == "combo" and entry["genius"] == rid, entry
    now = datetime.datetime(2026, 10, 3, 22, tzinfo=datetime.timezone.utc)
    assert len(auto_reply.targets(queue, now)) == 7


def test_recipe_ranking_from_comment_picks():
    """댓글로 나간 분석법 번호를 모아 분석법별 순위를 매긴다(로또흐름분석 글과 같은 방식)."""
    calls = sandbox()
    lp.fetch_winning = lambda draw: WIN
    numbers, bonus = WIN
    for day in range(28, 31):
        lp.run_daily(at(2026, 9, day, 17), dry=False)
    for day in range(1, 4):
        lp.run_daily(at(2026, 10, day, 17), dry=False)

    # 아르키메데스: 2명 다 당첨번호와 하나도 안 겹침(등수권 밖). 피보나치: 1명이 당첨번호 그대로(1등).
    seed_comment_picks(1244, [
        ("archimedes", [1, 2, 4, 5, 7, 8]),
        ("archimedes", [1, 2, 4, 5, 7, 9]),
        ("fibonacci", numbers),
    ])

    assert lp.run_result(at(2026, 10, 3, 21, 37), dry=False) == 0
    picks = json.loads(lp.PICKS.read_text(encoding="utf-8"))
    assert picks["1244"]["recipe_result"]["winners"] == ["fibonacci"]

    result_text = [t for t, r in calls["posts"] if r is None][-1]
    assert "월~금 분석법 댓글 3명 채점" in result_text
    assert "아르키메데스  2명 중 0명 등수권·최고0개" in result_text
    assert "피보나치  1명 중 1명 등수권·최고6개" in result_text
    assert "이번 주 분석법 1위: 피보나치" in result_text
    assert "순위는 회차마다 뒤집힘" in result_text and "확률을 바꾸진 않음" in result_text
    assert "누적 1위: 피보나치 1" in result_text

    week = picks["1244"]
    day_ids = {d["post_id"] for d in week["days"].values()}
    scored = {r: t for t, r in calls["posts"] if r in day_ids and "채점" in t}
    mon_post = week["days"]["mon"]["post_id"]
    tue_post = week["days"]["tue"]["post_id"]
    assert "댓글 2명, 최고 0개 일치. 등수권은 없음" in scored[mon_post]
    assert "댓글 1명 중 1명 등수권! 최고 6개 일치" in scored[tue_post]


def test_saturday_after_cutoff_and_sunday_post_nothing():
    calls = sandbox()
    lp.run_daily(at(2026, 10, 3, 20, 10), dry=False)
    lp.run_daily(at(2026, 10, 4, 17), dry=False)
    assert calls["posts"] == []


def test_missing_numbers_waits_then_alerts():
    calls = sandbox()
    lp.fetch_winning = lambda draw: None
    lp.run_daily(at(2026, 9, 29, 17), dry=False)  # 화요일(번호가 실리는 날)
    calls["telegram"].clear()
    posts = len(calls["posts"])
    assert lp.run_result(at(2026, 10, 3, 21, 37), dry=False) == 0  # 아직 기다린다
    assert calls["telegram"] == []
    assert lp.run_result(at(2026, 10, 4, 11, 37), dry=False) == 1  # 일요일 11시 넘으면 알림
    assert any("당첨번호를 못 받아" in t for t in calls["telegram"])
    assert len(calls["posts"]) == posts


def test_partial_week_still_scores():
    """중간 요일 발행이 실패했어도(또는 애초에 없어도) 올라간 글만으로 결과 글을 낸다."""
    calls = sandbox()
    lp.fetch_winning = lambda draw: WIN
    lp.run_daily(at(2026, 9, 30, 17), dry=False)  # 수요일(파스칼)만
    assert lp.run_result(at(2026, 10, 3, 21, 37), dry=False) == 0
    text = [t for t, r in calls["posts"] if r is None][-1]
    assert "토요일 명당 5게임" not in text  # 명당 글 자체가 없던 주
    assert "분석법 댓글 번호가 없어서" in text  # 파스칼 글 하나뿐, 아직 댓글 없음


def test_district_reply_has_no_generated_number():
    """구 TOP3만 답한다. 1등 3~6회짜리 동네 이름으로 번호를 뽑아주던 줄은 뺐다."""
    replies = json.loads((HERE / "district_replies.json").read_text(encoding="utf-8"))
    msg = auto_reply.compose("hit", "서울 노원구", "u1", replies, True)
    assert msg.startswith("u1아 노원구 1등 많이 나온 집 뽑아왔어!")
    assert "명당 기운" not in msg and "회 번호" not in msg
    for key in replies:
        m = auto_reply.compose("hit", key, "x" * 30, replies, True)
        assert m is None or len(m) <= auto_reply.REPLY_LIMIT, key


def fake_history(last):
    """1~last회 가짜 당첨번호(결정론적). 통계 계산이 도는지만 본다."""
    return {n: g.store_game(f"h{n}", n) for n in range(1, last + 1)}


def test_stats_post_is_facts_only_and_fits():
    import lotto_stats

    draws = fake_history(1243)
    stats = lotto_stats.analyze(draws, 1243)
    text = lotto_stats.build_post(stats)
    assert text.startswith("1244회 로또 흐름 정리")
    assert "1244회 조합 1게임" in text.split("\n")[1]
    assert len(text) <= lp.LIMIT
    assert "팔로우" in text
    # 가장 오래 쉰 번호는 실제로 그만큼 안 나왔어야 한다
    n, gap = stats["longest"]
    assert all(n not in draws[k] for k in range(1244 - gap, 1244))
    assert n in draws[1243 - gap]


def test_sunday_stats_post_and_combo_replies():
    import lotto_stats

    calls = sandbox()
    lotto_stats.fetch_all = lambda: fake_history(1243)
    assert lp.run_auto(at(2026, 9, 27, 18), dry=False) == 0
    bodies = [t for t, r in calls["posts"] if r is None]
    assert len(bodies) == 1 and bodies[0].startswith("1244회 로또 흐름 정리")
    lp.run_auto(at(2026, 9, 27, 19, 37), dry=False)  # 백업 실행은 아무것도 안 함
    assert len(calls["posts"]) == 1

    queue = json.loads(lp.QUEUE.read_text(encoding="utf-8"))
    entry = queue[-1]
    assert entry["id"] == "picks-1244-stats" and entry["reply_mode"] == "combo"
    now = datetime.datetime(2026, 9, 27, 12, tzinfo=datetime.timezone.utc)
    assert auto_reply.targets(queue, now) == [entry]

    # 댓글: 지역 없는 것 / 지역 있는 것 / 내 답글에 단 것 / 내 답글
    post = entry["post_id"]
    items = [
        {"id": "c1", "username": "kim", "text": "저도 부탁해요!", "replied_to": {"id": post}},
        {"id": "c2", "username": "lee", "text": "노원구요", "replied_to": {"id": post}},
        {"id": "r1", "username": "gzclab", "text": "...", "replied_to": {"id": "c9"}},
        {"id": "c3", "username": "park", "text": "고마워요", "replied_to": {"id": "r1"}},
    ]
    sent = []
    auto_reply.conversation = lambda media_id, token: items
    auto_reply.send = lambda text, reply_to: sent.append((reply_to, text))
    publish.TOKEN = "fake"  # 실제 실행에선 __main__이 넣는다
    orig = auto_reply.HERE
    auto_reply.HERE = lp.QUEUE.parent
    try:
        auto_reply.main()
    finally:
        auto_reply.HERE = orig
    by = dict(sent)
    draw = g.upcoming_draw_no()  # auto_reply는 실행 시각의 회차로 뽑는다
    assert by["c1"].startswith(f"kim아 {draw}회 네 조합 뽑아왔어!")
    assert g.fmt(g.store_game("user:kim", draw)) in by["c1"]
    assert "노원구 1등 많이 나온 집" in by["c2"] and f"{draw}회 번호" not in by["c2"]
    assert "c3" not in by  # 내 답글에 달린 감사 댓글엔 또 답하지 않는다


def test_rank_of():
    nums, bonus = [1, 2, 3, 4, 5, 6], 7
    assert lp.rank_of([1, 2, 3, 4, 5, 6], nums, bonus) == 1
    assert lp.rank_of([1, 2, 3, 4, 5, 7], nums, bonus) == 2
    assert lp.rank_of([1, 2, 3, 4, 5, 8], nums, bonus) == 3
    assert lp.rank_of([1, 2, 3, 4, 9, 8], nums, bonus) == 4
    assert lp.rank_of([1, 2, 3, 10, 9, 8], nums, bonus) == 5
    assert lp.rank_of([1, 2, 11, 10, 9, 8], nums, bonus) is None


if __name__ == "__main__":
    real_publish, real_telegram, real_fetch = publish.publish, publish.telegram, lp.fetch_winning
    for name, fn in sorted(vars().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
    publish.publish, publish.telegram, lp.fetch_winning = real_publish, real_telegram, real_fetch


def test_pick_times_weekday_midnight_saturday_afternoon():
    calls = sandbox()
    lp.fetch_winning = lambda draw: None
    assert lp.run_auto(at(2026, 10, 5, 0, 5), dry=False) == 0  # 월 00:05 — 아직 안 올림
    assert not calls["posts"]
    assert lp.run_auto(at(2026, 10, 5, 0, 7), dry=False) == 0  # 월 00:07
    assert len([1 for t, r in calls["posts"] if r is None]) == 1
    n = len(calls["posts"])
    assert lp.run_auto(at(2026, 10, 10, 0, 5), dry=False) == 0  # 토 00:05 — 아직
    assert len(calls["posts"]) == n
    assert lp.run_auto(at(2026, 10, 10, 0, 7), dry=False) == 0  # 토 00:07
    assert len(calls["posts"]) > n


def test_grade_post_masks_names_and_asks_for_next_draw():
    calls = sandbox()
    win, bonus = [4, 5, 25, 28, 32, 42], 12
    lp.fetch_winning = lambda draw: (win, bonus)
    items = [{"username": "gzclab", "text": f"{u}아 1245회 네 조합 뽑아왔어!\n{g.fmt(n)}\n\n닉네임으로"}
             for u, n in (("m_j000n", [4, 5, 16, 19, 25, 42]), ("siri__babyyy", [5, 17, 20, 32, 42, 45]),
                          ("nobody", [1, 2, 3, 6, 7, 8]))]
    items.append({"username": "someone", "text": "댓글"})
    lp.conversation_all = lambda media_id, token: items
    publish.TOKEN = "x"
    lp.save(lp.QUEUE, [{"id": "picks-1245-stats", "post_id": "S", "status": "published"}])
    now = at(2026, 10, 14, 1, 0)
    assert lp.run_grade(now, dry=False, draw_no=1245) == 0
    text = calls["posts"][0][0]
    assert "3게임 채점 결과" in text and "4등 1게임 · 5등 1게임 (1~3등은 없음)" in text
    assert "m_j***님" in text and "m_j000n" not in text and "sir***" in text and "siri__" not in text
    assert "1246회 번호 1게임 뽑아서 답 달아줌" in text.split("\n")[1]
    assert len(text) <= lp.LIMIT
    entry = [p for p in lp.load(lp.QUEUE, []) if p["id"] == "picks-1245-grade"][0]
    assert entry["reply_mode"] == "combo" and entry["draw"] == 1246
    # 두 번째 호출은 아무것도 올리지 않는다
    assert lp.run_grade(now, dry=False, draw_no=1245) == 0
    assert len(calls["posts"]) == 1


def test_grade_one_off_runs_after_1am_only():
    calls = sandbox()
    lp.fetch_winning = lambda draw: ([4, 5, 25, 28, 32, 42], 12)
    lp.conversation_all = lambda m, t: [{"username": "gzclab", "text": "a아 x\n04 05 16 19 25 42"}]
    publish.TOKEN = "x"
    lp.save(lp.QUEUE, [{"id": "picks-1245-stats", "post_id": "S", "status": "published"}])
    lp.run_auto(at(2026, 10, 14, 0, 50), dry=False)
    assert not any("채점 결과" in t for t, _ in calls["posts"])
    lp.run_auto(at(2026, 10, 14, 1, 5), dry=False)
    assert any("채점 결과" in t for t, _ in calls["posts"])
