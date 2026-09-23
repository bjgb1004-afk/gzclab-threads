"""districts.json -> 구별 TOP5 글을 만들어 queue.json 앞쪽(아침 슬롯)에 꽂는다.

실행: python gen_district_posts.py 서울        (해당 시도 전부)
      python gen_district_posts.py 서울 --dry  (붙이지 않고 미리보기)
"""

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
APP = "https://play.google.com/store/apps/details?id=com.gzc.lottomap"
LIMIT = 500  # Threads 본문 글자 제한


def where(store):
    """주소에서 동 이름만 뽑는다. 못 뽑으면 빈 문자열."""
    for part in store["address"].split()[2:4]:
        if part.endswith(("동", "읍", "면", "가")) and not part[0].isdigit():
            return part
    return ""


def hook(top):
    first, second = top[0]["first"], top[1]["first"] if len(top) > 1 else 0
    if second and first >= second * 3:
        return f"1위가 {first}회인데 2위가 {second}회. {first // second}배 차이 남. 이 동네는 사실상 한 집 독주."
    if second and first == second:
        return f"1·2위가 {first}회로 동률임. 여긴 몰리는 집 없이 골고루 나옴."
    if second:
        return f"1위랑 2위가 {first}회 대 {second}회. 생각보다 촘촘함."
    return "기록이 남은 집이 몇 안 됨. 그만큼 한 번 나오면 티가 크게 남."


def build(district, stores):
    gu = district.split()[-1]
    lines = [f"{gu}에서 로또 1등 제일 많이 나온 판매점 TOP5", ""]
    for i, s in enumerate(stores, 1):
        spot = f" ({where(s)})" if where(s) else ""
        lines.append(f"{i}. {s['name']}{spot} — 1등 {s['first']}회")
    lines += ["", hook(stores)]
    text = "\n".join(lines)
    assert len(text) <= LIMIT, f"{district} {len(text)}자 초과"
    return {
        "id": f"top5-{gu}",
        "status": "pending",
        "slot": "am",
        "text": text,
        "link": APP,
    }


def main(sido, dry):
    districts = json.loads((HERE / "districts.json").read_text(encoding="utf-8"))
    # 노원구는 사용자가 이미 수동으로 올려서 반응(13시간 1,300뷰)까지 본 구라 중복 제외.
    done = {"서울 노원구"}
    picked = {
        k: v for k, v in districts.items()
        if k.startswith(sido) and len(v) >= 3 and k not in done
    }
    # 1등 배출이 많은 구부터. 얘기거리가 많은 쪽을 먼저 쓴다.
    order = sorted(picked, key=lambda k: -sum(s["first"] for s in picked[k]))
    posts = [build(k, picked[k]) for k in order]

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
