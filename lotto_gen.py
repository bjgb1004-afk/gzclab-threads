"""천재 수학자 5인 / 명당 방식의 로또 번호 생성기. 표준 라이브러리만 쓴다.

복권명당 앱의 src/features/generator/geniusGenerator.ts를 그대로 옮긴 것이다. 같은
(회차, 천재)면 두 쪽이 같은 5게임을 내야 스레드 글과 앱 화면이 일치한다.
test_lotto_gen.py의 GOLDEN 값이 두 구현에 똑같이 박혀 있어서, 한쪽만 바꾸면 테스트가 깨진다.

어떤 방식도 당첨 확률을 바꾸지 않는다(모든 조합 1/8,145,060). 글에서는 "천재의 수학으로
만든 번호"까지만 쓰고 "예측"이라고 하지 않는다.
"""

import datetime
import math

from math_digits import E_DIGITS, PI_DIGITS

GENIUSES = (
    {"id": "archimedes", "name": "아르키메데스", "how": "원주율 π를 이어 읽어 뽑은 5게임"},
    {"id": "fibonacci", "name": "피보나치", "how": "황금비 간격으로 45칸 원을 돌며 뽑은 5게임"},
    {"id": "pascal", "name": "파스칼", "how": "파스칼 삼각형을 45로 나눈 나머지로 뽑은 5게임"},
    {"id": "euler", "name": "오일러", "how": "자연상수 e를 이어 읽어 뽑은 5게임"},
    {"id": "gauss", "name": "가우스", "how": "여섯 번호의 합이 평균 138에 가장 가까운 5게임"},
)
GENIUS_BY_ID = {g["id"]: g for g in GENIUSES}
GAMES_PER_SET = 5

FIRST_DRAW = datetime.datetime(2002, 12, 7, 20, 45, tzinfo=datetime.timezone(datetime.timedelta(hours=9)))
WEEK = datetime.timedelta(days=7)
KST = datetime.timezone(datetime.timedelta(hours=9))

M32 = 0xFFFFFFFF


# ---------- 회차 ----------

def upcoming_draw_no(now=None):
    """지금 구매 대상인 회차 = 추첨 시각(토 20:45 KST)이 아직 오지 않은 가장 이른 회차."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    elapsed = now - FIRST_DRAW
    if elapsed.total_seconds() < 0:
        return 1
    return int(elapsed // WEEK) + 2


def draw_datetime(draw_no):
    return FIRST_DRAW + (draw_no - 1) * WEEK


# ---------- 결정론적 난수 (TS의 hashString / mulberry32와 비트 단위로 같다) ----------

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


# ---------- 공통 필터 ----------

def combo_key(numbers):
    return ",".join(str(n) for n in sorted(numbers))


def passes_common_filters(numbers):
    """합계 100~175, 홀짝 6:0/0:6 제외, 연속번호 3개 이상 제외."""
    if len(numbers) != 6 or len(set(numbers)) != 6:
        return False
    if any(not isinstance(n, int) or n < 1 or n > 45 for n in numbers):
        return False
    s = sorted(numbers)
    if not 100 <= sum(s) <= 175:
        return False
    odd = sum(1 for n in s if n % 2 == 1)
    if odd in (0, 6):
        return False
    run = 1
    for i in range(1, 6):
        run = run + 1 if s[i] == s[i - 1] + 1 else 1
        if run >= 3:
            return False
    return True


def _random_combo(rng, accept):
    for _ in range(10_000):
        pool = list(range(1, 46))
        for i in range(6):
            j = i + math.floor(rng() * (45 - i))
            pool[i], pool[j] = pool[j], pool[i]
        pick = sorted(pool[:6])
        if accept(pick):
            return pick
    raise RuntimeError("no valid combination found")


# ---------- 천재별 방식 ----------

def _from_digits(digits, pos, accept):
    """pos부터 두 자리씩 읽어 01~45만 채택. (조합, 다음 읽을 위치). 실패하면 두 칸 밀고 다시."""
    n_digits = len(digits)
    pos %= n_digits
    for _ in range(500):
        picked = []
        p = pos
        steps = 0
        while steps < 200 and len(picked) < 6:
            n = int(digits[p % n_digits] + digits[(p + 1) % n_digits])
            p += 2
            steps += 1
            if 1 <= n <= 45 and n not in picked:
                picked.append(n)
        s = sorted(picked)
        if len(picked) == 6 and accept(s):
            return s, p % n_digits
        pos = (pos + 2) % n_digits
    return None, pos


PHI_FRAC = (math.sqrt(5) - 1) / 2  # 0.6180339887…


def _fibonacci_one(rng, accept):
    for _ in range(500):
        u0 = rng()
        picked = []
        k = 0
        while k < 100 and len(picked) < 6:
            n = math.floor(((u0 + k * PHI_FRAC) % 1) * 45) + 1
            if n not in picked:
                picked.append(n)
            k += 1
        s = sorted(picked)
        if len(picked) == 6 and accept(s):
            return s
    return None


def _pascal_row_mod45(row):
    cur = [1]
    for r in range(1, row + 1):
        nxt = [1] * (r + 1)
        for k in range(1, r):
            nxt[k] = (cur[k - 1] + cur[k]) % 45
        cur = nxt
    return cur


def _pascal_games(draw_no, accept, count):
    base = 20 + (draw_no * 7) % 80  # 20~99번째 줄에서 출발
    games = []
    offset = 0
    while len(games) < count and offset < 1000:
        row = 20 + (base - 20 + offset) % 130
        offset += 1
        values = _pascal_row_mod45(row)
        inner = row - 1  # 양 끝의 1을 뺀 칸 수
        start = 1 + (draw_no % inner)
        picked = []
        for i in range(inner):
            if len(picked) >= 6:
                break
            n = values[1 + (start - 1 + i) % inner] + 1
            if n not in picked:
                picked.append(n)
        s = sorted(picked)
        # 서로 다른 줄이 같은 조합을 낼 수 있다(1234회에서 실제로 겹침). 이미 뽑은 것은 건너뛴다.
        if len(picked) == 6 and accept(s) and s not in games:
            games.append(s)
    return games


GAUSS_TARGET_SUM = 138  # 1~45에서 6개 합의 기대값 = 6 × 23


def _gauss_games(rng, accept, count):
    cands = []
    seen = set()
    for _ in range(300):
        pick = _random_combo(rng, accept)
        key = combo_key(pick)
        if key not in seen:
            seen.add(key)
            cands.append(pick)
    # 합이 138에 가까운 순. 동점이면 먼저 나온 것(파이썬 sort는 안정 정렬 = TS도 같게 맞춤).
    cands.sort(key=lambda c: abs(sum(c) - GAUSS_TARGET_SUM))
    return cands[:count]


# ---------- 진입점 ----------

def genius_games(genius_id, draw_no, exclude=frozenset()):
    """그 회차 그 천재의 A~E 5게임. 같은 입력이면 언제나 같은 결과."""
    if genius_id not in GENIUS_BY_ID:
        raise ValueError(f"unknown genius: {genius_id}")
    used = set()

    def accept(nums):
        if not passes_common_filters(nums):
            return False
        key = combo_key(nums)
        return key not in used and key not in exclude

    rng = mulberry32(hash_string(f"{draw_no}|{genius_id}"))
    games = []

    def take(g):
        used.add(combo_key(g))
        games.append(g)

    if genius_id in ("archimedes", "euler"):
        digits = PI_DIGITS if genius_id == "archimedes" else E_DIGITS
        pos = draw_no * (37 if genius_id == "archimedes" else 41)
        for _ in range(GAMES_PER_SET):
            g, pos = _from_digits(digits, pos, accept)
            if g is None:
                break
            take(g)
    elif genius_id == "fibonacci":
        for _ in range(GAMES_PER_SET):
            g = _fibonacci_one(rng, accept)
            if g is None:
                break
            take(g)
    elif genius_id == "pascal":
        for g in _pascal_games(draw_no, accept, GAMES_PER_SET):
            take(g)
    elif genius_id == "gauss":
        for g in _gauss_games(rng, accept, GAMES_PER_SET):
            take(g)

    # 어떤 방식이 모자라게 끝나도(이론상 거의 없음) 빈 게임을 내보내지 않는다.
    while len(games) < GAMES_PER_SET:
        take(_random_combo(rng, accept))
    return games


def store_game(key, draw_no, exclude=frozenset()):
    """명당(판매점이나 지역) 이름으로 뽑는 1게임. 같은 주에는 같은 번호."""
    rng = mulberry32(hash_string(f"{draw_no}|store|{key}"))
    return _random_combo(rng, lambda n: passes_common_filters(n) and combo_key(n) not in exclude)


def fmt(numbers):
    return " ".join(f"{n:02d}" for n in numbers)
