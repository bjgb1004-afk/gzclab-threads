"""번호 6개를 지난 회차 전체에 되돌려 등수와 실수령 당첨금을 센다. 표준 라이브러리만 쓴다.

당첨금은 회차마다 다르다(5등도 1회차엔 10,000원이었다). 그래서 고정값을 쓰지 않고
smok95/lotto 미러의 `divisions`에 든 그 회차 실제 1인당 당첨금을 쓴다.

**복권명당 앱 src/features/backtest/replay.ts와 숫자가 같아야 한다.** 댓글로 받은 번호에
답해준 결과가 그 사람이 앱에서 확인한 값과 다르면 신뢰를 잃는다. 그래서 세 가지를 앱에 맞춘다.

1. 4·5등은 회차와 무관하게 금액이 정해져 있다(복권 및 복권기금법 시행령) — 50,000 / 5,000원.
   미러 데이터의 초기 회차에는 4등 139,300원 같은 옛 체계 값이 들어 있는데, 그걸 쓰면
   앱보다 많이 나온다. 1~3등만 회차 금액을 쓴다.
2. 회차 범위를 앱과 맞춘다(START_ROUND). 앱은 Supabase draw_history를 그대로 쓰고 그 테이블이
   262회부터라, 전체를 돌리면 회차 수와 당첨 횟수가 앱보다 커진다.
3. 비과세 기준은 5만원 이하다(앱 draws/lotteryTax.ts). 4·5등은 전부 여기 들어가 세금이 없다.

앱 화면이 보여주는 합계는 세전이다(4·5등만 나오는 경우가 사실상 전부라 세후와 같다).
summary_line도 그 값을 쓴다. 세후가 필요하면 after_tax를 따로 부른다.

lotto_picks.rank_of와 같은 판정을 쓴다. 한쪽만 고치면 번호 글 채점과 이 글의 결과가
어긋나므로, test_replay.py가 두 구현이 같은 등수를 내는지 본다.
"""

import json
import pathlib
import urllib.error
import urllib.request

# lotto_picks.MIRROR와 같은 호스트를 쓴다. smok95.github.io도 같은 파일을 주지만,
# 그 호스트는 막혀 있는 망이 있어서 raw 쪽으로 고정한다.
MIRROR_ALL = "https://raw.githubusercontent.com/smok95/lotto/master/results/all.json"
CACHE = pathlib.Path(__file__).with_name("draws_cache.json")

# 앱 draws/lotteryTax.ts와 같은 값. 당첨금은 건당 과세된다(여러 건을 합산하지 않는다).
TAX_FREE = 50_000       # 5만원 이하 비과세 — 4등(5만)·5등(5천)이 여기 든다
LOW_RATE = 0.22         # 3억 이하
HIGH_RATE = 0.33        # 3억 초과분
HIGH_BASE = 300_000_000


def after_tax(prize):
    """실수령액. 원 단위 버림."""
    if prize <= TAX_FREE:
        return prize
    if prize <= HIGH_BASE:
        return int(prize * (1 - LOW_RATE))
    return int(HIGH_BASE * (1 - LOW_RATE) + (prize - HIGH_BASE) * (1 - HIGH_RATE))


# 4·5등은 법으로 정해진 고정 금액이다(앱 replay.ts의 FIXED_PRIZE와 같다).
FIXED_PRIZE = {4: 50_000, 5: 5_000}

# 앱이 쓰는 draw_history가 이 회차부터라 전체를 돌리면 앱보다 회차가 많아진다.
# 앱 화면도 "262~1243회 · 982회 돌려본 결과"로 나온다.
START_ROUND = 262


def prize_of(rank, draw):
    """그 회차에 그 등수로 받았을 1인 당첨금. 모르면 0 — 없는 돈을 지어내지 않는다."""
    if rank in FIXED_PRIZE:
        return FIXED_PRIZE[rank]
    return draw["prizes"].get(rank, 0)


def rank_of(game, numbers, bonus):
    """lotto_picks.rank_of와 같은 판정. 등수가 없으면 None."""
    hit = len(set(game) & set(numbers))
    if hit == 6:
        return 1
    if hit == 5:
        return 2 if bonus in game else 3
    return {4: 4, 3: 5}.get(hit)


def fetch_draws(use_cache=True):
    """[{no, numbers, bonus, prizes}] 오름차순. prizes는 등수(1~5) -> 1인당 당첨금.

    all.json은 약 1MB다. Actions에서 5분마다 받으면 낭비라 캐시를 둔다. 캐시가 최신
    회차를 놓쳐도 결과가 몇 건 덜 세어질 뿐이라, 받기 실패하면 캐시로 조용히 넘어간다.
    """
    if use_cache and CACHE.exists():
        try:
            cached = json.loads(CACHE.read_text(encoding="utf-8"))
            # JSON은 dict 키를 문자열로만 쓴다. prizes의 등수 키가 "4"로 돌아오는데
            # replay()는 정수 4로 찾으므로, 되돌리지 않으면 당첨금이 전부 0으로 집계된다
            # (2026-10-02에 카드 렌더링에서 "세후 합계 0원"으로 드러난 버그).
            for d in cached:
                d["prizes"] = {int(k): v for k, v in d["prizes"].items()}
            return cached
        except (json.JSONDecodeError, OSError, ValueError, KeyError):
            pass  # 캐시가 깨졌으면 그냥 다시 받는다
    req = urllib.request.Request(MIRROR_ALL, headers={"User-Agent": "gzclab-threads"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = json.load(r)
    draws = []
    for d in raw:
        nums = d.get("numbers") or []
        if len(nums) != 6 or d.get("bonus_no") is None:
            continue
        prizes = {}
        for i, div in enumerate(d.get("divisions") or [], start=1):
            # 초창기 회차는 1등 당첨자가 없어 {} 가 들어 있다. 그 등수는 금액을 모르는 것으로 둔다.
            if isinstance(div, dict) and div.get("prize"):
                prizes[i] = div["prize"]
        draws.append({
            "no": d["draw_no"],
            "numbers": sorted(nums),
            "bonus": d["bonus_no"],
            "prizes": prizes,
        })
    draws.sort(key=lambda x: x["no"])
    try:
        CACHE.write_text(json.dumps(draws, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # 캐시를 못 써도 결과에는 영향이 없다
    return draws


def replay(game, draws, start_round=START_ROUND):
    """한 게임을 전 회차에 돌린 결과.

    반환: {회차수, 당첨횟수, 등수별{1~5: 횟수}, 세전총액, 세후총액, 최고등수, 최고회차}
    """
    game = sorted(game)
    use = [d for d in draws if d["no"] >= start_round] if start_round else list(draws)
    by_rank = {}
    gross = net = 0
    best = None
    best_no = None
    for d in use:
        r = rank_of(game, d["numbers"], d["bonus"])
        if not r:
            continue
        by_rank[r] = by_rank.get(r, 0) + 1
        prize = prize_of(r, d)
        gross += prize
        net += after_tax(prize)
        # 앱 replay.ts와 같은 규칙: 등수가 낮을수록(1등에 가까울수록) 좋고, 같은 등수면
        # 최근 회차를 쓴다. 회차 오름차순으로 돌고 있으므로 같은 등수면 뒤엣것이 이긴다.
        if best is None or r < best or r == best:
            best, best_no = r, d["no"]
    return {
        "draws": len(use),
        "from": use[0]["no"] if use else 0,
        "to": use[-1]["no"] if use else 0,
        "hits": sum(by_rank.values()),
        "by_rank": by_rank,
        "gross": gross,
        "net": net,
        "best": best,
        "best_draw": best_no,
    }


def won(amount):
    """사람이 읽는 금액. 만원 미만은 그대로, 그 이상은 만/억 단위로 줄인다."""
    if amount >= 100_000_000:
        eok = amount / 100_000_000
        return f"{eok:.1f}억원".replace(".0억", "억")
    if amount >= 10_000:
        return f"{amount // 10_000:,}만원"
    return f"{amount:,}원"


def summary_line(res):
    """글과 답글에 공통으로 쓰는 한 줄 요약."""
    if not res["hits"]:
        return f"{res['draws']}회 동안 한 번도 등수에 못 들었음."
    order = sorted(res["by_rank"])
    detail = " · ".join(f"{r}등 {res['by_rank'][r]}번" for r in order)
    return f"{res['draws']}회 중 {res['hits']}번 당첨 ({detail}) · 합계 {won(res['gross'])}"
