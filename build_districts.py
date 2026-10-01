"""lottorich 공개 데이터로 시군구별 1·2등 배출 판매점 TOP5를 뽑아 districts.json에 저장.

앱(ruflo-starter)의 ingestLottorich.ts와 같은 소스를 쓰되, 앱 DB는 건드리지 않는다.
실행: python build_districts.py
"""

import collections
import json
import pathlib
import urllib.request

URL = "https://www.lottorich.co.kr/lotto/lotto_store/proc.html?mode=list&seq=0&rank={}&pg=1&item_num=15000"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; GzclabThreadsBot/1.0; +personal-project)",
    "Referer": "https://www.lottorich.co.kr/lotto/lotto_store/index.html",
}
OUT = pathlib.Path(__file__).with_name("districts.json")
METRO = ("서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종")

# 원본(lottorich)의 상호·주소가 틀린 집. 당첨 횟수는 맞는데 주소가 다른 동네를 가리키거나
# 상호가 옛 이름으로 남아 있다. where()가 주소에서 동 이름을 뽑아 글에 찍으므로 그대로
# 두면 틀린 동이 나간다. districts.json은 .gitignore라 거기만 고치면 재수집 때 되돌아간다
# — 고침은 여기 둔다. 키는 원본 주소, 값은 덮어쓸 필드.
#
# 정정 근거는 복권명당(ruflo-starter)에서 가져온다. 그쪽은 동행복권 공식 API + 네이버 검색
# + VWORLD 지오코딩으로 판매점을 검증하므로, 이 프로젝트가 따로 주소를 조사하면 안 된다.
STORE_FIXES = {
    # 2026-09-30 복권명당 감사(ruflo-starter 994ae34): lottorich의 '흥부네대박났네' 행 둘은
    # (역동 27-28 / 경충대로 763) 네이버에 없고 공식 판매점 ID도 없는 쓰레기 레코드라 삭제됐다.
    # 실제 가게는 '행복한사람들 (흥부네)'이고 주소는 초월읍 경충대로 1014 (기존 값이 2.7km 틀림).
    "경기 광주시 역동 27-28": {
        "name": "행복한사람들 (흥부네)",
        "address": "경기 광주시 초월읍 경충대로 1014",
        "road": "경기 광주시 초월읍 경충대로 1014",
    },
}


def fetch(rank):
    req = urllib.request.Request(URL.format(rank), headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("euc-kr", errors="replace"))


def sido(token):
    """'서울특별시' / '경기도' / '전북특별자치도' 같은 표기를 '서울' / '경기' / '전북'으로 통일."""
    for suffix in ("특별자치도", "특별자치시", "광역시", "특별시", "자치도", "도", "시"):
        if token.endswith(suffix) and len(token) > len(suffix):
            token = token[: -len(suffix)]
            break
    return {"전라북": "전북", "전라남": "전남", "충청북": "충북", "충청남": "충남",
            "경상북": "경북", "경상남": "경남"}.get(token, token)


def district_of(address):
    """'경기 수원시 장안구 …' -> '경기 수원시 장안구', '서울 노원구 …' -> '서울 노원구'."""
    parts = address.split()
    if len(parts) < 2:
        return None
    if parts[0].startswith("세종"):
        return "세종시"
    key = f"{sido(parts[0])} {parts[1]}"
    # 수원시 장안구처럼 시 아래 구가 또 있으면 거기까지 묶는다
    if len(parts) >= 3 and parts[1].endswith("시") and parts[2].endswith("구"):
        key += f" {parts[2]}"
    return key


def clean_name(name):
    return (name or "").strip().strip("]),.·-").strip()


def is_real_store(e):
    name, addr = clean_name(e.get("name")), (e.get("sido") or "")
    return bool(name) and "인터넷" not in name and "동행복권본사" not in addr and "복권위원회" not in addr


def main():
    stores = {}
    for rank in (1, 2):
        for e in fetch(rank):
            if not is_real_store(e):
                continue
            address = (e.get("sido") or "").strip()
            fix = STORE_FIXES.get(address, {})
            address = fix.get("address", address)
            district = district_of(address)
            if not district:
                continue
            key = (fix.get("name") or clean_name(e["name"]), address)
            s = stores.setdefault(
                key,
                {
                    "name": fix.get("name") or clean_name(e["name"]),
                    "address": address,
                    "road": fix.get("road") or (e.get("road_name") or "").strip(),
                    "district": district,
                    "first": 0,
                    "second": 0,
                },
            )
            count = int(e.get("win_cnt") or 0)
            field = "first" if rank == 1 else "second"
            s[field] = max(s[field], count)

    by_district = collections.defaultdict(list)
    for s in stores.values():
        s["total"] = s["first"] + s["second"]
        by_district[s["district"]].append(s)

    out = {}
    for district, items in by_district.items():
        items.sort(key=lambda s: (-s["first"], -s["second"], s["name"]))
        out[district] = items[:5]

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    seoul = sorted(d for d in out if d.startswith("서울"))
    print(f"시군구 {len(out)}개 / 판매점 {len(stores)}곳 -> {OUT.name}")
    print(f"서울 {len(seoul)}개 구: {', '.join(d.split()[1] for d in seoul)}")


if __name__ == "__main__":
    main()
