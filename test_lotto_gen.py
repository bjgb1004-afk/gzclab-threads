"""lotto_gen 자체 점검. `python test_lotto_gen.py`. 네트워크 없음.

GOLDEN은 복권명당 앱 src/features/generator/geniusGenerator.test.ts에도 똑같이 들어 있다.
이 값이 바뀌면 스레드 번호와 앱 번호가 갈라진 것이다 — 한쪽만 고치지 말 것.
"""

import datetime

import lotto_gen as g
from math_digits import E_DIGITS, PI_DIGITS

GOLDEN = {"1244": {"archimedes": [[3, 18, 19, 27, 30, 38], [1, 24, 25, 29, 38, 41], [6, 9, 11, 31, 37, 39], [1, 4, 11, 12, 39, 40], [10, 18, 19, 35, 37, 42]], "fibonacci": [[4, 8, 14, 25, 32, 42], [5, 15, 22, 33, 39, 43], [3, 14, 21, 25, 31, 42], [6, 16, 23, 34, 40, 44], [4, 10, 14, 21, 31, 38]], "pascal": [[1, 4, 7, 19, 34, 40], [1, 10, 11, 19, 31, 37], [4, 10, 16, 19, 31, 37], [1, 10, 13, 19, 28, 31], [4, 19, 22, 28, 37, 40]], "euler": [[7, 19, 21, 33, 34, 43], [3, 5, 15, 23, 24, 32], [3, 4, 9, 19, 35, 39], [3, 7, 16, 22, 29, 44], [7, 12, 13, 17, 20, 41]], "gauss": [[8, 14, 24, 25, 32, 35], [6, 15, 18, 22, 37, 40], [4, 9, 15, 31, 36, 43], [5, 18, 21, 27, 31, 36], [7, 8, 14, 30, 36, 43]], "store:서울 노원구": [9, 12, 17, 21, 28, 30]}, "1300": {"archimedes": [[2, 3, 6, 34, 38, 44], [14, 18, 20, 25, 28, 44], [4, 8, 13, 24, 33, 34], [5, 10, 17, 34, 39, 45], [5, 6, 14, 36, 38, 40]], "fibonacci": [[6, 13, 23, 30, 34, 40], [2, 13, 19, 30, 36, 40], [8, 14, 18, 25, 35, 42], [10, 16, 20, 27, 37, 44], [2, 13, 20, 30, 37, 41]], "pascal": [[9, 11, 21, 26, 36, 44], [1, 4, 19, 28, 31, 37], [1, 10, 19, 29, 37, 39], [1, 19, 22, 28, 31, 37], [4, 13, 17, 27, 36, 44]], "euler": [[4, 12, 18, 23, 36, 38], [1, 3, 30, 33, 37, 43], [7, 13, 16, 23, 36, 38], [6, 12, 14, 17, 19, 37], [13, 16, 26, 33, 36, 39]], "gauss": [[13, 15, 16, 23, 32, 39], [6, 7, 20, 29, 36, 40], [6, 13, 24, 26, 33, 36], [14, 16, 17, 19, 29, 43], [5, 7, 21, 30, 33, 41]], "store:서울 노원구": [3, 6, 15, 17, 34, 44]}}


def test_golden_matches_app():
    for draw, sets in GOLDEN.items():
        for key, expected in sets.items():
            if key.startswith("store:"):
                assert g.store_game(key[6:], int(draw)) == expected, (draw, key)
            else:
                assert g.genius_games(key, int(draw)) == expected, (draw, key)


def test_digits():
    assert len(PI_DIGITS) == len(E_DIGITS) == 5000
    assert PI_DIGITS.startswith("14159265358979323846")
    assert E_DIGITS.startswith("71828182845904523536")
    assert PI_DIGITS[761:767] == "999999"  # 파인만 포인트


def test_upcoming_draw_no():
    kst = g.KST
    assert g.upcoming_draw_no(datetime.datetime(2002, 12, 1, tzinfo=kst)) == 1
    assert g.upcoming_draw_no(datetime.datetime(2022, 1, 29, 20, 44, tzinfo=kst)) == 1000
    assert g.upcoming_draw_no(datetime.datetime(2022, 1, 29, 20, 46, tzinfo=kst)) == 1001
    # 2026-09-26(토) 추첨이 1243회. 월요일엔 1244회를 산다.
    assert g.upcoming_draw_no(datetime.datetime(2026, 9, 28, 17, 7, tzinfo=kst)) == 1244


def test_filters():
    assert not g.passes_common_filters([1, 3, 5, 8, 10, 12])  # 합 39
    assert not g.passes_common_filters([11, 15, 21, 25, 31, 35])  # 전부 홀수
    assert not g.passes_common_filters([7, 20, 21, 22, 33, 40])  # 3연속
    assert g.passes_common_filters([3, 14, 22, 27, 35, 41])


def test_every_set_is_five_distinct_valid_games():
    for draw in range(1, 2000, 7):
        for x in g.GENIUSES:
            games = g.genius_games(x["id"], draw)
            assert len(games) == 5, (draw, x["id"])
            assert len({g.combo_key(a) for a in games}) == 5, (draw, x["id"], games)
            assert all(g.passes_common_filters(a) and a == sorted(a) for a in games), (draw, x["id"])


def test_deterministic_and_weekly():
    assert g.genius_games("gauss", 1244) == g.genius_games("gauss", 1244)
    assert g.genius_games("gauss", 1244) != g.genius_games("gauss", 1245)
    assert g.store_game("서울 노원구", 1244) != g.store_game("부산 동구", 1244)


def test_gauss_stays_near_138():
    for draw in (1244, 1300, 1500):
        for game in g.genius_games("gauss", draw):
            assert abs(sum(game) - 138) <= 3, (draw, game)


if __name__ == "__main__":
    for name, fn in sorted(vars().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
