# gzclab-threads

Threads(@gzclab) 자동 발행. 큐에 쌓아둔 글을 하루 3번(KST 07:07 / 12:07 / 19:07) 하나씩 발행하고,
글에 `link`가 있으면 본문이 아니라 **첫 댓글**로 링크를 붙인다.

- `queue.json` — 발행 대기열. 위에서부터 순서대로 나간다. `status`는 `pending` / `published`.
- `publish.py` — 큐에서 하나 꺼내 발행. 표준 라이브러리만 쓴다(설치할 의존성 없음).
- `.github/workflows/publish.yml` — cron 트리거.
- `.github/workflows/refresh-token.yml` — 매월 1일 액세스 토큰 갱신(60일 만료 대비).
- `test_publish.py` — `python test_publish.py`. 네트워크 없이 큐 처리 로직만 검증.

## 1. Threads 액세스 토큰 발급 (수동, 최초 1회)

1. https://developers.facebook.com/apps 에서 앱 생성 → 사용 사례에서 **Threads API** 선택.
2. 앱 설정에서 **Threads 앱 ID / 앱 시크릿**을 확인한다(페이스북 앱 ID와 다른 값이다).
3. 권한(스코프)에 `threads_basic`, `threads_content_publish`, `threads_manage_replies`를 추가한다.
   (`threads_manage_replies`가 있어야 첫 댓글 링크가 나간다.)
4. 앱에 @gzclab 계정을 Threads 테스터로 추가하고, 계정 쪽에서 수락한다.
5. 인증 창(Authorization Window)으로 로그인해 코드 → **단기 토큰(1시간)** 을 받는다.
6. 단기 토큰을 **장기 토큰(60일)** 으로 교환한다:
   `GET https://graph.threads.net/v1.0/access_token?grant_type=th_exchange_token&client_secret=<앱시크릿>&access_token=<단기토큰>`

## 2. GitHub 시크릿 등록

| 시크릿 | 값 |
| --- | --- |
| `THREADS_TOKEN` | 위에서 받은 장기 토큰 |
| `TELEGRAM_BOT_TOKEN` | gzclab_bot 토큰 (`gzclab-web/.env`와 동일) |
| `TELEGRAM_CHAT_ID` | 같은 파일의 chat id |
| `GH_PAT` | 토큰 자동 갱신용. **Fine-grained PAT**, 이 저장소만 선택, 권한은 `Secrets: Read and write` **하나만**. 만료는 `No expiration`. 없으면 갱신만 실패하고 발행은 토큰 만료일까지 계속 된다 |

> `repo` 클래식 스코프는 모든 저장소의 전체 통제권을 준다. 여기 필요한 건 이 저장소의
> 시크릿 쓰기 하나뿐이라 fine-grained로 좁힌다. PAT 자체에 만료를 걸면 그 날 갱신이
> 조용히 멈추므로 `No expiration`으로 둔다(대신 갱신 실패 시 텔레그램 알림이 온다).
>
> UI 주의: 토큰 상세 페이지는 읽기 전용 요약이라 권한 드롭다운이 없다. `Edit`
> (URL 끝에 `/edit`)로 들어가야 바꿀 수 있다. 목록에서 고를 것은 설명이
> "Manage Actions repository secrets"인 `Secrets` — `Dependabot secrets`,
> `Codespaces secrets`, `Secret scanning alerts`는 다른 것이다.

## 3. 한도

- GitHub Actions: 이 저장소는 public이라 실행 분이 **무제한**이다. (private으로 돌릴 경우
  무료 2,000분/월이고, 발행 잡 회당 1분 미만 × 하루 3회 = 월 90분으로 한도의 4.5%.)
- `districts.json`은 커밋하지 않는다(.gitignore). lottorich 원본 집계를 공개 저장소에
  재배포하지 않기 위한 것이고, 발행에는 `queue.json`만 쓰이므로 없어도 돌아간다.
  구별 글을 더 만들 때만 `python build_districts.py`로 로컬에서 다시 받으면 된다.
- Threads API: 프로필당 24시간 이동 기준 **250건**. 하루 3건이면 1.2%.
- 토큰: 60일 만료. **매주 일요일** 자동 갱신되며(갱신할 때마다 만료가 60일로 리셋),
  실패하면 텔레그램 알림 + Actions 잡도 빨간불로 끝난다. 주 1회면 만료 전에 8번의
  기회가 있어서, 한두 번 실패해도 토큰이 죽지 않는다.

## 4. 운영

- 큐가 3개 이하로 떨어지면 발행 알림에 경고가 붙는다. 그때 `queue.json`에 다음 글을 채운다.
- 발행 실패 시 텔레그램으로 사유가 오고 잡이 실패로 끝난다. 큐 항목은 `pending`으로 남아 다음 회차에 재시도된다.
- 급하게 한 건 더 내보내려면 Actions 탭에서 `Publish to Threads`를 수동 실행한다.
