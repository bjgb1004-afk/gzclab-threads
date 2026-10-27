"""인스타 발행 글의 성적을 24시간 뒤 한 번씩 거둬 instagram.json에 남긴다.

왜 필요했나 (2026-10-27): 인스타에 48건을 올리는 동안 측정이 한 건도 없었다. "반응이
없다"는 건 체감일 뿐이고, 도달이 안 나오는 건지 도달은 되는데 아무도 안 누르는 건지
구분이 안 되면 고칠 데를 못 찾는다. 스레드 쪽(collect_insights.py)은 처음부터 거두고
있었고 그 숫자가 지역 글·흐름 정리 글을 찾아냈다. 인스타도 같은 걸 해야 한다.

거두는 지표와 이유:
  reach              비팔로워까지 몇 명한테 닿았나. 도달 문제인지 콘텐츠 문제인지 가른다.
  saved / shares     인스타가 비팔로워 추천에 쓰는 신호. 특히 shares(전송)가 세다.
  profile_visits     글을 보고 프로필까지 들어온 사람. 팔로우 직전 단계다.
  follows            그 글로 실제로 늘어난 팔로워. 우리가 알고 싶은 바로 그 숫자다.
  likes / comments / views / total_interactions   보조 지표.

follows와 profile_visits가 핵심이다. 도달이 커도 follows가 0이면 글이 팔로우할 이유를
안 준다는 뜻이고, 그건 포맷이 아니라 내용 문제다.

계정 팔로워 수도 하루 한 번 기록한다. 글별 follows의 합과 실제 증가는 다르다(언팔로우가
빠져 있다). 둘 다 있어야 늘고 있는지 알 수 있다.

실행: python collect_ig_insights.py          (tick이 부르는 것)
      python collect_ig_insights.py report   (지금까지 거둔 숫자를 표로)
"""

import datetime
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

from publish import telegram

sys.stdout.reconfigure(encoding="utf-8")  # 윈도우 콘솔(cp949)에서 한글 출력 깨짐 방지

API = "https://graph.instagram.com/v23.0"
STATE = pathlib.Path(__file__).with_name("instagram.json")

# 전부 한 번에 달라고 하고, 하나라도 지원이 안 되면 응답 전체가 400으로 떨어진다.
# 그래서 두 단으로 나눈다 — CORE는 FEED에서 확실히 되는 것, EXTRA는 계정 연결 방식에
# 따라 안 될 수 있는 것. EXTRA가 깨져도 CORE는 건진다.
CORE = ("reach", "likes", "comments", "saved", "shares")
EXTRA = ("views", "total_interactions", "profile_visits", "follows")

SETTLE_HOURS = 24  # 이보다 이른 숫자는 아직 움직인다
# 삭제된 글이나 지원 안 하는 타입은 영원히 같은 이유로 실패한다. 끊지 않으면 5분마다
# 같은 실패 알림이 영원히 온다(스레드 쪽에서 실제로 겪은 일이다).
MAX_ATTEMPTS = 3


# 기본값을 `path=STATE`로 쓰면 import 시점의 STATE가 박혀서, 나중에 STATE를 바꿔도
# 옛 경로를 읽는다(점검·테스트에서 엉뚱한 파일을 건드린다). 호출할 때 읽는다.
def load(path=None):
    path = path or STATE
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"published": {}}


def save(state, path=None):
    path = path or STATE
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get(path, params, token):
    """access_token은 쿼리로만 받는 API다. 로그에 찍히지 않게 예외 문구에서 지운다."""
    qs = urllib.parse.urlencode({**params, "access_token": token})
    try:
        with urllib.request.urlopen(f"{API}/{path}?{qs}", timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300].replace(token, "***")
        raise RuntimeError(f"HTTP {e.code} {body}") from None


def fetch(media_id, token):
    """{지표: 값}. EXTRA가 거부되면 CORE만이라도 건진다."""
    for metrics in (CORE + EXTRA, CORE):
        try:
            data = get(f"{media_id}/insights", {"metric": ",".join(metrics)}, token)
        except RuntimeError:
            if metrics is CORE:
                raise
            continue
        out = {}
        for m in data.get("data", []):
            vals = m.get("values") or []
            # 데이터가 없으면 0이 아니라 빈 배열이 온다. 0으로 적으면 "측정했는데 0"과
            # 구별이 안 되므로 그 지표는 넣지 않는다.
            if vals and "value" in vals[0]:
                out[m["name"]] = vals[0]["value"]
        if out:
            return out
    return {}


def follower_count(token):
    """계정 팔로워 수. 사용자 id는 토큰에서 바로 받는다."""
    me = get("me", {"fields": "id,username,followers_count"}, token)
    return me.get("followers_count"), me.get("username")


def record_followers(state, token, now):
    """하루 한 번만 적는다. 같은 날 다시 불려도 덮어쓰지 않는다."""
    day = now.astimezone(datetime.timezone(datetime.timedelta(hours=9))).date().isoformat()
    hist = state.setdefault("followers", {})
    if day in hist:
        return False
    count, _name = follower_count(token)
    if count is None:
        return False
    hist[day] = count
    return True


def due(state, now):
    return [
        (key, item) for key, item in state.get("published", {}).items()
        if item.get("media_id") and item.get("at") and "insights" not in item
        and now - datetime.datetime.fromisoformat(item["at"]) >= datetime.timedelta(hours=SETTLE_HOURS)
    ]


def main(token, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    state = load()
    changed = False

    try:
        changed |= record_followers(state, token, now)
    except Exception as e:
        print(f"팔로워 수 조회 실패: {e}", file=sys.stderr)

    for key, item in due(state, now):
        try:
            got = fetch(item["media_id"], token)
        except Exception as e:
            attempts = item.get("insights_attempts", 0) + 1
            item["insights_attempts"] = attempts
            changed = True
            if attempts >= MAX_ATTEMPTS:
                item["insights"] = {"error": str(e)[:200]}  # 이후 due에서 영구히 빠진다
                telegram(f"⚠️ 인스타 인사이트 포기({attempts}번 실패)\n{key}\n{e}")
            continue
        item["insights"] = got
        item.pop("insights_attempts", None)
        changed = True

    if changed:
        save(state)
    return 0


# ---------- 보기 ----------

def report():
    state = load()
    rows = []
    for key, item in state.get("published", {}).items():
        i = item.get("insights") or {}
        if not i or "error" in i:
            continue
        rows.append((item.get("at", ""), key, i))
    rows.sort()
    if not rows:
        print("아직 거둔 숫자가 없음. 발행 24시간 뒤부터 쌓인다.")
    else:
        cols = ("reach", "saved", "shares", "profile_visits", "follows", "likes", "comments")
        print(f"{'발행':<11}{'글':<22}" + "".join(f"{c:>9}" for c in cols))
        for at, key, i in rows:
            print(f"{at[:10]:<11}{key:<22}" + "".join(f"{str(i.get(c, '-')):>9}" for c in cols))
        # 종류별 평균. 어떤 소재가 먹히는지는 이걸로 갈린다.
        import collections, statistics
        by = collections.defaultdict(list)
        for _at, key, i in rows:
            by[key.rsplit("-", 3)[0]].append(i)
        print()
        for kind, items in sorted(by.items()):
            def avg(c):
                v = [x[c] for x in items if isinstance(x.get(c), (int, float))]
                return round(statistics.mean(v), 1) if v else "-"
            print(f"  {kind:<10} {len(items):>3}건  도달 {avg('reach'):>8}  저장 {avg('saved'):>5}"
                  f"  공유 {avg('shares'):>5}  프로필방문 {avg('profile_visits'):>5}  팔로우 {avg('follows'):>5}")
    hist = state.get("followers", {})
    if hist:
        days = sorted(hist)
        print(f"\n팔로워: {days[0]} {hist[days[0]]}명 → {days[-1]} {hist[days[-1]]}명 "
              f"({hist[days[-1]] - hist[days[0]]:+d})")


if __name__ == "__main__":
    if "report" in sys.argv[1:]:
        report()
        sys.exit(0)
    tok = os.environ.get("IG_TOKEN")
    if not tok:
        print("IG_TOKEN 미설정 — 아무것도 하지 않음", file=sys.stderr)
        sys.exit(0)
    sys.exit(main(tok))
