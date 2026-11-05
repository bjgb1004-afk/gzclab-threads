"""녹화한 앱 화면을 인스타 릴스용 9:16 영상으로 편집한다.

역할 나눔 (2026-10-27 유저 결정): 화면 녹화는 Claude Code가 adb로 찍고(이 작업공간에는
adb도 안드로이드 SDK도 없고 기기도 안 보인다), 자르기·글자 얹기·마무리는 여기서 한다.

**매일 다시 찍지 않는다.** 바탕 영상(footage)은 한 번 찍어 assets/footage에 두고, 그 위에
그날의 훅과 번호를 얹는다. 날마다 녹화를 요구하면 자동화가 아니다.

글자를 ffmpeg drawtext로 넣지 않는 이유: 한글 글꼴·자간 처리가 빌드마다 다르고 깨지면
영상이 통째로 못 쓰게 된다. 글자판은 Pillow로 PNG(투명)를 그려서 overlay로 얹는다 —
카드와 같은 글꼴·같은 색이 나오고, 실패하면 영상 만들기 전에 바로 드러난다.

실행: python reel.py --footage assets/footage/genius.mp4 --kind genius --dry
      python reel.py --list                      (쓸 수 있는 바탕 영상)
      python reel.py --selftest                  (가짜 영상으로 파이프라인만 점검)
"""

import argparse
import datetime
import pathlib
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFilter

import cards as C
import replay as rp

sys.stdout.reconfigure(encoding="utf-8")

HERE = pathlib.Path(__file__).parent
FOOTAGE = HERE / "assets" / "footage"
OUT = HERE / "reels"

RW, RH = 1080, 1920      # 9:16. 릴스가 화면을 꽉 채우는 비율
FPS = 30
OUTRO_SEC = 3.5          # 마무리 CTA. 2.5초였을 땐 읽기 전에 끝났다
TAIL_SEC = 2.0           # 훅이 사라진 뒤 앱 화면만 보이는 시간
MAX_BODY = 20.0          # 사고 방지 상한. 긴 녹화본이 들어와도 릴스가 1분짜리가 되지 않게
FADE = 0.4
TOP = 340          # 훅 시작 높이. 위 UI(~250px)와 4:5 피드 자르기(285px) 둘 다 피한다
END_Y = 1240       # 마무리 자막 높이. 아래 UI(~350px) 위
END_SEC = 3.0      # 마무리 자막이 떠 있는 시간(영상 끝부분 = 결과 화면)
REPLAY_FOOTAGE_DRAW = 534   # assets/footage/replay.mp4에 찍힌 회차

# 훅 글자를 읽는 속도(자/초). 6.5는 큰 글씨를 편히 읽는 속도다 — 2026-11-01까지 훅이 글자
# 수와 무관하게 3초 고정이라, band는 10.7자/초 replay는 18자/초를 요구했고 유저가 "글자를
# 전부 읽지 못하겠다"고 했다. 훅 길이는 이제 글자 수가 정한다.
READ_CPS = 6.5
HOOK_MIN = 4.5

# 소재별 편집. start: 앞에서 버릴 초, speed: 배속(스크롤 사이 멈춤을 줄인다).
# 클립이 훅을 다 보여줄 만큼 길지 않으면 build_for가 speed를 알아서 낮춘다 — 글자가
# 잘리는 일은 없다. 녹화본을 다시 찍으면 여기만 맞춘다.
PROFILE = {
    "genius": {"start": 0.0, "speed": 1.6},
    "replay": {"start": 0.0, "speed": 1.25},  # 결과(합계 금액)까지 담긴다
    # 앞 3.2초를 버렸었다('당첨 0건·0원' 줄이 보여서). 훅의 어두운 막이 바로 그 자리를
    # 덮으므로 버릴 필요가 없고, 덕분에 7초를 통째로 써서 훅 읽을 시간이 생긴다.
    "band": {"start": 0.0, "speed": 1.0},
}


def hook_sec(hook, sub=None):
    """훅이 떠 있어야 하는 시간. 글자가 많으면 길어진다."""
    return max(HOOK_MIN, (len(hook) + len(sub or "")) / READ_CPS)


def run(args):
    """ffmpeg 호출. 실패하면 마지막 줄들을 그대로 보여준다 — 조용히 넘어가면 원인을 못 찾는다."""
    p = subprocess.run(args, capture_output=True, text=True)
    if p.returncode != 0:
        tail = "\n".join(p.stderr.strip().splitlines()[-12:])
        raise RuntimeError(f"ffmpeg 실패 ({' '.join(args[:6])} …)\n{tail}")
    return p


def _wrap(d, text, f, maxw):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def _center(d, y, text, f, fill):
    w = d.textbbox((0, 0), text, font=f)[2]
    d.text(((RW - w) // 2, y), text, font=f, fill=fill)


def hook_png(hook, sub, path):
    """위쪽에 훅, 나머지는 투명. 막 없이 테두리 글자로 얹어 뒤의 앱 화면이 보이게 한다."""
    im = Image.new("RGBA", (RW, RH), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    size = 92
    f = C.font(size, "black")
    def wrap_all(fnt):   # 줄바꿈(\n)은 그 자리에서 끊는다 — "그 / 회차에"처럼 말 중간에서 끊기지 않게
        return [ln for part in hook.split("\n") for ln in _wrap(d, part, fnt, RW - 120)]
    lines = wrap_all(f)
    while len(lines) > 4 and size > 56:
        size -= 8
        f = C.font(size, "black")
        lines = wrap_all(f)

    # 2026-11-05: 화면 폭 전체를 검은 막(215)으로 덮었더니 뒤의 앱 화면이 통째로 가려졌다(유저 지적).
    # 막을 없애고 릴스 자막처럼 글자 테두리(stroke)로 읽히게 한다. 글자 바로 뒤에만 옅은 그림자를 깔아
    # 밝은 앱 화면 위에서도 흰 글자가 묻히지 않게 한다 — 덮는 면적은 글자 획 근처뿐이다.
    # 위 ~250px는 인스타 UI(상단 바)가 덮고, 피드에서는 4:5로 잘려 위아래 285px가 사라진다.
    # 그 둘을 다 피하는 자리에서 시작한다(social-media-skills 릴스 안전영역 기준).
    top = TOP
    lh = int(size * 1.25)
    stroke = max(6, size // 11)
    shadow = Image.new("RGBA", (RW, RH), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    y = top
    for ln in lines:
        w = sd.textbbox((0, 0), ln, font=f)[2]
        sd.text(((RW - w) // 2 + 4, y + 6), ln, font=f, fill=(0, 0, 0, 150),
                stroke_width=stroke + 4, stroke_fill=(0, 0, 0, 150))
        y += lh
    im.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(im)
    y = top
    for ln in lines:
        w = d.textbbox((0, 0), ln, font=f)[2]
        d.text(((RW - w) // 2, y), ln, font=f, fill=(255, 255, 255, 255),
               stroke_width=stroke, stroke_fill=(20, 16, 14, 255))
        y += lh
    if sub:
        sf = C.font(48, "bold")
        w = d.textbbox((0, 0), sub, font=sf)[2]
        d.text(((RW - w) // 2, y + 18), sub, font=sf, fill=C.CREAM + (255,),
               stroke_width=5, stroke_fill=(20, 16, 14, 255))

    im.save(path)
    return path


def caption_png(text, path, y=END_Y):
    """결과 화면 위에 얹는 마무리 자막 한 줄(또는 두 줄). 훅과 같은 테두리 글자."""
    im = Image.new("RGBA", (RW, RH), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = C.font(76, "black")
    lines = [ln for part in text.split("\n") for ln in _wrap(d, part, f, RW - 120)]
    lh = 96
    shadow = Image.new("RGBA", (RW, RH), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    for i, ln in enumerate(lines):
        w = sd.textbbox((0, 0), ln, font=f)[2]
        sd.text(((RW - w) // 2 + 4, y + i * lh + 6), ln, font=f, fill=(0, 0, 0, 150),
                stroke_width=12, stroke_fill=(0, 0, 0, 150))
    im.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(im)
    for i, ln in enumerate(lines):
        w = d.textbbox((0, 0), ln, font=f)[2]
        d.text(((RW - w) // 2, y + i * lh), ln, font=f, fill=(255, 214, 64, 255),
               stroke_width=7, stroke_fill=(20, 16, 14, 255))
    im.save(path)
    return path


def outro_png(path):
    """마지막 장면. 카드의 CTA와 같은 말을 쓴다 — 채널마다 다른 약속을 하지 않는다."""
    im = C.cta_slide().convert("RGB").resize((RW, int(RW * C.H / C.W)))
    canvas = Image.new("RGB", (RW, RH), C.BG_BOTTOM)
    canvas.paste(im, (0, (RH - im.height) // 2))
    canvas.save(path, "JPEG", quality=92)
    return path


def build(footage, hook, sub, out_path, body_sec=None, start=0.0, speed=1.0, end_text=None):
    """바탕 영상 + 훅 + 마무리 → 릴스 한 편."""
    hs = hook_sec(hook, sub)
    if body_sec is None:
        body_sec = hs + TAIL_SEC
    footage = pathlib.Path(footage)
    if not footage.exists():
        raise FileNotFoundError(f"바탕 영상이 없습니다: {footage}")
    out_path = pathlib.Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        hk = hook_png(hook, sub, td / "hook.png")
        en = caption_png(end_text, td / "end.png") if end_text else None
        outro = outro_png(td / "outro.jpg")
        body = td / "body.mp4"
        tail = td / "tail.mp4"

        # 1) 바탕 영상을 9:16으로 채우고(넘치는 쪽은 잘라낸다) 길이를 맞춘 뒤 훅을 얹는다.
        #    훅은 글자 수가 정한 시간(hook_sec)만큼 보이고 부드럽게 사라진다.
        vf = (
            f"setpts=PTS/{speed},scale={RW}:{RH}:force_original_aspect_ratio=increase,"
            f"crop={RW}:{RH},fps={FPS},format=yuv420p[v];"
            f"[1:v]format=rgba,fade=t=out:st={hs - FADE}:d={FADE}:alpha=1[hk];"
            f"[v][hk]overlay=0:0:format=auto[vh];"
            + (f"[2:v]format=rgba[en];[vh][en]overlay=0:0:format=auto:enable='gte(t,{max(hs, body_sec - END_SEC)})'[ve];"
               if en else "[vh]null[ve];")
            + f"[ve]trim=0:{body_sec},setpts=PTS-STARTPTS[outv]"
        )
        extra = ["-loop", "1", "-framerate", str(FPS), "-t", str(body_sec), "-i", str(en)] if en else []
        run(["ffmpeg", "-y", "-loglevel", "error",
             "-ss", str(start), "-t", str(body_sec * speed), "-i", str(footage),
             # 훅은 정지 이미지라 한 프레임뿐이면 페이드가 걸리지 않고 끝까지 남는다 → 반복 입력으로 시간축을 준다
             "-loop", "1", "-framerate", str(FPS), "-t", str(body_sec), "-i", str(hk),
             *extra,
             "-filter_complex", vf, "-map", "[outv]",
             "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-an", str(body)])

        # 2) 마무리 장면을 같은 규격의 영상으로.
        run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-t", str(OUTRO_SEC),
             "-i", str(outro), "-vf", f"scale={RW}:{RH},fps={FPS},format=yuv420p",
             "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-an", str(tail)])

        # 3) 이어붙이고 무음 트랙을 넣는다. 오디오가 아예 없는 파일을 거부하는 경우가 있어
        #    무음이라도 넣어 둔다(음원은 저작권 때문에 쓰지 않는다).
        lst = td / "list.txt"
        lst.write_text(f"file '{body}'\nfile '{tail}'\n", encoding="utf-8")
        run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
             "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
             "-shortest", "-c:v", "copy", "-c:a", "aac", "-b:a", "96k",
             "-movflags", "+faststart", str(out_path)])

    return out_path


def reel_name(kind, day):
    return f"reel-{kind}-{day.isoformat()}"


def build_for(kind, day, footage=None, draws=None):
    """그날 릴스 한 편. 훅은 카드·캡션과 같은 문장을 쓴다."""
    hook, sub = C.slide_hook(kind, day, draws)
    end_text = None
    if kind == "replay":
        # 바탕 영상은 534회 1등 번호를 누르는 장면으로 고정이다(2026-10-28 녹화). 그날 회차를 말하면
        # 화면 번호와 자막이 어긋난다. 앱 화면이 1~1247회 전체를 돌리므로 집계도 1회부터 맞춘다.
        draws = draws if draws is not None else rp.fetch_draws()
        w = rp.draw_replay(REPLAY_FOOTAGE_DRAW, draws, start_round=1)
        hook = f"{w['draw_no']}회 1등 번호\n그 회차에 {w['own_prize'] / 100000000:.1f}억원"
        sub = f"이 회차를 빼고 나머지 {w['res']['draws']}회에 돌려보면?"
        end_text = f"이 회차를 빼면\n{rp.won(w['res']['gross'])}"
    if kind == "genius":
        # 바탕 영상이 다섯 천재 탭을 차례로 훑는다. 그날 한 명만 말하면 화면(아르키메데스부터 시작)과 어긋난다.
        draw_no = sub.split("회")[0]
        hook, sub = "수학자 5명의 방식으로 뽑은 번호", f"{draw_no}회 · 천재들의 한수"
    footage = pathlib.Path(footage) if footage else FOOTAGE / f"{kind}.mp4"
    p = PROFILE.get(kind, {})
    start, speed = p.get("start", 0.0), p.get("speed", 1.0)
    avail = max(0.5, _duration(footage) - start)   # 버린 앞부분을 뺀 원본 길이
    need = hook_sec(hook, sub) + TAIL_SEC          # 훅을 다 읽고도 앱 화면이 남아야 한다
    # 클립이 모자라면 배속을 낮춰서 채운다. 글자를 자르는 쪽으로 타협하지 않는다 —
    # 훅을 못 읽으면 영상이 하는 일이 없다.
    speed = min(speed, avail / need)
    body = min(MAX_BODY, avail / speed)
    return build(footage, hook, sub, OUT / f"{reel_name(kind, day)}.mp4",
                 body_sec=body, start=start, speed=speed, end_text=end_text)


def _duration(path):
    """바탕 영상 길이(초). 못 읽으면 바로 이유를 들고 죽는다.

    예전엔 빈 출력을 그대로 float()에 넘겨서, 파일이 없을 때 로그에
    "could not convert string to float: ''"만 남았다 — 러너에 영상이 없는 걸
    사흘 동안 못 찾은 원인이다.
    """
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    out = r.stdout.strip()
    if not out:
        if not pathlib.Path(path).exists():
            raise FileNotFoundError(f"바탕 영상이 없습니다: {path}")
        raise RuntimeError(f"바탕 영상 길이를 읽지 못했습니다: {path}\n{r.stderr.strip()}")
    return float(out)


def available():
    if not FOOTAGE.exists():
        return []
    return sorted(p for p in FOOTAGE.glob("*.mp4"))


def selftest():
    """가짜 바탕 영상으로 파이프라인만 점검한다. 녹화본이 오기 전에 깨진 데를 찾아둔다."""
    with tempfile.TemporaryDirectory() as td:
        fake = pathlib.Path(td) / "fake.mp4"
        run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
             "-i", f"testsrc=size=720x1560:rate={FPS}:duration=10",
             "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(fake)])
        out = build(fake, "986회를 돌려보니 23번 당첨돼 있었습니다", "오늘의 무작위 번호",
                    pathlib.Path(td) / "out.mp4")
        info = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_name,width,height:format=duration",
             "-of", "default=nw=1", str(out)], capture_output=True, text=True).stdout
        size = out.stat().st_size
        OUT.mkdir(parents=True, exist_ok=True)
        shutil.copy(out, OUT / "_selftest.mp4")
    print(info.strip())
    print(f"크기 {size / 1024 / 1024:.1f}MB")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--footage")
    ap.add_argument("--kind", choices=C.KINDS, default="replay")
    ap.add_argument("--day")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)

    if a.list:
        got = available()
        print(f"바탕 영상 {len(got)}개 ({FOOTAGE})")
        for p in got:
            print(" ", p.name, f"{p.stat().st_size / 1024 / 1024:.1f}MB")
        if not got:
            print("  없음 — 녹화본을 여기에 두면 그 위에 그날 훅을 얹는다.")
        return 0
    if a.selftest:
        return selftest()

    day = datetime.date.fromisoformat(a.day) if a.day else datetime.date.today()
    out = build_for(a.kind, day, a.footage)
    print(f"만듦: {out}  {out.stat().st_size / 1024 / 1024:.1f}MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
