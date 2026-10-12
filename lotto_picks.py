"""복권명당 "수학 분석" 5인 주간 시리즈. 월~금은 분석법 1개씩, 토요일은 명당 5게임.

  월 아르키메데스 / 화 피보나치 / 수 파스칼 / 목 오일러 / 금 가우시안 / 토 명당 5곳
  (2026-10-13 유저 결정: geniusGenerator 순서 그대로, 가우스 자리가 가우시안)

  월~금 글은 번호를 본문에 싣지 않는다 — 분석 과정(압축 방식·필터·검증 숫자, recipes.py)만
  숫자로 쓰고, 번호는 댓글 단 사람에게 auto_reply가 1게임씩 답으로 준다. 그 댓글 번호는
  auto_reply.py가 comment_picks.json에 기록한다.

  토 추첨 뒤: 댓글로 나간 번호를 분석법별로 모아 성적을 낸 결과 글(recipe_result) + 명당·
  분석법 각 글에 "이 글 채점" 답글 + 분석법별 누적 1위 횟수. "확률이 올라간다"류 표현은
  쓰지 않는다([[project_threads_copy_policy]]) — 다섯 방법 다 실측상 무작위와 차이 없다.

번호는 lotto_gen.py(천재들의 한수, geniusGenerator 포팅)가 아니라 recipes.py(수학 분석
탭, backtest recipes 포팅)가 만든다 — 서로 다른 앱 기능이니 혼동하지 말 것. 명당(토요일)만
예외로 lotto_gen.store_game을 그대로 쓴다.
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
import recipes

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


def record_in_queue(entry_id, text, post_id, draw_no, reply_mode=None, genius=None):
    """collect_insights(조회수 수집)와 auto_reply(댓글 답글)가 이 글을 보게 한다."""
    queue = load(QUEUE, [])
    if any(p["id"] == entry_id for p in queue):
        return
    extra = {k: v for k, v in (("reply_mode", reply_mode), ("genius", genius)) if v}
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

# 복권명당 앱 "수학 분석" 탭(recipes.py가 포팅한 것)을 월~금에 쓴다. 다섯 레시피 모두 번호를
# 본문에 싣지 않는다 — 분석 과정(압축 방식·필터·검증 숫자)만 숫자로 보여주고, 번호는 댓글 단
# 사람에게 1게임씩 답으로 준다(auto_reply.compose_combo). 1246회 흐름 정리 글이 숫자·분석법
# 만으로 반응이 제일 좋았던 게 근거다. "확률이 올라간다"류 표현은 쓰지 않는다([[project_threads_copy_policy]]).
COMBO_ASK = "댓글 남기면 네 닉네임으로 {draw}회 번호 1게임 뽑아서 답 달아줌."
BACKTEST_ROUNDS = 300


def _candidates_line(candidates):
    return " ".join(f"{n:02d}" for n in sorted(candidates))


def _backtest_line(recipe, history):
    bt = recipes.backtest_candidate_hits(recipe, history, rounds=BACKTEST_ROUNDS)
    if not bt:
        return None
    return (f"최근 {bt['rounds']}회 검증: {bt['candidate_count']}개 안에 당첨번호 평균 "
            f"{bt['mean_hits']:.2f}개(무작위면 {bt['expected_hits']:.2f}개)")


def _recipe_body(recipe_id, draw_no, history):
    """레시피별 본문 가운데 줄들. (설명 줄들, meta용 추가 정보 없음)."""
    recipe = recipes.RECIPES_BY_ID[recipe_id]
    if recipe_id == "pascal":
        shape = recipes.count_combinations_by_shape(**recipe["filters"])
        shape33 = recipes.count_combinations_by_shape(odd_even={(3, 3)})
        return [
            "45개 번호를 좁히지 않고 조합의 '모양'만 고른다 — 조합론엔 \"어느 번호가 유망한가\"의 답이 없다",
            "홀짝·저고(1~22/23~45) 모두 2:4·3:3·4:2만, 합 100~175인 조합만 남김",
            f"전체 {recipes.total_combinations():,}가지 중 이 모양 통과분 {shape:,}개"
            f"({100 * shape / recipes.total_combinations():.1f}%) — 홀짝 3:3만 보면 {shape33:,}개",
        ]

    candidates, _ = recipes.analyze(recipe, history)
    method = {
        "archimedes": "전체출현40%·최근100회출현30%·미출현기간20%·구간균형10%로 점수 매겨 구간당 최대 3개씩 15개로 압축",
        "fibonacci": "피보나치수(1·2·3·5·8·13·21·34)근접25%·전체출현30%·최근50회출현20%·미출현10%·구간균형15%로 점수 매겨 구간당 최대 3개씩 15개로 압축",
        "euler": "전체출현35%·최근50회출현25%·나머지그룹(5로나눈나머지)균형20%·서로소비율φ(n)/n 20%로 점수 매겨 그룹당 최대 4개씩 15개로 압축",
        "gaussian": "번호마다 출현횟수가 이론 기대치에서 몇 표준편차(z) 떨어졌는지 재서 0에 가까운 걸 앞에 둠 — 구간당 최대 3개씩 15개로 압축",
    }[recipe_id]
    combo_filter = {
        "archimedes": "6개 뽑을 땐 합 100~175·홀짝·저고(1~22/23~45) 모두 2:4·3:3·4:2만·3연속 제외",
        "fibonacci": "6개 뽑을 땐 번호 간격 5개 중 3개 이상이 피보나치 수·합 100~175·3연속 제외",
        "euler": "6개 뽑을 땐 합 100~175·3연속 제외",
        "gaussian": "6개 뽑을 땐 합계가 평균138 ±1표준편차(109~167)·3연속 제외",
    }[recipe_id]
    lines = [method, combo_filter, f"이번 주 {len(candidates)}개: {_candidates_line(candidates)}"]
    bt = _backtest_line(recipe, history)
    if bt:
        lines.append(bt)
    if recipe_id == "gaussian":
        sd = recipes.sum_distribution_stats(history, recipe["filters"]["sum_range"])
        lines.append(f"합계 실측({sd['n']:,}회): 평균{sd['mean']:.1f}·표준편차{sd['std']:.1f}, "
                     f"밴드 안 {100 * sd['within_ratio']:.0f}%(이론 68%)")
    return lines


def build_recipe_post(recipe_id, day, draw_no, history):
    """다섯 레시피 공통 포맷. 번호는 본문에 없다 — 댓글 1게임으로만 나간다."""
    idx = DAYS.index(day)
    name = recipes.KOREAN_NAME[recipe_id]
    head = [
        f"[{draw_no}회] {DAY_KO[day]}요일의 분석: {name}",
        FOLLOWS[idx % len(FOLLOWS)],
        COMBO_ASK.format(draw=draw_no),
        "",
        *_recipe_body(recipe_id, draw_no, history),
    ]
    foot = ["", "토요일 밤에 댓글로 나간 번호까지 모아서 분석법별 성적 올림."]
    text = "\n".join(head + foot)
    assert len(text) <= LIMIT, f"{recipe_id} 글 {len(text)}자"
    return text, [], {"kind": "method", "genius": recipe_id}


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
        "오늘 20시 판매 마감. 추첨 끝나면 이번 주 올린 번호 전부 채점해서 올림.",
    ]
    meta = {"kind": "store", "stores": [s["name"] for s in stores]}
    return "\n".join(lines), games, meta


def build_daily(draw_no, day, history=None):
    if day == "sat":
        text, games, meta = build_store_post(draw_no)
    else:
        recipe_id = recipes.ORDER[DAYS.index(day)]
        text, games, meta = build_recipe_post(recipe_id, day, draw_no, history)
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


def summary(sc):
    s = f"최고 {sc['best']}개"
    if sc["ranks"]:
        best_rank = sc["ranks"][0]
        s += f" · {best_rank}등" + (f" 외 {len(sc['ranks']) - 1}게임" if len(sc["ranks"]) > 1 else "")
    return s


# ---------- 분석법 랭킹(2026-10-13: 로또흐름분석 글처럼 "댓글 → 그 댓글의 당첨"으로 순위를
# 매긴다. 월~금 글은 번호를 안 싣기 때문에, 몸통 5게임이 아니라 auto_reply가 댓글마다 준
# 번호(comment_picks.json)를 모아서 분석법별 성적을 낸다. ----------

COMMENT_PICKS = HERE / "comment_picks.json"


def recipe_result(draw_no, numbers, bonus):
    """그 회차에 댓글로 나간 번호를 분석법별로 집계. {recipe_id: {entries, ranked, best, total_hits}}."""
    by_recipe = {}
    for p in load(COMMENT_PICKS, []):
        if p["draw"] != draw_no:
            continue
        r = by_recipe.setdefault(p["recipe"], {"entries": 0, "ranked": 0, "best": 0, "total_hits": 0})
        hits = len(set(p["numbers"]) & set(numbers))
        r["entries"] += 1
        r["best"] = max(r["best"], hits)
        r["total_hits"] += hits
        if rank_of(p["numbers"], numbers, bonus):
            r["ranked"] += 1
    return by_recipe


def recipe_winners(by_recipe):
    """등수권 댓글 수 → 총 일치 수. 다 같으면 공동 1위. 댓글이 하나도 없으면 빈 리스트."""
    if not by_recipe:
        return []
    key = lambda rid: (by_recipe[rid]["ranked"], by_recipe[rid]["total_hits"])
    top = max(key(rid) for rid in by_recipe)
    return sorted((rid for rid in by_recipe if key(rid) == top), key=lambda rid: recipes.ORDER.index(rid))


def recipe_standings(picks):
    wins = {}
    for week in picks.values():
        for rid in week.get("recipe_result", {}).get("winners", []):
            wins[rid] = wins.get(rid, 0) + 1
    return sorted(wins.items(), key=lambda kv: (-kv[1], kv[0]))


def build_result_post(draw_no, numbers, bonus, store_score, by_recipe, table, weeks):
    lines = [
        f"[{draw_no}회 결과] {g.fmt(numbers)} + 보너스 {bonus:02d}",
        ASKS[(draw_no + 1) % len(ASKS)],
        "",
    ]
    if store_score:
        lines.append(f"토요일 명당 5게임  {summary(store_score)}")
    win_ids = recipe_winners(by_recipe)
    if by_recipe:
        total = sum(r["entries"] for r in by_recipe.values())
        lines.append(f"월~금 분석법 댓글 {total}명 채점")
        for rid in recipes.ORDER:
            if rid in by_recipe:
                r = by_recipe[rid]
                lines.append(f"{recipes.KOREAN_NAME[rid]}  {r['entries']}명 중 {r['ranked']}명 등수권·최고{r['best']}개")
        win_names = " · ".join(recipes.KOREAN_NAME[rid] for rid in win_ids)
        lines.append(f"이번 주 분석법 1위: {win_names}" + (" (공동)" if len(win_ids) > 1 else ""))
        # 1회차 표본은 거칠다(5게임이면 회차당 기대 적중 0.8개) — "1위니까 다음 주도 X"로
        # 읽히면 안 된다. ruflo-starter-63 지적: 순위는 매주 뒤집히고 확률은 안 바뀐다는 걸
        # 같은 글에 못 박는다.
        lines.append("순위는 회차마다 뒤집힘 — 어느 분석법도 확률을 바꾸진 않음.")
    else:
        lines.append("이번 주는 분석법 댓글 번호가 없어서 분석법 순위는 없음")
    if table:
        lines.append("누적 1위: " + " · ".join(f"{recipes.KOREAN_NAME[rid]} {n}" for rid, n in table))
    lines.append(f"기록 {weeks}주째. 월~금은 분석법 과정만 쓰고 번호는 댓글로 줌. 이어서 볼 사람은 팔로우.")
    text = "\n".join(lines)
    assert len(text) <= LIMIT, f"결과 글 {len(text)}자 — {LIMIT}자 초과"
    return text, win_ids


def day_reply(draw_no, sc):
    """토요일 명당 글의 자체 채점 답글(명당은 몸통 5게임을 그대로 유지한다)."""
    if sc["ranks"]:
        won = " · ".join(f"{r}등" for r in sc["ranks"])
        return f"{draw_no}회 채점: 이 글에서 {won} 나옴! 최고 {sc['best']}개 일치({sc['best_game']}게임)"
    return f"{draw_no}회 채점: 최고 {sc['best']}개 일치({sc['best_game']}게임). 당첨은 없음. 다음 주에 다시."


def recipe_reply(draw_no, recipe_id, by_recipe):
    """월~금 분석법 글에 다는 답글. 댓글로 나간 번호들의 성적이다(그 글의 몸통 게임이 아니다)."""
    r = by_recipe.get(recipe_id)
    if not r or not r["entries"]:
        return f"{draw_no}회 채점: 이 글 댓글로 나간 번호가 없어서 집계할 게 없음"
    if r["ranked"]:
        return f"{draw_no}회 채점: 댓글 {r['entries']}명 중 {r['ranked']}명 등수권! 최고 {r['best']}개 일치"
    return f"{draw_no}회 채점: 댓글 {r['entries']}명, 최고 {r['best']}개 일치. 등수권은 없음"


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


def history_or_none(dry=False):
    """레시피 분석에 쓸 전체 당첨 이력. 미러가 죽으면 None — 월~금 글은 번호 없이는 못 쓴다."""
    try:
        draws = lotto_stats.fetch_all()
        return sorted(draws.items())
    except Exception as e:
        print(f"미러 조회 실패: {e}", file=sys.stderr)
        if not dry:
            publish.telegram(f"⚠️ 번호 글용 당첨 이력 조회 실패 — 이번 틱은 건너뜀\n{e}")
        return None


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
    history = None
    if day != "sat":
        history = history_or_none(dry)
        if history is None:
            return 1
    text, games, meta = build_daily(draw_no, day, history)

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
    combo = meta["kind"] == "method"  # 번호가 본문에 없는 글은 댓글 답글로만 나간다
    record_in_queue(f"picks-{draw_no}-{day}", text, post_id, draw_no,
                    reply_mode="combo" if combo else None,
                    genius=meta["genius"] if combo else None)

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
    if not week or not week.get("days"):
        print(f"{draw_no}회 글이 하나도 없음 — 채점할 것 없음")
        return 0
    store = week["days"].get("sat")
    store = store if store and store.get("post_id") else None
    # 월~금(분석법) 글은 몸통에 게임이 없다 — 채점은 댓글로 나간 번호(comment_picks.json)로 한다.
    method_days = {d: week["days"][d] for d in DAYS[:5] if week["days"].get(d, {}).get("post_id")}
    if not store and not method_days:
        print(f"{draw_no}회 글이 하나도 없음 — 채점할 것 없음")
        return 0

    if not week.get("result"):
        got = fetch_winning(draw_no)
        if not got:
            local = kst(now)
            late = (local.weekday(), local.hour) >= RESULT_GIVE_UP
            print(f"{draw_no}회 당첨번호 아직 없음", file=sys.stderr)
            if late and not dry:
                publish.telegram(f"❌ {draw_no}회 당첨번호를 못 받아 결과 글을 못 올렸습니다. 미러({MIRROR.format(draw_no)}) 확인.")
                return 1
            return 0
        week["result"] = {"numbers": got[0], "bonus": got[1]}
        if not dry:
            save(PICKS, picks)

    numbers, bonus = week["result"]["numbers"], week["result"]["bonus"]
    if store:
        store.setdefault("score", score(store["games"], numbers, bonus))
    by_recipe = recipe_result(draw_no, numbers, bonus)

    if not week["result"].get("post_id"):
        # 이번 주 1위도 누적 집계(recipe_standings)에 바로 반영해야 글에 쓸 숫자가 맞는다.
        win_ids = recipe_winners(by_recipe)
        week["recipe_result"] = {"winners": win_ids}
        weeks = sum(1 for w in picks.values() if w.get("result", {}).get("post_id")) + 1
        text, _ = build_result_post(
            draw_no, numbers, bonus, store.get("score") if store else None,
            by_recipe, recipe_standings(picks), weeks)

        if dry:
            print(text)
            print(f"--- {len(text)}자")
            if store:
                print(f"[sat 답글] {day_reply(draw_no, store['score'])}")
            for d in method_days:
                print(f"[{d} 답글] {recipe_reply(draw_no, recipes.ORDER[DAYS.index(d)], by_recipe)}")
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
        win_label = " · ".join(recipes.KOREAN_NAME[r] for r in win_ids) or "없음(댓글 번호 없음)"
        publish.telegram(f"🏁 {draw_no}회 결과 글 발행됨. 분석법 1위: {win_label}")

    if dry:
        return 0
    # 명당·분석법 글에 채점 답글. 중간에 죽어도 다음 실행이 빠진 것만 채운다.
    if store and not store.get("result_reply_id"):
        try:
            store["result_reply_id"] = publish.publish(day_reply(draw_no, store["score"]), reply_to=store["post_id"])
            save(PICKS, picks)
        except Exception as e:
            print(e, file=sys.stderr)
            publish.telegram(f"⚠️ {draw_no}회 토 글 채점 답글 실패\n{e}")
    for day, entry in method_days.items():
        if entry.get("result_reply_id"):
            continue
        try:
            msg = recipe_reply(draw_no, recipes.ORDER[DAYS.index(day)], by_recipe)
            entry["result_reply_id"] = publish.publish(msg, reply_to=entry["post_id"])
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
