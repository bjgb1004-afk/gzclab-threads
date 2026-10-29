"""Self-check: run `python test_instagram.py`. No network, no framework."""

import datetime
import json
import pathlib

import instagram_publish as ip

KST = datetime.timezone(datetime.timedelta(hours=9))
REPO_PREFIX = f"repos/{ip.GH_REPO}"

# ---------- 릴스 발행: 컨테이너 생성 → 변환 대기 → 발행 ----------
calls = []


def fake_api(path, params):
    calls.append((path, params))
    return {"id": "container-1" if path.endswith("/media") else "post-1"}


ip.api = fake_api
ip.container_status = lambda cid: ("FINISHED", "ok")
ip.time.sleep = lambda s: None
ip.IG_USER_ID = "123"
ip.TOKEN = "t"

assert ip.publish_reel("https://x/y.mp4", "본문") == "post-1"
assert calls[0][0] == "123/media" and calls[0][1]["video_url"] == "https://x/y.mp4"
assert calls[1][0] == "123/media_publish" and calls[1][1]["creation_id"] == "container-1"

# 한도를 넘은 캡션은 잘린 채 올라가므로 쏘기 전에 죽어야 한다
try:
    ip.publish_reel("https://x/y.mp4", "가" * 2300)
    raise AssertionError("한도를 넘겼는데 통과했다")
except RuntimeError as e:
    assert "한도" in str(e)

# ---------- 릴스 호스팅: GitHub Release 애셋 ----------
gh_calls, has_release, assets = [], {"v": False}, {"v": []}


def fake_gh(method, path, data=None, raw=False, content_type="application/json"):
    gh_calls.append((method, path))
    if method == "GET" and path == f"{REPO_PREFIX}/releases/tags/{ip.REEL_RELEASE_TAG}":
        if has_release["v"]:
            return {"id": 99}
        raise RuntimeError(f"GET {path} 404: Not Found")
    if method == "POST" and path == f"{REPO_PREFIX}/releases":
        has_release["v"] = True
        return {"id": 99}
    if method == "GET" and path == f"{REPO_PREFIX}/releases/99/assets":
        return assets["v"]
    if method == "DELETE":
        return None
    if method == "POST" and path.startswith("https://uploads.github.com"):
        return {"id": 7, "browser_download_url": "https://objects.githubusercontent.com/reel.mp4"}
    raise AssertionError(f"예상 못 한 호출: {method} {path}")


ip.gh_api = fake_gh
ip.GH_TOKEN = "t"

# 없으면 만들고, 있으면 다시 안 만든다
assert ip.ensure_release() == 99 and has_release["v"]
gh_calls.clear()
assert ip.ensure_release() == 99
assert not any(m == "POST" and p == f"{REPO_PREFIX}/releases" for m, p in gh_calls)

video = pathlib.Path(__file__)  # 바이트만 읽히면 되므로 실제 영상 대신 이 파일을 쓴다
asset = ip.upload_reel_asset(99, video)
assert asset == {"id": 7, "url": "https://objects.githubusercontent.com/reel.mp4"}

# 같은 이름 애셋이 있으면 지우고 다시 올린다
assets["v"] = [{"id": 5, "name": video.name}]
gh_calls.clear()
ip.upload_reel_asset(99, video)
assert ("DELETE", f"{REPO_PREFIX}/releases/assets/5") in gh_calls

ip.delete_reel_asset(7)
assert ("DELETE", f"{REPO_PREFIX}/releases/assets/7") in gh_calls

# ---------- 캡션 ----------
mon = datetime.date(2026, 10, 5)   # 월요일
for kind in ip.SLOTS:
    _, cap = ip.build(kind, mon if kind != "band" else datetime.date(2026, 10, 10))
    assert len(cap) <= ip.CAPTION_LIMIT, (kind, len(cap))
    assert ip.APP_LINK in cap, kind
    # 글에 쓰면 안 되는 표현은 캡션에도 쓰면 안 된다(스토어 심사 기준과 같은 선)
    for banned in ("예측", "적중률", "확률 높"):
        assert banned not in cap, (kind, banned)

# ---------- 같은 건을 두 번 올리지 않는다 ----------
noon = datetime.datetime(2026, 10, 5, 12, 30, tzinfo=KST)        # 월
assert [k for k, _, _ in ip.due(noon)] == ["genius"]
evening = datetime.datetime(2026, 10, 5, 21, 0, tzinfo=KST)
assert sorted(k for k, _, _ in ip.due(evening)) == ["genius", "replay"]
# 주말은 천재가 없다(월~금 5명뿐). 점심 자리를 번호대가 받는다.
sat = datetime.datetime(2026, 10, 10, 21, 0, tzinfo=KST)
assert sorted(k for k, _, _ in ip.due(sat)) == ["band", "replay"]
assert [k for k, _, _ in ip.due(datetime.datetime(2026, 10, 11, 13, 0, tzinfo=KST))] == ["band"]
# 하루 두 건을 넘기지 않는다
for d in range(5, 12):
    n = datetime.datetime(2026, 10, d, 23, 0, tzinfo=KST)
    assert len(ip.due(n)) == 2, (d, ip.due(n))

# ---------- 발행에 실패해도 임시 애셋은 지운다 ----------
deleted = []
ip.reel.build_for = lambda *a, **k: video
ip.ensure_release = lambda: 99
ip.upload_reel_asset = lambda rid, p: {"id": 7, "url": "https://x/y.mp4"}
ip.delete_reel_asset = lambda aid: deleted.append(aid)


def boom(*a, **k):
    raise RuntimeError("인스타가 영상을 거부했습니다")


ip.publish_reel = boom
sent, tmp = [], pathlib.Path("_test_instagram_state.json")
ip.STATE = tmp
ip.telegram = lambda m: sent.append(m)
try:
    ip.run_auto(noon)
    assert deleted == [7]          # publish_reel이 터져도 애셋은 지운다
    assert sent == []               # 첫 실패는 알리지 않는다
finally:
    tmp.unlink(missing_ok=True)

# ---------- 실패해도 5분마다 알림이 오지 않는다 ----------
ip.reel.build_for = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("ffmpeg 없음"))
sent.clear()
try:
    for _ in range(8):
        ip.run_auto(noon)
    assert len(sent) == 1, sent          # 셋째 실패에서 한 번만
    assert json.loads(tmp.read_text(encoding="utf-8"))["fails"]["genius-2026-10-05"] == ip.MAX_TRIES
finally:
    tmp.unlink(missing_ok=True)

print("ok")
