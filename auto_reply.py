"""댓글에서 지역명을 읽어 그 구의 TOP3를 답글로 단다.

대상은 "댓글에 구 이름 남겨줘" 형 발행글. 이미 답한 댓글은 conversation 응답에서
바로 걸러지므로 상태 파일이 없다.
"""

import datetime
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

import lotto_gen
import publish
from publish import API, telegram

HERE = pathlib.Path(__file__).parent
REPLIES = HERE / "district_replies.json"
ME = "gzclab"
REPLY_LIMIT = 500  # Threads 글자 제한. 넘으면 번호 줄을 빼고 TOP3만 보낸다


def match(text, keys):
    """댓글에서 지역을 고른다. ('hit', 키) / ('ambiguous', 키들) / ('need_gu', 시도) / (None, None).

    '노원'처럼 접미사를 뗀 축약도 받는다. 다만 한 글자 축약('중구'->'중')은
    아무 문장에나 걸려서 쓰지 않는다.
    """
    # 전체 이름을 말한 경우가 가장 정확하다. 공백 유무를 모두 본다.
    for key in keys:
        if key in text or key.replace(" ", "") in text:
            return "hit", key

    # 부분 이름 -> 그 이름을 가진 키들. 키는 '서울 노원구'가 대부분이지만
    # '경기 용인시 기흥구'(시 아래 구)와 '세종시'(시도 자체)도 있다.
    by_part = {}
    for key in keys:
        toks = key.split()
        for tok in toks[1:] or toks:
            by_part.setdefault(tok, []).append(key)
            short = tok[:-1]  # 노원구 -> 노원
            if len(short) >= 2:
                by_part.setdefault(short, []).append(key)

    # 긴 이름부터 본다. '중구'보다 '노원구'가 먼저 걸려야 한다.
    for part in sorted(by_part, key=len, reverse=True):
        if part in text:
            cand = by_part[part]
            if len(cand) == 1:
                return "hit", cand[0]
            return "ambiguous", sorted(cand)

    # 광역만 말한 경우. '세종시'처럼 시도가 곧 키인 것은 위에서 이미 걸린다.
    for sido in sorted({k.split()[0] for k in keys if " " in k}):
        if sido in text:
            return "need_gu", sido

    return None, None


def compose(kind, value, username, replies, followup_ok):
    """답글 본문. 답할 것이 없으면 None.

    예전에는 여기에 "그 동네 명당 기운으로 뽑은 번호" 한 줄을 붙였다. 시·군·구 1위가
    1등 3~6회짜리인 동네가 대부분이라 그 숫자를 번호 근거로 쓰는 건 과장이어서 뺐다.
    """
    if kind == "hit":
        body = replies.get(value)
        if not body:  # 1위가 2회짜리라 굽는 단계에서 걸러진 구
            return None
        gu = value.split()[-1]
        return f"{username}아 {gu} 1등 많이 나온 집 뽑아왔어!\n\n{body}"
    if not followup_ok:
        return None
    if kind == "ambiguous":
        return f"{username}아 그 이름이 여러 군데 있어 ㅋㅋ {' / '.join(value)} 중에 어디야?"
    if kind == "need_gu":
        return f"{username}아 구까지 말해주면 바로 뽑아줄게. {value} 어느 구?"
    return None


def compose_combo(username, draw_no):
    """지역 없이 댓글만 단 사람 몫의 조합. 닉네임+회차로 뽑아서 같은 주엔 누가 다시 물어도 같다."""
    nums = lotto_gen.fmt(lotto_gen.store_game(f"user:{username}", draw_no))
    return (
        f"{username}아 {draw_no}회 네 조합 뽑아왔어!\n{nums}\n\n"
        "닉네임으로 뽑은 거라 이번 주엔 다시 물어봐도 같은 번호야. "
        "다음 주 일요일에도 올리니까 그때 또 와"
    )


def pick(items, my_ids):
    """답할 댓글만 고른다. (항목, 되묻기 허용) 목록.

    이미 답했는지는 conversation 응답만 보고 안다 — 내 답글이 그 댓글을 부모로
    달려 있으면 끝난 것이다. 그래서 상태 파일이 없다.
    """
    answered = {i.get("replied_to", {}).get("id") for i in items if i["username"] == ME}
    out = []
    for item in items:
        if item["username"] == ME or item["id"] in answered:
            continue
        # 내 되묻기에 달린 댓글에 또 되물으면 무한히 돈다. 확정일 때만 답한다.
        followup_ok = item.get("replied_to", {}).get("id") not in my_ids
        out.append((item, followup_ok))
    return out


DAILY_CAP = 50   # 글 하나당. 한 글이 터져도 그 글만 50건에서 멈춘다
# 계정 전체 상한. DAILY_CAP만 있으면 7일 창에 든 글 10개 × 50건 = 500건까지 갈 수 있고,
# 그건 Threads의 24시간 250건을 넘겨 그날 본문 발행까지 같이 죽는다. 발행(본문·링크답글)이
# 하루 10건 안팎이므로 답글은 150건에서 끊고 90건을 여유로 남긴다.
ACCOUNT_DAILY_CAP = 150
RUN_CAP = 10     # 한 번 실행에 10건. 밀려도 5분 뒤 이어서 답한다
WINDOW_DAYS = 7  # 이보다 오래된 글의 댓글은 뒤늦게 답해도 의미 없다


def conversation(media_id, token):
    fields = "id,text,username,timestamp,replied_to"
    url = f"{API}/{media_id}/conversation?fields={fields}&access_token={urllib.parse.quote(token)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r).get("data", [])
    except urllib.error.HTTPError as e:
        # publish.py와 같은 이유로 본문을 여기서 읽는다. 안 그러면 로그에 코드만 남는다.
        raise RuntimeError(
            f"conversation {media_id} {e.code}: {e.read().decode(errors='replace')[:300]}"
        ) from None


def targets(queue, now):
    """댓글을 유도한 글 중 최근 7일 내 발행된 것."""
    cut = now - datetime.timedelta(days=WINDOW_DAYS)
    out = []
    for p in queue:
        if p.get("status") != "published" or not p.get("post_id") or not p.get("published_at"):
            continue
        if datetime.datetime.fromisoformat(p["published_at"]) < cut:
            continue
        # 지역을 물어본 글, 또는 "댓글 남기면 조합 드림" 글(reply_mode=combo)만 대상이다.
        # 잡담 유도 글은 기계가 답할 거리가 없다.
        if "구 이름 남겨줘" in p["text"] or p.get("reply_mode") == "combo":
            out.append(p)
    return out


def send(text, reply_to):
    """답글 발행. 테스트는 이 함수를 갈아끼운다."""
    return publish.publish(text, reply_to=reply_to)


def main():
    queue = json.loads((HERE / "queue.json").read_text(encoding="utf-8"))
    replies = json.loads(REPLIES.read_text(encoding="utf-8"))
    keys = list(replies)
    now = datetime.datetime.now(datetime.timezone.utc)
    today = now.date().isoformat()
    draw_no = lotto_gen.upcoming_draw_no(now)

    sent = 0
    today_total = 0  # 오늘 내가 단 답글 수. 대상 글들의 conversation을 세어 알아낸다(상태 파일 없음)
    for post in targets(queue, now):
        if sent >= RUN_CAP:
            break
        try:
            items = conversation(post["post_id"], publish.TOKEN)
        except Exception as e:
            print(e, file=sys.stderr)
            telegram(f"⚠️ 댓글 조회 실패\n{post['id']}\n{e}")
            continue

        my_ids = {i["id"] for i in items if i["username"] == ME}
        # 하루 상한은 오늘 내가 이미 단 답글 수로 센다. 여기서도 상태 파일이 필요 없다.
        today_mine = sum(
            1 for i in items
            if i["username"] == ME and i.get("timestamp", "").startswith(today)
        )
        today_total += today_mine
        if today_mine >= DAILY_CAP or today_total >= ACCOUNT_DAILY_CAP:
            # 상한에 걸린 뒤로는 5분마다 같은 알림이 오게 된다. 이번 실행에서 실제로 답을
            # 단 경우에만, 즉 상한을 넘은 그 실행에서만 알린다.
            if sent:
                cap = DAILY_CAP if today_mine >= DAILY_CAP else ACCOUNT_DAILY_CAP
                telegram(f"⚠️ 자동 답글 하루 상한({cap}건) 도달. 남은 댓글은 내일 답합니다.")
            break

        for item, followup_ok in pick(items, my_ids):
            if sent >= RUN_CAP:
                break
            kind, value = match(item["text"], keys)
            msg = compose(kind, value, item["username"], replies, followup_ok)
            # 조합 글은 지역을 말하지 않은 댓글에도 답한다. 내 답글에 달린 댓글엔 또 답하지 않는다(무한 핑퐁 방지).
            if not msg and post.get("reply_mode") == "combo" and followup_ok:
                msg = compose_combo(item["username"], draw_no)
            if not msg:
                continue
            try:
                send(msg, item["id"])
                sent += 1
            except Exception as e:
                print(e, file=sys.stderr)
                telegram(f"⚠️ 자동 답글 실패\n{item['id']}\n{e}")

    print(f"답글 {sent}건")
    return 0


if __name__ == "__main__":
    token = os.environ.get("THREADS_TOKEN")
    if not token:
        print("THREADS_TOKEN 미설정 — 아무것도 하지 않음", file=sys.stderr)
        sys.exit(0)
    # publish.py는 TOKEN을 __main__에서만 설정한다. import해서 쓸 때는 직접 넣어야 한다.
    publish.TOKEN = token
    sys.exit(main())
