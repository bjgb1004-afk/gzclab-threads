"""번호 글 두 가지 — 번호대 분석(토요일 5게임)과 놓친 당첨금(매일 1게임).

번호는 band_gen(복권명당 앱 bandGenerator.ts의 포팅본)에서 가져온다. 여기서 따로 뽑으면
앱 화면과 다른 번호가 나가고, "앱에서 뽑아도 같은 번호"라는 말이 거짓이 된다.

앱과 마찬가지로 **날짜**로 고정된다(회차가 아니다). 같은 날이면 앱·스레드·인스타가 모두
같은 번호를 낸다. 놓친 당첨금 글의 1게임은 번호대 5게임의 A게임과 같은 번호다.

확률은 바뀌지 않는다(어떤 조합이든 1/8,145,060). 글에는 규칙만 적고 "그래서 잘 나온다"는
쓰지 않는다. 성적도 과거 사실로만 쓴다.
"""

import datetime
import json
import pathlib

import band_gen as bg
import replay as rp

HERE = pathlib.Path(__file__).parent
QUEUE = HERE / "queue.json"

GAMES = 5
LIMIT = 500       # Threads 본문 글자 제한
LETTERS = "ABCDE"
LINK = "https://gzclab.com/lottomap/?c=band"
MISS_LINK = "https://gzclab.com/lottomap/?c=miss"


def build_band(date_key, draws):
    """번호대 분석 글(토요일). 본문 500자 안에 들어가야 한다."""
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
        raise RuntimeError(f"{date_key} 번호대 글 {len(text)}자 — 한도 {LIMIT} 초과")
    return {
        "id": f"band-{date_key}",
        "status": "pending",
        "slot": "band",
        "text": text,
        "link": LINK,
        "reply_mode": "replay",
    }


def build_miss(date_key, draws):
    """놓친 당첨금 글(매일). 오늘의 번호 1게임 + 1회차부터 전부 돌린 성적.

    번호대 5게임의 A게임과 같은 번호다 — 앱에서도 인스타 카드에서도 같은 줄이 나온다.
    매일 5게임을 올리면 타임라인이 번호표가 되므로, 분석(토)과 성적(매일)을 나눴다.
    """
    nums = bg.generate_daily_band_games(date_key, 1)[0]["numbers"]
    res = rp.replay(nums, draws)
    if res["hits"]:
        order = sorted(res["by_rank"])
        detail = " · ".join(f"{r}등 {res['by_rank'][r]}번" for r in order)
        grade = (
            f"{res['from']}회부터 {res['to']}회까지 {res['draws']}회를 돌려봤더니\n"
            f"{res['hits']}번 당첨돼 있었음. ({detail})\n"
            f"다 합치면 {rp.won(res['gross'])}."
        )
    else:
        grade = f"{res['draws']}회 동안 한 번도 등수에 못 들었음. 이런 번호도 드묾."

    text = (
        f"오늘의 번호 {bg.fmt(nums)}\n"
        "\n"
        "이런 거 매일 하나씩 올림. 팔로우해두고 보면 됨.\n"
        "\n"
        f"{grade}\n"
        "\n"
        "사지 않았으면 받을 수 없는 돈이고, 지나간 회차 성적이라 다음 회차랑은 상관없음.\n"
        "\n"
        "자기 번호 6개 댓글에 남겨봐. 똑같이 돌려서 답 달아줌.\n"
        "4시간 지나면 답 못 달 수도 있음."
    )
    if len(text) > LIMIT:
        raise RuntimeError(f"{date_key} 놓친당첨금 글 {len(text)}자 — 한도 {LIMIT} 초과")
    return {
        "id": f"miss-{date_key}",
        "status": "pending",
        "slot": "miss",
        "text": text,
        "link": MISS_LINK,
        "reply_mode": "replay",
    }


# ---------- 발행 ----------
# 번호는 날짜로 고정이라 날이 바뀌면 번호도 바뀐다. id가 band-2026-10-03 / miss-2026-10-03
# 꼴이라 같은 날 몇 번을 돌려도 각각 한 번만 나간다.
#
# 번호대 분석은 **토요일만**이다. 월~금 번호 자리는 천재 5인(17:07)이 쓰고 토 17:07은
# 명당 5게임이다 — 그 둘을 합친 30게임을 토요일 밤에 채점하므로 lotto_picks는 건드리지
# 않는다. 놓친 당첨금은 매일.
#
# 두 글 다 본문이 "4시간 안에 답 달아줌"을 약속하므로 창이 닫히면 올리지 않는다.
# 밤에 살아난 루프가 지킬 수 없는 약속을 하면 안 된다.
BAND_DAY = 5                                  # 0=월 … 5=토
BAND_TIME, BAND_UNTIL = (10, 7), (14, 0)
MISS_TIME, MISS_UNTIL = (14, 7), (18, 0)      # 매일

LINK_LEAD = "번호 사러 갈 때 근처에 1등 많이 나온 집 있는지는 여기서 보면 됨:"

BUILD = {"band": build_band, "miss": build_miss}
TITLE = {"band": "번호대", "miss": "놓친 당첨금"}


def kst(now):
    return now.astimezone(datetime.timezone(datetime.timedelta(hours=9)))


def already(queue, entry_id):
    return any(p["id"] == entry_id for p in queue)


def due(now):
    """지금 올려야 할 종류. 창 밖이면 빈 목록."""
    local = kst(now)
    hm = (local.hour, local.minute)
    kinds = []
    if local.weekday() == BAND_DAY and BAND_TIME <= hm < BAND_UNTIL:
        kinds.append("band")
    if MISS_TIME <= hm < MISS_UNTIL:
        kinds.append("miss")
    return kinds


def publish_one(kind, date_key, queue, draws, dry=False):
    post = BUILD[kind](date_key, draws)
    if dry:
        print(f"[{post['id']}] {len(post['text'])}자\n{post['text']}\n{'-' * 50}")
        return

    import publish  # tick.py가 TOKEN을 넣어둔 모듈을 그대로 쓴다

    post_id = publish.publish(post["text"])
    # 본문 성공을 먼저 남긴다. 링크 답글에서 죽어도 다음 실행이 본문을 또 올리면 안 된다.
    queue.append({**post, "status": "published", "post_id": post_id, "date": date_key,
                  "published_at": datetime.datetime.now(datetime.timezone.utc)
                  .isoformat(timespec="seconds")})
    QUEUE.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    try:
        publish.publish(f"{LINK_LEAD}\n{post['link']}", reply_to=post_id)
    except Exception as e:
        publish.telegram(f"{TITLE[kind]} 글은 올랐는데 링크 답글 실패\n{post['id']}\n{e}")
    publish.telegram(
        f"{date_key} {TITLE[kind]} 글 발행됨\nhttps://www.threads.net/@gzclab\n"
        "댓글 답글은 4시간쯤까지만 나갑니다."
    )


def run_auto(now, dry=False):
    """tick.py가 5분마다 부른다. 창 안이고 오늘 그 글이 아직 없으면 발행한다."""
    kinds = due(now)
    if not kinds:
        return 0
    date_key = bg.kst_date_key(now)
    queue = json.loads(QUEUE.read_text(encoding="utf-8")) if QUEUE.exists() else []
    todo = [k for k in kinds if not already(queue, f"{k}-{date_key}")]
    if not todo:
        return 0
    draws = rp.fetch_draws()
    for kind in todo:
        publish_one(kind, date_key, queue, draws, dry=dry)
    return 0


def main(argv=()):
    """미리보기: python band_picks.py --dry [--now 2026-10-10T10:07:00+09:00]"""
    dry = "--dry" in argv
    now = datetime.datetime.now(datetime.timezone.utc)
    if "--now" in argv:
        now = datetime.datetime.fromisoformat(argv[argv.index("--now") + 1])
    if "--force" in argv or dry:
        draws = rp.fetch_draws(use_cache=not dry)
        for kind in BUILD:
            post = BUILD[kind](bg.kst_date_key(now), draws)
            print(f"[{post['id']}] {len(post['text'])}자\n{post['text']}\n{'-' * 50}")
        return 0
    return run_auto(now, dry=False)


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv[1:]))
