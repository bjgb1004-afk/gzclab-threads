"""Self-check: run `python test_band_gen.py`. No network, no framework.

GOLDEN은 복권명당 앱 화면을 직접 보고 옮긴 값이다(2026-10-02, 1244회 번호대 분석).
앱 bandGenerator.ts와 이 포팅본 중 한쪽만 고치면 여기서 깨진다.
"""

import band_gen as bg

# ---------- 앱 화면 GOLDEN ----------
GOLDEN_DATE = "2026-10-02"
GOLDEN = [
    ([4, 12, 15, 19, 25, 39], "1-3-1-1-0", "4:2"),
    ([4, 5, 13, 21, 29, 42], "2-1-2-0-1", "4:2"),
    ([6, 10, 17, 23, 30, 39], "1-2-1-2-0", "3:3"),
    ([2, 10, 33, 40, 44, 45], "1-1-0-1-3", "2:4"),
    ([7, 14, 17, 20, 28, 33], "1-2-2-1-0", "4:2"),
]

games = bg.generate_daily_band_games(GOLDEN_DATE)
assert len(games) == 5
for g, (nums, pattern, ratio) in zip(games, GOLDEN):
    assert g["numbers"] == nums, (g["numbers"], nums)
    assert g["band_pattern"] == pattern, (g["band_pattern"], pattern)
    assert g["low_high"] == ratio, (g["low_high"], ratio)

# 같은 날짜면 몇 번을 돌려도 같다
assert bg.generate_daily_band_games(GOLDEN_DATE) == games
# 날짜가 다르면 다르다
assert bg.generate_daily_band_games("2026-10-03") != games

# ---------- 채택 규칙 ----------
ok = bg.satisfies_band_rules
# 구간 1-3-1-1-0: 빈 구간 1개, 최대 3개, 저고 4:2 -> 통과
assert ok([4, 12, 15, 19, 25, 39])
# 빈 구간이 2개면 탈락
assert not ok([1, 2, 3, 11, 12, 13])
# 한 구간에 4개면 탈락
assert not ok([10, 11, 12, 13, 25, 44])
# 저:고가 1:5면 탈락 (허용은 2:4 / 3:3 / 4:2)
assert not ok([1, 25, 26, 35, 41, 44])
# 범위 밖·중복
assert not ok([0, 12, 15, 19, 25, 39])
assert not ok([4, 4, 15, 19, 25, 39])
assert not ok([4, 12, 15, 19, 25])

# ---------- 생성된 게임은 전부 규칙을 지킨다 ----------
for day in ("2026-10-05", "2026-11-20", "2027-01-01"):
    gs = bg.generate_daily_band_games(day)
    assert len({tuple(x["numbers"]) for x in gs}) == 5, "게임이 중복됨"
    for x in gs:
        assert ok(x["numbers"]), (day, x["numbers"])

# ---------- 분석 ----------
a = bg.analyze_game([39, 4, 25, 12, 19, 15])
assert a["numbers"] == [4, 12, 15, 19, 25, 39], "오름차순 정렬이 안 됨"
assert a["band_counts"] == [1, 3, 1, 1, 0]
assert a["low"] == 4 and a["high"] == 2
assert bg.fmt([4, 12]) == "04 12"

print("ok")
