"""spitto.py 검증. 발행은 가짜로 바꿔 네트워크를 타지 않는다."""

import datetime
import json
import pathlib
import tempfile

import publish
import spitto as sp

KST = sp.KST


def at(y, m, d, hh=16, mm=7):
    return datetime.datetime(y, m, d, hh, mm, tzinfo=KST)


def round_(game="스피또2000", code="SP2000", no=70, r1=8, t1=8, r2=23, t2=24,
           rate=20, status="판매중", claim="2027-12-31", as_of="26-10-16"):
    return {
        "game_type": code, "round_no": no, "game_name": game, "status": status,
        "stock_rate": rate, "rank1_remaining": r1, "rank1_total": t1,
        "rank2_remaining": r2, "rank2_total": t2, "rank1_prize": "10억원",
        "price": 2000, "sale_end_date": "2026-12-31",
        "claim_end_date": claim, "figures_as_of": as_of,
    }


# 실제 응답 모양 그대로(parseSpittoRow.test.ts의 샘플 + 판매종료 회차 하나)
ROUNDS = [
    round_(),                                                      # 1등 8/8 = 1.00
    round_("스피또1000", "SP1000", 97, 3, 10, 5, 20, 55),           # 0.30
    round_("스피또500", "SP500", 41, 1, 4, 2, 8, 80),               # 0.25
    round_("스피또2000", "SP2000", 62, None, None, None, None, 100,
           status="판매종료", claim="2026-10-31"),
]


def sandbox():
    """임시 큐를 쓰고 발행을 가짜로 바꾼다. 발행된 (본문, 답글대상)을 모아 돌려준다."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    sp.QUEUE = tmp / "queue.json"
    sp.QUEUE.write_text("[]", encoding="utf-8")
    calls = {"posts": [], "telegram": []}
    publish.TOKEN = "x"
    publish.publish = lambda text, reply_to=None: (
        calls["posts"].append((text, reply_to)) or f"id{len(calls['posts'])}")
    publish.telegram = lambda text: calls["telegram"].append(text)
    return calls


def bodies(calls):
    return [t for t, reply in calls["posts"] if reply is None]


# ---------- 정렬 ----------

def test_selling_order_matches_app():
    """1등 많이 남은 순. 앱 목록 1위와 글의 1위가 같아야 글이 거짓이 안 된다."""
    order = [(r["game_name"], r["round_no"]) for r in sp.selling_rounds(ROUNDS)]
    assert order == [("스피또2000", 70), ("스피또1000", 97), ("스피또500", 41)]
    # 판매종료 회차는 빠진다
    assert ("스피또2000", 62) not in order


def test_unknown_quantity_goes_last():
    unknown = round_("스피또500", "SP500", 9, None, None, None, None, 50)
    order = sp.selling_rounds([unknown, round_()])
    assert order[-1]["round_no"] == 9
    assert sp.remaining_ratio(unknown) == -1


# ---------- 잔여 글 ----------

def test_stock_post_shape():
    calls = sandbox()
    assert sp.run_stock(at(2026, 10, 26), dry=False, rounds=ROUNDS) == 0
    text = bodies(calls)[0]
    # 첫 줄 후킹은 실제 숫자. 8/8이면 "한 장도 안 나갔다"로 쓴다.
    assert text.startswith("[스피또] 스피또2000 70회는 1등 8매가 아직 한 장도 안 나갔습니다.")
    assert "스피또1000 97회  1등 3/10매 · 2등 5/20매 · 입고율 55%" in text
    # 기준일을 반드시 밝힌다 — 빠지면 실시간으로 오해한다
    assert "26-10-16 기준" in text and "주 1회 갱신" in text
    # 정직 문구가 같은 글에 있어야 한다
    assert "기대값은 마이너스" in text
    assert len(text) <= sp.LIMIT
    # 링크 답글이 따라붙는다
    assert any(reply == "id1" and sp.LINK in t for t, reply in calls["posts"])
    # 판매종료 회차는 본문에 안 들어간다
    assert "62회" not in text


def test_stock_post_never_triggers_lotto_auto_reply():
    """'구 이름 남겨줘'가 들어가면 auto_reply가 이 글에 로또 TOP3를 답으로 단다."""
    calls = sandbox()
    sp.run_stock(at(2026, 10, 26), dry=False, rounds=ROUNDS)
    text = bodies(calls)[0]
    assert "구 이름 남겨줘" not in text
    entry = json.loads(sp.QUEUE.read_text(encoding="utf-8"))[0]
    assert "reply_mode" not in entry and entry["slot"] == "spitto"


def test_stock_post_fits_limit_with_many_rounds():
    many = [round_(f"스피또2000", "SP2000", 50 + i, i % 8 + 1, 8, 20, 24, 40 + i)
            for i in range(12)]
    text = sp.build_stock_post(many, at(2026, 10, 26))
    assert len(text) <= sp.LIMIT
    assert "기대값은 마이너스" in text  # 줄 수를 줄여서라도 이 줄은 남긴다


def test_stock_cooldown():
    calls = sandbox()
    assert sp.run_stock(at(2026, 10, 26), dry=False, rounds=ROUNDS) == 0
    n = len(calls["posts"])
    # 다음 날은 같은 숫자라 안 올린다
    assert sp.run_stock(at(2026, 10, 27), dry=False, rounds=ROUNDS) == 0
    assert len(calls["posts"]) == n
    # 3일 뒤엔 갱신분이 들어가므로 올린다
    assert sp.run_stock(at(2026, 10, 29), dry=False, rounds=ROUNDS) == 0
    assert len(calls["posts"]) > n


def test_stock_skipped_when_quantities_unknown():
    calls = sandbox()
    blind = [round_("스피또500", "SP500", 9, None, None, None, None, 50)]
    assert sp.run_stock(at(2026, 10, 26), dry=False, rounds=blind) == 0
    assert not calls["posts"]  # 모르는 값을 0으로 쓰지 않는다


# ---------- 마감 경고 ----------

def test_claim_warning_picks_earliest_and_groups():
    rounds = [
        round_("스피또2000", "SP2000", 62, status="판매종료", claim="2026-10-31"),
        round_("스피또1000", "SP1000", 97, status="판매종료", claim="2026-10-31"),
        round_("스피또500", "SP500", 41, status="판매종료", claim="2026-11-30"),
    ]
    w = sp.claim_warning(rounds, at(2026, 10, 25))
    assert w["claim_end_date"] == "2026-10-31" and w["days_left"] == 6
    assert w["labels"] == ["스피또2000 62회", "스피또1000 97회"]
    # 11-30은 14일 밖이라 안 섞인다
    assert "스피또500 41회" not in w["labels"]


def test_claim_warning_window():
    r = [round_(claim="2026-11-30", status="판매종료")]
    assert sp.claim_warning(r, at(2026, 11, 15)) is None       # 15일 남음 — 아직
    assert sp.claim_warning(r, at(2026, 11, 16))["days_left"] == 14
    assert sp.claim_warning(r, at(2026, 11, 30))["days_left"] == 0   # 오늘이 마지막
    assert sp.claim_warning(r, at(2026, 12, 1)) is None         # 지났다


def test_claim_post_shape_and_once_per_deadline():
    calls = sandbox()
    rounds = [round_("스피또1000", "SP1000", 97, status="판매종료", claim="2026-10-31")]
    assert sp.run_claim(at(2026, 10, 25), dry=False, rounds=rounds) == 0
    text = bodies(calls)[0]
    assert text.startswith("[스피또] 6일 뒤면 당첨금을 못 받습니다.")
    assert "10월 31일까지 — 스피또1000 97회" in text
    assert "긁어놓고 안 바꾼 것도" in text
    assert len(text) <= sp.LIMIT
    # 같은 마감일로 두 번 올리지 않는다
    n = len(calls["posts"])
    assert sp.run_claim(at(2026, 10, 26), dry=False, rounds=rounds) == 0
    assert len(calls["posts"]) == n


def test_claim_post_last_day_wording():
    rounds = [round_(status="판매종료", claim="2026-10-31")]
    w = sp.claim_warning(rounds, at(2026, 10, 31))
    assert "오늘이 당첨금 받는 마지막 날" in sp.build_claim_post(w)
    w = sp.claim_warning(rounds, at(2026, 10, 30))
    assert "내일이면 당첨금을 못 받습니다" in sp.build_claim_post(w)


# ---------- auto ----------

def test_auto_posts_once_a_day_and_prefers_claim(monkeypatch):
    calls = sandbox()
    rounds = ROUNDS[:3] + [round_("스피또1000", "SP1000", 97,
                                  status="판매종료", claim="2026-10-31")]
    monkeypatch.setattr(sp, "fetch_rounds", lambda: rounds)
    # 16:07 전에는 아무것도 안 한다
    assert sp.run_auto(at(2026, 10, 25, 16, 5), dry=False) == 0
    assert not calls["posts"]
    # 마감이 걸려 있으면 마감 글이 먼저
    assert sp.run_auto(at(2026, 10, 25, 16, 7), dry=False) == 0
    assert "당첨금을 못 받습니다" in bodies(calls)[0]
    # 같은 날 또 불러도 하루 한 건
    n = len(calls["posts"])
    assert sp.run_auto(at(2026, 10, 25, 20, 0), dry=False) == 0
    assert len(calls["posts"]) == n


def test_auto_falls_back_to_stock_when_deadline_already_posted(monkeypatch):
    calls = sandbox()
    rounds = ROUNDS[:3] + [round_("스피또1000", "SP1000", 97,
                                  status="판매종료", claim="2026-10-31")]
    monkeypatch.setattr(sp, "fetch_rounds", lambda: rounds)
    assert sp.run_auto(at(2026, 10, 25), dry=False) == 0        # 마감 글
    assert sp.run_auto(at(2026, 10, 26), dry=False) == 0        # 같은 마감일 → 잔여 글로
    assert "1등" in bodies(calls)[1] and "못 받습니다" not in bodies(calls)[1]


def test_auto_silent_without_credentials(monkeypatch):
    calls = sandbox()
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    assert sp.run_auto(at(2026, 10, 25), dry=False) == 0
    assert not calls["posts"] and not calls["telegram"]


def test_question_rotates():
    """같은 질문이 매번 나가면 그게 제일 큰 봇 티다."""
    seen = {sp.build_stock_post(ROUNDS, at(2026, 10, d)).split("\n")[1] for d in range(1, 8)}
    assert len(seen) >= 5
