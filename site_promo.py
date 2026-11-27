"""gzclab이 만든 다른 서비스 홍보 글. 2026-11-23부터 14일간 매일 (2026-11-23 유저 요청).

  05:07 현장원(구글 플레이, 11/25부터)     id: hjone-<key>
  20:07 케이스탁(k-stockreplay.pe.kr)      id: kstock-<key>
  21:07 골목 놀이터(golmok-play)            id: golmok-<key>
  22:07 직장비교 앱(구글 플레이)             id: jobapp-<key>
        └ 11/28부터 하루 5개(08:07·12:37·16:37·19:37·22:07), 실제 공공기관 공고   id: jobapp-real-MMDD-N

gzclab은 원래 '직접 만든 웹/앱 홍보' 계정이다. 다만 팔로워 1,300명은 로또 글로 모였고, 주제가 다른
한글폭탄 글은 조회 중간값 152(번호 글 1,044)였다. 그래서 시리즈 첫 글은 "복권명당 만든 사람이"로
기존 팔로워와 잇고, 글마다 첫 줄은 훅·끝은 질문 하나로 쓴다(social-media-skills threads-post).

사실만 쓴다 — 기능·숫자는 각 저장소 코드에서 확인한 값이다(k-stockreplay, golmok-play, jobscale).
케이스탁 글은 매수·매도 권유로 읽히지 않게 쓴다(사이트 원칙: 추천 없음, 실시간 시세 없음).

본문에는 링크·주제 태그를 넣지 않고, 링크는 첫 댓글로 단다(2026-11-23 유저 요청). — 프로필에 링크 답글이
줄줄이 쌓이는 걸 유저가 싫어했다(publish.LINK_REPLY_PREFIXES, 2026-11-06).
auto_reply 대상이 아니다("구 이름 남겨줘"를 쓰지 않는다). 댓글은 사람이 단다.

토요일 21시대에는 로또 결과 글(picks-*-result)이 나간다. 같은 계정에서 몇 분 차로 두 글이 붙지
않게, 어떤 글이든 GAP_MIN 안에 나간 게 있으면 다음 틱으로 미룬다.
"""

import datetime
import json
import re
import pathlib
import sys

import urllib.request

import publish

KST = datetime.timezone(datetime.timedelta(hours=9))
QUEUE = pathlib.Path(__file__).with_name("queue.json")
LIMIT = 500
GAP_MIN = 15
LATE_MIN = 240  # 이만큼 늦으면 그날 그 글은 건너뛴다. 루프가 끊겼다 살아나도 늦게라도 나가게(2026-11-25 유저: 케이스탁도 나가라) — 몰림은 GAP_MIN이 15분 간격으로 푼다. 자정은 넘기지 않는다
D = datetime.date

KSTOCK = "https://k-stockreplay.pe.kr"
GOLMOK = "https://golmok-play.gzclab.workers.dev"
HJONE = ("https://play.google.com/store/apps/details?id=com.gzc.hyeonjangone"
         "&referrer=utm_source%3Dthreads%26utm_medium%3Dsocial%26utm_campaign%3Dpromo")
JOBAPP = ("https://play.google.com/store/apps/details?id=io.github.bjgb1004_afk.jobscore"
          "&referrer=utm_source%3Dthreads%26utm_medium%3Dsocial%26utm_campaign%3Dpromo")

SERIES = {
    "hjone": {"time": (5, 7), "name": "현장원", "lead": "현장사업자 ONE 받기 (구글 플레이)", "link": HJONE},
    "kstock": {"time": (20, 7), "name": "케이스탁", "lead": "케이스탁 바로가기", "link": KSTOCK},
    "golmok": {"time": (21, 7), "name": "골목 놀이터", "lead": "골목 놀이터 바로가기", "link": GOLMOK},
    "jobapp": {"time": (22, 7), "name": "직장비교", "lead": "직장비교 받기 (구글 플레이)", "link": JOBAPP},
}

START = D(2026, 11, 23)


def _days(texts, start=START):
    return [{"date": start + datetime.timedelta(i), **t} for i, t in enumerate(texts)]


KSTOCK_POSTS = _days([
    {"key": "intro", "text": """로또 번호 앱 만든 사람이 만든 주식 사이트도 있음.

케이스탁은 "내 관심종목에 오늘 무슨 일이 있었나"만 정리해줌.
그날 나온 공시, 배당, 지분 변화를 모아서 보여주는 곳.

실시간 시세 없음. 이 종목 사라 같은 추천도 없음.
일부러 뺐음.

주식 하는 사람들, 공시는 매일 챙겨봄? 아니면 뉴스 뜨고 나서야 앎?"""},
    {"key": "today", "text": """주식 앱 열면 차트부터 보는데, 진짜 중요한 건 공시일 때가 많음.

케이스탁 '오늘' 탭은 네 칸으로 나눠놨음.
오늘 새로 생긴 공시 / 중요 FACT / 배당 이벤트 / 지분·관계 변화.
누르면 DART 원문으로 바로 넘어감.

주말엔 공시가 없으니 다음 거래일 아침에 갱신됨.

공시 제목만 보고 호재인 줄 알았는데 아니었던 적 있음?"""},
    {"key": "13f", "text": """워런 버핏이 지금 뭘 들고 있는지, 공시로 다 나옴.

케이스탁 '큰손 따라보기'에 미국 13F 공시를 정리해놨음.
버크셔 해서웨이 30종목, 브리지워터 974종목(9월 말 기준).
직전 분기 대비 신규 편입·증가·감소·전량 매도를 표시함.

단, 13F는 분기 끝나고 최대 45일 뒤에 나와서 이미 늦은 정보임.

유명 투자자 따라 사본 적 있음? 결과는 어땠음?"""},
    {"key": "congress", "text": """미국 하원의원은 주식 사고팔면 신고해야 함.

STOCK Act라는 법 때문인데, 거래 후 최대 45일 안에 신고하고 금액은 구간으로만 공개됨.
케이스탁 '큰손 따라보기'에서 의원들이 최근 신고한 거래랑, 많이 거래한 종목을 모아서 볼 수 있음.
본인·배우자·자녀 명의가 섞여 있다는 것도 같이 적어둠.

한국 국회의원 주식 거래도 이렇게 바로바로 공개되면 좋겠다고 봄?"""},
    {"key": "kr5pct", "text": """국민연금이 지분 5% 넘게 들고 있는 회사, 어디서 확인함?

5% 넘게 사면 '대량보유상황보고서'를 내야 함.
케이스탁 '큰손 따라보기' 국내 탭에 그 보고서를 모아놨음.
국민연금공단, 자산운용사들이 어느 종목을 몇 % 들고 있는지, 직전 보고보다 늘었는지 줄었는지.

보고 사이에 사고판 건 안 보임. 그건 공시의 한계.

국민연금이 늘린 종목, 같이 보는 편임?"""},
    {"key": "room", "text": """5분 동안 1,000만 원으로 몇 % 낼 수 있을까.

케이스탁 '리플레이 방'은 여럿이 같은 차트를 보면서 사고파는 게임임.
3초마다 봉 하나가 열리고, 한 판은 5분.
판 끝나면 수익률 순위가 바로 뜸. 한 방에 최대 20명.

진짜 돈 아님. 상금도 없음. 연습용.

5분짜리 판이면 너는 몇 번 사고팔 것 같음?"""},
    {"key": "synthetic", "text": """리플레이 방 차트는 진짜 종목 차트가 아님.

실제 시세를 여러 사람한테 다시 뿌리는 건 문제가 될 수 있어서, 실제처럼 움직이는 가상 차트를 만들었음.
갑자기 튀는 꼬리, 변동성이 몰려오는 구간, 급등락, 거래량까지 진짜 주가 움직임을 흉내 냄.

그래서 종목 이름 보고 감으로 맞히는 게 안 됨. 차트만 보고 판단해야 함.

가상 차트랑 진짜 차트, 보고 구분할 자신 있음?"""},
    {"key": "myreplay", "text": """지난 차트를 한 봉씩 가리고 다시 보면, 내가 얼마나 늦게 파는지 보임.

케이스탁 개인 리플레이는 내 HTS에서 받은 일봉 엑셀·CSV 파일을 올리면 됨.
처음엔 앞쪽 30개 봉만 보이고, 재생 누르면 한 봉씩 열림.
사고판 자리는 차트에 화살표로 남고, 손익이 바로 계산됨.

올린 파일은 서버로 안 감. 내 기기에만 저장됨.

과거 차트로 매매 연습 해본 적 있음?"""},
    {"key": "heatmap", "text": """오늘 시장 돈이 어느 업종으로 몰렸는지, 한 장으로 보임.

케이스탁 '업종 지도'는 그날 거래대금이 몰린 업종을 히트맵으로 보여줌.
칸 하나 누르면 그 업종 종목들이 거래대금 순으로 나옴.
날짜를 바꾸면 지난 날도 볼 수 있음.

장 마감 뒤에 자동으로 채워짐.

장 끝나고 오늘 무슨 업종이 올랐는지 매일 확인하는 편임?"""},
    {"key": "nologin", "text": """케이스탁에는 회원가입이 없음.

관심종목은 서버가 아니라 내 브라우저에 저장됨.
그래서 가입 안 하고 바로 담으면 됨.
대신 브라우저 데이터 지우면 같이 사라짐.

담아둔 종목 정리를 '내 관심종목 리포트'로 복사해서 메모장이나 카톡에 붙여넣을 수 있음.

주식 정보 보려고 가입하라고 하면 그냥 나가는 편임?"""},
    {"key": "dividend", "text": """배당 공시, 놓치면 1년 기다려야 하는 경우도 있음.

케이스탁 '배당·이벤트' 탭은 관심종목의 배당·주주총회 공시만 골라서 모아줌.
정확한 배당락일이랑 주당 배당금은 공시 원문에 있어서, 원문 링크를 같이 붙여둠.
실적발표 일정은 아직 안 됨. 솔직하게 적어둠.

배당주 하는 사람들, 배당 공시 어디서 챙겨봄?"""},
    {"key": "quickstart", "text": """관심종목이 하나도 없으면 첫 화면이 텅 빔. 그게 싫었음.

그래서 케이스탁은 처음 들어오면 오늘 거래대금 상위 종목을 먼저 보여줌.
종목마다 거래대금(억 단위)이랑 20일 추이가 붙어 있고,
'한 번에 담기' 누르면 관심종목에 한꺼번에 들어감.
담는 순간 공시·배당 칸이 채워짐.

요즘 거래대금 제일 많은 종목, 짐작 가는 거 있음?"""},
    {"key": "valuechain", "text": """2차전지 테마라고 다 같은 회사가 아님.

셀 만드는 회사, 소재 만드는 회사, 장비 대는 회사, 리사이클링 회사가 다 다름.
케이스탁 '업종 지도'에 반도체·2차전지·방산·조선·원전 등 9개 테마를 밸류체인 단계별로 정리해놨음.
이건 자동이 아니라 직접 손으로 정리한 거임.

다음에 정리했으면 하는 테마 하나만 댓글로 줘봐."""},
    {"key": "why", "text": """케이스탁은 사람이 매일 글을 쓰지 않음.

공시, 배당, 큰손 보유 현황, 업종 지도 전부 정해진 규칙대로 매일 자동으로 모아짐.
AI 요약도 안 씀. 원문이랑 사실만 보여주는 게 목표.
그래서 유지비가 거의 안 듦.

매수 추천이 없는 것도 같은 이유임. 판단은 보는 사람 몫.

주식 정보 사이트에 딱 하나 바란다면 뭐임?"""},
])

GOLMOK_POSTS = _days([
    {"key": "intro", "path": "", "text": """로또 앱 만든 사람이 이번엔 골목 놀이를 만들었음.

말뚝박기, 경찰과 도둑, 땅따먹기.
설치 없이 링크 하나 누르면 바로 됨.
친구한테 링크 보내면 같이 한 판.

어릴 때 학교 끝나고 골목에서 제일 많이 한 놀이, 뭐였음?"""},
    {"key": "malttuk", "path": "/malttuk", "text": """말뚝박기를 이제 다치지 않게 할 수 있음.

탭하면 달리고, 발판 앞에서 한 번 더 탭하면 점프.
풀파워로 맨 앞까지 날면 필살 말뚝 박기.
세게 올라타서 말을 무너뜨리면 이김.

착지하는 순간 한 번 더 탭하면 퍼펙트 착지, 충격 1.5배.

말뚝박기 할 때 너는 타는 쪽이었음, 말 쪽이었음?"""},
    {"key": "deulsseok", "path": "/malttuk", "text": """말뚝박기에서 제일 웃긴 구간을 넣었음. 들썩들썩.

다 올라타면 5초 동안 연타 대결.
말은 기우는 반대쪽을 연타해서 버티고, 위에 탄 쪽은 꽉 잡아야 함.
버티면 말머리랑 가위바위보.

먼저 5판 이기면 끝.

어릴 때 말뚝박기 하다 말 무너져서 다 같이 깔린 적 있음?"""},
    {"key": "rps", "path": "/malttuk", "text": """가위바위보 꼭 늦게 내는 친구 있었음.

골목 놀이터 말뚝박기 친구 대전은 가위바위보를 둘 다 낸 다음에 동시에 공개함.
먼저 낸 쪽이 상대 화면에 안 보이게 서버에서 막아둠.
늦게 내기 원천 차단.

친구랑 하기 누르면 링크가 나오고, 카톡으로 보내면 바로 1:1.

너희 동네에도 늦게 내던 애 있었지?"""},
    {"key": "gyeongdo", "path": "/gyeongdo", "text": """이 놀이, 너희 동네에선 뭐라고 불렀음?

경찰과 도둑. 경도. 도둑과 경찰. 순경과 도둑.
골목 놀이터에선 '경찰과 도둑'으로 만들었음.

경찰은 도둑을 터치하면 감옥으로.
도둑은 감옥을 터치하면 잡힌 친구들이 전부 탈출.
최대 8명까지 같이 함.

부르는 이름 댓글로 남겨줘. 동네마다 다른지 궁금함."""},
    {"key": "gyeongdo-bots", "path": "/gyeongdo", "text": """경찰과 도둑은 사람이 모여야 재밌는데, 8명 모으기가 어려움.

그래서 빈자리는 컴퓨터 친구로 채울 수 있게 했음. 6명까지.
친구 둘만 있어도 판이 돌아감.
혼자 연습하기도 있음.

지난 판에 경찰이었으면 이번엔 도둑부터 시작함.

경도 할 때 너는 잘 잡는 쪽이었음, 잘 도망가는 쪽이었음?"""},
    {"key": "ttang", "path": "/ttang", "text": """땅따먹기 돌 튕기던 거 기억남?

골목 놀이터 땅따먹기 대전.
화면을 뒤로 끌었다 놓으면 돌이 튕겨 나감.
세 번 안에 내 땅으로 돌아오면 돌이 지나간 만큼 내 땅.
판 밖으로 나가거나 상대 땅에 멈추면 실패.

8턴 뒤 넓은 쪽이 이김.

땅따먹기 할 때 바닥에 뭘로 그렸음? 분필? 돌?"""},
    {"key": "ttang-steal", "path": "/ttang", "text": """땅따먹기에서 남의 땅을 뺏을 수 있게 만들었음.

내 선이 상대 땅을 감싸면 그 땅이 내 거.
대신 처음 집은 못 뺏음.
내 땅 선에 닿기만 해도 돌아온 걸로 쳐줌.

그래서 안전하게 조금씩 넓힐지, 크게 돌아서 한 방에 뺏을지 고민하게 됨.

너는 조금씩 가는 쪽임, 한 방 노리는 쪽임?"""},
    {"key": "kids", "path": "", "text": """요즘 애들 골목에서 말뚝박기 하는 거 거의 못 봄.

모일 골목도 줄었고, 다칠까 봐 말리기도 하고.
그래서 폰으로 링크 하나 누르면 바로 할 수 있게 만들었음.
설치도 가입도 없음.

어른이 애한테 '이거 아빠 엄마 어릴 때 하던 거야' 하면서 같이 해도 됨.

아이한테 알려주고 싶은 옛날 놀이 하나 고르면 뭐임?"""},
    {"key": "phone", "path": "", "text": """골목 놀이터는 폰에서 바로 됨.

말뚝박기는 화면을 가로로 돌리면 더 커짐.
경찰과 도둑은 왼손으로 화면을 끌어서 움직이고, 달리기 버튼으로 잠깐 빨라짐.
PC에서는 방향키나 WASD, 스페이스.

앱 깔 필요 없음. 링크가 곧 게임.

이런 거 폰으로 함, PC로 함?"""},
    {"key": "next", "path": "", "text": """골목 놀이터 다음 게임을 고르는 중임.

후보는 셋.
무궁화 꽃이 피었습니다.
딱지치기.
구슬치기.

다 '곧 나와요'로 걸어놨는데, 순서는 아직 안 정함.
댓글 보고 참고할 생각.

셋 중에 뭐부터 하고 싶음?"""},
    {"key": "rules", "path": "/malttuk", "text": """말뚝박기 규칙, 동네마다 달랐음.

골목 놀이터 버전은
타는 쪽이 다 올라타면 버티기 연타 대결,
버티면 말머리랑 가위바위보,
너무 짧게 뛰거나 친구 위에 겹쳐 앉다 떨어지면 탄 쪽이 짐.

다음 업데이트 때 참고하려고 함.
너희 동네 말뚝박기엔 어떤 규칙이 있었음?"""},
    {"key": "group", "path": "/gyeongdo", "text": """연말 모임에서 할 거 없으면 이거 해봐.

경찰과 도둑 '친구들이랑 하기' 누르면 대기실 링크가 나옴.
그 링크를 단톡방에 뿌리면 최대 8명이 한 판에 들어옴.
방장이 시작 누르면 끝.

폰만 있으면 되고 설치 없음.

단톡방에 이거 뿌리면 몇 명이나 들어올 것 같음?"""},
    {"key": "fav", "path": "", "text": """골목 놀이터 2주 동안 소개했음.

말뚝박기 1:1 대전.
경찰과 도둑 최대 8명.
땅따먹기 대전.

해본 사람 있으면 어느 게 제일 재밌었는지,
어디가 불편했는지 한 줄만 남겨줘.
다음 게임 만들 때 참고함.

셋 중에 하나만 다시 한다면 뭐 할 거임?"""},
])

JOBAPP_POSTS = _days([
    {"key": "intro", "text": """로또 앱 만든 사람이 만든 다른 앱도 있음. 직장비교.

공고 세 개 앞에 두고 뭐가 제일 나은지 멈춘 적 있지?
월급은 A가 높은데 B는 집에서 10분이고, C는 6시 퇴근인데 주 6일.

급여·통근·퇴근시각·출근시각·근무일수·업무강도·고용안정 7가지를
내가 정한 중요도로 100점 만점 채점해서 순위를 매겨줌.

직장 고를 때 너한테 제일 중요한 거 하나만 꼽으면 뭐임?"""},
    {"key": "realwage", "text": """월급 30만 원 더 주는 회사가 실제로는 더 짠 경우.

A: 월 260만 원, 하루 8시간, 편도 1시간
B: 월 230만 원, 하루 8시간, 편도 10분

근무시간으로만 나누면 A 14,960원, B 13,234원.
왕복 통근 시간까지 일한 걸로 치면 A 11,968원, B 12,704원.
뒤집힘.

직장비교는 이 실질시급을 자동으로 계산해줌.

너라면 A 감, B 감?"""},
    {"key": "convert", "real": True, "text": """일급 100,620원이랑 월급 210만 원, 뭐가 더 많음?

공고마다 연봉, 월급, 일급, 시급으로 제각각 적혀 있어서 비교가 안 됨.
직장비교는 전부 월급으로 바꿔서 같은 줄에 세워줌.
일급 100,620원에 주 5일이면 월 219만 원.

알바 공고 볼 때 시급으로 보는 편임, 월급으로 계산해보는 편임?"""},
    {"key": "presets", "text": """직장 고르는 기준은 사람마다 다름.

직장비교에 기본 세팅 4개를 넣어놨음.
육아 병행형 / 돈 우선형 / 몸 편한 일형 / 워라밸형.
하나 누르면 순위가 그 자리에서 다시 매겨짐.
별점을 직접 옮겨도 바로 바뀜.

넷 중에 너는 어느 형임?"""},
    {"key": "filter", "real": True, "text": """절대 양보 못 하는 조건이 있으면 아예 걸러버리면 됨.

직장비교에 선을 정해두면
"퇴근 18시 30분까지", "통근 40분 이내", "최저 월급 230만 원", "주 5일까지"
이걸 넘는 공고는 탈락 처리되고, 어느 조건 때문에 떨어졌는지 사유가 같이 뜸.

너한테 절대 양보 못 하는 조건 하나는 뭐임?"""},
    {"key": "paste", "text": """공고 하나 입력하는 데 칸 열 개 채우라고 하면 안 씀.

그래서 직장비교는 공고 내용을 복사해서 붙여넣으면
회사명, 급여, 출퇴근 시각, 근무요일을 알아서 채움.
드래그 복사가 막힌 사이트는 서클 투 서치나 구글 렌즈로 글자 가져오는 방법을 앱 안에 적어둠.

공고 볼 때 보통 어디서 봄? 앱? 사이트?"""},
    {"key": "public", "real": True, "text": """공기업 채용공고를 앱 안에서 바로 찾을 수 있게 했음.

지방공기업, 지방 출자·출연기관 채용공고를 지역별로 보여주고
마감 임박한 순서로 정렬함. 하루 한 번 새로 받아옴(공공데이터포털).
마음에 드는 공고는 눌러서 비교 목록에 바로 담으면 됨.

공고에 근무시간이 안 적혀 있으면 '확인 필요'로 표시해둠.

공기업 준비해본 적 있음?"""},
    {"key": "takehome", "text": """첫 월급 받고 생각보다 적어서 놀란 적 있지?

직장비교에 월급 실수령액 계산기를 넣었음.
급여를 넣으면 4대보험료랑 소득세를 뗀 금액이 바로 나옴.
식대 같은 비과세(기본 20만 원)까지 반영함.
시급·일급·연봉으로 넣어도 됨.

첫 월급 받았을 때 제일 먼저 뭐 했음?"""},
    {"key": "table", "real": True, "text": """공고 두 개를 머릿속으로 비교하면 조건 네 개 넘어가는 순간 꼬임.

직장비교 '나란히 비교표'는
월급, 실질시급, 근무시간, 통근, 근무일수, 업무강도, 주말근무를
한 표에 세로로 세워서 공고끼리 바로 견줌.

종이에 표 그려서 비교해본 적 있음?"""},
    {"key": "privacy", "text": """직장비교에는 서버가 없음.

등록한 공고랑 설정은 전부 내 폰 안에만 저장됨.
회원가입 없음, 로그인 없음, 광고 없음, 추적 도구 없음.
이직 고민 중인 거 회사에 들킬 일도 없음.

대신 폰 바꿀 땐 백업 파일로 옮겨야 함.

구직 앱 쓸 때 개인정보 신경 쓰는 편임?"""},
    {"key": "share", "real": True, "text": """이직 고민은 혼자 하기 어려움.

직장비교에서 결과를 링크로 만들어서 보내면
받는 사람은 읽기 전용으로 내 순위를 그대로 봄.
가족이나 친구한테 "이거 보고 어디가 나은지 말해줘" 하기 좋음.

이직할 때 누구한테 제일 먼저 물어봄?"""},
    {"key": "move", "text": """지금 회사랑 새 공고, 숫자로 비교해본 적 있음?

직장비교에 지금 자리도 공고처럼 하나 넣으면 됨.
월급, 통근, 퇴근시각을 같이 넣고 새 공고랑 나란히 세우면
"옮기면 월급은 오르는데 실질시급은 내려간다" 같은 게 바로 보임.

이직 고민할 때 제일 오래 붙잡고 있던 조건은 뭐였음?"""},
    {"key": "parttime", "real": True, "text": """시급 1만 2천 원이랑 1만 3천 원 중 어디가 나을까.

천 원 차이면 당연히 1만 3천 원 같은데,
버스 40분 더 타야 하면 얘기가 달라짐.

직장비교는 알바 두세 곳도 통근 시간까지 넣어서 실질시급으로 비교해줌.
통근을 넣을지 말지는 직접 고를 수 있음.

알바 고를 때 시급이랑 거리 중에 뭘 더 봄?"""},
    {"key": "score", "text": """직장비교 점수는 회사 평가가 아님.

'내가 정한 기준에 얼마나 맞나'를 점수로 바꾼 거라,
같은 공고도 사람마다 1위가 다름.
1위가 왜 1위인지는 한 문장으로 알려줌.

2주 동안 소개했음. 써본 사람 있으면 불편했던 점 한 줄만 남겨줘. 참고함.

너한테 좋은 직장의 기준 딱 하나는?"""},
])

# 현장원(현장사업자 ONE): 11/25부터 14일(11/24 새벽엔 Actions 루프가 멈춰 첫 글이 못 나가 하루 미룸), 새벽 05:07 (2026-11-23 유저 요청). 현장 나가기 전 시간대.
# 기능은 hyeonjang-one 코드 + 플레이 등록정보(10/3 버전)에서 확인한 것만. 전/후 사진 촬영은 코드에 있지만
# 플레이 최신 버전(10/3)에 아직 없어서 뺐다. '거래명세서'는 등록정보 문구엔 있어도 코드에 없어서 뺐다.
# 덜 AI스럽게: 장면으로 시작하고, 목록 줄 맞춤·이모지·"~해드립니다" 없이 현장 말투로.
HJONE_POSTS = _days([
    {"key": "intro", "text": """새벽 5시. 현장 나가기 전에 어제 공수 적어놨나부터 생각나는 사람 있음?

수첩에 적다가 비 맞아서 번지고
카톡 나에게 보내기로 적다가 묻히고
월말 되면 누구한테 얼마 받을지 다시 계산함.

그래서 만들었음. 현장사업자 ONE.
오늘 어느 현장에서 몇 공수 했는지 폰에 바로 찍어두는 앱.
인테리어, 설비, 전기, 타일, 목수 혼자 뛰는 사장님용.

다들 공수 기록 지금 어디다 하고 있음?"""},
    {"key": "gongsu", "text": """한 달 지나면 꼭 이 말 나옴.
"그날 내가 반 공수였나, 한 공수였나."

현장사업자 ONE은 공수를 0.5, 1, 1.5로 눌러서 적음.
달력에서 그날 누르고, 현장 고르고, 공수 누르면 끝.
이번 달 몇 공수 뛰었는지 현장별, 거래처별로 합계가 나옴.

반 공수 날 한 공수 받은 적은 없어도 그 반대는 있지 않음?"""},
    {"key": "receivable", "text": """일은 끝났는데 돈 안 들어온 현장, 지금 몇 군데인지 바로 말할 수 있음?

대부분 "거기 아직이었나" 정도로만 기억함.
현장사업자 ONE 미수금 화면은 아직 못 받은 현장만 따로 모아서 보여줌.
돈 들어오면 눌러서 입금 처리하면 됨.

받을 돈 제일 오래 묵혀본 게 몇 달이었음?"""},
    {"key": "invoice", "text": """청구서 하나 보내려고 밤에 컴퓨터 켜는 거, 이제 안 해도 됨.

현장사업자 ONE에서 작업 내역 고르면 청구서가 PDF로 나옴.
카톡으로 바로 보내거나 메일로 보내면 끝.
사업자 정보 한 번 넣어두면 매번 다시 안 적어도 됨.

거래처에 청구서 보낼 때 다들 뭘로 만듦? 엑셀? 한글? 손글씨?"""},
    {"key": "receipt", "text": """5월에 종합소득세 한다고 영수증 찾느라 차 안 다 뒤집어본 사람.

현장사업자 ONE은 비용 적을 때 영수증 사진을 같이 붙여둘 수 있음.
그리고 영수증 없는 비용만 따로 모아서 보여줌.
뭐가 빠졌는지 그때그때 보임.

영수증 제일 많이 잃어버리는 데가 어디임? 차? 작업복 주머니?"""},
    {"key": "tax", "text": """세무사 사무실에서 "자료 좀 정리해서 주세요" 들으면 막막하지.

현장사업자 ONE에 '세무자료 만들기'가 있음.
수입, 비용, 증빙, 미수금을 기간별로 묶어서 PDF로 뽑아줌.
엑셀로 열리는 파일(CSV)로도 됨.

세금 신고 혼자 함, 세무사한테 맡김?"""},
    {"key": "mileage", "text": """현장 왔다 갔다 하는 기름값, 장부에 넣고 있음?

현장사업자 ONE 설정에 km당 차량비를 한 번 적어두면
비용 넣을 때 차량비 고르고 주행거리만 쓰면 금액이 알아서 나옴.
km당 800원으로 해두면 왕복 40km는 32,000원.

하루에 현장 몇 군데까지 돌아봄?"""},
    {"key": "pyeong", "text": """도면엔 ㎡로 적혀 있는데 집주인은 "그래서 몇 평이에요?"

현장사업자 ONE 도구에 단위 변환 넣어둠.
㎡ 넣으면 평, m 넣으면 자·치로 바로 나옴.
1평 3.3058㎡, 1자 30.3cm 기준.

현장에서 아직 자·치로 말하는 분들 많음?"""},
    {"key": "vat", "text": """견적 말하면 꼭 돌아오는 질문. "부가세 포함이에요, 별도예요?"

현장사업자 ONE 부가세 계산기는 금액 하나 넣으면
그게 공급가일 때 합계, 합계일 때 공급가를 한 번에 보여줌.
1.1 곱했다 나눴다 머리 안 굴려도 됨.

견적 낼 때 부가세 포함으로 말함, 별도로 말함?"""},
    {"key": "offline", "text": """지하 현장 들어가면 폰 안 터지는 데 많음.

현장사업자 ONE은 서버가 없어서 인터넷 안 돼도 그냥 다 적힘.
가입도 로그인도 없음. 기록은 내 폰 안에만 있음.
대신 폰 바꾸기 전엔 백업 파일 하나 내보내서 옮겨야 함.

현장에서 폰 안 터져서 곤란했던 적 있음?"""},
    {"key": "history", "text": """2년 전에 했던 그 집에서 AS 전화 오면, 그때 뭐 했는지 기억남?

현장사업자 ONE에 거래처랑 현장 주소를 등록해두면
현장마다 언제 무슨 작업 했는지 기록이 쌓임.
메모도 같이 남겨둘 수 있음.
전화 받으면서 열어보면 됨.

AS 전화 오면 제일 먼저 뭐부터 찾아봄?"""},
    {"key": "calendar", "text": """이번 달 며칠 일했는지 세려면 달력 앞에서 손가락 접게 됨.

현장사업자 ONE은 첫 화면이 달력임.
일한 날은 표시가 남고, 날짜 누르면 그날 현장이랑 작업이 뜸.
빨간 날도 달력에 다 들어가 있음.

이번 달 며칠 뛰었음?"""},
    {"key": "maker", "text": """이 앱 만든 건 개발 회사가 아님. 혼자 앱 만드는 사람임.

공수는 수첩에, 받을 돈은 머릿속에, 영수증은 차 안에.
이렇게 세 군데 흩어져 있는 걸 하나로 모아보자고 만들었음.
그래서 화려한 건 없음. 대신 광고 없고 가입 없음.

써보고 "이거 하나만 있었으면" 하는 거 있으면 댓글로 줘. 다음 업데이트 때 참고함."""},
    {"key": "worst", "text": """현장 사장님들한테 하나만 물어보고 싶음.

일 끝나고 집에 와서 제일 하기 싫은 게 뭐임?
공수 정리, 영수증 정리, 청구서 만들기, 돈 달라고 연락하기.

현장사업자 ONE은 앞에 세 개 줄여보려고 만든 앱임.
마지막 건 앱이 대신 못 해줌.

너는 뭐가 제일 싫음?"""},
], start=D(2026, 11, 25))

# 직장비교 "real": True 날(격일 6개)은 그날 마감이 가까운 실제 공공기관 채용공고 하나를 골라 쓴다(2026-11-23 유저 요청).
# 출처: 공공데이터포털 「행정안전부 한국지역정보개발원_채용정보 조회 서비스」(이용허락범위 제한 없음) —
# 직장비교 앱의 '공고 찾기'가 하루 한 번 받아 jobscale 저장소에 올리는 jobs.json을 그대로 읽는다.
# 민간 구인 사이트 공고는 쓰지 않는다(약관·업체 분쟁). 공고를 못 가져오면 그날의 기능 소개 글(text)로 대신한다.
# 연봉은 공고에 '3400만원 이상' 같은 구간 하한으로만 나오니 "최소"로 쓰고, 근무시간은 공고에 없어서
# 주 40시간(월 209시간, 최저임금 월 환산과 같은 기준)으로 잡았다고 글에 밝힌다.
JOBS_URL = "https://raw.githubusercontent.com/bjgb1004-afk/jobscale/main/docs/data/jobs.json"
MIN_WAGE = 10320          # 2026년 최저시급(고용노동부 고시). 2027년 1월부터 10,700원 — 시리즈는 12/6에 끝난다.
MONTH_HOURS = 209         # 주 40시간 + 주휴, 월 환산
COMMUTE_HOURS = round(1 * 5 * 4.345, 1)   # 왕복 1시간 × 주 5일 × 월 4.345주


def fetch_jobs(url=JOBS_URL):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def used_job_ids(queue):
    return {q["job_id"] for q in queue if q.get("job_id")}


# 채용공고 목록에 합격자 발표·결과·취소 공지도 섞여 온다(예: "…신입직원 채용 최종합격자 발표"). 지원할 수 없는 글은 뺀다.
NOT_OPENING = re.compile(r"합격자|발표|결과|취소|중지|연기")


def pick_job(data, today, used=(), today_orgs=(), today_sidos=()):
    """마감이 가장 가까운(오늘 포함) 공고 중 연봉 하한이 3천만~8천만 원인 것 하나.
    하루 5개라 같은 날엔 같은 기관을 다시 안 쓰고, 오늘 아직 안 나온 지역·정규직을 먼저 고른다."""
    cands = [j for j in data.get("items", [])
             if j.get("incomeBound") == "min" and j.get("incomeWon") and 30000000 <= j["incomeWon"] <= 80000000
             and "억" not in (j.get("income") or "") and j.get("end", "") >= today.isoformat()
             and j.get("url") and j.get("id") not in used and j.get("org") not in today_orgs
             and not NOT_OPENING.search(j.get("title") or "")]
    if not cands:
        return None
    cands.sort(key=lambda j: (j["end"], j.get("sido") in today_sidos, j.get("emp") != "regular", j.get("id")))
    return cands[0]


def _won(n):
    return f"{int(round(n, -1)):,}"


def real_post(job, data, today, idx=0):
    region = data.get("regions", {}).get(job.get("sido"), "")
    if region and job["org"].startswith(region[:2]):
        region = ""            # '인천광역시 인천광역시서해구시설공단'처럼 겹치지 않게
    end = datetime.date.fromisoformat(job["end"])
    when = "오늘" if end == today else "내일" if end == today + datetime.timedelta(1) else f"{end.month}월 {end.day}일"
    title = job.get("title", "")
    title = title if len(title) <= 40 else title[:39] + "…"
    monthly = job["incomeWon"] / 12
    h = monthly / MONTH_HOURS
    hc = monthly / (MONTH_HOURS + COMMUTE_HOURS)
    gap = h - MIN_WAGE
    vs = f"올해 최저시급 10,320원보다 {_won(gap)}원 높음." if gap >= 0 else f"올해 최저시급 10,320원보다 {_won(-gap)}원 낮게 나옴(연봉 하한 기준)."
    place = data.get("regions", {}).get(job.get("sido"), "")
    hooks = [
        f"{when} 마감인 공공기관 공고 하나 가져옴.",
        "공고에 적힌 연봉 말고, 시간당 얼마인지 계산해본 적 있음?",
        "공기업 공고엔 연봉이 '얼마 이상'으로만 적혀 있음. 그래서 직접 쪼개봄.",
        f"{place} 사는 사람, 이 공고 봤음?" if place else "이 공고 본 사람 있음?",
        "출퇴근 왕복 1시간이면 이 연봉, 시급으로 얼마일까.",
    ]
    asks = [
        "너라면 이 공고, 집에서 몇 분 거리까지면 지원함?",
        "연봉 볼 때 시급으로도 바꿔서 봄?",
        "통근 왕복 1시간, 너는 감수할 수 있음?",
        "이 조건이면 지원함, 넘김?",
        "공공기관 연봉, 생각보다 높음 아니면 낮음?",
    ]
    i = idx % len(hooks)
    return (f"{hooks[i]}\n\n"
            f"{(region + ' ') if region else ''}{job['org']}\n{title}\n{job.get('jobType') or ''}, 연봉 {job['income']}, {when} 마감\n\n"
            f"연봉을 12로 나누면 최소 월 {monthly / 10000:.0f}만 원.\n"
            f"공고에 근무시간이 없어서 주 40시간(월 209시간)으로 잡으면 시급 약 {_won(h)}원.\n"
            f"{vs}\n\n"
            f"근데 출퇴근 왕복 1시간을 일한 시간처럼 치면 시급 약 {_won(hc)}원까지 내려감.\n"
            f"직장비교는 이걸 공고마다 자동으로 계산해줌.\n\n"
            f"{asks[i]}")


def real_link_text(job):
    return f"원문 공고\n{job['url']}\n\n직장비교 받기 (구글 플레이)\n{JOBAPP}"


# 11/28부터 직장비교는 하루 5개, 전부 실제 공공기관 공고 글(2026-11-23 유저: "직장비교앱을 살려보자… 매일 5개로").
# 로또 글 자리(07·09·14·18시)와 다른 시리즈 자리를 피해 출퇴근·점심·저녁에 둔다. 끝나는 날은 정하지 않았다.
# 공고를 못 가져오면 그 자리는 기능 소개 글(아래 JOBAPP_POSTS의 기능 글)을 돌려 쓴다.
JOBREAL_FROM = D(2026, 11, 28)
JOBREAL_TIMES = ((8, 7), (12, 37), (16, 37), (19, 37), (22, 7))


def jobreal_due(local, done):
    if local.date() < JOBREAL_FROM:
        return None
    for n, (h, m) in enumerate(JOBREAL_TIMES, 1):
        start = local.replace(hour=h, minute=m, second=0, microsecond=0)
        key = f"real-{local:%m%d}-{n}"
        if start <= local < start + datetime.timedelta(minutes=LATE_MIN) and f"jobapp-{key}" not in done:
            feats = [x for x in JOBAPP_POSTS if not x.get("real")]
            fb = feats[(local.toordinal() * 5 + n) % len(feats)]
            return "jobapp", {"key": key, "date": local.date(), "real": True, "text": fb["text"]}
    return None


POSTS = {"hjone": HJONE_POSTS, "kstock": KSTOCK_POSTS, "golmok": GOLMOK_POSTS, "jobapp": JOBAPP_POSTS}


def kst(now):
    return now.astimezone(KST)


def body(series, p):
    """본문만. 주제 태그·링크 없음(2026-11-23 유저 요청). 링크는 첫 댓글로 단다."""
    return p["text"]


def link_text(series, p):
    s = SERIES[series]
    link = s["link"] + p.get("path", "") if series == "golmok" else s["link"]
    return f"{s['lead']}\n{link}"


def recent_post(queue, now, minutes=GAP_MIN):
    """방금(minutes 안에) 나간 글이 있는가. 같은 계정에서 글 두 개가 몇 분 차로 붙지 않게."""
    cut = now - datetime.timedelta(minutes=minutes)
    for q in queue:
        t = q.get("published_at")
        if t and datetime.datetime.fromisoformat(t) > cut:
            return True
    return False


def due(now, queue):
    """지금 나갈 (series, post) 하나. 없으면 None. 하루에 시리즈당 한 번, 그날 날짜 글만."""
    local = kst(now)
    done = {q["id"] for q in queue}
    for series, s in SERIES.items():
        if series == "jobapp" and local.date() >= JOBREAL_FROM:
            hit = jobreal_due(local, done)
            if hit:
                return hit
            continue
        start = local.replace(hour=s["time"][0], minute=s["time"][1], second=0, microsecond=0)
        if not start <= local < start + datetime.timedelta(minutes=LATE_MIN):
            continue
        for p in POSTS[series]:
            if p["date"] == local.date() and f"{series}-{p['key']}" not in done:
                return series, p
    return None


def run_auto(now, dry=False):
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    hit = due(now, queue)
    if not hit:
        return 0
    if recent_post(queue, now):
        return 0
    series, p = hit
    text, link, job = body(series, p), link_text(series, p), None
    if p.get("real"):
        try:
            data = fetch_jobs()
            today = kst(now).date()
            todays = [q for q in queue if q.get("job_id") and q.get("published_at")
                      and kst(datetime.datetime.fromisoformat(q["published_at"])).date() == today]
            job = pick_job(data, today, used_job_ids(queue),
                           {q.get("job_org") for q in todays}, {q.get("job_sido") for q in todays})
            if job:
                idx = sum(1 for q in queue if q.get("job_id"))
                text, link = real_post(job, data, today, idx), real_link_text(job)
        except Exception as e:
            publish.telegram(f"⚠️ 직장비교 실제 공고 못 가져옴 — 기능 소개 글로 대신 ({p['key']})\n{e}")
    if dry:
        print(text)
        return 0
    name = SERIES[series]["name"]
    try:
        pid = publish.publish(text)
    except Exception as e:
        publish.telegram(f"❌ {name} 홍보 글 발행 실패 ({p['key']})\n{e}")
        raise
    try:
        publish.link_reply(f"{series}-{p['key']}", link, pid)
    except Exception as e:
        publish.telegram(f"⚠️ {name} 링크 댓글 실패 ({p['key']})\n{e}")
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    queue.append({"id": f"{series}-{p['key']}", "status": "published", "slot": series, "text": text,
                  "post_id": pid, **({"job_id": job["id"], "job_org": job.get("org"), "job_sido": job.get("sido")} if job else {}),
                  "published_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")})
    QUEUE.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    publish.telegram(f"📣 {name} 홍보 글 발행됨 ({p['key']})")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for series in SERIES:
        for p in POSTS[series]:
            t = body(series, p)
            print(f"== {series} {p['date']} {p['key']} {len(t)}자\n{t}\n-- 첫 댓글: {link_text(series, p)}\n")
