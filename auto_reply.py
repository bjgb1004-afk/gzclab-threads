"""댓글에서 지역명을 읽어 그 구의 TOP3를 답글로 단다.

대상은 "댓글에 구 이름 남겨줘" 형 발행글. 이미 답한 댓글은 conversation 응답에서
바로 걸러지므로 상태 파일이 없다.
"""

import json
import pathlib

HERE = pathlib.Path(__file__).parent
REPLIES = HERE / "district_replies.json"
ME = "gzclab"


def match(text, keys):
    """댓글에서 지역을 고른다. ('hit', 키) / ('ambiguous', 키들) / ('need_gu', 시도) / (None, None).

    '노원'처럼 접미사를 뗀 축약도 받는다. 다만 한 글자 축약('중구'->'중')은
    아무 문장에나 걸려서 쓰지 않는다.
    """
    # 전체 이름을 말한 경우가 가장 정확하다. 공백 유무를 모두 본다.
    for key in keys:
        if key in text or key.replace(" ", "") in text:
            return "hit", key

    # 부분 이름 -> 그 이름을 가진 키들. 키는 '서울 노원구'가 대부분이지만
    # '경기 용인시 기흥구'(시 아래 구)와 '세종시'(시도 자체)도 있다.
    by_part = {}
    for key in keys:
        toks = key.split()
        for tok in toks[1:] or toks:
            by_part.setdefault(tok, []).append(key)
            short = tok[:-1]  # 노원구 -> 노원
            if len(short) >= 2:
                by_part.setdefault(short, []).append(key)

    # 긴 이름부터 본다. '중구'보다 '노원구'가 먼저 걸려야 한다.
    for part in sorted(by_part, key=len, reverse=True):
        if part in text:
            cand = by_part[part]
            if len(cand) == 1:
                return "hit", cand[0]
            return "ambiguous", sorted(cand)

    # 광역만 말한 경우. '세종시'처럼 시도가 곧 키인 것은 위에서 이미 걸린다.
    for sido in sorted({k.split()[0] for k in keys if " " in k}):
        if sido in text:
            return "need_gu", sido

    return None, None
