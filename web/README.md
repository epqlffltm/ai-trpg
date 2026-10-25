# 화면 (web)

일곱 서버를 부르는 화면 하나다. Vite, React, TypeScript 로 만든 SPA 이고, 빌드한 정적 파일을 프록시(nginx)가 내준다(#290).
무엇을 왜 그렇게 정했는지는 [화면 명세의 프런트 구조](../docs/product/screens.md#프런트-구조)에 있다. 이 문서는 실행과 구조만 다룬다.

지금 있는 것: 뼈대(npm workspaces, 프록시의 이미지에 굽기, CI), 로그인(A2 의 두 단계, 갱신은 한 번에 하나 #30), 가입(세 단계와 동의),
비밀번호 찾기와 재설정, 다시 동의와 탈퇴 취소, 첫 화면(A1: 서비스 고르기, 이어하기, 공개된 것),
마이페이지(A5: 계정, 비밀번호 바꾸기, 모든 기기 로그아웃, 선택 동의), 지갑(A6: 머리의 잔액, 골드·실버, 원장), 충전(A7: 상품, 주문, 시험용 결제창, 승인과 다시 확인), 주문 내역과 청약철회(A8), TRPG 의 시나리오 탐색(B1), 소개(B2), 로비(B3), 테이블 만들기(B4), 테이블 방(B6)의 대기실과 스트림, 채팅, 캐릭터 정하기(B5, 모집 중), 라운드(서술, 행동을 붙인 선언과 사고팔기·돈 건네기·무기와 노릴 부위, 결과, 서술의 미리 보기, 방장의 닫기), 상태 패널(B7, 선언으로 가는 단추, 장비의 착용과 벗기), 일어난 일(이벤트 기록과 서술을 막는 일의 알림), 방장의 운영(내보내기, 방장 넘기기, 한 번 더 굴리기, 설정, 끝내기), 서술 모델과 단계 고르기(B8, 만들기와 방장 패널), 운영자의 신고 처리(E4: 캐릭터의 신고와 대화 속 답의 신고, `/operator/reports`), chat 의 캐릭터 만들기(C6: 목록, 만들기, 기본·소개·말·시작 상황·지도·물건·호감도·그림·캐릭터 그림·이벤트 씬·로어북·게시 탭과 게시 점검, `/chat/studio/characters`), chat 의 로어북(목록, 만들기, 항목, 게시, `/chat/studio/lorebooks`).
본인인증, 보호자 동의, 토스페이먼츠 결제창, 출석, 탈퇴 요청, TRPG 의 캐릭터 보관함과 진행 중의 새 캐릭터, chat 의 화면(C)은 다음이다. 그 경로는 "준비 중"을 보인다.

## 실행

Node 24 가 필요하다(`.nvmrc`, 게시판 서버와 같다). 명령은 모두 `web/` 에서 친다.

```bash
npm ci
npm run dev        # http://localhost:5173
```

개발 서버는 `/api/` 를 로컬 compose 의 프록시(`http://127.0.0.1:8080`)로 넘긴다. 서버들을 먼저 띄운다([루트 README 의 실행](../README.md#실행)).
서버마다 주소를 적지 않는다. 주소의 갈래와 요청 수 제한이 실제와 같아진다. 프록시의 포트를 바꿨으면 `API_PROXY_TARGET=http://127.0.0.1:<포트> npm run dev`.

**로그인을 되살리려면 인증 서버가 개발 서버의 출처를 알아야 한다.** refresh 와 logout 은 요청의 출처(Origin)를 허용 목록과 비교한다.
적지 않으면 허용 목록은 compose 의 프록시 주소(`localhost:8080`, `127.0.0.1:8080`)뿐이라, 개발 서버(`localhost:5173`)에서는 403 `origin_not_allowed` 다.
`auth-server/.env` 에 셋을 함께 적고 인증 서버를 다시 띄운다.

```bash
REFRESH_COOKIE_ALLOWED_ORIGINS=http://localhost:8080,http://127.0.0.1:8080,http://localhost:5173
```

비밀번호 재설정 메일의 링크는 인증 서버의 `PASSWORD_RESET_URL` 이 정한다. 적지 않으면 개발 서버(`http://localhost:5173/reset-password`)다.
컨테이너의 화면(8080)으로 쓰면 `PASSWORD_RESET_URL=http://localhost:8080/reset-password` 로 바꾼다. staging 은 compose 가 도메인으로 채운다.

### 컨테이너로

프록시의 이미지가 화면을 담는다(`Dockerfile`, 멀티 스테이지). compose 로 띄우면 `http://localhost:8080` 에서 화면과 API 가 같은 출처로 나온다.
화면을 고쳤으면 이미지를 다시 만든다.

```bash
docker compose --profile app up -d --build proxy
```

nginx 의 설정은 이미지에 담지 않고 compose 가 붙인다(`docker/nginx/templates/`). 화면은 `web.inc.template`, 화면의 머리말(CSP)은 `web-headers.inc.template` 에 있다.

| 주소 | 프록시가 하는 일 |
| --- | --- |
| `/api/v1/<서버>/...` | 그 서버로 보낸다. `/api/` 의 그 밖은 404(JSON) |
| `/assets/...` | 빌드가 해시를 붙인 파일. 1년 캐시(`immutable`). 없으면 404(새로 올린 뒤의 예전 조각도. 화면이 새로 고치라고 알린다) |
| 그 밖(`/`, `/login`, `/trpg/...`) | 있는 파일이면 그것, 없으면 `index.html`. 캐시하지 않는다(`no-cache`) |
| `/admin/`, `/static/`, `/health` | 404. 관리자 화면은 SSH 터널로 인증 서버에 직접 붙는다. 그래서 운영자의 화면(E)은 `/operator/` 아래에 둔다 |

빌드는 화면마다 조각을 나눈다. 첫 화면, 로그인, 가입, 비밀번호는 첫 묶음에 있고, 나머지 화면은 처음 갈 때 받는다(`src/routing/pages.ts`).
React, React Router, TanStack Query 는 `vendor` 조각 하나로 묶는다(`vite.config.ts`). 화면만 고쳐 올리면 이 조각의 이름이 그대로라 캐시가 남는다.

빌드할 때 고르는 것은 둘이다.

| 이름 | 기본 | 뜻 |
| --- | --- | --- |
| `VITE_PAYMENT_GATEWAY` | `fake` | 충전(A7)의 결제창. `fake` 는 결제 서버의 가짜 결제 대행사에 맞춘 시험용 결제창이다(결과를 골라 결제 번호의 앞머리를 정한다). 그 밖의 값이면 결제창을 띄우지 않고 준비 중이라 알린다. 토스페이먼츠 결제창은 다음에 더한다 |
| `VITE_IDENTITY_PROVIDER` | `fake` | 본인인증(A3)과 보호자 동의(A4)의 본인확인 창. `fake` 는 인증 서버의 가짜 업체에 맞춘 시험용 창이다(생일과 사람 식별값을 골라 `fake:<DI>:<생일>` 을 낸다). 그 밖의 값이면 창을 띄우지 않고 지금은 할 수 없다고 알린다. 실제 업체의 창은 계약한 뒤에 더한다 |

## 구조

```
web/
  package.json            npm workspaces 의 뿌리. 린트(ESLint)와 TypeScript 를 여기서 함께 쓴다
  Dockerfile              프록시의 이미지(Node 에서 빌드 → nginx-unprivileged 에 dist)
  apps/web/               앱
    src/api/              서버를 부르는 것. http.ts(래퍼), refresh.ts(갱신), session.ts(토큰), auth.ts, lists.ts(첫 화면), listings.ts(B1, B2), tables.ts(B3, B4), tableRoom.ts·rounds.ts·tableHost.ts·tableStream.ts·sse.ts·transcripts.ts(B6, B10), rulebooks.ts·worlds.ts·lorebooks.ts·bestiaries.ts·scenarios.ts·studio.ts(B9), wallet.ts(A6), orders.ts(A7), attendance.ts(A9), identity.ts(A3), guardian.ts(A4), notifications.ts(A10), board.ts(A11), publicNames.ts, errors.ts
    src/api/generated/    서버의 API 목록(docs/api/*.openapi.json)에서 만든 타입. 손으로 고치지 않는다
    src/api/account.ts    본인의 계정(동의, 비밀번호 바꾸기, 모든 기기 로그아웃, 탈퇴 취소)
    src/auth/             로그인 상태를 읽는 훅, 처음 열 때 되살리기, 로그인해야 열리는 화면(RequireSession), 실패의 글, 돌아갈 주소
    src/legal/            동의 항목의 이름과 요약, 판마다의 문서(documents/, docs/legal 의 사본), 문서를 보이는 창
    src/pages/            화면. home(A1), login·signup·password(A2), limited(다시 동의, 탈퇴 유예), me(A5), identity(A3 본인인증), guardian(A4 보호자 동의와 보호자의 링크 화면), notifications(A10 알림), board(A11 공지·게시판 읽기), wallet(A6), charge(A7), orders(A8), attendance(A9 출석·보물 상자), trpg(B1 탐색, B2 소개, B3 로비, B4 테이블 만들기, room 의 B6 테이블 방, room/character 의 B5 캐릭터 정하기, room/round 의 라운드(앞의 라운드 B10)와 round/action 의 행동, room/transcript 의 기록 받기, room/status 의 B7 상태 패널, room/money.ts 의 판 안의 돈, room/events 의 일어난 일, room/host 의 방장의 운영, models 의 B8 서술 모델 고르기, studio 의 B9 제작 도구: 허브, 룰북, 세계관, 로어북, 몬스터 모음, 시나리오 조립의 뼈대, 캐릭터, 물건·돈, 인물, 지도와 길의 문, 몬스터, 퀘스트·사건, 소개와 공개), operator(E4 신고 처리), chat/studio/characters(C6 캐릭터 만들기), 준비 중, 없는 경로
    src/components/       여러 화면이 함께 쓰는 것(목록 한 칸, 실패 한 줄, 한 번 더 묻는 단추)
    src/hooks/            남은 초 세기, 다른 사람의 이름 찾기(public-names, #532)
    src/layout/           머리와 틀
    src/routing/          코드 분할. 처음 갈 때 받는 화면들(pages.ts), 받지 못했거나 깨졌을 때의 안내(RouteBoundary)
  packages/ui/            공통 구성요소(버튼, 입력 칸, 고르기 칸, 체크, 라디오, 창, 칩, 안내, 목록 한 줄)와 색·글꼴의 변수(styles.css)
```

Stitch 의 시안을 받으면 `packages/ui` 의 변수와 구성요소의 모양에만 입힌다. 화면의 코드는 그대로다.

## 서버를 부르는 법

모든 호출은 `src/api/http.ts` 의 `apiRequest` 하나를 지난다. 읽기는 TanStack Query 가 맡는다.

- access 토큰(15분)은 **메모리에만** 둔다(`session.ts`). 창을 새로 열면 refresh 쿠키(httpOnly, 14일)로 다시 받는다(`useBootSession`).
- 토큰이 없으면 `Authorization` 을 **아예 보내지 않는다.** 빈 토큰이나 지난 토큰을 실으면 공개 목록까지 401 이다.
- 401 이면 갱신을 한 번만 하고 한 번만 다시 부른다. 갱신도 401 이면 로그인이 끝난 것이다.
- **갱신은 한 번에 하나다(#30).** 같은 refresh 토큰으로 두 요청이 동시에 가면 인증 서버가 재사용으로 보고 모든 세션을 끊는다.
  - 한 창 안: 진행 중인 갱신이 있으면 그 결과를 함께 기다린다(`refresh.ts` 의 inflight). 개발 중 StrictMode 가 효과를 두 번 돌려도 한 번만 간다.
  - 창 사이: 탭 둘이 같은 쿠키를 쓴다. Web Locks 로 한 탭씩 차례로 보낸다. 앞 탭이 쿠키를 새것으로 바꾼 뒤에 다음 탭이 보낸다.
- 503 이나 연결 끊김은 로그아웃시키지 않는다. 그 요청만 실패한다.
- 다시 동의할 약관이 있거나 탈퇴를 기다리는 중이면 토큰이 인증 서버에만 통한다(`consents_pending`, `withdrawal_scheduled_at`).
  다른 서버는 모두 401 이라 화면마다 다루지 않는다. 틀(`AppLayout`)이 경로의 화면 대신 다시 동의나 탈퇴 취소를 그린다(`pages/limited/`).
  마치면 `/refresh` 로 모든 서버에 통하는 토큰을 받고, 그 자리에 원래 화면이 뜬다. 로그인, 가입, 비밀번호의 화면은 막지 않는다.
- 읽기는 4xx 를 다시 시도하지 않고, 5xx 와 연결 끊김은 한 번만 더 해 본다(`queryClient.ts`).

## 테이블의 스트림

테이블 방(B6)은 `GET /tables/{id}/stream`(SSE)을 붙잡고 있는다. `EventSource` 는 `Authorization` 을 붙이지 못해 `fetch` 로 읽는다(`api/tableStream.ts`, 글 나누기는 `api/sse.ts`).

- 한 번 열고 끝날 때까지 읽는 것(`readTableStream`)과 끝난 뒤에 무엇을 할지(`pages/trpg/room/streamPolicy.ts`)를 나눴다. 다시 붙는 고리는 `useTableStream` 이다.
- 끊기면 마지막 `id` 를 `Last-Event-ID` 로 보내며 다시 붙는다. 1~5초 사이에서 무작위로 쉰다(모두가 한꺼번에 붙지 않게).
- 토큰이 만료되면(`token_expired`, 401) `refresh.ts` 로 갱신한다. 갱신은 다른 요청과 같이 한 번에 하나다(#30).
- 이벤트로 값을 고치지 않는다. 오면 테이블을 묶어서 다시 읽는다(화면 명세 B7 의 "다시 읽기").
- 남이 캐릭터를 정한 것은 이벤트가 없다. 모집 중에는 15초마다도 테이블을 읽는다(`roomQueries.ts`).
- 남이 선언을 낸 것도 이벤트가 없다. 선언을 받는 동안에는 10초마다 지금 라운드를 읽는다(`round/roundQueries.ts`).
- 서술의 미리 보기(`narration_preview`)는 조각을 이어 보이고(`round/preview.ts`), 서술이 끝났다는 이벤트가 오면 지운다. 남는 장면은 이벤트와 라운드의 글뿐이다.
- 프록시는 이 주소의 버퍼를 끈다(`docker/nginx/templates/api.inc.template` 의 `/stream`). 개발 서버(Vite)의 프록시도 그대로 흘려보낸다.

## API 의 타입

서버의 API 목록에서 만든다(openapi-typescript). 손으로 쓴 타입을 두지 않는다.

```bash
npm run gen:api    # docs/api/{auth,trpg,asset,chat,billing,notification,board}.openapi.json → apps/web/src/api/generated/
```

서버의 API 가 바뀌면 이것을 다시 돌려 함께 올린다. CI 가 다시 만들어 보고 어긋나면 실패한다. 새 서버를 부르기 시작하면 `apps/web/scripts/gen-api.mjs` 의 `SERVERS` 에 더한다.

## 동의 문서

가입 3단계, 다시 동의, 마이페이지의 "보기"가 여는 글이다(#450). 서버(`GET /api/v1/auth/consents`)는 항목과 판 번호만 주고 문서의 글은 화면이 갖는다.
원본은 `docs/legal/` 이고, 사용자에게 보이는 본문(두 `---` 사이)만 판마다 `apps/web/src/legal/documents/` 에 옮긴다.

```bash
npm run sync:legal    # docs/legal/{terms,privacy}.md → apps/web/src/legal/documents/{terms,privacy}-v1.md
```

원본을 고치면 다시 돌려 함께 올린다. CI 가 다시 만들어 보고 어긋나면 실패한다.
판을 올리면(`auth-server/accounts/consents.py` 의 `POLICIES`) `scripts/sync-legal.mjs` 의 `DOCUMENTS` 와 `src/legal/consentItems.ts` 의 `DOCUMENTS` 에 새 판을 더한다.
화면이 갖지 않은 판을 서버가 주면 그 동의를 받지 않는다(가입, 다시 동의, 마이페이지 모두. 옛 문서로 동의를 받지 않는다).
선택 항목(마케팅, AI 학습)은 따로의 문서가 없어 개인정보 처리방침을 보인다. 초안이라 문서의 맨 위에 "검토 중인 초안"을 띄운다.
문서는 처음 열 때 받는다(마크다운을 그리는 react-markdown 도 그때). HTML 은 그대로 넣지 않고, 문서 안의 링크는 글로만 둔다.

## 시험

```bash
npm run typecheck
npm run lint
npm test
npm run build
```

시험은 서버를 부르지 않는다. `fetch` 를 가짜로 바꿔(`src/test/fakeFetch.ts`) 갱신이 하나만 가는지, 로그인 두 단계와 그 실패, 가입 세 단계와 동의(체크한 것만 보내기, 판이 바뀌면 다시 읽기), 비밀번호 재설정, 첫 화면의 줄이 따로 실패하는지,
다시 동의와 탈퇴 취소가 어느 경로든 막고 마치면 원래 화면을 여는지, 마이페이지(비밀번호 바꾸기, 모든 기기 로그아웃, 선택 동의 켜고 끄기),
시나리오 탐색(로그인 전에 토큰 없이, 거르기, 더 보기와 그 실패, 만든 사람의 이름)과 소개(고를 거리, 로그인 전후의 할 일, 404),
테이블 만들기(보내는 본문, 모델을 쓸 수 없을 때)와 로비(들어가기, 비밀번호, 그 사이에 자리가 참, 초대 코드),
테이블 방(붙는 번호, 스트림의 채팅과 입력 중, 쓰기, 이벤트가 오면 묶어서 다시 읽기, Last-Event-ID 로 다시 붙기, 토큰 만료, 시작, 나가기, 내보내짐), 캐릭터 정하기(프리젠, 점수제의 총점, 주사위를 굴리고 놓기, 바꾸기, 그 사이 남이 가져간 프리젠),
라운드(지난 라운드와 지금 라운드, 판정을 붙인 선언과 고치기, 판정 결과, 서술의 미리 보기와 끝, 방장의 닫기와 다시 맡기기, 그 사이 마감함),
상태 패널(내 HP, 쓰러짐과 부상, 소지품과 회복량, 퀘스트와 장소, 단축키, 이벤트가 오면 다시 읽기, 맵이 없는 판),
행동(고를 수 있는 종류와 대상, 보내는 칸, 공격, 패널의 단추로 채우기, 쓰러지면 글만),
방장의 운영(방장에게만, 내보내기와 새 초대 코드, 방장 넘기기, 설정, 한 번 더 굴리기, 끝내기, 그 사이 방장이 바뀜),
서술 모델(단계 고르기와 맞추기, 값과 바뀜의 글, 만들 때 보내는 단계, 시작한 뒤에는 쓸 수 없을 때만 바꾸기),
신고 처리(운영자가 아니면 없는 화면, 두 목록, 처리를 고르고 사유를 적어야 보내기, 숨기기, 까닭을 적어야 열리는 대화의 글과 다시 읽지 않기, 먼저 처리된 신고),
캐릭터 만들기(빈 목록에서 만들기, 운영자만 만드는 때, 탭마다의 저장 본문과 점검 다시 읽기, 점검에서 탭으로, 모르는 문제, 숨긴 캐릭터, 게시와 걸러 낸 것,
지도의 장소·길·처음 있는 장소와 지우면 길도, 물건과 시작 소지품, 그림 칸을 그대로 보내기, 호감도의 켜고 끄기·단계·규칙, 그림의 올리기·토큰을 실은 미리 보기·장소의 배경, 탭끼리 그림 칸을 되돌리지 않기,
캐릭터 그림의 체크무늬 미리 보기와 옷만 고르는 차림, 이벤트 씬의 조건을 바꾸면 대상을 비우기,
로어북 탭의 붙이기·차례·게시하지 않은 것·남의 로어북), chat 의 로어북(만들기, 항목과 겹친 키워드, 이름과 설명만 보내기, 게시와 판)을 본다.
가짜 스트림은 `src/test/tableFixtures.ts` 의 `sseResponse` 다.
프록시에 실려 실제로 뜨는지(index.html 로 돌리기, 캐시, CSP)는 CI 의 stack(`.github/scripts/stack-smoke.sh check-proxy`)이 본다.
끝에서 끝까지(Playwright)는 한 판이 화면으로 이어질 때 붙인다.
