"""번호대(구간) 분석 번호 생성기. 복권명당 앱 src/features/generator/bandGenerator.ts를 그대로 옮긴 것.

그쪽 파일 머리에 "앱과 스레드 자동화(gzclab-threads)가 같은 번호를 내야 하므로 이 파일 하나만
복사하면 어디서든 그대로 돈다"라고 적혀 있다. 이 파일이 그 복사본이다.

같은 날짜면 앱에서 보든 스레드·인스타에서 보든 같은 5게임이 나와야 한다. 한쪽만 고치면
test_band_gen.py의 GOLDEN이 깨진다 — 그 값은 앱 화면에서 직접 확인한 것이다.

어떤 방식도 당첨 확률을 바꾸지 않는다(모든 조합이 1/8,145,060). 글에 "확률을 높인다"는
표현은 쓰지 않는다.
"""

import datetime

BANDS = ((1, 9), (10, 19), (20, 29), (30, 39), (40, 45))
BAND_KO = ("1~9", "10번대", "20번대", "30번대", "40~45")
LOW_MAX = 22                      # 1~22가 저, 23~45가 고
ALLOWED_LOW_COUNTS = (2, 3, 4)    # 허용하는 저:고 비율
GAMES_PER_SET = 5
MAX_ATTEMPTS_PER_GAME = 10_000

M32 = 0xFFFFFFFF


# ---------- 난수 (bandGenerator.ts의 hashString / mulberry32와 비트 단위로 같다) ----------

def _imul(a, b):
    return (a * b) & M32


def hash_string(s):
    h1, h2 = 0xDEADBEEF, 0x41C6CE57
    for ch in s:
        c = ord(ch)
        h1 = _imul(h1 ^ c, 2654435761)
        h2 = _imul(h2 ^ c, 1597334677)
    h1 = _imul(h1 ^ (h1 >> 16), 2246822507) ^ _imul(h2 ^ (h2 >> 13), 3266489909)
    h2 = _imul(h2 ^ (h2 >> 16), 2246822507) ^ _imul(h1 ^ (h1 >> 13), 3266489909)
    return (h1 ^ h2) & M32


def mulberry32(seed):
    state = [seed & M32]

    def rng():
        state[0] = (state[0] + 0x6D2B79F5) & M32
        t = state[0]
        t = _imul(t ^ (t >> 15), t | 1)
        t ^= (t + _imul(t ^ (t >> 7), t | 61)) & M32
        return ((t ^ (t >> 14)) & M32) / 4294967296

    return rng


def seeded_rng(seed):
    return mulberry32(hash_string(seed))


# ---------- 분석 ----------

def band_index_of(n):
    for i, (lo, hi) in enumerate(BANDS):
        if lo <= n <= hi:
            return i
    return -1


def analyze_game(numbers):
    """구간 분포와 저:고 비율. 조건 충족 여부는 보지 않는다."""
    s = sorted(numbers)
    counts = [0] * len(BANDS)
    for n in s:
        i = band_index_of(n)
        if i >= 0:
            counts[i] += 1
    low = sum(1 for n in s if n <= LOW_MAX)
    return {
        "numbers": s,
        "band_counts": counts,
        "band_pattern": "-".join(str(c) for c in counts),
        "low": low,
        "high": len(s) - low,
        "low_high": f"{low}:{len(s) - low}",
    }


def satisfies_band_rules(numbers):
    """1) 5구간 중 정확히 1곳이 0개  2) 한 구간 최대 3개  3) 저:고가 2:4 / 3:3 / 4:2"""
    if len(numbers) != 6 or len(set(numbers)) != 6:
        return False
    if any((not isinstance(n, int)) or n < 1 or n > 45 for n in numbers):
        return False
    a = analyze_game(numbers)
    if a["band_counts"].count(0) != 1:
        return False
    if any(c > 3 for c in a["band_counts"]):
        return False
    return a["low"] in ALLOWED_LOW_COUNTS


# ---------- 생성 ----------

def _combo_key(numbers):
    return ",".join(str(n) for n in sorted(numbers))


def _draw_six(rng):
    pool = list(range(1, 46))
    for i in range(6):
        j = i + int(rng() * (45 - i))
        pool[i], pool[j] = pool[j], pool[i]
    return sorted(pool[:6])


def generate_band_games(rng, count=GAMES_PER_SET):
    """조건을 만족하는 5게임. 5게임끼리 같은 조합은 나오지 않는다."""
    used = set()
    games = []
    while len(games) < count:
        picked = None
        for _ in range(MAX_ATTEMPTS_PER_GAME):
            cand = _draw_six(rng)
            if not satisfies_band_rules(cand):
                continue
            if _combo_key(cand) in used:
                continue
            picked = cand
            break
        if picked is None:
            raise RuntimeError(
                f"generate_band_games: {MAX_ATTEMPTS_PER_GAME}번 안에 조건에 맞는 조합을 찾지 못했다")
        used.add(_combo_key(picked))
        games.append(analyze_game(picked))
    return games


def generate_daily_band_games(date_key, count=GAMES_PER_SET):
    """날짜(YYYY-MM-DD)를 시드로 쓰는 '오늘의 추천'. 앱과 같은 시드 문자열을 쓴다."""
    return generate_band_games(seeded_rng(f"band|{date_key}"), count)


def kst_date_key(now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    kst = now.astimezone(datetime.timezone(datetime.timedelta(hours=9)))
    return kst.date().isoformat()


def fmt(numbers):
    return " ".join(f"{n:02d}" for n in numbers)
