# gzclab-threads

Threads(@gzclab) 자동 발행. 큐에 쌓아둔 글을 하루 3번(KST 07:07 / 12:07 / 19:07) 하나씩 발행하고,
글에 `link`가 있으면 본문이 아니라 **첫 댓글**로 링크를 붙인다.

- `queue.json` — 발행 대기열. 위에서부터 순서대로 나간다. `status`는 `pending` / `published`.
- `publish.py` — 큐에서 하나 꺼내 발행. 표준 라이브러리만 쓴다(설치할 의존성 없음).
- `.github/workflows/publish.yml` — cron 트리거.
- `.github/workflows/refresh-token.yml` — 매주 일요일 액세스 토큰 갱신(60일 만료 대비).
- `collect_insights.py` + `insights.yml` — 발행 24시간 지난 글의 조회·좋아요·댓글 수집.
- `auto_reply.py` + `auto-reply.yml` — 댓글에 달린 지역명을 읽어 그 동네 TOP3를 답글로 단다.
- `bake_replies.py` + `district_replies.json` — 구별 답글 문장을 미리 구워둔 것.
  `districts.json`이 Actions에 없어서 런타임에 만들 수 없다.
- `test_publish.py`, `test_collect_insights.py`, `test_auto_reply.py` —
  `python test_*.py`. 네트워크 없이 로직만 검증.

## 1. Threads 액세스 토큰 발급 (수동, 최초 1회)

1. https://developers.facebook.com/apps 에서 앱 생성 → 사용 사례에서 **Threads API** 선택.
2. 앱 설정에서 **Threads 앱 ID / 앱 시크릿**을 확인한다(페이스북 앱 ID와 다른 값이다).
3. 권한(스코프)에 `threads_basic`, `threads_content_publish`, `threads_manage_replies`,
   `threads_manage_insights`를 추가한다. 각각 무엇에 쓰는지:

   | 스코프 | 없으면 안 되는 것 |
   | --- | --- |
   | `threads_basic` | 전부 |
   | `threads_content_publish` | 본문 발행, 링크 답글, 자동 답글 — **쓰기는 전부 이것 하나면 된다** |
   | `threads_manage_replies` | 댓글 **읽기**(`/{id}/conversation`). 자동 답글이 누가 뭐라 달았는지 알려면 필요 |
   | `threads_manage_insights` | 조회수·좋아요 수집(`collect_insights.py`) |

   > 스코프는 인증 창에서 실제로 체크된 것만 토큰에 붙는다. 앱 설정에 적어두는 것만으로는
   > 안 붙는다. 2026-09-25에 이 문서에 `threads_manage_replies`가 적혀 있었는데도
   > 실제 토큰에는 없어서 `code 10: Application does not have permission`이 났다.
   > 발급 후 아래로 확인할 것:
   >
   > ```
   > curl -s "https://graph.threads.net/v1.0/<내 게시물 id>/conversation?fields=id,text&access_token=<토큰>"
   > ```
   >
   > `{"data":[...]}`가 나오면 붙은 것이고, `code 10`이면 안 붙은 것이다.
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
- Threads API: 프로필당 24시간 이동 기준 **250건**. 발행 3건 + 링크답글 3건에 자동 답글
  최대 50건을 더해도 56건으로 한도의 22%다.
- 토큰: 60일 만료. **매주 일요일** 자동 갱신되며(갱신할 때마다 만료가 60일로 리셋),
  실패하면 텔레그램 알림 + Actions 잡도 빨간불로 끝난다. 주 1회면 만료 전에 8번의
  기회가 있어서, 한두 번 실패해도 토큰이 죽지 않는다.

## 4. 운영

- 큐가 3개 이하로 떨어지면 발행 알림에 경고가 붙는다. 그때 `queue.json`에 다음 글을 채운다.
- 발행 실패 시 텔레그램으로 사유가 오고 잡이 실패로 끝난다. 큐 항목은 `pending`으로 남아 다음 회차에 재시도된다.
- 급하게 한 건 더 내보내려면 Actions 탭에서 `Publish to Threads`를 수동 실행한다.
- 댓글 자동 답글: "구 이름 남겨줘" 형 글에 달린 댓글에 10분마다 그 동네 TOP3를 답한다.
  지역명을 못 알아들으면 답하지 않는다 — 그건 직접 답하면 된다.
  하루 상한 50건, 1회 10건, 최근 7일 글만 본다. 답글에는 링크를 넣지 않는다(같은
  댓글창에 같은 링크가 쌓이면 스팸으로 읽힌다).
- 새 시도 데이터를 추가했으면 로컬에서 `python bake_replies.py`를 돌리고
  `district_replies.json`을 커밋해야 자동 답글에 반영된다. `districts.json`은 로컬에만
  있으므로 Actions는 구운 결과만 본다.
