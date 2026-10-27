"""인스타그램 자동 발행. 평일 하루 2건 — 천재들의 한수(점심), 놓친 당첨금(저녁).

Threads(publish.py)와 구조가 같다. 컨테이너를 만들고 → 발행하는 2단계다. 표준 라이브러리만 쓴다.

**이미지는 공개 URL이어야 한다.** 인스타 서버가 그 주소로 직접 받아간다. 그래서 카드를
저장소에 커밋하고 raw.githubusercontent 주소를 넘긴다. tick이 `ensure_cards`로 그날 카드를
만들어 커밋하고, 푸시가 끝난 다음 틱(5분 뒤)에 발행된다. 손으로 할 일은 없다.

발행 전에 그 주소가 실제로 열리는지 확인한다(HEAD). 안 열리면 올리지 않고 알림만 보낸다.
깨진 이미지로 컨테이너를 만들면 그 컨테이너가 계정에 남는다.

한도: 24시간 100건. 하루 2건이면 2%다.
"""

import datetime
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import band_gen as bg
import cards
import lotto_gen as g
import replay as rp
from publish import telegram

HERE = pathlib.Path(__file__).parent
STATE = HERE / "instagram.json"       # 발행 기록. 같은 건을 두 번 올리지 않기 위한 것
API = "https://graph.instagram.com/v23.0"

# 카드 주소. Pages가 아니라 raw를 쓴다 — 저장소 설정에서 켤 것이 없고, 배포 대기 없이
# 푸시된 직후부터 image/jpeg로 받힌다(2026-10-03 확인).
CARD_BASE = "https://raw.githubusercontent.com/bjgb1004-afk/gzclab-threads/main/cards"

APP_LINK = "https://gzclab.com/lottomap/?c=ig"

# KST 발행 시각. Threads 작업(07:07 / 12:07 / 17:07 / 21:07)과 분 단위로 겹치지 않게 둔다.
SLOTS = {
    "genius": (12, 17),
    "band": (12, 17),
    "replay": (20, 17),
}


def kinds_for(day):
    """그날 올릴 두 가지. 점심은 평일 천재 / 주말 번호대, 저녁은 매일 놓친 당첨금.

    천재는 월~금 다섯 명뿐이라 주말에 쓸 것이 없다. 스레드도 토요일 번호 자리가
    번호대 분석이라 두 채널이 같은 요일에 같은 소재를 낸다.
    """
    return ("genius" if day.weekday() < 5 else "band", "replay")

TOKEN = None
IG_USER_ID = None


# ---------- API ----------

def api(path, params):
    body = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(f"{API}/{path}", data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        # publish.py와 같은 이유로 본문을 여기서 읽는다. 안 그러면 로그에 코드만 남는다.
        raise RuntimeError(f"{path} {e.code}: {e.read().decode(errors='replace')[:400]}") from None


def image_reachable(url):
    """인스타 서버가 받아갈 수 있는 주소인지 먼저 확인한다."""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "gzclab-threads"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status == 200
    except Exception:
        return False


CAPTION_LIMIT = 2200   # 넘기면 글이 잘린 채 올라간다


def user_id():
    """미디어 엔드포인트에 쓸 계정 id. IG_USER_ID가 없으면 토큰에서 직접 받아온다.

    앱 대시보드가 보여주는 "Instagram 앱 ID"는 이 값이 아니다(그걸 넣으면 전부 실패한다).
    /me가 주는 user_id가 인스타 프로 계정 id이고, 같은 응답의 id(앱 스코프)도 발행에는
    통한다 — 2026-10-03에 content_publishing_limit로 둘 다 확인했다. 문서가 어느 쪽이라고
    못 박지 않아서, 사람이 고르게 두지 않고 여기서 정한다.
    """
    global IG_USER_ID
    if not IG_USER_ID:
        info = me()
        IG_USER_ID = str(info.get("user_id") or info["id"])
    return IG_USER_ID


def publish_image(image_url, caption):
    """컨테이너 생성 → 발행. 발행된 미디어 id."""
    if len(caption) > CAPTION_LIMIT:
        raise RuntimeError(f"캡션 {len(caption)}자 — 한도 {CAPTION_LIMIT} 초과")
    uid = user_id()
    container = api(f"{uid}/media", {
        "image_url": image_url,
        "caption": caption,
        "access_token": TOKEN,
    })["id"]
    # Threads와 같은 전파 지연이 있다. 사진은 보통 바로 되지만 한 번 실패하면 글이 통째로 빠지므로
    # 기다렸다 재시도한다.
    last = None
    for wait in (3, 10, 30):
        time.sleep(wait)
        try:
            return api(f"{uid}/media_publish", {
                "creation_id": container,
                "access_token": TOKEN,
            })["id"]
        except RuntimeError as e:
            last = e
    raise last


def publish_carousel(image_urls, caption):
    """여러 장을 한 글로. 자식 컨테이너 → 부모(CAROUSEL) → 발행.

    왜 캐러셀로 바꿨나 (2026-10-27): 단일 이미지는 넘기면 끝이지만 여러 장이면 넘기는
    동작 자체가 체류 시간이 되고, 도달 1명당 참여가 더 높다. 1장이 표지이자 섬네일이다.

    자식에는 caption을 넣지 않는다 — 부모에만 붙는다. 자식에 넣으면 조용히 무시된다.
    """
    if not 2 <= len(image_urls) <= 10:
        raise RuntimeError(f"캐러셀은 2~10장이어야 한다 — {len(image_urls)}장")
    if len(caption) > CAPTION_LIMIT:
        raise RuntimeError(f"캡션 {len(caption)}자 — 한도 {CAPTION_LIMIT} 초과")
    uid = user_id()

    children = []
    for url in image_urls:
        children.append(api(f"{uid}/media", {
            "image_url": url,
            "is_carousel_item": "true",
            "access_token": TOKEN,
        })["id"])

    parent = api(f"{uid}/media", {
        "media_type": "CAROUSEL",
        "children": ",".join(children),
        "caption": caption,
        "access_token": TOKEN,
    })["id"]

    # 자식이 여럿이라 단일 사진보다 준비가 늦다. 단일보다 길게 기다린다.
    last = None
    for wait in (5, 15, 30, 60):
        time.sleep(wait)
        try:
            return api(f"{uid}/media_publish", {
                "creation_id": parent,
                "access_token": TOKEN,
            })["id"]
        except RuntimeError as e:
            last = e
    raise last


# 릴스 영상 주소. 사진과 달리 raw.githubusercontent는 .mp4를 application/octet-stream으로
# 돌려준다(2026-10-27 확인). 인스타 영상 수집이 이를 거부할 수 있어 주소 기준을 밖에서
# 바꿀 수 있게 둔다 — 다른 호스팅으로 옮길 때 코드를 고치지 않는다.
REEL_BASE = os.environ.get("REEL_BASE_URL", f"{CARD_BASE.rsplit('/', 1)[0]}/reels")
REEL_POLL = (10, 15, 20, 30, 30, 45, 60)  # 영상은 서버가 변환을 끝내야 발행된다


def container_status(container_id):
    """영상 컨테이너의 준비 상태. FINISHED가 되어야 발행할 수 있다."""
    qs = urllib.parse.urlencode({"fields": "status_code,status", "access_token": TOKEN})
    with urllib.request.urlopen(f"{API}/{container_id}?{qs}", timeout=30) as r:
        d = json.load(r)
    return d.get("status_code"), d.get("status")


def publish_reel(video_url, caption, cover_url=None):
    """릴스 발행. 사진과 달리 변환이 끝날 때까지 기다려야 한다.

    바로 media_publish를 때리면 아직 IN_PROGRESS라 실패한다. 상태를 물어보며 기다리고,
    ERROR면 인스타가 준 사유를 그대로 올린다 — "실패"만 남으면 원인을 못 찾는다.
    """
    if len(caption) > CAPTION_LIMIT:
        raise RuntimeError(f"캡션 {len(caption)}자 — 한도 {CAPTION_LIMIT} 초과")
    uid = user_id()
    params = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "access_token": TOKEN,
    }
    if cover_url:
        params["cover_url"] = cover_url
    container = api(f"{uid}/media", params)["id"]

    for wait in REEL_POLL:
        time.sleep(wait)
        code, detail = container_status(container)
        if code == "FINISHED":
            break
        if code == "ERROR":
            raise RuntimeError(f"인스타가 영상을 거부했습니다: {detail}")
    else:
        raise RuntimeError(f"영상 변환이 끝나지 않았습니다(마지막 상태 {code})")

    return api(f"{uid}/media_publish", {"creation_id": container, "access_token": TOKEN})["id"]


# ---------- 캡션 ----------
# 구조 기준 (2026-10-27 조사). 인스타는 스레드와 읽는 방식이 다르다:
#
#  1) 첫 줄이 전부다. 피드에서는 캡션이 한두 줄만 보이고 나머지는 "...더 보기"로 접힌다.
#     예전 첫 줄은 "1245회 · 아르키메데스"였다 — 회차와 이름은 훅이 아니다. 각 소재가
#     가진 제일 이상한 사실을 첫 줄에 올린다("원주율 π를 이어 읽어 뽑은 5게임").
#  2) 공유(sends)를 유도한다. 인스타가 비팔로워에게 밀어줄지 정할 때 쓰는 신호 중
#     전송이 가장 세다고 알려져 있다(Mosseri). 예전 캡션에는 공유를 청하는 줄이 아예
#     없었다.
#  3) 해시태그는 도달에 도움이 안 되고 5개까지만 인식된다(Mosseri). 검색으로 발견되는
#     용도만 남겨 소재별로 구체적인 것 4개씩 쓴다. 예전엔 #로또 #복권 같은 일반 태그
#     6개를 모든 글에 똑같이 붙였다.
#
# 고지 문구는 그대로 둔다. 위치만 아래로 내린다 — 실제 돈이 걸린 주제라 빼지 않는다.

DISCLAIMER = ("당첨 확률을 높이거나 당첨을 보장하지 않습니다. "
              "모든 번호 조합의 당첨 확률은 같습니다.")

# 소재별 해시태그. 5개 넘게 쓰면 뒤는 무시된다.
TAGS = {
    "genius": "#로또번호추천 #수학으로뽑은번호 #로또분석 #복권명당",
    "replay": "#놓친당첨금 #로또당첨확인 #내번호확인 #복권명당",
    "band": "#로또번호대분석 #로또통계 #로또번호추천 #복권명당",
}
assert all(len(v.split()) <= 5 for v in TAGS.values()), "해시태그는 5개까지만 인식된다"


def _tail(kind, share):
    """공유 유도 → 앱 → 고지 → 해시태그. 순서를 바꾸지 말 것."""
    return f"{share}\n\n앱: {APP_LINK}\n\n{DISCLAIMER}\n\n{TAGS[kind]}"


def genius_caption(draw_no, genius_id):
    gi = g.GENIUS_BY_ID[genius_id]
    games = g.genius_games(genius_id, draw_no)
    rows = "\n".join(f"{'ABCDE'[i]}  {g.fmt(x)}" for i, x in enumerate(games))
    return (
        f"{gi['how']}\n"                      # 훅 — 접히기 전에 보이는 한 줄
        f"{draw_no}회 {gi['name']} 번호입니다.\n\n"
        f"{rows}\n\n"
        "회차랑 천재가 정해지면 번호도 하나로 고정됩니다. "
        "복권명당 앱에서 뽑아도 글자 하나 안 다릅니다.\n\n"
        + _tail("genius", "로또 사는 사람한테 보내주세요. 다음 회차는 다른 천재 차례입니다.")
    )


def replay_caption(nums, res):
    """'놓친 당첨금'은 결과 자체가 훅이다. 번호보다 결과를 먼저 쓴다."""
    if res["hits"]:
        order = sorted(res["by_rank"])
        detail = " · ".join(f"{r}등 {res['by_rank'][r]}번" for r in order)
        hook = f"이 번호, 지난 {res['draws']}회를 돌려보니 {res['hits']}번 당첨돼 있었습니다."
        body = f"{res['from']}회부터 {res['to']}회까지 ({detail})\n다 합치면 {rp.won(res['gross'])}."
    else:
        hook = f"이 번호는 {res['draws']}회 동안 한 번도 등수에 못 들었습니다."
        body = "이렇게 한 번도 안 걸리는 번호도 드뭅니다."
    return (
        f"{hook}\n"                           # 훅
        f"오늘의 번호 {bg.fmt(nums)}\n\n"
        f"{body}\n\n"
        "사지 않았으면 받을 수 없는 돈이고, 지나간 회차 성적이라 다음 회차와는 상관없습니다.\n"
        "내 번호로 직접 돌려보는 건 복권명당 앱 '놓친 당첨금'에서 됩니다.\n\n"
        + _tail("replay", "자기 번호 궁금해할 사람한테 보내주세요.")
    )


def band_caption(date_key, games, res):
    rows = "\n".join(
        f"{'ABCDE'[i]}  {bg.fmt(x['numbers'])}  ({x['band_pattern']} · 저고 {x['low_high']})"
        for i, x in enumerate(games)
    )
    return (
        "다섯 구간 중 한 곳은 일부러 비우고 뽑은 5게임입니다.\n"   # 훅
        f"{date_key} 번호대 분석\n\n"
        f"{rows}\n\n"
        "1~9 / 10번대 / 20번대 / 30번대 / 40~45 중 한 구간은 비우고, 한 구간에 세 개까지만. "
        "저(1~22)와 고(23~45)는 2:4 · 3:3 · 4:2 중 하나로 맞췄습니다.\n"
        f"A 번호는 {res['from']}~{res['to']}회에서 {res['hits']}번 당첨돼 있었습니다.\n\n"
        + _tail("band", "번호 고를 때 참고하는 사람한테 보내주세요.")
    )


# ---------- 발행 ----------

def load_state():
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"published": {}}


def save_state(state):
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def due(now):
    """지금까지 시각이 지난 (종류, 키, 날짜) 목록.

    지난 슬롯을 전부 돌려주는 건 일부러다 — 점심 건이 실패해도 저녁 틱에서 다시 시도된다.
    이미 올린 건은 state로 걸러지므로 두 번 나가지 않는다.
    """
    local = now.astimezone(cards.KST)
    day = local.date()
    return [(kind, f"{kind}-{day.isoformat()}", day)
            for kind in kinds_for(day) if (local.hour, local.minute) >= SLOTS[kind]]


# tick이 5분마다 부른다. 실패할 때마다 알리면 하루 100통이 온다 — 셋째 실패에서 한 번만
# 알리고 네 번째에 그날은 포기한다. 카드를 막 만든 직후엔 아직 푸시 전이라 한두 번
# 실패하는 게 정상이므로 첫 실패는 알리지 않는다.
MAX_TRIES = 4


def bump(state, key, note):
    """실패를 세고, 알릴 차례면 한 번만 알린다."""
    fails = state.setdefault("fails", {})
    fails[key] = n = fails.get(key, 0) + 1
    save_state(state)
    if n == 3:
        telegram(f"인스타 {key} 실패 — {note} / {MAX_TRIES - n}번 더 해보고 오늘은 포기합니다.")


def run_auto(now, dry=False):
    state = load_state()
    for kind, key, day in due(now):
        if key in state["published"] or state.get("fails", {}).get(key, 0) >= MAX_TRIES:
            continue
        name, caption = build(kind, day)
        # 표지 → 알맹이 → 안내 3장. 1장이 섬네일이라 순서를 바꾸지 말 것.
        urls = [f"{CARD_BASE}/{name}-hook.jpg",
                f"{CARD_BASE}/{name}.jpg",
                f"{CARD_BASE}/{name}-cta.jpg"]

        if dry:
            print(f"[{key}] {len(urls)}장\n" + "\n".join(urls) + f"\n{caption}\n{'-' * 50}")
            continue
        missing = [u for u in urls if not image_reachable(u)]
        if missing:
            # 카드를 방금 만들었으면 아직 커밋·푸시 전이다. 다음 틱에 다시 온다.
            bump(state, key, "카드 주소가 안 열림\n" + "\n".join(missing))
            continue
        try:
            media_id = publish_carousel(urls, caption)
        except Exception as e:
            print(e, file=sys.stderr)
            bump(state, key, f"발행 실패\n{e}")
            continue
        state["published"][key] = {
            "media_id": media_id,
            "url": urls[1],
            "slides": len(urls),
            "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        }
        state.get("fails", {}).pop(key, None)
        save_state(state)
        telegram(f"✅ 인스타 발행됨 ({key})\nhttps://www.instagram.com/gzclab/")
    return 0


def build(kind, day):
    """(이미지 파일명, 캡션). 파일명은 cards.card_name 한 곳에서만 정한다."""
    name = cards.card_name(kind, day)
    if kind == "genius":
        draw_no = g.upcoming_draw_no(datetime.datetime.combine(day, datetime.time(12), cards.KST))
        return name, genius_caption(draw_no, g.GENIUSES[day.weekday()]["id"])
    draws = rp.fetch_draws()
    if kind == "replay":
        nums = cards.daily_random(day)
        return name, replay_caption(nums, rp.replay(nums, draws))
    if kind == "band":
        key = day.isoformat()
        games = bg.generate_daily_band_games(key)
        return name, band_caption(key, games, rp.replay(games[0]["numbers"], draws))
    raise ValueError(kind)


def ensure_cards(now):
    """그날 올릴 카드가 저장소에 없으면 만든다. tick이 발행보다 먼저 부른다.

    인스타는 공개 URL로 이미지를 받아가므로 커밋·푸시된 뒤에야 올릴 수 있다. 그래서
    이 틱에서 만들어지고 다음 틱에서 발행된다. 이미 있으면 아무것도 하지 않는다.
    """
    day = now.astimezone(cards.KST).date()
    made = []
    for kind in kinds_for(day):
        made += cards.build_slides(kind, day)
    # 발행이 끝난 카드는 인스타가 자기 쪽에 복사해 두므로 저장소에 남길 필요가 없다.
    # 안 지우면 하루 300KB씩 쌓여 체크아웃만 느려진다. 손으로 넣은 파일은 건드리지 않는다.
    keep = {p.name for p in made}
    for old_card in cards.OUT.glob("*.jpg"):
        if old_card.name.startswith(("genius-", "replay-", "band-")) and old_card.name not in keep:
            old_card.unlink()
    return made


def me():
    """토큰이 살아 있고 어떤 계정에 붙었는지. `python instagram_publish.py --check`"""
    q = urllib.parse.urlencode({"fields": "user_id,username,account_type", "access_token": TOKEN})
    with urllib.request.urlopen(f"{API}/me?{q}", timeout=60) as r:
        return json.load(r)


def main(argv=()):
    if "--check" in argv:
        print(json.dumps(me(), ensure_ascii=False))
        return 0
    if "--cards" in argv:
        for p in ensure_cards(datetime.datetime.now(datetime.timezone.utc)):
            print(p.name)
        return 0
    dry = "--dry" in argv
    now = datetime.datetime.now(datetime.timezone.utc)
    if "--now" in argv:
        now = datetime.datetime.fromisoformat(argv[argv.index("--now") + 1])
    return run_auto(now, dry=dry)


if __name__ == "__main__":
    TOKEN = os.environ.get("IG_TOKEN")
    IG_USER_ID = os.environ.get("IG_USER_ID")
    if not (TOKEN and IG_USER_ID):
        print("IG_TOKEN / IG_USER_ID 미설정 — 아무것도 하지 않음", file=sys.stderr)
        sys.exit(0)
    sys.exit(main(sys.argv[1:]))
