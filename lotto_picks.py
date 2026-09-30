"""천재 5인 번호 주간 시리즈. 월~금은 천재 1명의 5게임, 토요일은 명당 5게임, 토요일 밤엔 채점.

  월 아르키메데스 / 화 피보나치 / 수 파스칼 / 목 오일러 / 금 가우스 / 토 명당 5곳
  토 추첨 뒤: 이번 주 30게임 채점 글 + 각 요일 글에 "이 글 채점" 답글 + 천재별 누적 승수

번호는 lotto_gen.py가 (회차, 천재)로 고정 생성한다. 앱(복권명당 천재 번호생성기)과 같은 번호다.
글은 큐를 거치지 않고 바로 발행한다(시각이 정해진 시리즈라서). 발행한 글은 queue.json에
published로 기록해서 collect_insights와 auto_reply가 그대로 집어가게 한다.

실행: python lotto_picks.py auto            (cron이 부르는 것. 지금 시각에 맞는 일을 한다)
      python lotto_picks.py daily [--dry]   (오늘 번호 글)
      python lotto_picks.py result [--dry]  (직전 회차 채점)
      python lotto_picks.py stats [--dry]   (다음 회차 흐름 정리. 일요일 18시)
      --now 2026-10-05T17:07:00+09:00      (시각 지정, 점검용)
      --draw 1244                           (result 회차 지정)
"""

import datetime
import json
import pathlib
import re
import sys
import urllib.error
import urllib.request

import lotto_gen as g
import lotto_stats
import publish

sys.stdout.reconfigure(encoding="utf-8")  # 윈도우 콘솔(cp949)에서 한글·기호 출력 깨짐 방지

HERE = pathlib.Path(__file__).parent
PICKS = HERE / "picks.json"
QUEUE = HERE / "queue.json"
REPLIES = HERE / "district_replies.json"

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat")
DAY_KO = {"mon": "월", "tue": "화", "wed": "수", "thu": "목", "fri": "금", "sat": "토"}
LETTERS = "ABCDE"
LIMIT = 500  # Threads 본문 글자 제한

# auto_reply.targets()가 "구 이름 남겨줘"가 든 글만 대상으로 잡는다. 빠지면 댓글에 답이 안 달린다.
# 접힘 뒤로 밀리면 안 보이므로(2026-09-26 참여 0 원인) 둘째 줄에 둔다.
# 예전 문구는 "그 동네 명당 번호 뽑아준다"였다. 시·군·구 1위가 1등 3~6회짜리인 동네가
# 대부분이라(2026-09-28 전국 집계) 그걸 근거로 번호를 만들어주는 건 과장이다. 약속도
# 빼고 auto_reply의 번호 한 줄도 뺐다. 실제로 가진 데이터(그 동네 TOP3)만 약속한다.
# 매일 같은 두 번째 줄이 7일 내내 반복되면 그게 제일 큰 봇 티다. 요일마다 돌려 쓴다.
ASKS = (
    "댓글에 구 이름 남겨줘. 그 동네 1등 많이 나온 집 바로 답으로 달아줌.",
    "우리 동네 명당 궁금하면 댓글에 구 이름 남겨줘. 바로 답 달아줌.",
    "댓글에 구 이름 남겨줘. 그 동네에서 1등 제일 많이 터진 집 찾아서 답 감.",
)
assert all("구 이름 남겨줘" in a for a in ASKS), "auto_reply가 대상에서 놓친다"

# 팔로우 유도. 지금까지 팔로워 235명 중 200명이 이 문구가 제목 바로 아래 있던 글
# 하나(9/28 월, 도달 32,012)에서 왔다. 전환 0.6%. 계정에서 유일하게 검증된 유입 경로라
# 맨 끝(접힘 뒤)이 아니라 제목 바로 아래에 둔다. 요일마다 돌려 쓴다 — mon이 0번이고
# 도달이 제일 큰 날이라, 실제로 200명을 데려온 "매일 번호가 온다" 약속을 0번에 둔다.
FOLLOWS = (
    "팔로우하면 수학천재들 번호가 매일 뜸.",
    "토요일 밤에 채점 결과 올라옴. 놓치기 싫으면 팔로우.",
    "누가 제일 많이 맞히는지 보려면 팔로우해두면 됨.",
    "매일 저녁 5시에 올림. 팔로우하면 안 찾아와도 뜸.",
    "지난주 순위는 토요일 글에 다 있음. 이어서 볼 사람은 팔로우.",
)

# Play 링크를 직접 달면 미리보기에 구글플레이 기본 아이콘이 뜬다. 랜딩을 거치면
# 복권명당 아이콘이 뜨고 ?c= 값이 Play Console referrer로 넘어간다.
LINK = "https://gzclab.com/lottomap/?c=picks"
LINK_LEAD = "번호 사러 갈 때 근처에 1등 많이 나온 집 있는지는 여기서 보면 됨:"

# 당첨번호. 앱(scripts/ingest/fetchDrawHistory.ts)도 이 미러를 쓴다. 동행복권 옛 API는 막혔다.
MIRROR = "https://raw.githubusercontent.com/smok95/lotto/master/results/{}.json"

STORE_MIN_WINS = 10  # 토요일 명당 후보: 그 구 1위이면서 1등 10회 이상(47곳, 약 9주에 한 바퀴)
SAT_CUTOFF_HOUR = 20  # 토요일 20시 판매 마감. 그 뒤에 명당 번호를 올리면 살 수가 없다
# 번호 글 KST 발행 시각. 예전엔 cron이 이 시각을 정했지만 지금은 tick.py 루프가 5분마다
# 물어보므로, 시각 판단이 여기 있어야 한다. 없으면 자정 직후 첫 틱에 그날 글이 나간다.
PICK_TIME = (17, 7)
RESULT_GIVE_UP = (6, 11)  # (일요일, 11시) KST 이후에도 당첨번호가 없으면 알린다


# ---------- 저장 ----------

def load(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def utc_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def record_in_queue(entry_id, text, post_id, draw_no, reply_mode=None):
    """collect_insights(조회수 수집)와 auto_reply(댓글 답글)가 이 글을 보게 한다."""
    queue = load(QUEUE, [])
    if any(p["id"] == entry_id for p in queue):
        return
    extra = {"reply_mode": reply_mode} if reply_mode else {}
    queue.append({
        **extra,
        "id": entry_id,
        "status": "published",
        "slot": "picks",
        "draw": draw_no,
        "text": text,
        "post_id": post_id,
        "published_at": utc_iso(),
    })
    save(QUEUE, queue)


# ---------- 명당 ----------

_TOP1 = re.compile(r"^1\. (.+?)(?: \((.+?)\))? — 1등 (\d+)회$", re.M)


def top_stores():
    """구별 1위 판매점 중 1등 STORE_MIN_WINS회 이상, 많은 순."""
    out = []
    for district, body in load(REPLIES, {}).items():
        m = _TOP1.search(body)
        if m and int(m.group(3)) >= STORE_MIN_WINS:
            out.append({"district": district, "name": m.group(1), "wins": int(m.group(3))})
    out.sort(key=lambda s: (-s["wins"], s["district"]))
    return out


def weekly_stores(draw_no, stores):
    """회차마다 5곳씩 돌아간다. 같은 회차면 언제 돌려도 같은 5곳."""
    if len(stores) < 5:
        raise RuntimeError(f"명당 후보가 {len(stores)}곳뿐 — district_replies.json 확인")
    start = (draw_no * 5) % len(stores)
    return [stores[(start + i) % len(stores)] for i in range(5)]


# ---------- 글 ----------

def build_genius_post(draw_no, day):
    genius = g.GENIUSES[DAYS.index(day)]
    games = g.genius_games(genius["id"], draw_no)
    lines = [
        f"[{draw_no}회] {DAY_KO[day]}요일의 천재: {genius['name']}",
        FOLLOWS[DAYS.index(day) % len(FOLLOWS)],
        ASKS[DAYS.index(day) % len(ASKS)],
        "",
        genius["how"],
        *[f"{LETTERS[i]}  {g.fmt(game)}" for i, game in enumerate(games)],
        "",
        "월~금 천재 한 명씩, 토요일은 명당. 토요일 밤에 그 주 30게임 전부 채점해서 순위 올림.",
    ]
    return "\n".join(lines), games, {"kind": "genius", "genius": genius["id"]}


def build_store_post(draw_no):
    stores = weekly_stores(draw_no, top_stores())
    games = []
    rows = []
    for i, s in enumerate(stores):
        game = g.store_game(s["name"], draw_no, exclude={g.combo_key(x) for x in games})
        games.append(game)
        # '남구'·'중구'는 여러 도시에 있어서 시도까지 붙인다.
        rows.append(f"{LETTERS[i]}  {g.fmt(game)}\n    {s['name']} ({s['district']}, 1등 {s['wins']}회)")
    lines = [
        f"[{draw_no}회] 토요일은 명당 번호",
        "월~금 천재 5명 vs 오늘 명당. 결과 보려면 팔로우.",
        ASKS[draw_no % len(ASKS)],
        "",
        f"1등 {STORE_MIN_WINS}회 이상 터진 명당 5곳, 그 집 이름으로 하나씩 뽑은 5게임",
        *rows,
        "",
        "오늘 20시 판매 마감. 추첨 끝나면 이번 주 30게임 채점해서 올림.",
    ]
    meta = {"kind": "store", "stores": [s["name"] for s in stores]}
    return "\n".join(lines), games, meta


def build_daily(draw_no, day):
    text, games, meta = build_store_post(draw_no) if day == "sat" else build_genius_post(draw_no, day)
    assert len(text) <= LIMIT, f"{day} 글 {len(text)}자 — {LIMIT}자 초과"
    return text, games, meta


# ---------- 채점 ----------

def rank_of(game, numbers, bonus):
    hit = len(set(game) & set(numbers))
    if hit == 6:
        return 1
    if hit == 5:
        return 2 if bonus in game else 3
    return {4: 4, 3: 5}.get(hit)


def score(games, numbers, bonus):
    hits = [len(set(x) & set(numbers)) for x in games]
    ranks = [r for r in (rank_of(x, numbers, bonus) for x in games) if r]
    best = max(hits)
    return {
        "best": best,
        "best_game": LETTERS[hits.index(best)],
        "ranks": sorted(ranks),
        "total": sum(hits),
    }


def contestant(entry):
    return g.GENIUS_BY_ID[entry["genius"]]["name"] if entry["kind"] == "genius" else "명당"


def summary(sc):
    s = f"최고 {sc['best']}개"
    if sc["ranks"]:
        best_rank = sc["ranks"][0]
        s += f" · {best_rank}등" + (f" 외 {len(sc['ranks']) - 1}게임" if len(sc["ranks"]) > 1 else "")
    return s


def weekly_winners(days):
    """최고 일치 수 → 당첨 게임 수 → 총 일치 수. 다 같으면 공동 1위."""
    key = lambda d: (d["score"]["best"], len(d["score"]["ranks"]), d["score"]["total"])
    top = max(key(d) for d in days.values())
    return [contestant(d) for d in days.values() if key(d) == top]


def standings(picks):
    wins = {}
    for draw in picks.values():
        for name in draw.get("result", {}).get("winners", []):
            wins[name] = wins.get(name, 0) + 1
    return sorted(wins.items(), key=lambda kv: (-kv[1], kv[0]))


def build_result_post(draw_no, days, numbers, bonus, table, weeks):
    n_games = sum(len(d["games"]) for d in days.values())
    winners = weekly_winners(days)
    lines = [
        f"[{draw_no}회 결과] {g.fmt(numbers)} + 보너스 {bonus:02d}",
        ASKS[(draw_no + 1) % len(ASKS)],
        "",
        f"이번 주 {n_games}게임 채점",
        *[f"{DAY_KO[day]} {contestant(d)}  {summary(d['score'])}" for day, d in days.items()],
        "",
        f"이번 주 1위: {' · '.join(winners)}" + (" (공동)" if len(winners) > 1 else ""),
        "누적 승수: " + " · ".join(f"{name} {n}" for name, n in table),
        f"기록 {weeks}주째. 월요일에 아르키메데스부터 다시 시작함. 이어서 볼 사람은 팔로우.",
    ]
    text = "\n".join(lines)
    assert len(text) <= LIMIT, f"결과 글 {len(text)}자 — {LIMIT}자 초과"
    return text, winners


def day_reply(draw_no, sc):
    if sc["ranks"]:
        won = " · ".join(f"{r}등" for r in sc["ranks"])
        return f"{draw_no}회 채점: 이 글에서 {won} 나옴! 최고 {sc['best']}개 일치({sc['best_game']}게임)"
    return f"{draw_no}회 채점: 최고 {sc['best']}개 일치({sc['best_game']}게임). 당첨은 없음. 다음 주에 다시."


def fetch_winning(draw_no):
    """(번호 6개, 보너스). 아직 안 올라왔으면 None."""
    req = urllib.request.Request(MIRROR.format(draw_no), headers={"User-Agent": "gzclab-threads"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    if d.get("draw_no") != draw_no or len(d.get("numbers", [])) != 6:
        return None
    return sorted(d["numbers"]), d["bonus_no"]


# ---------- 실행 ----------

def kst(now):
    return now.astimezone(g.KST)


def run_daily(now, dry):
    local = kst(now)
    wd = local.weekday()  # 0=월 … 6=일
    if wd == 6:
        print("일요일 — 번호 글 없음")
        return 0
    day = DAYS[wd]
    if day == "sat" and local.hour >= SAT_CUTOFF_HOUR:
        print("토요일 판매 마감 뒤 — 명당 번호 글 건너뜀")
        return 0
    draw_no = g.upcoming_draw_no(now)
    text, games, meta = build_daily(draw_no, day)

    if dry:
        print(text)
        print(f"--- {len(text)}자")
        return 0

    picks = load(PICKS, {})
    entry = picks.setdefault(str(draw_no), {"days": {}})["days"].get(day)
    if entry and entry.get("post_id"):
        print(f"{draw_no}회 {day} 이미 발행됨 — 아무것도 하지 않음")
        return 0

    try:
        post_id = publish.publish(text)
    except Exception as e:
        print(e, file=sys.stderr)
        publish.telegram(f"❌ 천재 번호 글 발행 실패 ({draw_no}회 {DAY_KO[day]})\n{e}")
        raise

    # 본문 성공을 먼저 기록한다. 링크 답글에서 죽어도 다음 실행이 본문을 또 올리지 않게.
    picks[str(draw_no)]["days"][day] = {**meta, "games": games, "post_id": post_id, "posted_at": utc_iso()}
    save(PICKS, picks)
    record_in_queue(f"picks-{draw_no}-{day}", text, post_id, draw_no)

    # 예전엔 토요일에만 링크를 달았다. 그 결과 도달 1·3위 글(9/28 월 32,012, 9/30 수
    # 12,987)에 클릭할 링크가 하나도 없었다. 링크 답글이 도달을 죽이지 않는 건
    # 9/28 김포 글(22,158, 링크 답글 있음)로 확인됐다. 매일 단다.
    try:
        publish.publish(f"{LINK_LEAD}\n{LINK}", reply_to=post_id)
    except Exception as e:
        print(e, file=sys.stderr)
        publish.telegram(f"⚠️ 번호 글은 올랐는데 링크 답글 실패\n{e}")

    publish.telegram(f"✅ {draw_no}회 {DAY_KO[day]}요일 번호 글 발행됨\nhttps://www.threads.net/@gzclab")
    return 0


def run_result(now, dry, draw_no=None):
    draw_no = draw_no or g.upcoming_draw_no(now) - 1
    picks = load(PICKS, {})
    week = picks.get(str(draw_no))
    days = {d: week["days"][d] for d in DAYS if week and d in week["days"] and week["days"][d].get("post_id")}
    if not days:
        print(f"{draw_no}회 번호 글이 하나도 없음 — 채점할 것 없음")
        return 0

    result = week.get("result", {})
    if not result.get("post_id"):
        got = fetch_winning(draw_no)
        if not got:
            local = kst(now)
            late = (local.weekday(), local.hour) >= RESULT_GIVE_UP
            print(f"{draw_no}회 당첨번호 아직 없음", file=sys.stderr)
            if late and not dry:
                publish.telegram(f"❌ {draw_no}회 당첨번호를 못 받아 결과 글을 못 올렸습니다. 미러({MIRROR.format(draw_no)}) 확인.")
                return 1
            return 0
        numbers, bonus = got
        for d in days.values():
            d["score"] = score(d["games"], numbers, bonus)
        # 이번 회차 승자를 넣은 상태로 누적을 센다.
        _, winners = build_result_post(draw_no, days, numbers, bonus, [], 0)
        week["result"] = {"numbers": numbers, "bonus": bonus, "winners": winners}
        weeks = sum(1 for w in picks.values() if w.get("result", {}).get("winners"))
        text, _ = build_result_post(draw_no, days, numbers, bonus, standings(picks), weeks)

        if dry:
            print(text)
            print(f"--- {len(text)}자")
            for day, d in days.items():
                print(f"[{day} 답글] {day_reply(draw_no, d['score'])}")
            return 0

        try:
            post_id = publish.publish(text)
        except Exception as e:
            print(e, file=sys.stderr)
            publish.telegram(f"❌ {draw_no}회 결과 글 발행 실패\n{e}")
            raise
        week["result"].update({"post_id": post_id, "posted_at": utc_iso()})
        save(PICKS, picks)
        record_in_queue(f"picks-{draw_no}-result", text, post_id, draw_no)
        try:
            publish.publish(f"{LINK_LEAD}\n{LINK}", reply_to=post_id)
        except Exception as e:
            print(e, file=sys.stderr)
        publish.telegram(f"🏁 {draw_no}회 결과 글 발행됨. 1위: {', '.join(winners)}")

    if dry:
        return 0
    # 각 요일 글에 채점 답글. 중간에 죽어도 다음 실행이 빠진 것만 채운다.
    for day, d in days.items():
        if d.get("result_reply_id") or "score" not in d:
            continue
        try:
            d["result_reply_id"] = publish.publish(day_reply(draw_no, d["score"]), reply_to=d["post_id"])
            save(PICKS, picks)
        except Exception as e:
            print(e, file=sys.stderr)
            publish.telegram(f"⚠️ {draw_no}회 {DAY_KO[day]} 글 채점 답글 실패\n{e}")
    return 0


STATS_HOUR = 18  # 일요일 18시 이후 흐름 정리 글
STATS_GIVE_UP_HOUR = 20  # 이때도 지난 회차 번호가 미러에 없으면 알린다


def run_stats(now, dry):
    """다음 회차 흐름 정리 글. 지난 회차까지의 실제 당첨번호로 매주 새로 계산한다."""
    draw_no = g.upcoming_draw_no(now)
    picks = load(PICKS, {})
    if picks.get(str(draw_no), {}).get("stats", {}).get("post_id"):
        print(f"{draw_no}회 흐름 글 이미 발행됨 — 아무것도 하지 않음")
        return 0
    draws = lotto_stats.fetch_all()
    if draw_no - 1 not in draws:
        print(f"{draw_no - 1}회 번호가 아직 미러에 없음", file=sys.stderr)
        if not dry and kst(now).hour >= STATS_GIVE_UP_HOUR:
            publish.telegram(f"❌ {draw_no - 1}회 번호가 미러에 없어 흐름 정리 글을 못 올렸습니다.")
            return 1
        return 0
    text = lotto_stats.build_post(lotto_stats.analyze(draws, draw_no - 1))
    if dry:
        print(text)
        print(f"--- {len(text)}자")
        return 0
    try:
        post_id = publish.publish(text)
    except Exception as e:
        print(e, file=sys.stderr)
        publish.telegram(f"❌ {draw_no}회 흐름 정리 글 발행 실패\n{e}")
        raise
    picks = load(PICKS, {})  # 채점이 같은 실행에서 파일을 바꿨을 수 있다
    picks.setdefault(str(draw_no), {"days": {}})["stats"] = {"post_id": post_id, "posted_at": utc_iso()}
    save(PICKS, picks)
    # reply_mode=combo: 지역 이름이 없어도 댓글마다 조합 1게임을 답으로 단다.
    record_in_queue(f"picks-{draw_no}-stats", text, post_id, draw_no, reply_mode="combo")
    publish.telegram(f"📈 {draw_no}회 흐름 정리 글 발행됨")
    return 0


def run_auto(now, dry):
    """cron 한 개로 돌린다. 월~토 낮엔 번호 글, 토 21시 이후~일요일엔 채점."""
    local = kst(now)
    wd = local.weekday()
    code = 0
    if (local.hour, local.minute) >= PICK_TIME and (wd <= 4 or (wd == 5 and local.hour < SAT_CUTOFF_HOUR)):
        code |= run_daily(now, dry)
    if (wd == 5 and local.hour >= 21) or wd == 6:
        code |= run_result(now, dry)
    if wd == 6 and local.hour >= STATS_HOUR:
        code |= run_stats(now, dry)
    return code


def main(argv):
    mode = argv[0] if argv and not argv[0].startswith("--") else "auto"
    dry = "--dry" in argv
    now = datetime.datetime.now(datetime.timezone.utc)
    if "--now" in argv:
        now = datetime.datetime.fromisoformat(argv[argv.index("--now") + 1])
    draw = int(argv[argv.index("--draw") + 1]) if "--draw" in argv else None

    if mode == "daily":
        return run_daily(now, dry)
    if mode == "result":
        return run_result(now, dry, draw)
    if mode == "stats":
        return run_stats(now, dry)
    if mode == "auto":
        return run_auto(now, dry)
    print(__doc__)
    return 2


if __name__ == "__main__":
    import os

    token = os.environ.get("THREADS_TOKEN")
    if not token and "--dry" not in sys.argv:
        print("THREADS_TOKEN 미설정 — 아무것도 하지 않음", file=sys.stderr)
        sys.exit(0)
    publish.TOKEN = token
    sys.exit(main(sys.argv[1:]))
