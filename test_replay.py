"""Self-check: run `python test_replay.py`. No network, no framework."""

import datetime
import json
import pathlib

import auto_reply
import band_picks
import lotto_gen
import lotto_picks
import replay as rp

# ---------- 세금 ----------
# 20만원 이하는 비과세. 5등 5,000원과 4등 50,000원이 그대로 남아야 한다.
assert rp.after_tax(5_000) == 5_000
assert rp.after_tax(50_000) == 50_000
assert rp.after_tax(200_000) == 200_000
# 3억 이하 22%
assert rp.after_tax(1_000_000) == 780_000
assert rp.after_tax(300_000_000) == 234_000_000
# 3억 초과분은 33%. 사장님이 9/26 글에 쓴 "20억이면 실수령 13.7억"과 맞아야 한다.
assert 1_370_000_000 < rp.after_tax(2_000_000_000) < 1_375_000_000, rp.after_tax(2_000_000_000)

# ---------- 등수 판정: lotto_picks와 어긋나면 번호글 채점과 이 글이 따로 논다 ----------
WIN = [1, 2, 3, 4, 5, 6]
BONUS = 7
for game in ([1, 2, 3, 4, 5, 6], [1, 2, 3, 4, 5, 7], [1, 2, 3, 4, 5, 8],
             [1, 2, 3, 4, 9, 10], [1, 2, 3, 9, 10, 11], [1, 2, 9, 10, 11, 12]):
    assert rp.rank_of(game, WIN, BONUS) == lotto_picks.rank_of(game, WIN, BONUS), game
assert rp.rank_of([1, 2, 3, 4, 5, 6], WIN, BONUS) == 1
assert rp.rank_of([1, 2, 3, 4, 5, 7], WIN, BONUS) == 2   # 보너스 포함 = 2등
assert rp.rank_of([1, 2, 3, 4, 5, 8], WIN, BONUS) == 3
assert rp.rank_of([1, 2, 9, 10, 11, 12], WIN, BONUS) is None  # 2개 = 꽝

# ---------- replay 집계 ----------
DRAWS = [
    {"no": 1, "numbers": [1, 2, 3, 4, 5, 6], "bonus": 7,
     "prizes": {1: 2_000_000_000, 2: 50_000_000, 3: 1_000_000, 4: 50_000, 5: 5_000}},
    {"no": 2, "numbers": [1, 2, 3, 4, 5, 8], "bonus": 9,
     "prizes": {1: 1_000_000_000, 2: 40_000_000, 3: 1_500_000, 4: 50_000, 5: 5_000}},
    {"no": 3, "numbers": [40, 41, 42, 43, 44, 45], "bonus": 39,
     "prizes": {1: 900_000_000, 2: 30_000_000, 3: 1_200_000, 4: 50_000, 5: 5_000}},
]
res = rp.replay([1, 2, 3, 4, 5, 6], DRAWS)
assert res["draws"] == 3
# 1회 1등, 2회는 5개 일치에 보너스(9) 미포함 -> 3등, 3회는 꽝
assert res["by_rank"] == {1: 1, 3: 1}, res["by_rank"]
assert res["hits"] == 2
assert res["best"] == 1 and res["best_draw"] == 1
assert res["gross"] == 2_000_000_000 + 1_500_000
assert res["net"] == rp.after_tax(2_000_000_000) + rp.after_tax(1_500_000)

# 한 번도 안 맞는 번호
none_res = rp.replay([10, 11, 12, 13, 14, 15], DRAWS)
assert none_res["hits"] == 0 and none_res["net"] == 0
assert "한 번도" in rp.summary_line(none_res)

# 당첨금이 비어 있는 초창기 회차(1등 당첨자 0명)여도 죽지 않는다
NO_PRIZE = [{"no": 1, "numbers": [1, 2, 3, 4, 5, 6], "bonus": 7, "prizes": {}}]
assert rp.replay([1, 2, 3, 4, 5, 6], NO_PRIZE)["net"] == 0

# ---------- 금액 표기 ----------
assert rp.won(5_000) == "5,000원"
assert rp.won(250_000) == "25만원"
assert rp.won(1_612_766_099) == "16.1억원"
assert rp.won(2_000_000_000) == "20억원"

# ---------- 번호대 분석 ----------
avg, n = band_picks.band_counts(DRAWS, recent=3)
assert n == 3
assert abs(sum(avg) - 6) < 1e-9, avg  # 구간 평균의 합은 언제나 6개
shape = band_picks.target_shape(avg)
assert sum(shape) == 6, shape
assert all(s >= 0 for s in shape)

# 같은 날이면 언제나 같은 5게임이어야 글과 답글이 어긋나지 않는다
SHAPE = [1, 1, 1, 2, 1]
DAY = datetime.date(2026, 10, 3)
a = band_picks.games_for(DAY, SHAPE)
b = band_picks.games_for(DAY, SHAPE)
assert a == b, "같은 날인데 번호가 달라짐"
assert band_picks.games_for(DAY + datetime.timedelta(days=1), SHAPE) != a, "날이 달라도 번호가 같음"
assert len(a) == len(set(tuple(x) for x in a)) == 5, "게임이 중복됨"
for game in a:
    assert len(game) == 6 and len(set(game)) == 6
    assert lotto_gen.passes_common_filters(game), game
    # 구간 할당을 실제로 지키는지
    got = [0] * len(band_picks.BANDS)
    for x in game:
        got[band_picks.band_of(x)] += 1
    assert got == SHAPE, (game, got)

# 매일 나가므로 요일 7개 전부 글이 만들어지고, 500자 한도와 문구 규칙을 지켜야 한다
seen = set()
for i in range(7):
    day = DAY + datetime.timedelta(days=i)
    post = band_picks.build(1244, DRAWS, day)
    assert post["id"] == f"band-{day}", post["id"]
    assert len(post["text"]) <= band_picks.LIMIT, (day, len(post["text"]))
    assert post["reply_mode"] == "replay"
    assert "팔로우" in post["text"], "둘째 줄 팔로우 유도가 빠졌다"
    assert "4시간" in post["text"], "4시간 안내가 빠지면 답글 창과 본문이 어긋난다"
    for banned in ("예측", "적중", "확률 높", "잘 나오"):
        assert banned not in post["text"], (day, banned)
    seen.add(post["text"])
assert len(seen) == 7, "날짜가 달라도 글이 같다 — 매일 올리면 같은 글이 반복된다"

# 전 회차를 보는 요일(일)엔 "최근 N회"라고 쓰면 거짓말이 된다
sunday = band_picks.build(1244, DRAWS, DAY + datetime.timedelta(days=(6 - DAY.weekday()) % 7))
assert band_picks.WINDOWS[6] is None and "전 회차(" in sunday["text"], sunday["text"][:40]

# ---------- 발행 창 ----------
# 14:07 전에도, 18시 뒤에도 올리지 않는다. 밤에 올리면 본문의 "4시간" 약속을 못 지킨다.
assert band_picks.run_auto(
    datetime.datetime(2026, 10, 2, 4, 0, tzinfo=datetime.timezone.utc), dry=True
) == 0, "13:00 KST는 창 전"
# 창 밖(20:30 KST)에서 fetch_draws까지 가면 네트워크를 타므로, 창 판정만으로 빠져야 한다.
band_picks.rp = type("X", (), {"fetch_draws": staticmethod(lambda *a, **k: (_ for _ in ()).throw(
    AssertionError("창 밖인데 데이터를 받으러 갔다")))})()
assert band_picks.run_auto(
    datetime.datetime(2026, 10, 2, 11, 30, tzinfo=datetime.timezone.utc), dry=True
) == 0, "20:30 KST는 창 밖"
band_picks.rp = rp

# ---------- 댓글 번호 파싱 ----------
pn = auto_reply.parse_numbers
assert pn("3 11 24 32 37 45") == [3, 11, 24, 32, 37, 45]
assert pn("3,11,24,32,37,45") == [3, 11, 24, 32, 37, 45]
assert pn("03-11-24-32-37-45") == [3, 11, 24, 32, 37, 45]
assert pn("제 번호는 45 37 32 24 11 3 입니다") == [3, 11, 24, 32, 37, 45]
assert pn("1 2 3 4 5") is None            # 5개
assert pn("1 2 3 4 5 6 7") is None        # 7개
assert pn("1 2 3 4 5 5") is None          # 중복
assert pn("1 2 3 4 5 46") is None         # 범위 밖
assert pn("1244회 번호 알려줘") is None     # 회차 숫자를 번호로 읽으면 안 된다
assert pn("노원구요") is None
assert pn("ㅋㅋㅋ") is None

# ---------- 리플레이 답글 ----------
msg = auto_reply.compose_replay("chloekim83", [1, 2, 3, 4, 5, 6], DRAWS)
assert msg.startswith("chloekim83아 01 02 03 04 05 06 돌려봤어!"), msg
assert "2번 당첨" in msg, msg
assert "1등 1번" in msg and "3등 1번" in msg, msg
assert "다음 회차랑은 상관없는" in msg, "예측이 아니라는 단서가 빠지면 안 된다"
assert "play.google.com" not in msg and "gzclab.com" not in msg, "답글에는 링크를 넣지 않는다"
assert len(msg) <= auto_reply.REPLY_LIMIT, len(msg)

msg0 = auto_reply.compose_replay("u1", [10, 11, 12, 13, 14, 15], DRAWS)
assert "한 번도 등수에 못 들었음" in msg0, msg0

# ---------- 4시간 창 ----------
NOW = datetime.datetime(2026, 10, 3, 12, 0, tzinfo=datetime.timezone.utc)


def post_at(minutes_ago, mode="replay"):
    return {
        "id": "band-1244", "status": "published", "post_id": "p1", "text": "번호글",
        "reply_mode": mode,
        "published_at": (NOW - datetime.timedelta(minutes=minutes_ago)).isoformat(),
    }


assert auto_reply.targets([post_at(10)], NOW), "막 올린 글은 대상이어야 한다"
assert auto_reply.targets([post_at(239)], NOW), "3시간 59분은 아직 창 안"
assert not auto_reply.targets([post_at(241)], NOW), "4시간 넘으면 대상에서 빠진다"
# 지역 글은 종전대로 7일
old = {"id": "top5-x", "status": "published", "post_id": "p2",
       "text": "댓글에 구 이름 남겨줘", "published_at": (NOW - datetime.timedelta(days=3)).isoformat()}
assert auto_reply.targets([old], NOW), "지역 글의 7일 창이 줄어들면 안 된다"

print("ok")
