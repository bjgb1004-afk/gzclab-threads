"""districts.json -> district_replies.json. 로컬에서 가끔 돌리고 결과를 커밋한다.

Actions에는 districts.json이 없다(.gitignore). 답글에 필요한 건 완성된 문장뿐이라
미리 구워서 올린다. 새 시도를 추가했을 때만 다시 돌리면 된다.

실행: python bake_replies.py
"""

import json
import pathlib

from gen_district_posts import hook, name, where

HERE = pathlib.Path(__file__).parent
# 런타임에 "<닉>아 <구> 1등 많이 나온 집 뽑아왔어!\n\n"가 앞에 붙는다. 닉이 30자여도
# 500자를 넘지 않도록 본문은 400자로 제한한다.
BODY_LIMIT = 400


def body(stores):
    """TOP3 + 격차 한 줄. 격차 문장은 본문 글과 같은 hook()을 써서 서로 어긋나지 않게 한다."""
    lines = []
    for i, s in enumerate(stores[:3], 1):
        spot = f" ({where(s)})" if where(s) else ""
        lines.append(f"{i}. {name(s)}{spot} — 1등 {s['first']}회")
    return "\n".join(lines) + "\n\n" + hook(stores)


def main():
    districts = json.loads((HERE / "districts.json").read_text(encoding="utf-8"))
    out = {}
    for district, stores in districts.items():
        # 본문 글과 같은 기준으로 거른다. 1위가 2회짜리면 답글로 내줄 게 없다.
        if len(stores) < 3 or stores[0]["first"] < 3:
            continue
        text = body(stores)
        assert len(text) <= BODY_LIMIT, f"{district} {len(text)}자 초과"
        out[district] = text

    path = HERE / "district_replies.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(out)}개 구 저장 -> {path.name} ({path.stat().st_size // 1024}KB)")


if __name__ == "__main__":
    main()
