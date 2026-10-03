"""Self-check: run `python test_instagram.py`. No network, no framework."""

import datetime
import json
import pathlib

import cards
import instagram_publish as ip

KST = datetime.timezone(datetime.timedelta(hours=9))

# ---------- 2단계 발행: 컨테이너 → 발행 ----------
calls = []


def fake_api(path, params):
    calls.append((path, params))
    return {"id": "container-1" if path.endswith("/media") else "post-1"}


ip.api = fake_api
ip.time.sleep = lambda s: None
ip.IG_USER_ID = "123"
ip.TOKEN = "t"

assert ip.publish_image("https://x/y.jpg", "본문") == "post-1"
assert calls[0][0] == "123/media" and calls[0][1]["image_url"] == "https://x/y.jpg"
assert calls[1][0] == "123/media_publish" and calls[1][1]["creation_id"] == "container-1"

# 한도를 넘은 캡션은 잘린 채 올라가므로 쏘기 전에 죽어야 한다
try:
    ip.publish_image("https://x/y.jpg", "가" * 2300)
    raise AssertionError("한도를 넘겼는데 통과했다")
except RuntimeError as e:
    assert "한도" in str(e)

# ---------- 파일명은 cards.py 한 곳에서만 정한다 ----------
mon = datetime.date(2026, 10, 5)   # 월요일
for kind in ip.SLOTS:
    name, cap = ip.build(kind, mon)
    assert name == cards.card_name(kind, mon), (kind, name)
    assert f"{ip.CARD_BASE}/{name}.jpg".startswith("https://raw.githubusercontent.com/")
    assert len(cap) <= ip.CAPTION_LIMIT, (kind, len(cap))
    assert ip.APP_LINK in cap, kind
    # 글에 쓰면 안 되는 표현은 캡션에도 쓰면 안 된다(스토어 심사 기준과 같은 선)
    for banned in ("예측", "적중률", "확률 높"):
        assert banned not in cap, (kind, banned)

# ---------- 같은 건을 두 번 올리지 않는다 ----------
noon = datetime.datetime(2026, 10, 5, 12, 30, tzinfo=KST)
assert [k for k, _, _ in ip.due(noon)] == ["genius"]
evening = datetime.datetime(2026, 10, 5, 21, 0, tzinfo=KST)
assert sorted(k for k, _, _ in ip.due(evening)) == ["genius", "replay"]
# 주말은 쉰다
assert ip.due(datetime.datetime(2026, 10, 4, 21, 0, tzinfo=KST)) == []
assert ip.ensure_cards(datetime.datetime(2026, 10, 4, 21, 0, tzinfo=KST)) == []

# ---------- 실패해도 5분마다 알림이 오지 않는다 ----------
sent, tmp = [], pathlib.Path("_test_instagram_state.json")
ip.STATE = tmp
ip.telegram = lambda m: sent.append(m)
ip.image_reachable = lambda url: False      # 카드가 아직 안 올라간 상태
try:
    for _ in range(8):
        ip.run_auto(datetime.datetime(2026, 10, 5, 12, 30, tzinfo=KST))
    assert len(sent) == 1, sent          # 셋째 실패에서 한 번만
    assert json.loads(tmp.read_text(encoding="utf-8"))["fails"]["genius-2026-10-05"] == ip.MAX_TRIES
finally:
    tmp.unlink(missing_ok=True)

print("ok")
