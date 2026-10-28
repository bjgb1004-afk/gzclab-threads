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

from PIL import Image, ImageDraw

import cards as C

sys.stdout.reconfigure(encoding="utf-8")

HERE = pathlib.Path(__file__).parent
FOOTAGE = HERE / "assets" / "footage"
OUT = HERE / "reels"

RW, RH = 1080, 1920      # 9:16. 릴스가 화면을 꽉 채우는 비율
FPS = 30
HOOK_SEC = 3.0           # 훅이 떠 있는 시간. 첫 3초에 멈추게 하지 못하면 나머지는 안 본다
OUTRO_SEC = 2.5
BODY_SEC = 7.0           # 바탕 영상에서 쓸 길이
FADE = 0.4

# 소재별 편집. start: 앞에서 버릴 초(첫 장면이 불리한 영상), speed: 배속(스크롤 사이 멈춤을 줄이고
# 결과 화면까지 담는다). 녹화본을 다시 찍으면 여기만 맞춘다.
PROFILE = {
    "genius": {"start": 0.0, "speed": 1.6},   # 12초 → 7.5초
    "replay": {"start": 0.0, "speed": 1.25},  # 10초 → 8초. 결과(합계 금액)까지 나온다
    "band": {"start": 3.2, "speed": 1.0},     # 7초 → 3.8초. 첫 2초는 '당첨 0원' 목록이라 자른다
}


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
    """위쪽에 훅, 아래는 투명. 영상이 비치도록 글자 뒤에만 어두운 막을 깐다."""
    im = Image.new("RGBA", (RW, RH), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    size = 92
    f = C.font(size, "black")
    lines = _wrap(d, hook, f, RW - 120)
    while len(lines) > 4 and size > 56:
        size -= 8
        f = C.font(size, "black")
        lines = _wrap(d, hook, f, RW - 120)

    block = len(lines) * int(size * 1.2) + (90 if sub else 0)
    top = 210
    # 글자 뒤 어두운 막. 앱 화면이 밝아도 흰 글자가 읽힌다.
    d.rectangle([0, top - 70, RW, top + block + 70], fill=(0, 0, 0, 150))

    y = top
    for ln in lines:
        _center(d, y, ln, f, (255, 255, 255, 255))
        y += int(size * 1.2)
    if sub:
        _center(d, y + 18, sub, C.font(46, "bold"), C.CREAM + (255,))

    im.save(path)
    return path


def outro_png(path):
    """마지막 장면. 카드의 CTA와 같은 말을 쓴다 — 채널마다 다른 약속을 하지 않는다."""
    im = C.cta_slide().convert("RGB").resize((RW, int(RW * C.H / C.W)))
    canvas = Image.new("RGB", (RW, RH), C.BG_BOTTOM)
    canvas.paste(im, (0, (RH - im.height) // 2))
    canvas.save(path, "JPEG", quality=92)
    return path


def build(footage, hook, sub, out_path, body_sec=BODY_SEC, start=0.0, speed=1.0):
    """바탕 영상 + 훅 + 마무리 → 릴스 한 편."""
    footage = pathlib.Path(footage)
    if not footage.exists():
        raise FileNotFoundError(f"바탕 영상이 없습니다: {footage}")
    out_path = pathlib.Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        hk = hook_png(hook, sub, td / "hook.png")
        outro = outro_png(td / "outro.jpg")
        body = td / "body.mp4"
        tail = td / "tail.mp4"

        # 1) 바탕 영상을 9:16으로 채우고(넘치는 쪽은 잘라낸다) 길이를 맞춘 뒤 훅을 얹는다.
        #    훅은 HOOK_SEC 동안만 보이고 부드럽게 사라진다.
        vf = (
            f"setpts=PTS/{speed},scale={RW}:{RH}:force_original_aspect_ratio=increase,"
            f"crop={RW}:{RH},fps={FPS},format=yuv420p[v];"
            f"[1:v]format=rgba,fade=t=out:st={HOOK_SEC - FADE}:d={FADE}:alpha=1[hk];"
            f"[v][hk]overlay=0:0:format=auto,trim=0:{body_sec},setpts=PTS-STARTPTS[outv]"
        )
        run(["ffmpeg", "-y", "-loglevel", "error",
             "-ss", str(start), "-t", str(body_sec * speed), "-i", str(footage),
             # 훅은 정지 이미지라 한 프레임뿐이면 페이드가 걸리지 않고 끝까지 남는다 → 반복 입력으로 시간축을 준다
             "-loop", "1", "-framerate", str(FPS), "-t", str(body_sec), "-i", str(hk),
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
    if kind == "genius":
        # 바탕 영상이 다섯 천재 탭을 차례로 훑는다. 그날 한 명만 말하면 화면(아르키메데스부터 시작)과 어긋난다.
        draw_no = sub.split("회")[0]
        hook, sub = "수학자 5명의 방식으로 뽑은 번호", f"{draw_no}회 · 천재들의 한수"
    footage = pathlib.Path(footage) if footage else FOOTAGE / f"{kind}.mp4"
    p = PROFILE.get(kind, {})
    start, speed = p.get("start", 0.0), p.get("speed", 1.0)
    # 쓸 수 있는 길이(버린 앞부분 제외, 배속 반영)만큼만 쓴다. 영상이 짧은데 7초를 요구하면 끝이 멈춘 화면이 된다.
    body = min(BODY_SEC if "speed" not in p else 99.0, max(1.0, (_duration(footage) - start) / speed))
    return build(footage, hook, sub, OUT / f"{reel_name(kind, day)}.mp4",
                 body_sec=body, start=start, speed=speed)


def _duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout.strip()
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
