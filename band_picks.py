"""번호대(구간) 분포로 뽑는 5게임 + 그 번호의 전 회차 성적 글.

천재 시리즈(lotto_picks)는 원주율·황금비 같은 상수에서 번호를 만든다. 이 글은 반대로
지난 회차 데이터에서 만든다 — 1~9 / 10번대 / 20번대 / 30번대 / 40~45 다섯 구간이
최근 N회에 평균 몇 개씩 나왔는지 세고, 그 비중대로 6자리를 채운다.

확률은 바뀌지 않는다(어떤 조합이든 1/8,145,060). 글에는 "이 비중대로 뽑았다"까지만 쓰고
"그래서 잘 나온다"는 쓰지 않는다. 성적도 과거 사실로만 쓴다.

번호는 (날짜)로 고정이다. 같은 날엔 몇 번을 돌려도 같은 5게임이 나와야 글과 답글이
어긋나지 않는다. 날짜가 바뀌면 번호도 바뀌므로 매일 나간다.

요일마다 비중을 세는 구간(WINDOWS)이 다르다. 같은 회차에 매일 올려도 근거와 번호가
같이 바뀌어야, 어제 글과 오늘 글이 서로를 반박하지 않는다.
"""

import datetime
import json
import pathlib

import lotto_gen as g
import replay as rp

HERE = pathlib.Path(__file__).parent
QUEUE = HERE / "queue.json"

# 구간 정의. 40~45는 6칸뿐이라 다른 구간보다 좁다 — 그래서 개수가 아니라 비중으로 쓴다.
BANDS = ((1, 9), (10, 19), (20, 29), (30, 39), (40, 45))
BAND_KO = ("1~9", "10번대", "20번대", "30번대", "40~45")
RECENT = 100      # 비중을 셀 기본 구간. 짧으면 흔들리고 길면 전체 평균과 같아진다
# 요일별로 보는 구간. None은 1회차부터 전부. 월→일 순서다.
WINDOWS = (30, 50, 100, 200, 300, 500, None)
GAMES = 5
LIMIT = 500       # Threads 본문 글자 제한
LETTERS = "ABCDE"
LINK = "https://gzclab.com/lottomap/?c=band"


def band_of(n):
    for i, (lo, hi) in enumerate(BANDS):
        if lo <= n <= hi:
            return i
    raise ValueError(n)


def band_counts(draws, recent=RECENT):
    """최근 recent회의 구간별 평균 출현 개수. 합은 6이다. recent=None이면 전 회차."""
    use = draws if recent is None else draws[-recent:]
    tot = [0] * len(BANDS)
    for d in use:
        for n in d["numbers"]:
            tot[band_of(n)] += 1
    return [t / len(use) for t in tot], len(use)


def target_shape(avg):
    """평균 개수를 정수 6자리로 바꾼다. 내림한 뒤 남는 자리는 소수부가 큰 구간에 준다."""
    base = [int(x) for x in avg]
    rest = 6 - sum(base)
    order = sorted(range(len(avg)), key=lambda i: -(avg[i] - base[i]))
    for i in order[:rest]:
        base[i] += 1
    return base


def games_for(seed, shape, count=GAMES):
    """그 시드의 5게임. 구간별 할당 개수(shape)를 지키면서 공통 필터를 통과시킨다.

    seed는 날짜(date)다. 같은 날 다시 불러도 같은 번호가 나와야 본문과 답글이 맞는다.
    """
    rng = g.mulberry32(g.hash_string(f"{seed}|band"))
    out = []
    used = set()
    guard = 0
    while len(out) < count and guard < 20_000:
        guard += 1
        pick = []
        ok = True
        for bi, need in enumerate(shape):
            lo, hi = BANDS[bi]
            pool = list(range(lo, hi + 1))
            if need > len(pool):
                ok = False
                break
            for _ in range(need):
                j = int(rng() * len(pool))
                pick.append(pool.pop(j))
        if not ok or len(pick) != 6:
            continue
        s = sorted(pick)
        key = g.combo_key(s)
        if key in used or not g.passes_common_filters(s):
            continue
        used.add(key)
        out.append(s)
    if len(out) < count:
        raise RuntimeError(f"{seed} 번호대 게임 {len(out)}개밖에 못 만듦")
    return out


def shape_line(avg, shape):
    """'20번대가 제일 많이 나왔음' 식의 근거 한 줄 + 할당표."""
    parts = [f"{BAND_KO[i]} {shape[i]}개" for i in range(len(BANDS)) if shape[i]]
    top = max(range(len(avg)), key=lambda i: avg[i])
    return f"{' · '.join(parts)}", BAND_KO[top], avg[top]


# 둘째 줄에 들어가는 팔로우 유도. 팔로워 235명 중 200명이 이 위치의 문구에서 왔다
# (lotto_picks.FOLLOW와 같은 근거). 같은 문구를 매일 쓰면 그 자체가 봇 티라 돌려 쓴다.
FOLLOW = (
    "이런 거 매일 하나씩 올림. 팔로우해두고 보면 됨.",
    "번호 돌려본 성적까지 매일 같이 올림. 이어서 볼 사람은 팔로우.",
    "요일마다 보는 구간이 다름. 전부 보려면 팔로우해두면 됨.",
)


def build(draw_no, draws, day):
    """큐에 넣을 글 하나. day(date)가 번호와 구간을 둘 다 정한다. 본문 500자 안이어야 한다."""
    window = WINDOWS[day.weekday()]
    avg, used_n = band_counts(draws, window)
    shape = target_shape(avg)
    games = games_for(day, shape)
    alloc, top_ko, top_avg = shape_line(avg, shape)
    res = rp.replay(games[0], draws)

    rows = "\n".join(f"{LETTERS[i]}  {g.fmt(x)}" for i, x in enumerate(games))
    if res["hits"]:
        order = sorted(res["by_rank"])
        detail = " · ".join(f"{r}등 {res['by_rank'][r]}번" for r in order)
        grade = (
            f"A 번호를 1회차부터 {res['draws']}회까지 전부 돌려봤음.\n"
            f"{res['hits']}번 당첨({detail}), 세후 다 합쳐서 {rp.won(res['net'])}. "
            f"제일 잘 나온 건 {res['best_draw']}회 {res['best']}등."
        )
    else:
        grade = f"A 번호는 {res['draws']}회 동안 한 번도 등수에 못 들었음."

    # 전 회차를 보는 날엔 "최근"이 거짓말이 된다.
    scope = f"전 회차({used_n}회)" if window is None else f"최근 {used_n}회"
    text = (
        f"{scope} 분포로 뽑은 {draw_no}회 5게임\n"
        "\n"
        f"{FOLLOW[day.toordinal() % len(FOLLOW)]}\n"
        "\n"
        f"{scope}에서 {top_ko}가 평균 {top_avg:.1f}개로 제일 많이 나왔음. "
        f"그 비중 그대로 {alloc} 맞춰서 뽑음.\n"
        "\n"
        f"{rows}\n"
        "\n"
        f"{grade}\n"
        "\n"
        "자기 번호 6개 댓글에 남겨봐. 똑같이 돌려서 답 달아줌.\n"
        "4시간 지나면 답 못 달 수도 있음."
    )
    if len(text) > LIMIT:
        raise RuntimeError(f"{day} 글 {len(text)}자 — 한도 {LIMIT} 초과")
    return {
        "id": f"band-{day}",
        "status": "pending",
        "slot": "band",
        "text": text,
        "link": LINK,
        # auto_reply가 이 글을 번호 답글 대상으로 고른다.
        "reply_mode": "replay",
    }


# ---------- 발행 ----------
# 번호와 구간이 날짜로 정해지므로 매일 다른 글이 나온다. 하루 한 번, 14:07이다 —
# 07:07/12:07/17:07/21:07 사이에서 제일 넓게 빈 자리다.
BAND_TIME = (14, 7)   # KST
# 창을 닫는 시각. 루프가 몇 시간 끊겼다가 밤에 살아나도 그때 올리지는 않는다 —
# 본문이 "4시간 안에 답 달아줌"을 약속하므로, 그 4시간이 자는 시간이면 약속을 못 지킨다.
BAND_UNTIL = (18, 0)
LINK_LEAD = "번호 사러 갈 때 근처에 1등 많이 나온 집 있는지는 여기서 보면 됨:"


def kst(now):
    return now.astimezone(datetime.timezone(datetime.timedelta(hours=9)))


def already(queue, entry_id):
    return any(p["id"] == entry_id for p in queue)


def run_auto(now, dry=False):
    """tick.py가 5분마다 부른다. 오늘 14:07이 지났고 오늘 글이 없으면 발행한다."""
    local = kst(now)
    if not BAND_TIME <= (local.hour, local.minute) < BAND_UNTIL:
        return 0
    draw_no = g.upcoming_draw_no(now)
    entry_id = f"band-{local.date()}"
    queue = json.loads(QUEUE.read_text(encoding="utf-8")) if QUEUE.exists() else []
    if already(queue, entry_id):
        return 0

    post = build(draw_no, rp.fetch_draws(), local.date())
    if dry:
        print(f"[{entry_id}] {len(post['text'])}자\n")
        print(post["text"])
        return 0

    import publish  # tick.py가 TOKEN을 넣어둔 모듈을 그대로 쓴다

    post_id = publish.publish(post["text"])
    # 본문 성공을 먼저 남긴다. 링크 답글에서 죽어도 다음 실행이 본문을 또 올리면 안 된다.
    queue.append({
        "reply_mode": "replay",
        "id": entry_id,
        "status": "published",
        "slot": "band",
        "draw": draw_no,
        "text": post["text"],
        "post_id": post_id,
        "published_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    })
    QUEUE.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    try:
        publish.publish(f"{LINK_LEAD}\n{LINK}", reply_to=post_id)
    except Exception as e:
        publish.telegram(f"⚠️ 번호대 글은 올랐는데 링크 답글 실패\n{entry_id}\n{e}")
    publish.telegram(
        f"✅ {local.date()} 번호대 글 발행됨({draw_no}회)\nhttps://www.threads.net/@gzclab\n"
        f"댓글 답글은 {BAND_TIME[0] + 4}시경까지만 나갑니다."
    )
    return 0


def main(argv=()):
    """미리보기: python band_picks.py --dry [--now 2026-10-09T14:07:00+09:00]"""
    dry = "--dry" in argv
    now = datetime.datetime.now(datetime.timezone.utc)
    if "--now" in argv:
        now = datetime.datetime.fromisoformat(argv[argv.index("--now") + 1])
    if "--force" in argv or dry:
        draws = rp.fetch_draws(use_cache=not dry)
        post = build(g.upcoming_draw_no(now), draws, kst(now).date())
        print(f"[{post['id']}] {len(post['text'])}자\n")
        print(post["text"])
        return 0
    return run_auto(now, dry=False)


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
