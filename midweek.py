"""수요일 저녁 "번호 중간 점검" 글 (2026-11-02 도입, 조회수 하락 대응 실험).

왜 만들었나: 계정 조회수는 일요일 흐름 정리 글(4~9천)과 당첨 결과 글 몇 개가 거의 다 만든다.
평일 글은 ~400에 갇혀 있다. 같은 구조(닉네임 남기면 조합 1게임 답)를 주중에 한 번 더 시험한다.

일요일 글을 복사하지 않는다. 같은 글이 주 2번 나가면 그게 반복 콘텐츠다. 이 글은 그 주 월·화
천재가 실제로 고른 15개를 겹쳐 본 것(이번 주에만 있는 정보)에 지난 회차 번호와 이월 비율을 붙인다.

하루 글 수는 늘리지 않는다 — 수요일 밤 슬롯(21:07) 글을 이 글이 대신한다(tick.due_slot_start).
성적 집계(채점)에는 넣지 않는다. 댓글 답은 combo로 나가지만 genius를 안 달아 comment_picks에
기록되지 않는다.
"""

import datetime
import re
import sys

import lotto_gen as g
import lotto_picks as lp
import lotto_stats
import publish

MID_TIME = (18, 7)   # 수요일 KST. 일요일 흐름 글(18:00)이 저녁에 반응이 좋았다
WEEKDAY = 2          # 수요일
LIMIT = 500
ASK = "댓글 남기면 네 닉네임으로 {draw}회 조합 1게임 뽑아서 답 달아줌."
FOOT = "흐름 정리는 일요일 저녁, 이 중간 점검은 수요일 저녁에 올림. 팔로우하면 둘 다 뜸."
_FIFTEEN = re.compile(r"이번 주 15개: ((?:\d{2} ?){15})")
DAY_KO = {"mon": "월", "tue": "화", "wed": "수", "thu": "목", "fri": "금"}


def week_sets(queue, draw_no):
    """그 회차의 월~금 천재 글 중 '이번 주 15개'가 본문에 있는 것들. [(요일, set)]"""
    out = []
    for day in ("mon", "tue", "wed", "thu", "fri"):
        for p in queue:
            if p["id"] == f"picks-{draw_no}-{day}":
                m = _FIFTEEN.search(p["text"])
                if m:
                    out.append((day, {int(x) for x in m.group(1).split()}))
    return out


def overlap(sets):
    """모든 글이 같이 고른 번호(오름차순). 글이 2개 미만이면 비교할 게 없다."""
    if len(sets) < 2:
        return None
    return sorted(set.intersection(*(s for _, s in sets)))


def build_post(draw_no, stats, sets):
    last = draw_no - 1
    days = "·".join(DAY_KO[d] for d, _ in sets)
    lines = [f"{draw_no}회 번호 중간 점검", ASK.format(draw=draw_no), "",
             f"지난 {last}회: {g.fmt(stats['latest'])}"]
    ov = overlap(sets)
    if ov is not None:
        lines += ["", f"{days} 천재가 뽑은 15개 중 다 같이 고른 번호 {len(ov)}개"]
        lines.append(" · ".join(f"{n:02d}" for n in ov) if ov else "겹친 번호 없음")
    lines += ["", f"직전 회차 번호가 1개 이상 다시 나온 비율 {stats['carry_rate']}% (최근 {lotto_stats.CARRY_WINDOW}회)",
              "", FOOT]
    text = "\n".join(lines)
    if len(text) > LIMIT:
        raise AssertionError(f"중간 점검 글 {len(text)}자")
    return text


def due(now):
    local = now.astimezone(g.KST)
    return local.weekday() == WEEKDAY and (local.hour, local.minute) >= MID_TIME


def run_auto(now, dry=False):
    if not due(now):
        return 0
    draw_no = g.upcoming_draw_no(now)
    entry_id = f"picks-{draw_no}-mid"
    queue = lp.load(lp.QUEUE, [])
    if any(p["id"] == entry_id for p in queue):
        return 0
    sets = week_sets(queue, draw_no)
    draws = lotto_stats.fetch_all()
    if draw_no - 1 not in draws:
        print(f"{draw_no - 1}회 번호가 아직 미러에 없음", file=sys.stderr)
        return 0
    text = build_post(draw_no, lotto_stats.analyze(draws, draw_no - 1), sets)
    if dry:
        print(text)
        print(f"--- {len(text)}자")
        return 0
    try:
        post_id = publish.publish(text)
    except Exception as e:
        print(e, file=sys.stderr)
        publish.telegram(f"❌ {draw_no}회 중간 점검 글 발행 실패\n{e}")
        raise
    lp.record_in_queue(entry_id, text, post_id, draw_no, reply_mode="combo")
    publish.telegram(f"🔎 {draw_no}회 번호 중간 점검 글 발행됨")
    return 0


def posted_today(queue, now):
    """오늘(KST) 이 글이 나갔는가. 나갔으면 수요일 밤 슬롯은 비운다."""
    today = now.astimezone(g.KST).date()
    for p in queue:
        if p["id"].startswith("picks-") and p["id"].endswith("-mid") and p.get("published_at"):
            t = datetime.datetime.fromisoformat(p["published_at"]).astimezone(g.KST)
            if t.date() == today:
                return True
    return False


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    dry = "--dry" in sys.argv
    now = datetime.datetime.now(datetime.timezone.utc)
    if "--now" in sys.argv:
        now = datetime.datetime.fromisoformat(sys.argv[sys.argv.index("--now") + 1])
    sys.exit(run_auto(now, dry))
