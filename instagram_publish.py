"""인스타그램 자동 발행. 평일 하루 2건 — 천재들의 한수(점심), 놓친 당첨금(저녁). 릴스(영상)로 올린다.

Threads(publish.py)와 구조가 같다. 컨테이너를 만들고 → 발행하는 2단계다. 표준 라이브러리만 쓴다.

**영상도 공개 URL이어야 한다.** 인스타 서버가 그 주소로 직접 받아간다. 영상은 git에
커밋하지 않으므로(.gitignore의 reels/) GitHub Release 애셋으로 올려 그 주소를 넘긴다.
업로드는 API 호출 한 번으로 바로 공개되므로 사진 때처럼 틱을 하나 더 기다릴 필요가
없다 — 만들기·올리기·발행을 한 틱 안에서 끝낸다. 발행이 끝나면(성공·실패 모두) 그
애셋은 지운다.

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
import reel
import replay as rp
from publish import telegram

HERE = pathlib.Path(__file__).parent
STATE = HERE / "instagram.json"       # 발행 기록. 같은 건을 두 번 올리지 않기 위한 것
API = "https://graph.instagram.com/v23.0"
GITHUB_API = "https://api.github.com"
GH_REPO = os.environ.get("GITHUB_REPOSITORY", "bjgb1004-afk/gzclab-threads")
REEL_RELEASE_TAG = "reel-host"

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
GH_TOKEN = None


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


# ---------- 영상 호스팅 (GitHub Release 애셋) ----------
# 사진은 저장소에 커밋해 raw.githubusercontent로 받혔지만, 영상은 커밋하지 않기로
# 했다(.gitignore의 reels/·assets/footage/ 참고 — 쌓이면 히스토리가 영원히 커진다).
# 대신 release 애셋으로 올린다. 업로드가 API 호출 한 번으로 바로 공개 URL이 되므로
# 사진처럼 "이 틱에서 만들고 다음 틱에서 발행"할 필요가 없다 — 발행까지 한 틱에 끝낸다.
# 토큰은 새 시크릿을 안 만들고 Actions가 자동으로 주는 GITHUB_TOKEN을 쓴다
# (워크플로 permissions: contents: write가 release 생성·업로드 권한을 포함한다).

def gh_api(method, path, data=None, raw=False, content_type="application/json"):
    headers = {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    body = None
    if raw:
        body = data
        headers["Content-Type"] = content_type
    elif data is not None:
        body = json.dumps(data).encode()
    req = urllib.request.Request(f"{path}" if path.startswith("http") else f"{GITHUB_API}/{path}",
                                  data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            out = r.read()
            return json.loads(out) if out else None
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path} {e.code}: {e.read().decode(errors='replace')[:400]}") from None


def ensure_release():
    """릴스 영상을 올릴 release id. 없으면 만든다(최초 1회뿐, 이후는 재사용)."""
    try:
        return gh_api("GET", f"repos/{GH_REPO}/releases/tags/{REEL_RELEASE_TAG}")["id"]
    except RuntimeError as e:
        if "404" not in str(e):
            raise
    created = gh_api("POST", f"repos/{GH_REPO}/releases", {
        "tag_name": REEL_RELEASE_TAG,
        "name": "릴스 영상 호스팅 (자동)",
        "body": "인스타 릴스 업로드용 임시 저장소. 발행되면 그 애셋은 바로 지워진다.",
        "prerelease": True,
    })
    return created["id"]


def upload_reel_asset(release_id, path):
    """영상을 release 애셋으로 올리고 {id, url}을 돌려준다.

    같은 이름 애셋이 이미 있으면 먼저 지운다 — GitHub가 중복 이름을 거부한다.
    """
    name = path.name
    for a in gh_api("GET", f"repos/{GH_REPO}/releases/{release_id}/assets") or []:
        if a["name"] == name:
            gh_api("DELETE", f"repos/{GH_REPO}/releases/assets/{a['id']}")
            break
    uploaded = gh_api(
        "POST",
        f"https://uploads.github.com/repos/{GH_REPO}/releases/{release_id}/assets"
        f"?name={urllib.parse.quote(name)}",
        data=path.read_bytes(), raw=True, content_type="video/mp4",
    )
    return {"id": uploaded["id"], "url": uploaded["browser_download_url"]}


def delete_reel_asset(asset_id):
    gh_api("DELETE", f"repos/{GH_REPO}/releases/assets/{asset_id}")


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


def replay_caption(w):
    """1등 번호 되짚어보기. 그 회차 금액과 나머지 회차 성적을 반드시 따로 쓴다."""
    res = w["res"]
    ranks = " · ".join(f"{r}등 {res['by_rank'][r]}번" for r in sorted(res["by_rank"]))
    body = f"나머지 {res['draws']}회에서는 {ranks}.\n다 합쳐 {rp.won(res['gross'])}." if ranks \
        else f"나머지 {res['draws']}회에서는 한 번도 안 걸렸습니다."
    return (
        f"{w['draw_no']}회 1등 번호. 그 회차에 {w['own_prize'] / 100000000:.1f}억원 나왔습니다.\n"   # 훅
        f"{bg.fmt(w['numbers'])}\n\n"
        f"이 회차를 빼고 나머지 {res['draws']}회에 돌려보면?\n"
        f"{body}\n\n"
        "1등 번호라고 특별한 게 아닙니다. 그 회차를 빼면 아무 번호랑 성적이 같습니다.\n"
        "내 번호로 직접 돌려보는 건 복권명당 앱 '놓친 당첨금'에서 됩니다.\n\n"
        + _tail("replay", "1등 번호가 특별하다고 믿는 사람한테 보내주세요.")
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
        draws = rp.fetch_draws() if kind in ("replay", "band") else None
        _, caption = build(kind, day, draws)

        if dry:
            print(f"[{key}] {caption}\n{'-' * 50}")
            continue
        try:
            video_path = reel.build_for(kind, day, draws=draws)
            release_id = ensure_release()
            asset = upload_reel_asset(release_id, video_path)
            try:
                media_id = publish_reel(asset["url"], caption)
            finally:
                # 발행 성공·실패와 무관하게 임시 애셋은 지운다 — 쌓아둘 이유가 없다.
                delete_reel_asset(asset["id"])
        except Exception as e:
            print(e, file=sys.stderr)
            bump(state, key, f"발행 실패\n{e}")
            continue
        state["published"][key] = {
            "media_id": media_id,
            "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        }
        state.get("fails", {}).pop(key, None)
        save_state(state)
        telegram(f"✅ 인스타 발행됨 ({key})\nhttps://www.instagram.com/gzclab/")
    return 0


def build(kind, day, draws=None):
    """(카드 파일명, 캡션). 파일명은 cards.card_name 한 곳에서만 정한다 — 릴스 영상 이름은 reel.reel_name이 따로 정한다."""
    name = cards.card_name(kind, day)
    if kind == "genius":
        draw_no = g.upcoming_draw_no(datetime.datetime.combine(day, datetime.time(12), cards.KST))
        return name, genius_caption(draw_no, g.GENIUSES[day.weekday()]["id"])
    draws = draws if draws is not None else rp.fetch_draws()
    if kind == "replay":
        return name, replay_caption(rp.winner_replay(day.isoformat(), draws))
    if kind == "band":
        key = day.isoformat()
        games = bg.generate_daily_band_games(key)
        return name, band_caption(key, games, rp.replay(games[0]["numbers"], draws))
    raise ValueError(kind)


def me():
    """토큰이 살아 있고 어떤 계정에 붙었는지. `python instagram_publish.py --check`"""
    q = urllib.parse.urlencode({"fields": "user_id,username,account_type", "access_token": TOKEN})
    with urllib.request.urlopen(f"{API}/me?{q}", timeout=60) as r:
        return json.load(r)


def main(argv=()):
    if "--check" in argv:
        print(json.dumps(me(), ensure_ascii=False))
        return 0
    dry = "--dry" in argv
    now = datetime.datetime.now(datetime.timezone.utc)
    if "--now" in argv:
        now = datetime.datetime.fromisoformat(argv[argv.index("--now") + 1])
    return run_auto(now, dry=dry)


if __name__ == "__main__":
    TOKEN = os.environ.get("IG_TOKEN")
    IG_USER_ID = os.environ.get("IG_USER_ID")
    GH_TOKEN = os.environ.get("GITHUB_TOKEN")
    if not (TOKEN and IG_USER_ID):
        print("IG_TOKEN / IG_USER_ID 미설정 — 아무것도 하지 않음", file=sys.stderr)
        sys.exit(0)
    sys.exit(main(sys.argv[1:]))
