"""토요일 추첨 회차의 1등 배출점을 지역별로 묶어 queue.json 맨 앞(아침 슬롯)에 꽂는다.

실행: python gen_draw_post.py          (직전 토요일 회차)
      python gen_draw_post.py --dry    (붙이지 않고 미리보기)
      python gen_draw_post.py 1243     (회차 지정)
"""

import datetime
import json
import pathlib
import sys
import urllib.parse
import urllib.request

import publish  # telegram 알림만 쓴다. 토큰이 없어도 조용히 넘어간다.

sys.stdout.reconfigure(encoding="utf-8")  # 윈도우 콘솔(cp949)에서 '—' 출력 방지

HERE = pathlib.Path(__file__).parent
FIRST_DRAW = datetime.date(2002, 12, 7)  # 1회차 추첨일(토)
API = "https://www.dhlottery.co.kr/wnprchsplcsrch/selectLtWnShp.do"
# 구 엔드포인트(store.do?method=topStore)는 폐기돼 /errorPage로 리다이렉트된다. 이 경로만 열려 있다.
REFERER = "https://www.dhlottery.co.kr/wnprchsplcsrch/home"
# 인터넷 구매분이 같은 목록에 섞여 온다. 상호가 '인터넷 복권판매사이트', 좌표는 동행복권 본사.
# 지역별 정리에 그대로 넣으면 서울 강남이 매주 배출점으로 찍힌다.
NET_SHOP_ID = "51100000"
LIMIT = 500  # Threads 본문 글자 제한
# auto_reply.targets()가 "구 이름 남겨줘"로 대상 글을 고른다. 이 문구가 빠지면
# 댓글이 와도 자동답글이 안 붙는다.
OPENER = "여기 우리 동네 없으면 댓글에 구 이름 남겨줘. 그 동네 1등 TOP3 바로 답 달아줌."
assert "구 이름 남겨줘" in OPENER, "auto_reply가 대상에서 놓친다"
FOLLOW = "매주 추첨 끝나면 이렇게 정리해서 올림. 다음 주도 볼 사람은 팔로우."


def latest_draw(today=None):
    """직전(또는 당일) 토요일 회차. 일요일 새벽에 돌리면 어제 추첨분이 나온다."""
    today = today or (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)).date()
    sat = today - datetime.timedelta(days=(today.weekday() - 5) % 7)
    return (sat - FIRST_DRAW).days // 7 + 1


def fetch(draw):
    params = {"srchWnShpRnk": "1", "srchLtEpsd": str(draw), "srchShpLctn": ""}
    req = urllib.request.Request(
        f"{API}?{urllib.parse.urlencode(params)}",
        headers={"User-Agent": "Mozilla/5.0", "Referer": REFERER},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["data"]["list"]


def build(draw, stores):
    """1등 배출점 목록 -> 글 dict. 물리매장이 없으면 None."""
    real = [s for s in stores if s["ltShpId"] != NET_SHOP_ID]
    net = len(stores) - len(real)
    if not real:
        return None

    # 시도별로 묶고, 많이 나온 시도부터. 같은 시도가 흩어져 있으면 읽기 힘들다.
    by_region = {}
    for s in real:
        by_region.setdefault(s["region"], []).append(s)
    order = sorted(by_region, key=lambda r: (-len(by_region[r]), r))

    head = f"{draw}회 1등 배출점 지역별 정리 ({len(real)}곳"
    head += f" + 인터넷 {net}건)" if net else ")"
    rows = [
        # 주소 두 번째 토큰이 시·군·구. '경기 화성시', '서울 영등포구' 모두 여기서 나온다.
        f"[{r} {s['shpAddr'].split()[1]}] {s['shpNm']} ({s['atmtPsvYnTxt']})"
        for r in order
        for s in by_region[r]
    ]

    # 1등은 보통 10~15곳이라 여유가 크지만, 이월 회차는 20곳을 넘긴 적이 있다.
    # 넘치면 뒤에서 덜어내고 몇 곳을 덜어냈는지 밝힌다.
    def text_of(rows, cut):
        body = [head, "", OPENER, ""] + rows
        if cut:
            body.append(f"(외 {cut}곳)")
        body += ["", FOLLOW]
        return "\n".join(body)

    cut = 0
    while len(text_of(rows, cut)) > LIMIT and rows:
        rows.pop()
        cut += 1

    return {"id": f"draw-{draw}", "status": "pending", "slot": "am", "text": text_of(rows, cut)}


def main(argv):
    dry = "--dry" in argv
    nums = [a for a in argv if a.isdigit()]
    draw = int(nums[0]) if nums else latest_draw()

    stores = fetch(draw)
    post = build(draw, stores)
    if not post:
        # 추첨 직후엔 아직 안 올라와 있을 수 있다. 빨간불로 남겨 다음 cron이 이어받게 한다.
        print(f"{draw}회 1등 배출점 데이터 없음 (total={len(stores)})", file=sys.stderr)
        return 1

    if dry:
        print(post["text"])
        print(f"--- {len(post['text'])}자")
        return 0

    path = HERE / "queue.json"
    queue = json.loads(path.read_text(encoding="utf-8"))
    if any(p["id"] == post["id"] for p in queue):
        print(f"{post['id']} 이미 있음 — 아무것도 하지 않음")
        return 0
    path.write_text(
        json.dumps([post] + queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    msg = f"🎯 {draw}회 1등 배출점 글 큐에 넣음 ({len(post['text'])}자). 일요일 아침 발행 예정."
    print(msg)
    publish.telegram(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
