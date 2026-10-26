"""gen_region_posts.py 검증. 큐·원본은 임시 파일로 바꿔 실제 파일을 건드리지 않는다."""

import json
import pathlib
import tempfile

import gen_region_posts as gr

BODY_NOWON = """1. 스파 (상계동) — 1등 52회
2. 지원물산 (공릉동) — 1등 8회
3. 노다지복권방 (상계동) — 1등 6회

1위가 52회인데 2위가 8회. 6배 차이 남. 이 동네는 사실상 한 집 독주."""

BODY_ASAN = """1. 로또명당인주점 (인주면) — 1등 35회
2. 대박마트복권방 (음봉면) — 1등 12회
3. 대박행운복권방 (도고면) — 1등 6회

1위 35회, 2위 12회. 2배 넘게 벌어짐."""

BODY_SMALL = """1. 가게A (가동) — 1등 3회
2. 가게B (나동) — 1등 2회
3. 가게C (다동) — 1등 1회

1위 3회, 2위 2회. 촘촘함."""

REPLIES = {"서울 노원구": BODY_NOWON, "충남 아산시": BODY_ASAN, "강원 양양군": BODY_SMALL}


def sandbox(queue=None, replies=None):
    tmp = pathlib.Path(tempfile.mkdtemp())
    gr.QUEUE = tmp / "queue.json"
    gr.REPLIES = tmp / "district_replies.json"
    gr.QUEUE.write_text(json.dumps(queue or [], ensure_ascii=False), encoding="utf-8")
    gr.REPLIES.write_text(json.dumps(replies or REPLIES, ensure_ascii=False), encoding="utf-8")
    return gr.QUEUE


# ---------- 미발행 지역 고르기 ----------

def test_missing_sorted_by_wins():
    """1위 배출횟수 큰 동네부터. 반응이 큰 곳을 먼저 내보내려는 것이다."""
    got = [d for _w, d, _b in gr.missing([], REPLIES)]
    assert got == ["서울 노원구", "충남 아산시", "강원 양양군"]


def test_missing_skips_already_posted_full_name():
    queue = [{"id": "x", "text": "서울 노원구에서 로또 1등 제일 많이 나온 판매점 TOP3\n..."}]
    assert "서울 노원구" not in [d for _w, d, _b in gr.missing(queue, REPLIES)]


def test_missing_skips_already_posted_bare_name():
    """손으로 쓴 옛 글은 '노원구에서'처럼 시도를 뗀 제목이다. 그것도 발행으로 봐야 한다."""
    queue = [{"id": "x", "text": "노원구에서 로또 1등 제일 많이 나온 판매점 TOP5\n..."}]
    assert "서울 노원구" not in [d for _w, d, _b in gr.missing(queue, REPLIES)]


def test_missing_skips_unreadable_body():
    """1위 줄을 못 읽는 지역은 숫자를 지어내지 않고 건너뛴다."""
    bad = {"엉뚱 지역": "형식이 다른 본문"}
    assert gr.missing([], bad) == []


def test_bare():
    assert gr.bare("서울 노원구") == "노원구"
    assert gr.bare("경기 용인시 기흥구") == "용인시 기흥구"
    assert gr.bare("노원구") == "노원구"


# ---------- 글 조립 ----------

def test_build_keeps_numbers_and_note_verbatim():
    text = gr.build("서울 노원구", BODY_NOWON, 0)
    assert text.startswith("서울 노원구에서 로또 1등 제일 많이 나온 판매점 TOP3")
    # 숫자는 원문 그대로 — auto_reply가 댓글에 보내는 텍스트와 같아야 한다
    for row in ("1. 스파 (상계동) — 1등 52회",
                "2. 지원물산 (공릉동) — 1등 8회",
                "3. 노다지복권방 (상계동) — 1등 6회"):
        assert row in text
    # 한 줄 분석이 반드시 남아야 한다('1위가'로 시작해 필터에 걸려 날아간 적이 있다)
    assert "1위가 52회인데 2위가 8회. 6배 차이 남." in text
    assert len(text) <= gr.LIMIT


def test_build_has_comment_hook_for_auto_reply():
    """'구 이름 남겨줘'가 빠지면 auto_reply가 이 글 댓글에 답을 안 단다."""
    for i in range(6):
        text = gr.build("서울 노원구", BODY_NOWON, i)
        assert "구 이름 남겨줘" in text
        # 접힘 앞(셋째 줄)에 있어야 보인다
        assert "구 이름 남겨줘" in text.splitlines()[2]


def test_build_rotates_ask_and_tail():
    """매 글 같은 문장이면 그게 제일 큰 봇 티다."""
    asks = {gr.build("서울 노원구", BODY_NOWON, i).splitlines()[2] for i in range(3)}
    tails = {gr.build("서울 노원구", BODY_NOWON, i).splitlines()[-1] for i in range(3)}
    assert len(asks) == 3 and len(tails) == 3


def test_build_title_counts_actual_rows():
    """3줄이면 TOP3라고 쓴다 — 없는 2줄을 지어내 TOP5로 쓰지 않는다."""
    assert "TOP3" in gr.build("강원 양양군", BODY_SMALL, 0)


# ---------- 큐에 꽂기 ----------

def test_generate_does_not_touch_queue():
    q = sandbox()
    before = q.read_text(encoding="utf-8")
    made = gr.generate()
    assert len(made) == 3
    assert q.read_text(encoding="utf-8") == before


def test_entry_shape():
    sandbox()
    _district, item = gr.generate(1)[0]
    assert item["id"] == "region-서울-노원구"
    assert item["slot"] == "am" and item["status"] == "pending"
    # link이 있으면 publish.main()이 링크 답글을 자동으로 단다
    assert item["link"] == gr.APP and "?c=top5" in item["link"]


def test_main_inserts_at_front_and_is_idempotent():
    old = {"id": "top5-old", "status": "pending", "slot": "am", "text": "옛 글\n..."}
    q = sandbox(queue=[old])
    assert gr.main([]) == 0
    queue = json.loads(q.read_text(encoding="utf-8"))
    # 새 지역이 재활용된 옛 글보다 앞 — publish는 큐 순서에서 처음 만나는 am 글을 집는다
    assert queue[0]["id"] == "region-서울-노원구"
    assert queue[-1]["id"] == "top5-old"
    n = len(queue)
    # 두 번 돌려도 중복으로 안 들어간다
    assert gr.main([]) == 0
    assert len(json.loads(q.read_text(encoding="utf-8"))) == n


def test_main_limit():
    q = sandbox()
    assert gr.main(["-n", "2"]) == 0
    assert len(json.loads(q.read_text(encoding="utf-8"))) == 2


def test_main_when_nothing_left():
    sandbox(queue=[{"id": f"x{i}", "text": f"{d}에서 로또 1등 제일 많이 나온 판매점 TOP3"}
                   for i, d in enumerate(REPLIES)])
    assert gr.main([]) == 0
    assert gr.generate() == []


# ---------- 실제 데이터 ----------

def test_real_data_produces_posts_within_limit():
    """커밋된 district_replies.json으로 실제로 돌려본다. 숫자가 아니라 형식을 본다."""
    import importlib
    importlib.reload(gr)
    made = gr.generate()
    assert len(made) >= 100, f"미발행 지역이 {len(made)}곳뿐 — 기대보다 적다"
    for _d, item in made:
        assert len(item["text"]) <= gr.LIMIT, item["id"]
        assert "구 이름 남겨줘" in item["text"], item["id"]
        assert item["slot"] == "am"
    ids = [item["id"] for _d, item in made]
    assert len(ids) == len(set(ids)), "id가 겹친다"
