"""번호 6개를 지난 회차 전체에 되돌려 등수와 실수령 당첨금을 센다. 표준 라이브러리만 쓴다.

당첨금은 회차마다 다르다(5등도 1회차엔 10,000원이었다). 그래서 고정값을 쓰지 않고
smok95/lotto 미러의 `divisions`에 든 그 회차 실제 1인당 당첨금을 쓴다.

세금은 뺀다. 5만원 이하 비과세, 3억 이하 22%, 초과분 33%(소득세+지방세)다. 세전 금액만
쓰면 "총 당첨금 2억"처럼 실제로 손에 쥔 적 없는 숫자가 글에 나간다.

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

# 비과세 한도와 세율. 당첨금은 건당으로 과세된다(여러 건을 합산하지 않는다).
TAX_FREE = 200_000      # 20만원 이하는 과세 제외 (5등 5,000원, 4등 50,000원이 여기 든다)
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
            return json.loads(CACHE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
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


def replay(game, draws):
    """한 게임을 전 회차에 돌린 결과.

    반환: {회차수, 당첨횟수, 등수별{1~5: 횟수}, 세전총액, 세후총액, 최고등수, 최고회차}
    """
    game = sorted(game)
    by_rank = {}
    gross = net = 0
    best = None
    best_no = None
    for d in draws:
        r = rank_of(game, d["numbers"], d["bonus"])
        if not r:
            continue
        by_rank[r] = by_rank.get(r, 0) + 1
        prize = d["prizes"].get(r, 0)
        gross += prize
        net += after_tax(prize)
        if best is None or r < best:
            best, best_no = r, d["no"]
    return {
        "draws": len(draws),
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
    return f"{res['draws']}회 중 {res['hits']}번 당첨 ({detail}) · 세후 합계 {won(res['net'])}"
