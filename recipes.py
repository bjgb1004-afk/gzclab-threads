"""복권명당 앱 "수학 분석" 탭(백테스트 레시피)을 그대로 옮긴 것.

src/features/backtest/recipes.ts + pascal.ts (ruflo-starter, 2026-10-12 기준)를
비트 단위가 아니라 "같은 산출식"으로 포팅했다. geniusGenerator.ts(천재들의 한수,
lotto_gen.py가 옮긴 것)와는 완전히 다른 별도 기능이다 — 혼동하지 말 것.

입력은 미러(lotto_stats.fetch_all())의 전체 당첨 이력이면 된다. 앱은 Supabase에서
같은 모양의 데이터(draw_no, numbers)를 받아 오름차순 정렬해서 쓰므로 소스만 다르고
셈은 같다. 당첨 확률을 바꾸지 않는다 — 후보를 좁히거나 조합의 모양만 고를 뿐이다.
아르키메데스·오일러·가우시안을 옮겼다(2026-10-12). 피보나치·파스칼은 다음에.

ruflo-starter 세션이 같은 입력(미러 1~1245회 전체)으로 대조해 아르키메데스는 점수
순서까지 일치를 확인해 줬다. 앱 Supabase draw_history는 한때 262~1245회(984건)만
있었지만(1~261회 공백) 2026-10-12에 1~1245회로 백필 완료 — 이제 양쪽 입력이 같다.

실측(1~1245회, 5게임 1,145회차 평균 적중률): 무작위 0.7956 / 아르키메데스 0.8148 /
가우시안 0.8009 / 피보나치 0.7937 / 파스칼 0.7977 — 전부 무작위와 차이 없음. 오일러만
0.7708로 신뢰구간이 0.8 기준선을 안 포함한다(무작위보다 낮은 쪽). 이게 "실력"이라는
뜻은 아니고(구간 바꾸면 또 달라짐) — 글에서 오일러를 "더 나은 방법"처럼 쓰면 실측과
반대가 된다. 다섯 방법 다 "확률을 바꾸지 않는다"로만 쓸 것.
"""

import math

MAX_NUMBER = 45
PICK_COUNT = 6
SECTOR_COUNT = 6
MOD_GROUP_DIVISOR = 5  # 오일러: 45를 5로 나눠 9개씩 다섯 그룹(n % 5)
FIBONACCI_NUMBERS = (1, 2, 3, 5, 8, 13, 21, 34)


def mod_group_of(n):
    return n % MOD_GROUP_DIVISOR


def euler_totient(n):
    """φ(n) — n 이하에서 n과 서로소인 수의 개수. TS 원본과 같이 부동소수로 계산 후 반올림."""
    remaining, result = n, n
    p = 2
    while p * p <= remaining:
        if remaining % p == 0:
            while remaining % p == 0:
                remaining //= p
            result -= result / p
        p += 1
    if remaining > 1:
        result -= result / remaining
    return round(result)


def totient_ratio(n):
    """φ(n)/n. 번호 자체로 정해지며 당첨 이력과 무관하다."""
    return euler_totient(n) / n


def sector_ranges():
    edges = [MAX_NUMBER * i // SECTOR_COUNT for i in range(SECTOR_COUNT + 1)]
    return [(edges[i] + 1, edges[i + 1]) for i in range(SECTOR_COUNT)]


_SECTOR_RANGES = sector_ranges()


def sector_index_of(n):
    for i, (lo, hi) in enumerate(_SECTOR_RANGES):
        if lo <= n <= hi:
            return i
    return -1


def fibonacci_affinity(n):
    return 1 / (1 + min(abs(n - f) for f in FIBONACCI_NUMBERS))


def fibonacci_gap_count(numbers):
    fibs = set(FIBONACCI_NUMBERS)
    s = sorted(numbers)
    return sum(1 for a, b in zip(s, s[1:]) if (b - a) in fibs)


# ---------- 가우시안: 출현 횟수 표준점수 + 조합 합계 표준점수 ----------
# 번호 하나가 rounds회차 동안 나올 횟수는 이항분포(p=6/45)로 근사한다. 조합의 합계는
# "1~45에서 6개를 비복원추출했을 때의 합"의 분산 공식 n(N-n)(N+1)/12를 그대로 쓴다.

GAUSSIAN_SUM_MEAN = PICK_COUNT * (MAX_NUMBER + 1) / 2  # 138
GAUSSIAN_SUM_STD = math.sqrt(PICK_COUNT * (MAX_NUMBER - PICK_COUNT) * (MAX_NUMBER + 1) / 12)  # 29.9499…


def gaussian_number_affinity(actual, rounds):
    """번호 하나의 출현 횟수 표준점수 z를 1/(1+|z|)로 bound. rounds=0이면 0.5(차이 없음)."""
    if rounds <= 0:
        return 0.5
    p = PICK_COUNT / MAX_NUMBER
    mean = rounds * p
    std = math.sqrt(rounds * p * (1 - p))
    z = (actual - mean) / std if std else 0
    return 1 / (1 + abs(z))


def combo_sum_z(numbers):
    """조합 6개 합계의 표준점수. 글에 '합계 141 · z +0.10' 식으로 쓴다."""
    s = sum(numbers)
    return s, (s - GAUSSIAN_SUM_MEAN) / GAUSSIAN_SUM_STD


def sum_distribution_stats(history, band=(109, 167)):
    """역대 당첨번호 합계의 실측 평균·표준편차·이론 ±1σ(GAUSSIAN 필터와 같은 band) 안에 든 비율."""
    sums = [sum(numbers) for _, numbers in history]
    n = len(sums)
    mean = sum(sums) / n
    var = sum((s - mean) ** 2 for s in sums) / n
    lo, hi = band
    within = sum(1 for s in sums if lo <= s <= hi)
    return {
        "n": n, "mean": mean, "std": math.sqrt(var),
        "theory_mean": GAUSSIAN_SUM_MEAN, "theory_std": GAUSSIAN_SUM_STD,
        "band": band, "within_ratio": within / n,
    }


def compute_number_stats(history, recent_window):
    """history: [(round, [6개 번호]), ...] round 오름차순. 번호 1~45별 통계."""
    total = {n: 0 for n in range(1, MAX_NUMBER + 1)}
    recent = {n: 0 for n in range(1, MAX_NUMBER + 1)}
    gap = {n: len(history) for n in range(1, MAX_NUMBER + 1)}
    sector_recent = [0] * SECTOR_COUNT
    mod_recent = [0] * MOD_GROUP_DIVISOR
    for i, (_, numbers) in enumerate(history):
        from_end = len(history) - 1 - i  # 0이면 가장 최근 회차
        for n in numbers:
            total[n] += 1
            gap[n] = from_end
            if from_end < recent_window:
                recent[n] += 1
                sec = sector_index_of(n)
                if sec >= 0:
                    sector_recent[sec] += 1
                mod_recent[mod_group_of(n)] += 1

    recent_draws = min(len(history), recent_window)
    sector_size = [0] * SECTOR_COUNT
    mod_size = [0] * MOD_GROUP_DIVISOR
    for n in range(1, MAX_NUMBER + 1):
        sector_size[sector_index_of(n)] += 1
        mod_size[mod_group_of(n)] += 1
    sector_deficit = {}
    mod_deficit = {}
    for n in range(1, MAX_NUMBER + 1):
        sec = sector_index_of(n)
        sector_deficit[n] = recent_draws * PICK_COUNT * sector_size[sec] / MAX_NUMBER - sector_recent[sec]
        grp = mod_group_of(n)
        mod_deficit[n] = recent_draws * PICK_COUNT * mod_size[grp] / MAX_NUMBER - mod_recent[grp]

    return {
        n: {
            "total": total[n],
            "recent": recent[n],
            "gap": gap[n],
            "sector_deficit": sector_deficit[n],
            "mod_deficit": mod_deficit[n],
            "fib_affinity": fibonacci_affinity(n),
            "totient_ratio": totient_ratio(n),
            "gauss_affinity": gaussian_number_affinity(total[n], len(history)),
        }
        for n in range(1, MAX_NUMBER + 1)
    }


def _normalize(values):
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0.5] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def score_numbers(stats, weights):
    """weights 키: total, recent, gap, sector, fib, mod_balance, totient, gauss. 없는 키는 0."""
    nums = sorted(stats)
    parts = [
        (weights.get("total", 0), [stats[n]["total"] for n in nums]),
        (weights.get("recent", 0), [stats[n]["recent"] for n in nums]),
        (weights.get("gap", 0), [stats[n]["gap"] for n in nums]),
        (weights.get("sector", 0), [stats[n]["sector_deficit"] for n in nums]),
        (weights.get("fib", 0), [stats[n]["fib_affinity"] for n in nums]),
        (weights.get("mod_balance", 0), [stats[n]["mod_deficit"] for n in nums]),
        (weights.get("totient", 0), [stats[n]["totient_ratio"] for n in nums]),
        (weights.get("gauss", 0), [stats[n]["gauss_affinity"] for n in nums]),
    ]
    normed = [(w, _normalize(vs)) for w, vs in parts]
    return {n: sum(w * vs[i] for w, vs in normed) for i, n in enumerate(nums)}


def top_candidates(scores, count):
    """점수 내림차순, 동점은 번호 작은 쪽 먼저."""
    return sorted(scores, key=lambda n: (-scores[n], n))[:count]


def top_candidates_capped(scores, count, cap, group_of):
    ranked = sorted(scores, key=lambda n: (-scores[n], n))
    used, picked = {}, []
    for n in ranked:
        if len(picked) >= count:
            break
        g = group_of(n)
        if used.get(g, 0) >= cap:
            continue
        used[g] = used.get(g, 0) + 1
        picked.append(n)
    if len(picked) < count:  # cap이 너무 좁으면 cap을 넘겨서라도 채운다
        taken = set(picked)
        for n in ranked:
            if len(picked) >= count:
                break
            if n not in taken:
                picked.append(n)
    return picked


def passes_filters(numbers, odd_even=None, low_high=None, sum_range=None,
                    max_consecutive=None, min_fibonacci_gaps=None):
    s = sorted(numbers)
    if odd_even is not None:
        odd = sum(1 for n in s if n % 2)
        if (odd, len(s) - odd) not in odd_even:
            return False
    if low_high is not None:
        threshold = MAX_NUMBER // 2
        low = sum(1 for n in s if n <= threshold)
        if (low, len(s) - low) not in low_high:
            return False
    if sum_range is not None and not (sum_range[0] <= sum(s) <= sum_range[1]):
        return False
    if max_consecutive is not None:
        run = 1
        for i in range(1, len(s)):
            run = run + 1 if s[i] == s[i - 1] + 1 else 1
            if run > max_consecutive:
                return False
    if min_fibonacci_gaps is not None and fibonacci_gap_count(s) < min_fibonacci_gaps:
        return False
    return True


# ---------- 레시피 (아르키메데스·오일러. 피보나치·파스칼은 다음에) ----------

ARCHIMEDES = {
    "id": "archimedes",
    "weights": {"total": 0.4, "recent": 0.3, "gap": 0.2, "sector": 0.1},
    "recent_window": 100,
    "candidate_count": 15,
    "sector_cap": 3,
    "filters": dict(
        odd_even={(2, 4), (3, 3), (4, 2)},
        low_high={(2, 4), (3, 3), (4, 2)},
        sum_range=(100, 175),
        max_consecutive=2,
    ),
}

EULER = {
    "id": "euler",
    "weights": {"total": 0.35, "recent": 0.25, "mod_balance": 0.2, "totient": 0.2},
    "recent_window": 50,
    "candidate_count": 15,
    "mod_group_cap": 4,
    "filters": dict(sum_range=(100, 175), max_consecutive=2),
}

GAUSSIAN = {
    "id": "gaussian",
    "weights": {"gauss": 1.0},
    "recent_window": 50,  # 점수에는 안 쓰임 — 레시피 필드로만 남아 있다(ruflo-starter 확인)
    "candidate_count": 15,
    "sector_cap": 3,
    "filters": dict(sum_range=(109, 167), max_consecutive=2),  # 합계 평균138 ±1σ(29.9499)
}

FIBONACCI = {
    "id": "fibonacci",
    "weights": {"fib": 0.25, "total": 0.3, "recent": 0.2, "gap": 0.1, "sector": 0.15},
    "recent_window": 50,
    "candidate_count": 15,
    "sector_cap": 3,
    "filters": dict(sum_range=(100, 175), max_consecutive=2, min_fibonacci_gaps=3),
}

PASCAL = {
    "id": "pascal",
    "weights": {},  # 전부 0 — 번호를 좁히지 않는다(candidate_count가 45 = 전체)
    "recent_window": 20,
    "candidate_count": MAX_NUMBER,
    "filters": dict(
        odd_even={(3, 3), (4, 2), (2, 4)},
        low_high={(3, 3), (4, 2), (2, 4)},
        sum_range=(100, 175),
    ),
}


def analyze(recipe, history):
    """그 레시피를 history(대상 회차 이전까지)에 적용한 후보 번호 목록(점수 내림차순)."""
    stats = compute_number_stats(history, recipe["recent_window"])
    scores = score_numbers(stats, recipe["weights"])
    count = min(recipe["candidate_count"], MAX_NUMBER)
    if recipe.get("sector_cap") is not None:
        candidates = top_candidates_capped(scores, count, recipe["sector_cap"], sector_index_of)
    elif recipe.get("mod_group_cap") is not None:
        candidates = top_candidates_capped(scores, count, recipe["mod_group_cap"], lambda n: n % 5)
    else:
        candidates = top_candidates(scores, count)
    return candidates, scores


def _sample(pool, k, rng):
    pool = list(pool)
    for i in range(k):
        j = i + math.floor(rng() * (len(pool) - i))
        pool[i], pool[j] = pool[j], pool[i]
    return pool[:k]


def recipe_game(recipe, candidates, rng):
    """후보 풀에서 필터를 통과하는 1게임. candidates는 analyze()가 돌려준 목록."""
    for _ in range(2000):
        pick = _sample(candidates, PICK_COUNT, rng)
        if passes_filters(pick, **recipe["filters"]):
            return sorted(pick)
    raise RuntimeError(f"{recipe['id']}: 필터 통과 조합을 못 찾음")


# ---------- 검증(초기하분포) — "효과 없음"을 숫자로 보여줄 때 쓴다 ----------

def _comb(n, k):
    return math.comb(n, k) if 0 <= k <= n else 0


def hyper_prob(k, candidate_count):
    return (_comb(candidate_count, k) * _comb(MAX_NUMBER - candidate_count, PICK_COUNT - k)
            / _comb(MAX_NUMBER, PICK_COUNT))


def expected_candidate_hits(candidate_count):
    return PICK_COUNT * candidate_count / MAX_NUMBER


def hyper_at_least(min_hits, candidate_count):
    return sum(hyper_prob(k, candidate_count) for k in range(min_hits, PICK_COUNT + 1))


def backtest_candidate_hits(recipe, draws, rounds=300, minimum_history=100):
    """최근 rounds회를 되짚어, 그때까지의 데이터로 뽑은 후보 안에 당첨번호가 몇 개
    들어 있었는지. 각 회차의 후보는 그 회차 이전 기록만으로 만든다(미래 정보 누수 없음)."""
    sorted_draws = sorted(draws, key=lambda d: d[0])
    start = max(minimum_history, len(sorted_draws) - rounds)
    if start >= len(sorted_draws):
        return None
    hit_sum, tested = 0, 0
    hit_counts = [0] * (PICK_COUNT + 1)
    for i in range(start, len(sorted_draws)):
        _, target_numbers = sorted_draws[i]
        candidates, _ = analyze(recipe, sorted_draws[:i])
        inside = set(candidates)
        hits = sum(1 for n in target_numbers if n in inside)
        hit_counts[hits] += 1
        hit_sum += hits
        tested += 1
    candidate_count = min(recipe["candidate_count"], MAX_NUMBER)
    return {
        "rounds": tested,
        "candidate_count": candidate_count,
        "mean_hits": hit_sum / tested,
        "expected_hits": expected_candidate_hits(candidate_count),
        "at_least3_ratio": sum(hit_counts[3:]) / tested,
        "expected_at_least3_ratio": hyper_at_least(3, candidate_count),
    }


def total_combinations():
    return _comb(MAX_NUMBER, PICK_COUNT)  # 8,145,060


def count_combinations_by_shape(odd_even=None, low_high=None, sum_range=None):
    """홀짝·저고·합계 조건을 동시에 만족하는 조합이 몇 개인지 정확히 센다(파스칼 광고 숫자).

    0/1 배낭 DP — 번호를 1부터 하나씩 넣어가며 (뽑은 개수, 합계, 홀수 개수, 저번호 개수)별
    조합 수를 누적한다. 연속번호 같은 "번호 사이 관계" 조건은 이 셈으로 표현 못 한다.
    """
    low_max = MAX_NUMBER // 2
    max_sum = sum_range[1] if sum_range else PICK_COUNT * MAX_NUMBER
    min_sum = sum_range[0] if sum_range else 0

    dp = {(0, 0, 0, 0): 1}
    for n in range(1, MAX_NUMBER + 1):
        is_odd, is_low = n % 2, 1 if n <= low_max else 0
        new_dp = dict(dp)
        for (picked, total, odd, low), cnt in dp.items():
            if picked >= PICK_COUNT:
                continue
            nt = total + n
            if nt > max_sum:
                continue
            key = (picked + 1, nt, odd + is_odd, low + is_low)
            new_dp[key] = new_dp.get(key, 0) + cnt
        dp = new_dp

    result = 0
    for (picked, total, odd, low), cnt in dp.items():
        if picked != PICK_COUNT or total < min_sum or total > max_sum:
            continue
        if odd_even is not None and (odd, PICK_COUNT - odd) not in odd_even:
            continue
        if low_high is not None and (low, PICK_COUNT - low) not in low_high:
            continue
        result += cnt
    return result


# ---------- 조회 테이블 ----------

RECIPES_BY_ID = {
    "archimedes": ARCHIMEDES,
    "fibonacci": FIBONACCI,
    "pascal": PASCAL,
    "euler": EULER,
    "gaussian": GAUSSIAN,
}

# 월~금 배정(2026-10-13 유저 결정: 기존 geniusGenerator 순서 그대로 — 가우스 자리가 가우시안).
ORDER = ("archimedes", "fibonacci", "pascal", "euler", "gaussian")

# 첫 줄 제목의 "무엇을 보는 방법인가" 라벨. 요일 표시를 대체(2026-10-19 유저 결정) —
# 올린 시각은 스레드가 이미 보여주므로 첫 줄엔 방법의 내용을 넣는다.
LABEL = {
    "archimedes": "흐름분석",   # 총 출현 + 최근100회 + 안 나온 기간
    "fibonacci": "간격분석",    # 번호 사이 간격이 피보나치 수인지
    "pascal": "모양분석",       # 번호를 안 좁힌다 — 홀짝·저고·합계 모양만
    "euler": "그룹분석",        # 5로 나눈 나머지 그룹 + 서로소 비율
    "gaussian": "편차분석",     # 기대치에서 몇 표준편차 벗어났나
}

KOREAN_NAME = {
    "archimedes": "아르키메데스",
    "fibonacci": "피보나치",
    "pascal": "파스칼",
    "euler": "오일러",
    "gaussian": "가우시안",
}
