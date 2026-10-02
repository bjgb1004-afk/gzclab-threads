"""인스타그램에 카드 한 장을 올린다. 표준 라이브러리만 쓴다.

Threads와 같은 2단계다(컨테이너 만들고 → 발행). 다른 점 두 가지:

- 이미지는 **공개 URL**로만 받는다. 파일 업로드가 없다. 그래서 cards.py가 구운 JPEG을
  이 repo에 커밋하고 GitHub Pages 주소를 넘긴다. PNG는 거부되므로 JPEG만 쓴다.
- 캡션에 링크를 걸어도 **클릭이 안 된다**. 그래서 유입은 프로필 바이오 링크 하나로만
  들어오고, 글별 기여는 셀 수 없다. 캡션에 URL을 적지 않고 "프로필 링크"라고만 쓴다.

토큰: `Instagram 비즈니스 로그인` 경로로 받은 60일 장기 토큰(IG_TOKEN).
계정 ID: 같은 화면에 뜨는 숫자(IG_USER_ID).
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://graph.instagram.com/v23.0"
CAPTION_LIMIT = 2200
TOKEN = os.environ.get("IG_TOKEN", "")
USER_ID = os.environ.get("IG_USER_ID", "")

# 매번 같은 꼬리를 달면 봇 티가 나지만, 바이오 링크 안내는 빠지면 유입이 0이 된다.
# 링크 자체는 캡션에서 클릭이 안 되므로 주소를 적지 않는다.
LINK_LINE = "앱은 프로필 링크에 있음"
TAGS = "#로또 #로또번호 #복권 #로또명당 #복권명당"


def api(path, params, method="POST"):
    body = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(f"{API}/{path}", data=body, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        # 본문은 한 번만 읽힌다. 여기서 읽어두지 않으면 로그에 사유가 안 남는다.
        raise RuntimeError(f"{path} {e.code}: {e.read().decode(errors='replace')[:400]}") from None


def me():
    """토큰이 살아 있고 어떤 계정에 붙었는지. 설정 확인용."""
    q = urllib.parse.urlencode({"fields": "id,username,account_type", "access_token": TOKEN})
    with urllib.request.urlopen(f"{API}/me?{q}", timeout=60) as r:
        return json.load(r)


def caption(lines):
    """캡션 본문. 한도를 넘으면 글이 잘린 채 올라가므로 여기서 막는다."""
    text = "\n\n".join([*lines, LINK_LINE, TAGS])
    if len(text) > CAPTION_LIMIT:
        raise RuntimeError(f"캡션 {len(text)}자 — 한도 {CAPTION_LIMIT} 초과")
    return text


def publish_image(image_url, text, user_id=None, token=None):
    """JPEG 공개 URL 한 장을 올린다. 반환: 게시물 id."""
    uid, tok = user_id or USER_ID, token or TOKEN
    if not uid or not tok:
        raise RuntimeError("IG_USER_ID / IG_TOKEN 이 비어 있다")
    container = api(f"{uid}/media", {"image_url": image_url, "caption": text, "access_token": tok})["id"]
    # Threads에서 컨테이너가 발행 엔드포인트에 퍼지기 전에 쏘면 죽는 걸 겪었다(4279009).
    # 인스타도 이미지를 내려받아 처리하는 시간이 있어 같은 모양으로 기다렸다 재시도한다.
    last = None
    for wait in (5, 20, 40):
        time.sleep(wait)
        try:
            return api(f"{uid}/media_publish", {"creation_id": container, "access_token": tok})["id"]
        except RuntimeError as e:
            last = e
    raise last


def main(argv=()):
    """확인: python instagram.py --check
    테스트 발행: python instagram.py --image <공개 JPEG URL> [--caption <한 줄>]
    """
    if "--check" in argv or not argv:
        print(json.dumps(me(), ensure_ascii=False))
        return 0
    url = argv[argv.index("--image") + 1]
    line = argv[argv.index("--caption") + 1] if "--caption" in argv else "테스트"
    print(publish_image(url, caption([line])))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
