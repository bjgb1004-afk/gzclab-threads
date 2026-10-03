"""Self-check: run `python test_replay.py`. No network, no framework.

숫자는 복권명당 앱 src/features/backtest/replay.ts와 같아야 한다. 댓글로 받은 번호에
답해준 값이 그 사람이 앱에서 본 것과 다르면 신뢰를 잃는다.

앱 화면 실측(네트워크가 필요해 여기선 검증하지 않는다, 2026-10-02 확인):
  번호 1 9 17 25 33 41 → 262~1243회 982회 · 19번 당첨 · 4등 2번 · 5등 17번
                        · 합계 185,000원 · 최고 893회 4등
"""

import datetime
import json
import pathlib
import tempfile

import auto_reply
import band_gen as bg
import band_picks
import lotto_gen
import lotto_picks
import replay as rp

# ---------- 세금: 앱 draws/lotteryTax.ts와 같은 기준 ----------
# 5만원 이하 비과세. 4등(5만)·5등(5천)이 전부 여기 든다.
assert rp.after_tax(5_000) == 5_000
assert rp.after_tax(50_000) == 50_000
assert rp.after_tax(50_001) < 50_001, "5만원 초과부터 과세"
assert rp.after_tax(1_000_000) == 780_000          # 3억 이하 22%
assert rp.after_tax(300_000_000) == 234_000_000
# 3억 초과분은 33%. 사장님이 9/26 글에 쓴 "20억이면 실수령 13.7억"과 맞아야 한다.
assert 1_370_000_000 < rp.after_tax(2_000_000_000) < 1_375_000_000

# ---------- 4·5등은 회차와 무관한 고정 금액 ----------
assert rp.FIXED_PRIZE == {4: 50_000, 5: 5_000}
OLD = {"no": 300, "numbers": [1, 2, 3, 4, 5, 6], "bonus": 7,
       "prizes": {1: 2_000_000_000, 2: 50_000_000, 3: 1_000_000, 4: 139_300, 5: 10_000}}
# 미러 데이터의 옛 체계 금액(4등 139,300 / 5등 10,000)이 아니라 고정액을 써야 한다
assert rp.prize_of(4, OLD) == 50_000, "4등은 회차 금액을 쓰면 안 된다"
assert rp.prize_of(5, OLD) == 5_000
assert rp.prize_of(3, OLD) == 1_000_000, "1~3등은 회차 금액을 쓴다"
assert rp.prize_of(1, {"no": 1, "numbers": [], "bonus": 0, "prizes": {}}) == 0, "모르면 0"

# ---------- 등수 판정: lotto_picks와 어긋나면 번호글 채점과 따로 논다 ----------
WIN, BONUS = [1, 2, 3, 4, 5, 6], 7
for game in ([1, 2, 3, 4, 5, 6], [1, 2, 3, 4, 5, 7], [1, 2, 3, 4, 5, 8],
             [1, 2, 3, 4, 9, 10], [1, 2, 3, 9, 10, 11], [1, 2, 9, 10, 11, 12]):
    assert rp.rank_of(game, WIN, BONUS) == lotto_picks.rank_of(game, WIN, BONUS), game
assert rp.rank_of([1, 2, 3, 4, 5, 7], WIN, BONUS) == 2      # 보너스 포함 = 2등
assert rp.rank_of([1, 2, 3, 4, 5, 8], WIN, BONUS) == 3
assert rp.rank_of([1, 2, 9, 10, 11, 12], WIN, BONUS) is None

# ---------- replay 집계 ----------
DRAWS = [
    # START_ROUND(262) 밖 — 집계에서 빠져야 한다
    {"no": 100, "numbers": [1, 2, 3, 4, 5, 6], "bonus": 7, "prizes": {1: 9_000_000_000}},
    {"no": 300, "numbers": [1, 2, 3, 4, 5, 8], "bonus": 9,
     "prizes": {1: 1_000_000_000, 2: 40_000_000, 3: 1_500_000, 4: 139_300, 5: 10_000}},
    {"no": 500, "numbers": [1, 2, 3, 9, 10, 11], "bonus": 12, "prizes": {4: 139_300, 5: 10_000}},
    {"no": 900, "numbers": [40, 41, 42, 43, 44, 45], "bonus": 39, "prizes": {}},
]
res = rp.replay([1, 2, 3, 4, 5, 6], DRAWS)
assert res["draws"] == 3, "262회 미만이 섞였다"
assert res["from"] == 300 and res["to"] == 900
# 300회: 5개 일치·보너스(9) 미포함 -> 3등 / 500회: 3개 -> 5등 / 900회: 꽝
assert res["by_rank"] == {3: 1, 5: 1}, res["by_rank"]
assert res["hits"] == 2
assert res["gross"] == 1_500_000 + 5_000, "5등에 고정액 5,000이 쓰여야 한다"
assert res["best"] == 3 and res["best_draw"] == 300

# 같은 등수가 여럿이면 최근 회차를 최고 기록으로 쓴다(앱 replay.ts와 같은 규칙)
TIE = [
    {"no": 300, "numbers": [1, 2, 3, 40, 41, 42], "bonus": 9, "prizes": {}},
    {"no": 900, "numbers": [1, 2, 3, 43, 44, 45], "bonus": 39, "prizes": {}},
]
tie = rp.replay([1, 2, 3, 4, 5, 6], TIE)
assert tie["by_rank"] == {5: 2}
assert tie["best_draw"] == 900, "같은 등수면 최근 회차"

# 한 번도 안 맞는 번호
none_res = rp.replay([20, 21, 22, 23, 24, 25], DRAWS)
assert none_res["hits"] == 0 and none_res["gross"] == 0
assert "한 번도" in rp.summary_line(none_res)
# 요약줄은 앱 화면과 같이 세전 합계를 쓴다
assert "합계" in rp.summary_line(res) and "세후" not in rp.summary_line(res)

# ---------- 금액 표기 ----------
assert rp.won(5_000) == "5,000원"
assert rp.won(185_000) == "18만원"
assert rp.won(2_000_000_000) == "20억원"

# ---------- 캐시 왕복 (JSON은 dict 키를 문자열로 만든다) ----------
# 캐시에서 읽으면 당첨금이 전부 0이 되던 버그의 회귀 테스트.
_tmp = pathlib.Path(tempfile.mkdtemp()) / "draws_cache.json"
_orig = rp.CACHE
try:
    rp.CACHE = _tmp
    _tmp.write_text(json.dumps(DRAWS, ensure_ascii=False), encoding="utf-8")
    back = rp.fetch_draws(use_cache=True)
    assert all(isinstance(k, int) for d in back for k in d["prizes"]), "등수 키가 문자열로 남았다"
    assert rp.replay([1, 2, 3, 4, 5, 6], back)["gross"] == res["gross"]
finally:
    rp.CACHE = _orig

# ---------- 번호대 글 ----------
post = band_picks.build(bg.kst_date_key(), DRAWS)
assert len(post["text"]) <= band_picks.LIMIT
assert post["reply_mode"] == "replay"
assert "4시간" in post["text"], "4시간 안내가 빠지면 답글 창과 본문이 어긋난다"
for banned in ("예측", "적중", "확률 높", "잘 나오"):
    assert banned not in post["text"], banned
# 글에 실린 번호가 앱이 내는 번호와 같아야 한다
today = bg.kst_date_key()
for gm in bg.generate_daily_band_games(today):
    assert bg.fmt(gm["numbers"]) in post["text"], gm["numbers"]

# ---------- 댓글 번호 파싱 ----------
pn = auto_reply.parse_numbers
assert pn("3 11 24 32 37 45") == [3, 11, 24, 32, 37, 45]
assert pn("3,11,24,32,37,45") == [3, 11, 24, 32, 37, 45]
assert pn("03-11-24-32-37-45") == [3, 11, 24, 32, 37, 45]
assert pn("제 번호는 45 37 32 24 11 3 입니다") == [3, 11, 24, 32, 37, 45]
assert pn("1 2 3 4 5") is None
assert pn("1 2 3 4 5 6 7") is None
assert pn("1 2 3 4 5 5") is None
assert pn("1 2 3 4 5 46") is None
assert pn("1244회 번호 알려줘") is None
assert pn("노원구요") is None

# ---------- 리플레이 답글 ----------
msg = auto_reply.compose_replay("chloekim83", [1, 2, 3, 4, 5, 6], DRAWS)
assert msg.startswith("chloekim83아 01 02 03 04 05 06 돌려봤어!"), msg
assert "2번 당첨" in msg and "3등 1번" in msg, msg
assert "다음 회차랑은 상관없는" in msg, "예측이 아니라는 단서가 빠지면 안 된다"
assert "play.google.com" not in msg and "gzclab.com" not in msg, "답글에는 링크를 넣지 않는다"
assert len(msg) <= auto_reply.REPLY_LIMIT, len(msg)
assert "한 번도 등수에 못 들었음" in auto_reply.compose_replay("u1", [20, 21, 22, 23, 24, 25], DRAWS)

# ---------- 4시간 창 ----------
NOW = datetime.datetime(2026, 10, 3, 12, 0, tzinfo=datetime.timezone.utc)


def post_at(minutes_ago, mode="replay"):
    return {"id": "band-x", "status": "published", "post_id": "p1", "text": "번호글",
            "reply_mode": mode,
            "published_at": (NOW - datetime.timedelta(minutes=minutes_ago)).isoformat()}


assert auto_reply.targets([post_at(10)], NOW)
assert auto_reply.targets([post_at(239)], NOW), "3시간 59분은 창 안"
assert not auto_reply.targets([post_at(241)], NOW), "4시간 넘으면 대상에서 빠진다"
old = {"id": "top5-x", "status": "published", "post_id": "p2", "text": "댓글에 구 이름 남겨줘",
       "published_at": (NOW - datetime.timedelta(days=3)).isoformat()}
assert auto_reply.targets([old], NOW), "지역 글의 7일 창이 줄어들면 안 된다"

print("ok")
