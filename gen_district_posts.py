"""districts.json -> 구별 TOP5 글을 만들어 queue.json 앞쪽(아침 슬롯)에 꽂는다.

실행: python gen_district_posts.py 서울        (해당 시도 전부)
      python gen_district_posts.py 서울 --dry  (붙이지 않고 미리보기)
"""

import json
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8")  # 윈도우 콘솔(cp949)에서 '—' 출력 시 죽는 것 방지

HERE = pathlib.Path(__file__).parent
# referrer 값은 Play Console 유입 리포트에 그대로 잡힌다. 이게 없으면 어느 글이
# 설치로 이어졌는지 영영 알 수 없다.
APP = ("https://play.google.com/store/apps/details?id=com.gzc.lottomap"
       "&referrer=utm_source%3Dthreads%26utm_medium%3Dreply%26utm_campaign%3Dtop5")
LIMIT = 500  # Threads 본문 글자 제한


def where(store):
    """주소에서 동 이름만 뽑는다. 못 뽑으면 빈 문자열."""
    for part in store["address"].split()[2:4]:
        if part.endswith(("동", "읍", "면", "가")) and not part[0].isdigit():
            return part
    return ""


def name(store):
    """원본 데이터에 괄호가 열린 채 잘린 상호가 83곳 있다('훼미리마트(대림중앙점').
    그대로 올리면 글이 지저분해 보이니 괄호 앞까지만 쓴다."""
    n = store["name"]
    return n[: n.rindex("(")].strip() if n.count("(") > n.count(")") else n


def hook(top):
    """1·2위 격차를 사실대로 말한다. 구간을 안 나누면 16회 대 7회까지 '촘촘함'으로 나가서
    본문 숫자와 마지막 줄이 서로 어긋난다."""
    first, second = top[0]["first"], top[1]["first"] if len(top) > 1 else 0
    if not second:
        return "기록이 남은 집이 몇 안 됨. 그만큼 한 번 나오면 티가 크게 남."
    if first >= second * 3:
        return f"1위가 {first}회인데 2위가 {second}회. {first // second}배 차이 남. 이 동네는 사실상 한 집 독주."
    if first >= second * 2:
        return f"1위 {first}회, 2위 {second}회. 2배 넘게 벌어짐. 여긴 한 집으로 쏠린다고 봐야 함."
    if first >= second * 1.5:
        return f"1위 {first}회, 2위 {second}회. 한 집이 확실히 앞서는데 따라붙는 집도 있음."
    if first == second:
        return f"1·2위가 {first}회로 동률임. 여긴 몰리는 집 없이 골고루 나옴."
    return f"1위랑 2위가 {first}회 대 {second}회. 생각보다 촘촘함."


# 댓글을 부르는 줄은 본문 맨 아래가 아니라 제목 바로 다음에 둔다. 피드에서 긴 글은
# 몇 줄 뒤로 접히는데, 지금까지 이 줄이 리스트 아래에 있어서 2,676뷰짜리 글도 외부
# 댓글이 0이었다(2026-09-26 확인: 달린 답글 1개는 우리가 단 링크였다).
# "바로 답 달아줌"을 명시한다 — auto_reply.py가 실제로 즉시 TOP3를 달아주는데
# 본문이 그 즉시성을 안 알려주고 있었다("다음 글에 올림"은 보상이 너무 멀다).
# 세 문장 모두 "구 이름 남겨줘"를 포함해야 한다. auto_reply.targets()가 그 문구로
# 대상 글을 고르므로, 빠진 문장이 나가면 그 글은 댓글이 와도 자동답글이 안 된다.
OPENERS = (
    "궁금한 동네 있으면 댓글에 구 이름 남겨줘. 그 동네 TOP3 바로 답으로 달아줌.",
    "댓글에 구 이름 남겨줘. 1등 많이 나온 집 바로 뽑아서 답 달아줌.",
    "우리 동네도 보고 싶으면 댓글에 구 이름 남겨줘. 기다릴 필요 없이 바로 답 감.",
)
assert all("구 이름 남겨줘" in o for o in OPENERS), "auto_reply가 대상에서 놓친다"


def build(district, stores, index):
    gu = district.split()[-1]
    lines = [
        # 제목의 "<구> 로또 1등 판매점"은 검색 유입 자산이라 건드리지 않는다.
        f"{gu}에서 로또 1등 제일 많이 나온 판매점 TOP5",
        "",
        OPENERS[index % len(OPENERS)],
        "",
    ]
    for i, s in enumerate(stores, 1):
        spot = f" ({where(s)})" if where(s) else ""
        lines.append(f"{i}. {name(s)}{spot} — 1등 {s['first']}회")
    lines += ["", hook(stores)]
    text = "\n".join(lines)
    assert len(text) <= LIMIT, f"{district} {len(text)}자 초과"
    post = {
        # 구 이름만 쓰면 '중구'가 6개 시도에 있어서, 다른 시도를 돌릴 때 중복으로 걸러진다.
        "id": "top5-" + district.replace(" ", "-"),
        "status": "pending",
        "slot": "am",
        "text": text,
    }
    # 매일 링크를 달면 계정이 광고판이 된다. 한 편 걸러 하나만 링크를 건다.
    if index % 2 == 0:
        post["link"] = APP
    return post


def main(sido, dry):
    districts = json.loads((HERE / "districts.json").read_text(encoding="utf-8"))
    # 노원구는 사용자가 이미 수동으로 올려서 반응(13시간 1,300뷰)까지 본 구라 중복 제외.
    done = {"서울 노원구"}
    picked = {
        k: v for k, v in districts.items()
        # 1위가 1등 3회 미만이면 TOP5가 2·3회짜리 나열이라 읽을 게 없다 — 거른다.
        if k.startswith(sido) and len(v) >= 3 and v[0]["first"] >= 3 and k not in done
    }
    # 1등 배출이 많은 구부터. 얘기거리가 많은 쪽을 먼저 쓴다.
    order = sorted(picked, key=lambda k: -sum(s["first"] for s in picked[k]))
    posts = [build(k, picked[k], i) for i, k in enumerate(order)]

    if dry:
        print(f"{len(posts)}개 생성 (붙이지 않음)\n")
        print(posts[0]["text"])
        print("\n---\n")
        print(posts[-1]["text"])
        return

    queue_path = HERE / "queue.json"
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    have = {p["id"] for p in queue}
    new = [p for p in posts if p["id"] not in have]
    queue_path.write_text(
        json.dumps(new + queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{len(new)}개 추가. 큐 총 {len(new) + len(queue)}개, 대기 {sum(1 for p in new + queue if p['status'] == 'pending')}개")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "서울", "--dry" in sys.argv)
