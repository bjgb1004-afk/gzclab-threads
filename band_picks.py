"""번호대(구간) 글 — 앱과 같은 5게임 + 그 번호의 지난 회차 성적.

번호는 band_gen(복권명당 앱 bandGenerator.ts의 포팅본)에서 가져온다. 여기서 따로 뽑으면
앱 화면과 다른 번호가 나가고, "앱에서 뽑아도 같은 번호"라는 말이 거짓이 된다.

앱과 마찬가지로 **날짜**로 고정된다(회차가 아니다). 같은 날이면 앱·스레드·인스타가 모두
같은 5게임을 낸다.

확률은 바뀌지 않는다(어떤 조합이든 1/8,145,060). 글에는 규칙만 적고 "그래서 잘 나온다"는
쓰지 않는다. 성적도 과거 사실로만 쓴다.
"""

import datetime
import json
import pathlib

import band_gen as bg
import lotto_gen as g
import replay as rp

HERE = pathlib.Path(__file__).parent
QUEUE = HERE / "queue.json"

GAMES = 5
LIMIT = 500       # Threads 본문 글자 제한
LETTERS = "ABCDE"
LINK = "https://gzclab.com/lottomap/?c=band"


def build(date_key, draws):
    """큐에 넣을 글 하나. 본문 500자 안에 들어가야 한다."""
    games = bg.generate_daily_band_games(date_key, GAMES)
    res = rp.replay(games[0]["numbers"], draws)

    rows = "\n".join(
        f"{LETTERS[i]}  {bg.fmt(x['numbers'])}  ({x['band_pattern']} · 저고 {x['low_high']})"
        for i, x in enumerate(games)
    )
    if res["hits"]:
        order = sorted(res["by_rank"])
        detail = " · ".join(f"{r}등 {res['by_rank'][r]}번" for r in order)
        grade = (
            f"A 번호를 {res['from']}회부터 {res['to']}회까지 돌려봤음.\n"
            f"{res['hits']}번 당첨({detail}), 다 합쳐서 {rp.won(res['gross'])}."
        )
    else:
        grade = f"A 번호는 {res['draws']}회 동안 한 번도 등수에 못 들었음."

    text = (
        "오늘의 번호대 분석 5게임\n"
        "\n"
        "다섯 구간(1~9 / 10번대 / 20번대 / 30번대 / 40~45) 중 한 곳은 비우고, "
        "한 구간에 세 개까지만. 저(1~22)랑 고(23~45)는 2:4 · 3:3 · 4:2 중 하나로 맞춤.\n"
        "\n"
        f"{rows}\n"
        "\n"
        f"{grade}\n"
        "\n"
        "자기 번호 6개 댓글에 남겨봐. 똑같이 돌려서 답 달아줌.\n"
        "4시간 지나면 답 못 달 수도 있음."
    )
    if len(text) > LIMIT:
        raise RuntimeError(f"{date_key} 글 {len(text)}자 — 한도 {LIMIT} 초과")
    return {
        "id": f"band-{date_key}",
        "status": "pending",
        "slot": "band",
        "text": text,
        "link": LINK,
        "reply_mode": "replay",
    }


# ---------- 발행 ----------
# 번호는 (회차)로만 고정이라 같은 주엔 매일 올려도 글이 똑같다. 그래서 회차당 한 번,
# 주 1회만 나간다. 금요일을 고른 건 추첨(토 20:45) 직전이라 "사러 가기 전"에 읽히기 때문이다.
BAND_DAY = 4          # 월=0 … 금=4
BAND_TIME = (14, 7)   # KST. 07:07/12:07/17:07/21:07 사이에서 제일 넓게 빈 자리다.
LINK_LEAD = "번호 사러 갈 때 근처에 1등 많이 나온 집 있는지는 여기서 보면 됨:"


def kst(now):
    return now.astimezone(datetime.timezone(datetime.timedelta(hours=9)))


def already(queue, entry_id):
    return any(p["id"] == entry_id for p in queue)


def run_auto(now, dry=False):
    """tick.py가 5분마다 부른다. 금 14:07이 지났고 이번 회차 글이 없으면 발행한다."""
    local = kst(now)
    if local.weekday() != BAND_DAY or (local.hour, local.minute) < BAND_TIME:
        return 0
    date_key = bg.kst_date_key(now)
    entry_id = f"band-{date_key}"
    queue = json.loads(QUEUE.read_text(encoding="utf-8")) if QUEUE.exists() else []
    if already(queue, entry_id):
        return 0

    post = build(date_key, rp.fetch_draws())
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
        "date": date_key,
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
        f"✅ {date_key} 번호대 글 발행됨\nhttps://www.threads.net/@gzclab\n"
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
        post = build(bg.kst_date_key(now), draws)
        print(f"[{post['id']}] {len(post['text'])}자\n")
        print(post["text"])
        return 0
    return run_auto(now, dry=False)


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
