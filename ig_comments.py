"""인스타 '오늘의 1게임' 릴스 댓글에 번호 답글 (2026-11-05).

스레드 auto_reply와 같은 약속: 닉네임 남기면 그 닉네임으로 이번 회차 1게임을 뽑아 답글로 준다.
닉네임+회차로 정해지므로 같은 주엔 다시 물어도 같은 번호다.

인스타 API는 토큰에 instagram_business_manage_comments 권한이 있어야 댓글을 읽고 답한다.
권한이 없으면 첫 호출에서 바로 드러난다 — 그 사실을 instagram.json에 남기고 텔레그램으로 한 번만 알린 뒤
그날은 더 부르지 않는다(5분마다 같은 실패를 알리면 안 된다).

스팸으로 보이지 않게: 한 번 실행에 최대 RUN_CAP개, 하루 DAY_CAP개. 답글 문구는 번호가 사람마다 달라 같지 않다.
"""

import datetime
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

import lotto_gen as g

API = "https://graph.instagram.com/v23.0"
KINDS = ("genius", "band")       # 번호를 주는 릴스만 대상
LOOKBACK_DAYS = 3
RUN_CAP, DAY_CAP = 10, 100
ME = "gzclab"


def get(path, params, token):
    q = urllib.parse.urlencode({**params, "access_token": token})
    try:
        with urllib.request.urlopen(f"{API}/{path}?{q}", timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{path} {e.code}: {e.read().decode(errors='replace')[:300]}") from None


def post(path, params, token):
    body = urllib.parse.urlencode({**params, "access_token": token}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{API}/{path}", data=body, method="POST"), timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{path} {e.code}: {e.read().decode(errors='replace')[:300]}") from None


def reply_text(username, draw_no):
    nums = g.store_game(f"ig:{username}", draw_no)
    return (f"@{username} {draw_no}회 네 1게임\n{g.fmt(nums)}\n"
            "닉네임으로 뽑아서 이번 주엔 다시 물어봐도 같은 번호. 내일도 1게임 올라옴"), nums


def targets(state, now):
    """최근 LOOKBACK_DAYS일 안에 올린 번호 릴스 [(key, media_id, draw_no)]."""
    out = []
    today = now.astimezone(g.KST).date()
    for key, rec in state.get("published", {}).items():
        kind, _, d = key.partition("-")
        if kind not in KINDS or not rec.get("media_id"):
            continue
        try:
            day = datetime.date.fromisoformat(d)
        except ValueError:
            continue
        if (today - day).days <= LOOKBACK_DAYS:
            draw_no = g.upcoming_draw_no(datetime.datetime.combine(day, datetime.time(12), g.KST))
            out.append((key, rec["media_id"], draw_no))
    return out


def run(state, now, token, notify, fetch=get, send=post):
    """state(instagram.json 내용)를 고쳐서 돌려준다. 저장은 호출부가 한다."""
    cs = state.setdefault("comments", {"replied": {}, "day": None, "count": 0})
    today = now.astimezone(g.KST).date().isoformat()
    if cs.get("day") != today:
        cs["day"], cs["count"] = today, 0
    if cs.get("blocked_day") == today:
        return state
    sent = 0
    for key, media_id, draw_no in targets(state, now):
        try:
            items = fetch(f"{media_id}/comments", {"fields": "id,text,username,replies{username}"}, token).get("data", [])
        except Exception as e:
            cs["blocked_day"] = today
            if not cs.get("error_notified"):
                notify(f"⚠️ 인스타 댓글을 못 읽습니다(권한 확인 필요: instagram_business_manage_comments)\n{e}")
                cs["error_notified"] = True
            cs["last_error"] = str(e)[:300]
            return state
        cs.pop("error_notified", None)   # 읽기가 다시 되면 다음 실패 때 또 알린다
        for c in items:
            if sent >= RUN_CAP or cs["count"] >= DAY_CAP:
                return state
            cid, user = c.get("id"), c.get("username")
            if not cid or not user or user == ME or cid in cs["replied"]:
                continue
            if any(r.get("username") == ME for r in (c.get("replies") or {}).get("data", [])):
                cs["replied"][cid] = "already"
                continue
            text, nums = reply_text(user, draw_no)
            try:
                rid = send(f"{cid}/replies", {"message": text}, token).get("id")
            except Exception as e:
                cs["last_error"] = str(e)[:300]
                return state
            cs["replied"][cid] = {"reply_id": rid, "numbers": nums, "draw": draw_no, "post": key}
            cs["count"] += 1
            sent += 1
    return state


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(reply_text("tester", 1249)[0])
