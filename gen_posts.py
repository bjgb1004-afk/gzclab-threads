"""큐가 마르지 않게, 지난 회차 데이터에서 글을 찍어낸다.

지금까지 pm/night 글은 손으로 쓴 34편이 전부였다. 하루 2편씩 쓰면 17일이면 바닥이고,
바닥나면 발행이 멈춘다. 손으로 더 쓰는 건 같은 문제를 미루는 것뿐이라, 글감 자체를
데이터에서 만든다 — 회차는 매주 늘고 번호는 45개라 소재가 떨어지지 않는다.

여덟 가지 틀을 날짜·슬롯으로 돌려 쓰고, 틀마다 보는 창(최근 50/100/300회)이나 대상
번호가 또 바뀐다. '번호 하나 프로필'은 45가지, '유명한 조합 성적'은 조합 수만큼 나온다.

규칙은 기존 글과 같다: 500자 안, 둘째 줄은 팔로우 유도, 인과("그래서 또 나온다") 금지,
사실만. 링크는 10편 중 4편꼴로만 단다(광고 계정으로 읽히지 않게).
"""

import collections
import datetime
import json
import pathlib

import lotto_gen as g
import replay as rp

QUEUE = pathlib.Path(__file__).with_name("queue.json")
LIMIT = 500
LINK = "https://gzclab.com/lottomap/?c=auto"
SLOTS = ("pm", "night")
# 손으로 쓴 글이 이만큼 남아 있으면 굳이 찍어내지 않는다. 먼저 쓰던 걸 다 쓴다.
KEEP_PENDING = 4
AHEAD_DAYS = 3        # 며칠 치를 미리 채워둘지

FOLLOW = (
    "이런 거 매일 하나씩 올림. 팔로우해두고 보면 됨.",
    "지난 회차에서 뽑아낸 것만 올림. 이어서 볼 사람은 팔로우.",
    "매일 번호랑 기록 하나씩 꺼내 옴. 팔로우하면 안 찾아와도 뜸.",
)
WINDOWS = (50, 100, 300, None)   # None = 전 회차
# 구간 경계는 band_gen과 같다. 그쪽을 import하지 않는 건 모듈을 덜 묶기 위해서다(여섯 줄이면
# 여기서 센다). 경계를 바꿀 일이 생기면 양쪽을 같이 고칠 것 — 다르면 글끼리 어긋난다.
BANDS = ((1, 9), (10, 19), (20, 29), (30, 39), (40, 45))
BAND_KO = ("1~9", "10번대", "20번대", "30번대", "40~45")


def pick(seq, seed):
    return seq[seed % len(seq)]


def scope_ko(window, n):
    return f"{n}회 전부" if window is None else f"최근 {window}회"


def window_of(draws, window):
    return draws if window is None else draws[-window:]


def band_avg(use):
    """구간별 평균 출현 개수. 합은 6이다."""
    tot = [0] * len(BANDS)
    for d in use:
        for n in d["numbers"]:
            for i, (lo, hi) in enumerate(BANDS):
                if lo <= n <= hi:
                    tot[i] += 1
                    break
    return [t / len(use) for t in tot]


def compose(title, body, closer, follow_seed):
    """제목 / 팔로우 유도 / 본문 / 마무리. 한 덩어리 안의 줄바꿈은 각자 알아서 넣는다."""
    text = "\n\n".join([title, pick(FOLLOW, follow_seed), *body, closer])
    if len(text) > LIMIT:
        raise RuntimeError(f"{len(text)}자 — 한도 {LIMIT} 초과\n{text}")
    return text


# ---------- 글 여덟 가지 ----------
# 각 함수는 (seed, draws) -> (본문, reply_mode)

# 사람들이 실제로 많이 쓰는 조합들. 성적은 지난 회차에서 센 사실이다.
FAMOUS = (
    ([1, 2, 3, 4, 5, 6], "1부터 6까지 순서대로"),
    ([7, 14, 21, 28, 35, 42], "7의 배수로만"),
    ([1, 7, 12, 19, 24, 31], "생일 날짜로만(1~31)"),
    ([2, 4, 6, 8, 10, 12], "짝수 앞쪽만"),
    ([40, 41, 42, 43, 44, 45], "제일 큰 번호 여섯 개"),
    ([3, 10, 13, 23, 33, 43], "끝자리 3만 모아서"),
    ([1, 5, 11, 21, 31, 41], "끝자리 1만 모아서"),
)


def t_famous(seed, draws):
    game, label = pick(FAMOUS, seed)
    res = rp.replay(game, draws)
    if res["hits"]:
        line = (
            f"{res['draws']}회 중 {res['hits']}번 등수에 들었음. "
            f"세후 다 합쳐서 {rp.won(res['net'])}, 제일 잘 나온 건 {res['best_draw']}회 {res['best']}등."
        )
    else:
        line = f"{res['draws']}회 동안 한 번도 등수에 못 들었음."
    return compose(
        f"{label} 찍은 번호, 지금까지 성적",
        [g.fmt(game), line, "앞으로 어떻게 될지는 모름. 지나간 회차를 되돌려본 것뿐임."],
        "자기 번호 6개 댓글에 남겨봐. 똑같이 돌려서 답 달아줌.\n4시간 지나면 답 못 달 수도 있음.",
        seed,
    ), "replay"


def t_cold(seed, draws):
    """가장 오래 안 나온 번호. 마지막 출현 회차는 기록이라 반박할 수 없다."""
    last = {}
    for d in draws:
        for n in d["numbers"]:
            last[n] = d["no"]
    now = draws[-1]["no"]
    # 한 번도 안 나온 번호는 "며칠째 안 나옴"을 셀 수 없다(실제 데이터엔 없지만 방어한다).
    cold = sorted((n for n in range(1, 46) if n in last), key=lambda n: last[n])[:3]
    rows = "\n".join(f"{n:02d}번 — {now - last[n]}회째 안 나옴 (마지막 {last[n]}회)" for n in cold)
    return compose(
        f"{now}회까지 제일 오래 안 나온 번호 3개",
        [rows, "오래 쉰 번호가 나올 차례라는 뜻은 아님. 매 회차 확률은 똑같음."],
        "다음엔 반대로 제일 자주 나온 번호 올림.",
        seed,
    ), None


def t_hot(seed, draws):
    window = pick(WINDOWS[:3], seed)
    use = window_of(draws, window)
    c = collections.Counter(n for d in use for n in d["numbers"])
    rows = "\n".join(f"{n:02d}번 — {cnt}번" for n, cnt in c.most_common(3))
    return compose(
        f"{scope_ko(window, len(use))}에 제일 많이 나온 번호",
        [rows, f"{len(use)}회면 번호 하나당 평균 {len(use) * 6 / 45:.1f}번이 기대값임. 위 숫자는 그보다 위."],
        "이 숫자로 뭘 하라는 건 아님. 기록이 그렇다는 것뿐임.",
        seed,
    ), None


def t_band(seed, draws):
    window = pick(WINDOWS, seed)
    use = window_of(draws, window)
    avg = band_avg(use)
    rows = "\n".join(f"{BAND_KO[i]} — 평균 {avg[i]:.1f}개" for i in range(len(avg)))
    top = max(range(len(avg)), key=lambda i: avg[i])
    return compose(
        f"{scope_ko(window, len(use))} 번호대별로 몇 개씩 나왔나",
        [rows, f"제일 많은 건 {BAND_KO[top]}. 구간 폭이 다르니 개수만 보면 안 됨(40~45는 6칸뿐)."],
        "이 비중대로 뽑은 5게임은 따로 올림.",
        seed,
    ), None


def t_prize(seed, draws):
    """1등 당첨금 최고·최저. 세후로 적는다 — 세전은 손에 쥔 적 없는 돈이다."""
    withp = [d for d in draws if d["prizes"].get(1)]
    hi = max(withp, key=lambda d: d["prizes"][1])
    lo = min(withp, key=lambda d: d["prizes"][1])
    rows = (
        f"최고 {hi['no']}회 — 1인당 {rp.won(hi['prizes'][1])} (세후 {rp.won(rp.after_tax(hi['prizes'][1]))})\n"
        f"최저 {lo['no']}회 — 1인당 {rp.won(lo['prizes'][1])} (세후 {rp.won(rp.after_tax(lo['prizes'][1]))})"
    )
    return compose(
        "역대 1등 당첨금, 제일 많을 때와 제일 적을 때",
        [rows, "같은 1등인데 차이가 이만큼 남. 그 회차에 몇 명이 맞혔냐로 갈림."],
        "3억 넘는 구간은 33%, 그 아래는 22% 떼고 계산한 금액임.",
        seed,
    ), None


def t_shape(seed, draws):
    """홀짝과 합계. 번호 고를 때 제일 많이 묻는 두 가지다."""
    window = pick(WINDOWS[:3], seed)
    use = window_of(draws, window)
    odd = collections.Counter(sum(n % 2 for n in d["numbers"]) for d in use)
    top_odd, cnt = odd.most_common(1)[0]
    sums = [sum(d["numbers"]) for d in use]
    rows = (
        f"홀짝은 {top_odd}:{6 - top_odd}이 {cnt}번으로 제일 많았음\n"
        f"여섯 개 합은 평균 {sum(sums) // len(sums)}, 제일 작을 때 {min(sums)} 제일 클 때 {max(sums)}"
    )
    return compose(
        f"{scope_ko(window, len(use))} 당첨번호 모양",
        [rows, "6개가 전부 홀수거나 전부 짝수인 회차는 드물지만 있긴 있음."],
        "이 범위에 맞춰 뽑는다고 확률이 올라가진 않음. 모양이 그렇다는 기록임.",
        seed,
    ), None


def t_number(seed, draws):
    """번호 하나를 프로필처럼. 45가지라 이 틀만으로도 한참 간다."""
    n = seed % 45 + 1
    rows = [d for d in draws if n in d["numbers"]]
    while not rows:                      # 한 번도 안 나온 번호는 쓸 내용이 없다
        n = n % 45 + 1
        rows = [d for d in draws if n in d["numbers"]]
    partner = collections.Counter(x for d in rows for x in d["numbers"] if x != n)
    best, best_cnt = partner.most_common(1)[0]
    body = (
        f"{len(draws)}회 중 {len(rows)}번 나왔음 (번호 하나당 평균은 {len(draws) * 6 // 45}번)\n"
        f"마지막은 {rows[-1]['no']}회\n"
        f"{best:02d}번과 제일 자주 붙어 나왔음 — {best_cnt}회 같이 나옴"
    )
    return compose(
        f"{n:02d}번은 지금까지 이랬음",
        [body, "같이 나온 횟수가 많다고 묶여 다니는 건 아님. 회차가 많아서 생기는 숫자임."],
        "번호 하나씩 돌아가면서 올리는 중임.",
        seed,
    ), None


def t_genius(seed, draws):
    who = pick(g.GENIUSES, seed)
    body = (
        who["how"] + ".\n"
        "월 아르키메데스 / 화 피보나치 / 수 파스칼 / 목 오일러 / 금 가우스, 토요일은 명당 번호."
    )
    return compose(
        f"매일 저녁 5시에 올리는 천재 번호 — {who['name']}",
        [body, "회차랑 이름이 정해지면 번호도 하나로 고정됨. 앱에서 뽑은 거랑 한 자도 안 틀림."],
        "토요일마다 그 주 번호 전부 채점해서 올림. 맞은 것만 골라 올리는 거 아님.",
        seed,
    ), None


TEMPLATES = (t_famous, t_cold, t_hot, t_band, t_prize, t_shape, t_number, t_genius)


# ---------- 큐 채우기 ----------

def build(day, slot, draws):
    """그 날짜·슬롯의 글 하나. 같은 날 같은 슬롯이면 언제 불러도 같은 글이 나온다."""
    seed = g.hash_string(f"{day}|{slot}")
    # 틀은 순서대로 돌린다. 해시로 고르면 같은 틀이 연달아 걸려 이틀 내리 같은 모양이 된다.
    maker = TEMPLATES[(day.toordinal() * len(SLOTS) + SLOTS.index(slot)) % len(TEMPLATES)]
    text, reply_mode = maker(seed, draws)
    post = {
        "id": f"auto-{day}-{slot}",
        "status": "pending",
        "slot": slot,
        "text": text,
    }
    # 10편 중 4편꼴로만 링크를 단다. 매일 링크가 붙으면 광고 계정으로 읽힌다.
    if seed % 10 < 4:
        post["link"] = LINK
    if reply_mode:
        post["reply_mode"] = reply_mode
    return post


def top_up(now, days=AHEAD_DAYS, queue_path=QUEUE, draws=None):
    """tick이 부른다. 슬롯별 남은 글이 KEEP_PENDING 미만일 때만 며칠 치를 채운다."""
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    have = {p["id"] for p in queue}
    today = now.astimezone(g.KST).date()
    added = []
    for slot in SLOTS:
        left = sum(1 for p in queue if p.get("status") == "pending" and p.get("slot") == slot)
        if left >= KEEP_PENDING:
            continue
        for i in range(days):
            day = today + datetime.timedelta(days=i)
            if f"auto-{day}-{slot}" in have:
                continue
            if draws is None:
                draws = rp.fetch_draws()
            added.append(build(day, slot, draws))
    if added:
        queue.extend(added)
        queue_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return added


def recycle(queue_path=QUEUE):
    """손으로 쓴 am(지역 TOP5) 글이 다 나가면 맨 앞부터 다시 돌린다.

    pm/night는 top_up이 데이터에서 찍어내므로 소재가 안 떨어지지만, 지역 글은 손으로 쓴
    72편이 전부다. 새로 찍어내려면 districts.json이 있어야 하는데 그건 공개 재배포를
    피하려고 커밋하지 않아서 Actions에는 없다. 그래서 다시 돌린다 — 한 바퀴가 두 달이 넘어
    타임라인에서 같은 글이 붙어 보이지 않는다.

    status만 되돌린다. post_id와 published_at은 다음 발행이 덮어쓴다. 일부러 건너뛴
    글(skipped)은 그대로 둔다.
    """
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    if any(p.get("slot") == "am" and p.get("status") == "pending" for p in queue):
        return []
    again = [p for p in queue if p.get("slot") == "am" and p.get("status") == "published"]
    for p in again:
        p["status"] = "pending"
    if again:
        queue_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return again


def main(argv=()):
    """미리보기: python gen_posts.py --dry [--days 7]"""
    now = datetime.datetime.now(datetime.timezone.utc)
    if "--dry" in argv:
        days = int(argv[argv.index("--days") + 1]) if "--days" in argv else 4
        draws = rp.fetch_draws()
        today = now.astimezone(g.KST).date()
        for i in range(days):
            for slot in SLOTS:
                post = build(today + datetime.timedelta(days=i), slot, draws)
                print(f"\n[{post['id']}] {len(post['text'])}자"
                      f"{' +link' if post.get('link') else ''}\n{post['text']}")
        return 0
    for p in top_up(now):
        print(p["id"])
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
