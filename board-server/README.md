# 게시판 서버

[![board-server](https://github.com/epqlffltm/ai-trpg/actions/workflows/board-server.yml/badge.svg)](https://github.com/epqlffltm/ai-trpg/actions/workflows/board-server.yml)

[ai-trpg](../README.md)의 게시판 서버. 사이트가 운영하는 커뮤니티를 맡는다. 공지, 이벤트, 잡담, 시나리오 이야기 같은 글과 댓글이다. NestJS(TypeScript)로 만든다.
회원가입과 로그인은 하지 않는다. [인증 서버](../auth-server/README.md)가 발급한 토큰을 공개키로 검증만 한다.
시나리오의 소개 페이지에 붙는 댓글(플레이한 사람들의 평)은 여기가 아니라 시나리오 쪽의 일이다.

지금은 뼈대만 있다. 서버가 뜨고, 살아 있는지 확인하는 주소가 응답한다.

## 목차

- [실행](#실행)
- [API](#api)
- [구조](#구조)
- [CI](#ci)
- [설계 메모](#설계-메모)

## 실행

명령은 저장소 루트에서 시작한다고 보고 적었다. Node.js 24 가 필요하다.

### 설치와 실행

```
cd board-server
cp .env.example .env
npm install
npm run start:dev
```

인증 서버가 8000번, 게임 서버가 8001번을 쓰므로 8002번으로 띄운다. `http://127.0.0.1:8002/health`가 `{"status":"ok"}`를 돌려주면 정상이다.

`npm run start:dev`는 파일을 고치면 서버를 다시 띄운다. 고치지 않고 한 번만 띄우려면 `npm run start`다.

### 테스트와 검사

```
cd board-server
npm run lint
npm run format
npm run build
npm test
npm run test:e2e
```

- `npm run lint`(oxlint): 쓰지 않는 이름이나 기다리지 않은 Promise 같은 문제를 실행하지 않고 찾는다.
- `npm run format`(prettier): 코드의 모양을 정해진 규칙으로 맞춘다. 고치지 않고 검사만 하려면 `npm run format:check`다.
- `npm run build`: TypeScript 를 JavaScript 로 바꿔 `dist/`에 놓는다. 타입이 맞지 않으면 여기서 실패한다. 파이썬에는 없는 단계다.
- `npm test`(vitest): `src/` 안의 `*.spec.ts`. 함수와 클래스를 하나씩 본다. 서버를 띄우지 않는다.
- `npm run test:e2e`: `test/` 안의 `*.e2e-spec.ts`. 앱을 통째로 만들어 주소로 불러 본다.

커밋하기 전에 다섯을 모두 돌린다.

### 패키지를 더하고 뺄 때

```
npm install 패키지이름
npm install --save-dev 패키지이름
npm uninstall 패키지이름
```

`package.json`과 `package-lock.json`이 함께 바뀐다. 둘 다 커밋한다. `node_modules/`는 커밋하지 않는다.
설치할 때 취약점 경고가 나와도 `npm audit fix --force`는 쓰지 않는다. 버전의 범위를 무시하고 올리거나 내려서 프로젝트가 깨질 수 있다.
서버에 실제로 들어가는 패키지의 취약점만 보려면 `npm audit --omit=dev`다.

## API

게시판 서버의 API는 `/api/v1/board/` 아래에 놓는다. 아직 없다.

| 메서드 | 경로 | 설명 | 인증 |
| --- | --- | --- | --- |
| GET | `/health` | 서버가 살아 있는지 확인 | 불필요 |

`/health`는 API 주소 밖에 둔다. 프록시와 컨테이너 관리 도구가 부르는 주소라 버전이 없다.

## 구조

```
src/
  main.ts                    서버를 띄우는 시작점
  app.module.ts              이 서버를 이루는 모듈들을 모은다
  app.setup.ts               주소의 앞부분 같은, 앱에 거는 규칙
  config/environment.ts      환경 변수를 검사해 설정으로 바꾼다
  health/                    살아 있는지 확인하는 API
test/                        앱을 통째로 만들어 부르는 테스트
```

Nest 의 말을 다른 서버의 말로 옮기면 이렇다.

| Nest | 하는 일 | 게임 서버(FastAPI)에서 닮은 것 |
| --- | --- | --- |
| 모듈(`*.module.ts`) | 기능 하나에 어떤 컨트롤러와 서비스가 있는지 적은 목록 | 기능별 폴더와, 라우터를 앱에 붙이는 줄 |
| 컨트롤러(`*.controller.ts`) | 주소를 받아 서비스를 부른다 | `router.py` |
| 서비스(`*.service.ts`) | 실제 일을 한다 | `service.py` |
| 의존성 주입 | 생성자에 적은 타입을 보고 Nest 가 넣어 준다 | `Depends(...)` |

## CI

PR과 `main` 푸시마다 GitHub Actions가 게시판 서버를 검사한다. `board-server/`나 워크플로 파일이 바뀐 경우에만 돈다.

1. 의존성 설치 (`npm ci`): `package-lock.json`과 `package.json`이 어긋나면 실패한다
2. 린트 (`npm run lint`)
3. 모양 검사 (`npm run format:check`): 고치지 않고 검사만 한다
4. 빌드 (`npm run build`): 타입 검사를 겸한다
5. 테스트 (`npm test`, `npm run test:e2e`)

## 설계 메모

**설정은 `@nestjs/config`로 읽고, 뜰 때 검사한다.** `.env`와 환경 변수를 읽어 검사 함수(`config/environment.ts`)에 넘긴다.
값이 틀리면 앱을 만드는 데서 예외가 나고 프로세스가 끝난다. 틀린 설정으로 떠서 요청을 받다가 실패하지 않는다.
검사 함수는 Nest 를 모르는 순수한 함수라 따로 테스트한다. 꺼내 쓰는 쪽은 `ConfigService<Environment, true>`로 받아서, 없는 이름을 꺼내면 컴파일러가 잡는다.
`.env`는 다른 서버와 따로 둔다. 한 서버가 다른 서버의 비밀값을 읽을 수 없게 하기 위해서다.
테스트는 `.env`를 읽지 않는다. 개발자의 `.env`에 무엇이 적혀 있든 결과가 같아야 한다.

**기본으로 듣는 주소는 `127.0.0.1`이다.** Nest 는 주소를 주지 않으면 모든 주소에서 듣는다. 개발하는 컴퓨터에서 띄운 서버가 같은 공유기의 다른 기기에 열린다. 컨테이너에서는 `HOST=0.0.0.0`으로 바꾼다.

**앱에 거는 규칙을 한 함수에 둔다(`setupApp`).** 주소의 앞부분과 머리말의 규칙이다. 서버를 띄울 때와 테스트가 같은 함수를 부른다.
`main.ts`에만 적으면 테스트가 만든 앱에는 걸리지 않아서, 테스트는 통과하는데 실제 서버의 주소는 다른 일이 생긴다.

**`/health`는 프로세스가 살아 있는지만 본다.** DB까지 확인하면, DB가 잠깐 느려졌을 때 관리 도구가 멀쩡한 서버를 죽은 것으로 보고 재시작한다.

**응답에서 `X-Powered-By`를 뺀다.** 어떤 프레임워크로 만들었는지 알려 줄 이유가 없다.

**모듈 방식은 ESM 이다.** `import`와 `export`를 쓰는 지금의 표준이다. 같은 프로젝트의 파일을 가져올 때 `./app.module.js`처럼 끝에 `.js`를 붙인다. 파일은 `.ts`지만, 실행되는 것은 빌드된 `.js`이기 때문이다.

**패키지 관리자는 npm 이다.** Node.js 에 딸려 온다. 설치가 느려지면 pnpm 으로 옮길 수 있다(`pnpm import`가 잠금 파일을 바꿔 준다).

**외부 모니터링 서비스(`@nestjs/observe`)와 배포 도구(`@nestjs/mau`)는 넣지 않았다.** 프로젝트를 만드는 도구가 권하지만, 로그와 지표를 무엇으로 모을지는 아직 정하지 않았다.

**린트와 모양 검사를 처음부터 CI에 넣는다.** 코드가 쌓인 뒤에 넣으면 지적이 한꺼번에 나와 고치는 일이 따로 생긴다.

**테스트는 서버를 띄우지 않고 앱에 요청을 바로 넘긴다(supertest).** 네트워크의 포트를 열지 않아 빠르고, 포트가 겹칠 일이 없다.
