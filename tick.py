"""5분마다 한 번 도는 단일 진입점. 무엇을 할지는 cron이 아니라 이 파일이 시각을 보고 정한다.

GitHub Actions의 schedule은 이 저장소에서 하루 2~7번만 떴다(9/25~9/30 실측, 예상 144번).
그래서 번호 글이 17:07 예정인데 23:16~01:43에 나갔고, 자동답글은 댓글의 15%만 답했다.
cron 횟수를 늘려도 같은 비율로 씹히므로, 워크플로 하나가 5시간 루프를 돌며 이걸 부른다.

각 단계는 원래 멱등이다(queue.json의 published_at, picks.json, 답글은 conversation 조회).
한 단계가 죽어도 나머지는 돌아야 하므로 단계마다 예외를 잡는다.
"""

import datetime
import json
import os
import pathlib
import sys

import auto_reply
import band_picks
import collect_insights
import gen_draw_post
import gen_posts
import lotto_picks
import publish
from publish import telegram

KST = datetime.timezone(datetime.timedelta(hours=9))
QUEUE = pathlib.Path(__file__).with_name("queue.json")
# publish.py의 슬롯(am/pm/night)이 실제로 나가야 하는 KST 시각. :07은 정각 혼잡 회피.
SLOTS = ((7, 7), (12, 7), (21, 7))


def due_slot_start(queue, now):
    """지금 발행해야 하면 그 슬롯의 시작 시각, 아니면 None.

    '그 슬롯이 시작된 뒤로 발행 기록이 없다'가 기준이다. 슬롯을 통째로 놓친 날은
    지난 슬롯을 소급해서 올리지 않고 가장 최근 슬롯 하나만 본다 — 밀린 걸 몰아서
    올리면 같은 포맷이 연달아 나간다.
    """
    local = now.astimezone(KST)
    passed = [s for s in SLOTS if (local.hour, local.minute) >= s]
    if not passed:
        return None
    h, m = passed[-1]
    start = local.replace(hour=h, minute=m, second=0, microsecond=0)
    for p in queue:
        # picks(17:07)·band(14:07) 글은 제 시각에 따로 나간다. 그게 슬롯 발행을 대신하면 안 된다.
        if p["id"].startswith(("picks-", "band-", "miss-")) or not p.get("published_at"):
            continue
        if datetime.datetime.fromisoformat(p["published_at"]) >= start:
            return None
    return start


def weekly_draw_due(queue, now):
    """토 23시~일 12시(KST) 사이에 그 주 1등 배출점 글이 아직 큐에 없으면 True.

    추첨 직후엔 동행복권 API가 비어 있어 한 번에 안 들어온다. 창 안에서 5분마다 다시
    묻되, 한 번 들어오면 여기서 걸러져 API를 더 부르지 않는다.
    """
    local = now.astimezone(KST)
    wd = local.weekday()
    if not ((wd == 5 and local.hour >= 23) or (wd == 6 and local.hour < 12)):
        return False
    return not any(p["id"] == f"draw-{gen_draw_post.latest_draw(local.date())}" for p in queue)


def instagram(now):
    """인스타 평일 2건. 카드를 먼저 만들고(없을 때만) 커밋된 카드로 발행한다.

    인스타는 이미지를 공개 URL로 받아가므로 이 틱에서 만든 카드는 다음 틱에서 올라간다
    (커밋·푸시는 워크플로가 매 틱 한다). cards.py가 PIL을 쓰므로 여기서 늦게 import한다 —
    인스타 쪽 의존성이 없는 러너에서 스레드 파이프라인까지 멈추면 안 된다.
    """
    try:
        import instagram_publish as ip
    except ImportError as e:
        # Pillow 없는 러너. 스레드는 멀쩡하니 조용히 넘어간다(5분마다 알림이 오면 안 된다).
        print(f"instagram 건너뜀: {e}", file=sys.stderr)
        return

    ip.TOKEN = os.environ["IG_TOKEN"]
    # IG_USER_ID는 없어도 된다. 없으면 토큰에서 직접 받아온다.
    ip.IG_USER_ID = os.environ.get("IG_USER_ID")
    ip.ensure_cards(now)
    ip.run_auto(now)


def step(name, fn):
    try:
        fn()
    except Exception as e:
        print(f"{name}: {e}", file=sys.stderr)
        telegram(f"⚠️ tick {name} 실패\n{e}")


def main():
    now = datetime.datetime.now(datetime.timezone.utc)
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))

    # 큐가 비었을 때 publish를 부르면 5분마다 "큐 비었음" 알림이 온다. 큐가 3개
    # 남았을 때 publish가 미리 경고하므로, 여기선 조용히 건너뛴다.
    if any(p.get("status") == "pending" for p in queue) and due_slot_start(queue, now):
        step("publish", publish.main)
    if weekly_draw_due(queue, now):
        step("draw", lambda: gen_draw_post.main([]))
    step("picks", lambda: lotto_picks.run_auto(now, dry=False))
    # 토 10:07 번호대 분석 + 매일 14:07 놓친 당첨금. 각각 하루 한 번, 그 뒤 4시간은 답글.
    step("band", lambda: band_picks.run_auto(now, dry=False))
    # 큐가 마르면 지난 회차 데이터로 pm/night 글을 찍어 채운다. 손으로 쓴 글이 남아 있으면
    # 아무것도 하지 않는다.
    step("topup", lambda: gen_posts.top_up(now))
    # 아침 지역 글은 손으로 쓴 것이 전부라 다 나가면 맨 앞부터 다시 돌린다.
    step("recycle", gen_posts.recycle)
    # 인스타. 토큰이 없으면 아무 말 없이 건너뛴다 — 스레드만 돌려도 되게.
    if os.environ.get("IG_TOKEN"):
        step("instagram", lambda: instagram(now))
    step("reply", auto_reply.main)
    step("insights", collect_insights.main)
    return 0


if __name__ == "__main__":
    token = os.environ.get("THREADS_TOKEN")
    if not token:
        print("THREADS_TOKEN 미설정 — 아무것도 하지 않음", file=sys.stderr)
        sys.exit(0)
    # 세 모듈 모두 토큰을 __main__에서만 넣는다. import해서 쓸 때는 직접 넣어야 한다.
    publish.TOKEN = token
    collect_insights.TOKEN = token
    sys.exit(main())
