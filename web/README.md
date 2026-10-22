# 화면 (web)

일곱 서버를 부르는 화면 하나다. Vite, React, TypeScript 로 만든 SPA 이고, 빌드한 정적 파일을 프록시(nginx)가 내준다(#290).
무엇을 왜 그렇게 정했는지는 [화면 명세의 프런트 구조](../docs/product/screens.md#프런트-구조)에 있다. 이 문서는 실행과 구조만 다룬다.

지금 있는 것: 뼈대(npm workspaces, 프록시의 이미지에 굽기, CI), 로그인(A2 의 두 단계, 갱신은 한 번에 하나 #30), 첫 화면(A1: 서비스 고르기, 이어하기, 공개된 것).
가입, 비밀번호 재설정, 다시 동의, 본인인증과 서비스의 화면(B, C)은 다음이다. 그 경로는 "준비 중"을 보인다.

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
| `/assets/...` | 빌드가 해시를 붙인 파일. 1년 캐시(`immutable`). 없으면 404 |
| 그 밖(`/`, `/login`, `/trpg/...`) | 있는 파일이면 그것, 없으면 `index.html`. 캐시하지 않는다(`no-cache`) |
| `/admin/`, `/static/`, `/health` | 404. 관리자 화면은 SSH 터널로 인증 서버에 직접 붙는다 |

## 구조

```
web/
  package.json            npm workspaces 의 뿌리. 린트(ESLint)와 TypeScript 를 여기서 함께 쓴다
  Dockerfile              프록시의 이미지(Node 에서 빌드 → nginx-unprivileged 에 dist)
  apps/web/               앱
    src/api/              서버를 부르는 것. http.ts(래퍼), refresh.ts(갱신), session.ts(토큰), auth.ts, lists.ts, errors.ts
    src/api/generated/    서버의 API 목록(docs/api/*.openapi.json)에서 만든 타입. 손으로 고치지 않는다
    src/auth/             로그인 상태를 읽는 훅, 처음 열 때 되살리기, 로그인 실패의 글, 돌아갈 주소
    src/pages/            화면. home(A1), login(A2), 준비 중, 없는 경로
    src/layout/           머리와 틀
  packages/ui/            공통 구성요소(버튼, 입력 칸, 안내, 목록 한 줄)와 색·글꼴의 변수(styles.css)
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
- 다시 동의할 약관이 있거나 탈퇴를 기다리는 중이면 토큰이 인증 서버에만 통한다(`consents_pending`, `withdrawal_scheduled_at`). 첫 화면은 이어하기를 부르지 않고 그 까닭을 알린다.
- 읽기는 4xx 를 다시 시도하지 않고, 5xx 와 연결 끊김은 한 번만 더 해 본다(`queryClient.ts`).

## API 의 타입

서버의 API 목록에서 만든다(openapi-typescript). 손으로 쓴 타입을 두지 않는다.

```bash
npm run gen:api    # docs/api/{auth,trpg,asset,chat}.openapi.json → apps/web/src/api/generated/
```

서버의 API 가 바뀌면 이것을 다시 돌려 함께 올린다. CI 가 다시 만들어 보고 어긋나면 실패한다. 새 서버를 부르기 시작하면 `apps/web/scripts/gen-api.mjs` 의 `SERVERS` 에 더한다.

## 시험

```bash
npm run typecheck
npm run lint
npm test
npm run build
```

시험은 서버를 부르지 않는다. `fetch` 를 가짜로 바꿔(`src/test/fakeFetch.ts`) 갱신이 하나만 가는지, 로그인 두 단계와 그 실패, 첫 화면의 줄이 따로 실패하는지를 본다.
프록시에 실려 실제로 뜨는지(index.html 로 돌리기, 캐시, CSP)는 CI 의 stack(`.github/scripts/stack-smoke.sh check-proxy`)이 본다.
끝에서 끝까지(Playwright)는 한 판이 화면으로 이어질 때 붙인다.
