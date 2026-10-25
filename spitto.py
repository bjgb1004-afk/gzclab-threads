"""스피또(즉석복권) 글. 복권명당 앱이 쌓아둔 spitto_rounds 표를 읽어 스레드에 올린다.

왜 동행복권을 직접 안 긁나:
  앱 저장소(-ruflo-starter)의 sync-spitto.yml이 이미 하루 3회 발행내역을 받아 Supabase
  spitto_rounds에 덮어쓴다. 여기서 또 때리면 같은 데이터를 두 배로 긁는 셈이고, 과거
  연속 조회로 IP 차단을 당한 적이 있다. 읽기는 anon 키로 되는 공개 표다(RLS가 select 허용).
  덤으로 파싱("8매/8매"에서 앞이 잔여)이 이미 검증된 채로 들어와 있다.

글은 두 종류, 하루 한 건만 나간다:
  claim  지급 마감 14일 이내 회차 경고. 걸린 회차가 있을 때만 나간다.
  stock  1등이 많이 남은 판매중 회차. 입고율·잔여는 금요일 주 1회 갱신이라
         STOCK_COOLDOWN_DAYS 간격을 둔다 - 매일 올리면 같은 숫자를 반복한다.
claim이 stock보다 먼저다. 마감 날짜는 지나면 되돌릴 수 없고 잔여수량은 내일도 쓸 수 있다.

앱이 하는 일과 글이 약속하는 걸 일치시킨다(복권명당 스피또 화면):
  회차별 입고율·잔여수량, 1등 많이 남은 회차 먼저, 파는 가게 찾아 전화로 재고 확인,
  지급 마감 경고. 글에서 이 범위를 넘는 약속은 하지 않는다.

"구 이름 남겨줘"는 절대 쓰지 않는다 - auto_reply.targets()가 그 문구를 보면 이 글에도
로또 1등 TOP3를 답으로 달아버린다. 스피또 재고는 우리가 모르는 값이라 그건 거짓이 된다.

실행: python spitto.py auto [--dry]
      python spitto.py stock --dry
      python spitto.py claim --dry
      --now 2026-10-26T16:07:00+09:00   (시각 지정, 점검용)
"""

import datetime
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

import publish

sys.stdout.reconfigure(encoding="utf-8")  # 윈도우 콘솔(cp949)에서 한글 출력 깨짐 방지

HERE = pathlib.Path(__file__).parent
QUEUE = HERE / "queue.json"

KST = datetime.timezone(datetime.timedelta(hours=9))
LIMIT = 500  # Threads 본문 글자 제한

# 발행 시각. 이미 찬 자리를 피한 것이다: 번호글 07:07, 아침 슬롯 09:07, 점심 12:07,
# 놓친당첨금 14:07, 저녁 21:07, 토 번호대 10:07. 16:07이 가장 넓게 비어 있다.
POST_TIME = (16, 7)
# 입고율·잔여는 금요일 기준 주 1회 갱신이다(1등 지급 확정분만 수시 반영). 3일 간격이면
# 주 2회가 되고, 두 번째 글에는 최소 한 번의 갱신분이 들어간다.
STOCK_COOLDOWN_DAYS = 3
# 마감 경고는 같은 마감일을 두 번 올리지 않는다. 같은 날짜로 또 올리면 도배가 된다.
CLAIM_WARNING_DAYS = 14  # 앱(src/features/spitto/claimDeadline.ts)과 같은 기준

TABLE = "spitto_rounds"
COLUMNS = (
    "game_type,round_no,game_name,status,stock_rate,rank1_remaining,rank1_total,"
    "rank2_remaining,rank2_total,rank1_prize,price,sale_end_date,claim_end_date,figures_as_of"
)

LINK = "https://gzclab.com/lottomap/?c=spitto"  # ?c= 값이 Play Console referrer로 넘어간다
LINK_LEAD = "회차별 잔여수량이랑 파는 가게 찾기는 여기:"  # 링크 답글 전용
# 본문 맺음말. 링크는 답글에 따로 붙으므로 이 줄은 혼자서 문장이 되어야 한다.
APP_STOCK = "회차별 잔여수량 전체랑 스피또 파는 가게 찾기는 복권명당 앱에서 됨."
APP_CLAIM = "복권명당 앱은 지급 마감 다가오면 먼저 알려줌."

# 댓글 질문. 자동답글이 안 붙는 글이라 사람이 답할 거리를 묻는다. 요일로 돌려 쓴다.
QUESTIONS = (
    "스피또 사면 어느 거 사? 500 / 1000 / 2000 중에 댓글로 알려줘.",
    "긁어서 제일 많이 받아본 금액 얼마야? 댓글에 적어줘.",
    "복권방 가면 스피또도 같이 사? 댓글로 알려줘.",
    "안 긁고 모아두는 편이야, 바로 긁는 편이야?",
    "스피또로 5만원 이상 받아본 사람 있어? 댓글에 적어줘.",
    "이 숫자 매주 올려주면 도움 돼? 댓글에 적어줘.",
    "복권 살 때 회차 보고 골라본 적 있어?",
)
FOLLOW = "1등 많이 남은 회차 매주 올림. 이어서 볼 사람은 팔로우."


# ---------- 저장 ----------

def load(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def utc_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def record_in_queue(entry_id, text, post_id, kind):
    """collect_insights(조회수 수집)가 이 글을 집어가게 한다.

    reply_mode를 넣지 않는다 - auto_reply가 답할 거리가 없는 글이다(스피또 재고는 우리가
    가진 데이터가 아니다). 댓글은 사람이 받는다.
    """
    queue = load(QUEUE, [])
    if any(p["id"] == entry_id for p in queue):
        return
    queue.append({
        "id": entry_id,
        "status": "published",
        "slot": "spitto",
        "kind": kind,
        "text": text,
        "post_id": post_id,
        "published_at": utc_iso(),
    })
    save(QUEUE, queue)


def last_spitto(queue, kind=None):
    """마지막으로 나간 스피또 글의 발행 시각(UTC). 없으면 None."""
    times = [
        datetime.datetime.fromisoformat(p["published_at"])
        for p in queue
        if p.get("slot") == "spitto" and p.get("published_at")
        and (kind is None or p.get("kind") == kind)
    ]
    return max(times) if times else None


# ---------- 데이터 ----------

def fetch_rounds():
    """spitto_rounds 전부. 서른 몇 행이라 한 번에 받는다. 자격정보가 없으면 None."""
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_ANON_KEY")
    if not (url and key):
        return None
    req = urllib.request.Request(
        f"{url.rstrip('/')}/rest/v1/{TABLE}?select={urllib.parse.quote(COLUMNS)}",
        headers={"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def remaining_ratio(r):
    """1등이 몇 할 남았나. 모르는 회차는 맨 뒤로(앱 spittoApi.remainingRatio와 같은 규칙)."""
    remaining, total = r.get("rank1_remaining"), r.get("rank1_total")
    if remaining is None or not total:
        return -1.0
    return remaining / total


def selling_rounds(rounds):
    """지금 살 수 있는 회차를 1등 많이 남은 순으로. 앱 목록과 같은 순서여야 한다 -
    글에서 본 1위가 앱을 열었을 때 맨 위에 없으면 그 글이 거짓이 된다."""
    selling = [r for r in rounds if r.get("status") == "판매중"]
    return sorted(selling, key=lambda r: (-remaining_ratio(r), r.get("game_name") or ""))


def days_until(date_str, now):
    """오늘(KST)부터 그 날짜까지 남은 날. 지난 날짜는 음수. 모양이 다르면 None."""
    if not isinstance(date_str, str):
        return None
    try:
        end = datetime.date.fromisoformat(date_str.strip())
    except ValueError:
        return None
    return (end - now.astimezone(KST).date()).days


def claim_warning(rounds, now):
    """가장 급한 지급 마감 하나. 알릴 게 없으면 None.

    마감일이 여러 개 걸려도 가장 이른 하나만 쓴다 - 두 덩어리를 같이 올리면 둘 다 안 읽힌다
    (앱 claimDeadline.ts와 같은 판단). 같은 날 끝나는 회차는 모아서 한 줄에 쓴다.
    """
    soon = []
    for r in rounds:
        left = days_until(r.get("claim_end_date"), now)
        if left is not None and 0 <= left <= CLAIM_WARNING_DAYS:
            soon.append((left, r))
    if not soon:
        return None
    least = min(left for left, _ in soon)
    nearest = [r for left, r in soon if left == least]
    end = nearest[0]["claim_end_date"]
    return {
        "claim_end_date": end,
        "days_left": least,
        "labels": [f"{r.get('game_name')} {r.get('round_no')}회" for r in nearest],
    }


# ---------- 글 ----------

def fmt_stock(r):
    """한 회차 한 줄. 모르는 값은 쓰지 않는다 - 빈칸을 0으로 보여주면 거짓이 된다."""
    parts = []
    if r.get("rank1_remaining") is not None and r.get("rank1_total"):
        parts.append(f"1등 {r['rank1_remaining']}/{r['rank1_total']}매")
    if r.get("rank2_remaining") is not None and r.get("rank2_total"):
        parts.append(f"2등 {r['rank2_remaining']}/{r['rank2_total']}매")
    if r.get("stock_rate") is not None:
        parts.append(f"입고율 {r['stock_rate']}%")
    return f"{r.get('game_name')} {r.get('round_no')}회  " + " · ".join(parts)


def stock_hook(top):
    """첫 줄. 그 회차의 실제 숫자만 쓴다."""
    remaining, total = top["rank1_remaining"], top["rank1_total"]
    label = f"{top.get('game_name')} {top.get('round_no')}회"
    if remaining == total:
        return f"{label}는 1등 {total}매가 아직 한 장도 안 나갔습니다."
    return f"1등이 가장 많이 남은 건 {label}, {total}매 중 {remaining}매가 남았습니다."


def as_of_line(rounds):
    """숫자가 언제 기준인지. 이걸 빼면 실시간으로 오해한다 - 앱 쪽에서도 같이 띄우는 값이다."""
    days = sorted({r["figures_as_of"] for r in rounds if r.get("figures_as_of")})
    if not days:
        return "숫자 기준일을 못 받아왔음."
    return f"숫자는 {days[-1]} 기준. 입고율·잔여는 금요일에 주 1회 갱신되고, 1등 지급 확정분은 수시로 반영됨."


# 즉석복권은 긁힌 만큼 모집단이 줄어드는 복원 없는 추출이라, 잔여 비율이 높은 회차가
# 한 장당 1등 확률이 실제로 더 높다. 로또 번호 분석법과 성격이 다르므로 "확률이 올라간다"를
# 쓰지 않는 copy policy를 여기까지 끌고 오면 오히려 사실을 숨기게 된다. 다만 기대값이
# 플러스로 바뀌는 건 아니고 그 선을 반드시 같은 글에 박는다.
HONEST = ("잔여 비율이 높은 회차가 한 장당 1등 확률은 실제로 높음. "
          "그래도 복권 기대값은 마이너스라 많이 사라는 얘기는 아님.")


def build_stock_post(rounds, now):
    """1등 많이 남은 회차 글. 판매중 회차가 없으면 None."""
    selling = selling_rounds(rounds)
    known = [r for r in selling if remaining_ratio(r) >= 0]
    if not known:
        return None
    idx = now.astimezone(KST).timetuple().tm_yday

    def compose(rows_n, with_honest=True):
        lines = [
            "[스피또] " + stock_hook(known[0]),
            QUESTIONS[idx % len(QUESTIONS)],  # 접힘 앞 둘째 줄
            "",
            *[fmt_stock(r) for r in known[:rows_n]],
            "",
            as_of_line(known[:rows_n]),
        ]
        if with_honest:
            lines.append(HONEST)
        lines += ["", APP_STOCK, FOLLOW]
        return "\n".join(lines)

    # 판매중 회차가 많은 주엔 500자를 넘는다. 줄 수부터 줄이고, 그래도 넘치면 정직 문구를
    # 뺀다(그건 마지막이다 - 저 한 줄이 이 글에서 제일 중요하다).
    for rows_n in range(min(5, len(known)), 0, -1):
        text = compose(rows_n)
        if len(text) <= LIMIT:
            return text
    text = compose(1, with_honest=False)
    if len(text) <= LIMIT:
        return text
    raise AssertionError(f"스피또 잔여 글 {len(text)}자 — {LIMIT}자 초과")


def build_claim_post(warning):
    """지급 마감 경고 글."""
    left = warning["days_left"]
    if left <= 0:
        head = "오늘이 당첨금 받는 마지막 날입니다."
    elif left == 1:
        head = "내일이면 당첨금을 못 받습니다."
    else:
        head = f"{left}일 뒤면 당첨금을 못 받습니다."
    _, month, day = warning["claim_end_date"].split("-")
    lines = [
        f"[스피또] {head}",
        "서랍이나 지갑에 스피또 있는 사람 지금 확인해. 해당 회차면 댓글로 알려줘.",
        "",
        f"{int(month)}월 {int(day)}일까지 — " + ", ".join(warning["labels"]),
        "이 회차는 기한이 지나면 1등이어도 못 바꿈.",
        "안 긁은 것만이 아니라 긁어놓고 안 바꾼 것도 똑같이 사라짐.",
        "",
        APP_CLAIM,
        "매달 말에 한 번씩 확인하는 게 제일 안전함.",
    ]
    text = "\n".join(lines)
    assert len(text) <= LIMIT, f"스피또 마감 글 {len(text)}자"
    return text


# ---------- 실행 ----------

def post(text, entry_id, kind, label, dry):
    if dry:
        print(text)
        print(f"--- {len(text)}자  [{entry_id}]")
        return 0
    try:
        post_id = publish.publish(text)
    except Exception as e:
        print(e, file=sys.stderr)
        publish.telegram(f"❌ 스피또 {label} 글 발행 실패\n{e}")
        raise
    record_in_queue(entry_id, text, post_id, kind)
    # 본문이 성공했으면 링크 답글이 죽어도 글은 남는다. 번호 글과 같은 순서다.
    try:
        publish.publish(f"{LINK_LEAD}\n{LINK}", reply_to=post_id)
    except Exception as e:
        print(e, file=sys.stderr)
        publish.telegram(f"⚠️ 스피또 글은 올랐는데 링크 답글 실패\n{e}")
    publish.telegram(f"🎟️ 스피또 {label} 글 발행됨\nhttps://www.threads.net/@gzclab")
    return 0


def run_claim(now, dry, rounds=None):
    rounds = fetch_rounds() if rounds is None else rounds
    if rounds is None:
        print("SUPABASE_URL/ANON_KEY 미설정 — 스피또 건너뜀", file=sys.stderr)
        return 0
    warning = claim_warning(rounds, now)
    if not warning:
        print("지급 마감 14일 이내 회차 없음")
        return 0
    entry_id = f"spitto-claim-{warning['claim_end_date']}"
    if any(p["id"] == entry_id for p in load(QUEUE, [])):
        print(f"{warning['claim_end_date']} 마감 경고는 이미 나갔음")
        return 0
    return post(build_claim_post(warning), entry_id, "claim", "마감", dry)


def run_stock(now, dry, rounds=None):
    rounds = fetch_rounds() if rounds is None else rounds
    if rounds is None:
        print("SUPABASE_URL/ANON_KEY 미설정 — 스피또 건너뜀", file=sys.stderr)
        return 0
    queue = load(QUEUE, [])
    last = last_spitto(queue, "stock")
    if last and (now - last) < datetime.timedelta(days=STOCK_COOLDOWN_DAYS):
        print(f"잔여 글 쿨다운 중(마지막 {last.date()})")
        return 0
    text = build_stock_post(rounds, now)
    if not text:
        print("판매중 회차의 잔여수량을 못 받아왔음 — 잔여 글 건너뜀")
        return 0
    return post(text, f"spitto-stock-{now.astimezone(KST).date()}", "stock", "잔여", dry)


def run_auto(now, dry):
    """하루 한 번 POST_TIME 이후에 부른다. 마감 경고가 먼저, 없으면 잔여 글."""
    local = now.astimezone(KST)
    if (local.hour, local.minute) < POST_TIME:
        return 0
    queue = load(QUEUE, [])
    last = last_spitto(queue)
    if last and last.astimezone(KST).date() == local.date():
        return 0  # 스피또는 하루 한 건
    rounds = fetch_rounds()
    if rounds is None:
        print("SUPABASE_URL/ANON_KEY 미설정 — 스피또 건너뜀", file=sys.stderr)
        return 0
    if claim_warning(rounds, now):
        code = run_claim(now, dry, rounds)
        # 마감 경고가 이미 나간 날짜였으면 대신 잔여 글을 본다.
        if any(p.get("slot") == "spitto" and p.get("published_at")
               and datetime.datetime.fromisoformat(p["published_at"]).astimezone(KST).date() == local.date()
               for p in load(QUEUE, [])):
            return code
    return run_stock(now, dry, rounds)


def main(argv):
    mode = argv[0] if argv and not argv[0].startswith("--") else "auto"
    dry = "--dry" in argv
    now = datetime.datetime.now(datetime.timezone.utc)
    if "--now" in argv:
        now = datetime.datetime.fromisoformat(argv[argv.index("--now") + 1])
    if mode == "stock":
        return run_stock(now, dry)
    if mode == "claim":
        return run_claim(now, dry)
    if mode == "auto":
        return run_auto(now, dry)
    print(__doc__)
    return 2


if __name__ == "__main__":
    token = os.environ.get("THREADS_TOKEN")
    if not token and "--dry" not in sys.argv:
        print("THREADS_TOKEN 미설정 — 아무것도 하지 않음", file=sys.stderr)
        sys.exit(0)
    publish.TOKEN = token
    sys.exit(main(sys.argv[1:]))
