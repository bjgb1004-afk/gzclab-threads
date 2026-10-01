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

# 원본(lottorich) 지번이 틀린 집. 도로명과 당첨 횟수는 맞는데 지번만 엉뚱한 동네를 가리킨다.
# where()가 이 지번에서 동 이름을 뽑아 글에 찍으므로 그대로 두면 틀린 동이 나간다.
# districts.json은 .gitignore라 거기만 고치면 재수집 때 되돌아간다 — 고침은 여기 둔다.
ADDRESS_FIXES = {
    # 흥부네대박났네(1등 11회). 도로명 경충대로 763은 곤지암읍 구간이다(곤지암 675~732,
    # 초월 963번길, 장지동 1786, 중대동 1977 순). 역동일 수 없다. 2026-10-01 유저 제보.
    "경기 광주시 역동 27-28": "경기 광주시 곤지암읍 삼리 399-18",
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
            address = ADDRESS_FIXES.get(address, address)
            district = district_of(address)
            if not district:
                continue
            key = (clean_name(e["name"]), address)
            s = stores.setdefault(
                key,
                {
                    "name": clean_name(e["name"]),
                    "address": address,
                    "road": (e.get("road_name") or "").strip(),
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
