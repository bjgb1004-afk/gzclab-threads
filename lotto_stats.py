"""매주 일요일 "로또 흐름 정리" 글. 지난 회차까지의 실제 당첨번호로 통계를 새로 계산한다.

사람이 쓸 소재가 필요 없고 매주 내용이 달라진다. 댓글을 달면 auto_reply가 그 사람 몫의
조합 1게임을 답으로 단다(queue 항목의 reply_mode="combo").

통계는 지난 기록일 뿐이다. 글에는 사실만 쓰고 "그래서 이번에도 나온다" 같은 인과는 쓰지 않는다.

실행: python lotto_stats.py [--dry] [--draw 1245]
"""

import collections
import datetime
import json
import sys
import urllib.request

import lotto_gen as g

ALL = "https://raw.githubusercontent.com/smok95/lotto/master/results/all.json"

# auto_reply가 이 글의 댓글에 조합을 단다. 접힘 앞(둘째 줄)에 둔다.
ASK = "댓글 남기면 {draw}회 추천 조합 1게임 바로 뽑아서 답으로 달아줌."
FOOT = "통계는 지난 기록일 뿐, 다음 회차는 어떤 번호든 확률이 같음. 도움 됐으면 리포스트로 공유 부탁"
LIMIT = 500
RECENT = 10  # "최근" 기준 회차 수
CARRY_WINDOW = 100  # 이월 비율을 보는 회차 수
MIN_FOLLOW_SAMPLE = 30  # 연결 통계를 쓰려면 그 번호가 이만큼은 나왔어야 한다

BANDS = ((1, 10), (11, 20), (21, 30), (31, 40), (41, 45))


def fetch_all():
    req = urllib.request.Request(ALL, headers={"User-Agent": "gzclab-threads"})
    with urllib.request.urlopen(req, timeout=60) as r:
        rows = json.load(r)
    return {x["draw_no"]: sorted(x["numbers"]) for x in rows if len(x.get("numbers", [])) == 6}


def pct(a, b):
    return round(100 * a / b) if b else 0


def sum_band(s):
    lo = (s - 1) // 20 * 20 + 1  # 121~140, 141~160 …
    return lo, lo + 19


def odd_even(nums):
    odd = sum(n % 2 for n in nums)
    return f"{odd}:{6 - odd}"


def consecutive_pairs(nums):
    return sum(1 for a, b in zip(nums, nums[1:]) if b == a + 1)


def analyze(draws, last):
    """last회까지의 기록으로 통계. draws = {회차: 정렬된 번호 6개}."""
    hist = [draws[n] for n in range(1, last + 1) if n in draws]
    if len(hist) < CARRY_WINDOW + 1 or last not in draws:
        raise RuntimeError(f"{last}회까지 기록이 부족함 ({len(hist)}회)")
    latest = draws[last]

    # 이월: 직전 회차 번호가 다음 회차에 다시 나온 것
    carry = [len(set(draws[n]) & set(draws[n - 1])) for n in range(last - CARRY_WINDOW + 1, last + 1)]
    carry_rate = pct(sum(1 for c in carry if c), len(carry))
    carry_avg = sum(carry) / len(carry)

    recent = [draws[n] for n in range(last - RECENT + 1, last + 1)]
    freq = collections.Counter(x for d in recent for x in d)
    hot = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    cold_recent = [n for n in range(1, 46) if n not in freq]

    # 가장 오래 쉰 번호: 마지막으로 나온 뒤 몇 회째 안 나오는지
    last_seen = {}
    for n in range(1, last + 1):
        for x in draws.get(n, []):
            last_seen[x] = n
    gaps = {x: last - last_seen.get(x, 0) for x in range(1, 46)}
    longest = max(gaps, key=lambda x: (gaps[x], -x))

    # 연결: 지난 회차 번호 x가 나온 다음 회차에 가장 자주 함께 나온 번호
    follow = None
    for x in latest:
        after = [draws[n + 1] for n in range(1, last) if x in draws.get(n, []) and n + 1 in draws]
        if len(after) < MIN_FOLLOW_SAMPLE:
            continue
        c = collections.Counter(y for d in after for y in d)
        y, cnt = max(c.items(), key=lambda kv: (kv[1], -kv[0]))
        rate = pct(cnt, len(after))
        if not follow or rate > follow["rate"]:
            follow = {"from": x, "to": y, "rate": rate, "gap": gaps[y]}

    band_counts = collections.Counter()
    for d in recent:
        for x in d:
            band_counts[next(b for b in BANDS if b[0] <= x <= b[1])] += 1
    top_band, top_band_n = max(band_counts.items(), key=lambda kv: (kv[1], -kv[0][0]))

    sums = collections.Counter(sum_band(sum(d)) for d in hist)
    top_sum, top_sum_n = sums.most_common(1)[0]
    oe = collections.Counter(odd_even(d) for d in hist)
    top_oe, top_oe_n = oe.most_common(1)[0]
    no_consec = sum(1 for d in hist if consecutive_pairs(d) == 0)

    return {
        "last": last,
        "latest": latest,
        "carry_rate": carry_rate,
        "carry_avg": carry_avg,
        "hot": hot,
        "cold_recent": cold_recent,
        "longest": (longest, gaps[longest]),
        "follow": follow,
        "band": (top_band, pct(top_band_n, RECENT * 6)),
        "sum": (top_sum, pct(top_sum_n, len(hist))),
        "odd_even": (top_oe, pct(top_oe_n, len(hist))),
        "no_consec": pct(no_consec, len(hist)),
        "total": len(hist),
    }


def build_post(s):
    nxt = s["last"] + 1
    lines = [
        f"{nxt}회 로또 흐름 정리",
        ASK.format(draw=nxt),
        "",
        f"지난 {s['last']}회: {g.fmt(s['latest'])}",
        "",
        f"직전 회차 번호가 1개 이상 다시 나온 비율 {s['carry_rate']}% (최근 {CARRY_WINDOW}회)",
        f"이월번호는 평균 {s['carry_avg']:.2f}개",
        "",
        "최근 10회 많이 나온 번호: " + " · ".join(f"{n}번({c}회)" for n, c in s["hot"]),
        f"가장 오래 쉬고 있는 번호: {s['longest'][0]}번 ({s['longest'][1]}회째 미출현)",
    ]
    if s["cold_recent"]:
        lines.append("최근 10회 한 번도 안 나온 번호: " + ", ".join(map(str, s["cold_recent"])))
    f = s["follow"]
    if f:
        tail = f", 최근 {f['gap']}회째 안 나옴" if f["gap"] >= 5 else ""
        lines.append(f"{f['from']}번이 나온 다음 회차에 {f['to']}번이 같이 나온 비율 {f['rate']}%{tail}")
    (lo, hi), share = s["band"]
    (slo, shi), sshare = s["sum"]
    lines += [
        f"최근 10회는 {lo}~{hi} 구간이 전체 출현의 {share}%",
        "",
        f"역대 {s['total']}회 기준: 번호합 {slo}~{shi} {sshare}% · 홀짝 {s['odd_even'][0]} {s['odd_even'][1]}% · 연속번호 없음 {s['no_consec']}%",
        "",
        FOOT,
    ]
    text = "\n".join(lines)
    # 안 나온 번호가 많은 주는 길어진다. 넘치면 그 줄부터 뺀다.
    if len(text) > LIMIT:
        text = "\n".join(l for l in lines if not l.startswith("최근 10회 한 번도"))
    assert len(text) <= LIMIT, f"흐름 글 {len(text)}자"
    return text


def main(argv):
    draws = fetch_all()
    last = int(argv[argv.index("--draw") + 1]) - 1 if "--draw" in argv else max(draws)
    text = build_post(analyze(draws, last))
    print(text)
    print(f"--- {len(text)}자")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
