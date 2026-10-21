# 기여 지침

버그 신고, 기능 제안, 문서와 코드의 기여를 받는다. 개발 중인 프로젝트라 저장소의 설계, 테스트, 보안 원칙에 맞는지 보고 받는다.

## 시작하기 전에

1. [루트 README](README.md)와 고칠 서버의 README를 읽는다.
2. [Issues](https://github.com/epqlffltm/ai-trpg/issues)에 같은 문제나 제안이 있는지 본다.
3. 보안 취약점은 공개 Issue가 아니라 [보안 정책](SECURITY.md)의 비공개 신고로 알린다.
4. 여러 서버에 걸치거나 API, DB 의 약속을 바꾸는 변경은 먼저 Issue에서 범위를 정한다.

## 저장소의 구성

| 위치 | 하는 일 | 기술 |
| --- | --- | --- |
| `auth-server/` | 계정, 인증, JWT 발급 | Django |
| `trpg-server/` | 게임 엔진, 라운드, AI 서술 | FastAPI |
| `board-server/` | 게시판, 댓글, 신고 | NestJS |
| `billing-server/` | 연습용 결제, 크레딧, 원장 | Go |
| `docker/`, `docker-compose.yml` | 공용 인프라, 프록시, 컨테이너 | Docker |
| `docs/` | 서버들이 함께 지키는 규격 | Markdown |

프론트엔드(`web/`)는 아직 없다.

## 지키는 원칙

- **서버의 경계.** 서버끼리는 API 로 주고받는다. 다른 서버의 DB 테이블을 직접 읽지 않는다.
- **인증의 책임.** 로그인과 토큰 발급은 인증 서버가 한다. 다른 서버는 공개키(JWKS)로 토큰을 검증한다.
- **게임 상태의 권한.** 판정과 규칙은 게임 엔진이 정한다. LLM 의 제안과 서술을 검증 없이 게임 상태에 적용하지 않는다.
- **결제의 무결성.** 주문, 홀드, 확정, 반환, 원장은 같은 요청의 반복, 재시도, 중간에 끊긴 처리를 견뎌야 한다.
- **마이그레이션.** DB 모델을 바꾸면 마이그레이션과 함께, 있던 데이터를 어떻게 다루는지 적는다.
- **민감정보.** [관측 규격의 민감정보](docs/observability.md#민감정보)를 로그, Issue, PR 에 남기지 않는다.
- **작은 변경.** 서로 상관없는 리팩터링과 기능을 한 PR 에 섞지 않는다.

## 개발 환경과 검사

루트 README 대로 PostgreSQL, Redis, 환경 변수를 준비한다. 아래는 서버 폴더에서 돌리는 가장 기본의 검사다.

| 서버 | 기본 검사 |
| --- | --- |
| 인증 | `uv run python manage.py test`, `uv run ruff check .`, `uv run ruff format --check .` |
| 게임 | `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` |
| 게시판 | `npm run lint`, `npm run format:check`, `npm run build`, `npm test`, `npm run test:e2e` |
| 결제 | `go test ./...`, `go vet ./...`, `gofmt -l .` |
| 서버 폴더 밖의 파이썬(`tools/`, `.github/scripts/`, `docker/`), 저장소 루트에서 | `uvx ruff@0.17.1 check $(git ls-files '*.py' ':(exclude)*-server/*')`, 같은 것을 `format --check` 로. PowerShell 에서도 그대로 된다 |
| 서버의 API 를 바꿨을 때(게임, 게시판, 알림, 결제, asset, 인증), 저장소 루트에서 | `uv run --no-project python tools/export_openapi.py` 로 API 목록(`docs/api/`)을 다시 뽑아 함께 커밋한다. 빠뜨리면 CI 의 `api-docs` 가 실패한다. 게시판 서버는 `board-server` 에서 `npm ci` 를 먼저 해 둔다. 결제 서버는 먼저 `billing-server/api/openapi.yaml` 을, 인증 서버는 뷰의 `@extend_schema` 를 고친다(고치지 않으면 그 서버의 테스트가 실패한다) |

**기준은 CI 다.** CI 는 이보다 더 본다(커버리지 기준, 경합 검사, 마이그레이션의 누락). 무엇을 보는지는 `.github/workflows/`와
서버별 README 의 테스트 절에 있다. 버그를 고쳤으면 그 버그를 다시 만드는 테스트를 더한다.

`.env`, JWT 개인키, API 키, 토큰은 커밋하지 않는다. 설정은 `.env.example`을 보고 만든다.
오류 로그와 화면을 공유하기 전에도 민감정보를 지운다.

## 브랜치와 Pull Request

1. `main`에서 목적이 하나인 브랜치(`fix/...`, `feat/...`, `docs/...`)를 만든다.
2. 바꾼 범위의 테스트와 검사를 돌린다. **실제로 돌린 것만 돌렸다고 적는다.** 돌리지 못한 것은 이유를 적는다.
3. PR 은 [템플릿](.github/PULL_REQUEST_TEMPLATE.md)의 모양(왜, 한 것, 정한 것, 확인, 알아 둘 것)으로 쓴다.
4. `main`에는 PR 로만 들어간다. 필수 검사 `ci-ok`가 통과해야 한다.

`ci-ok`는 바뀐 파일을 보고 그 서버의 검사만 고른다. 공용 인프라(`docker/`, `docker-compose.yml`)가 바뀌면 넷 다 돈다.
서버가 하나라도 바뀌면 네 서버를 함께 띄워 확인한다. 문서만 바꾼 PR 은 서버 검사를 건너뛴다.

## Issue

- 버그: 재현하는 조건과 단계, 기대한 동작, 실제 동작, 영향받는 서버
- 기능 제안: 풀려는 문제, 원하는 동작, 끝났다고 볼 조건
- 보안 취약점: 공개 Issue에 쓰지 않는다. [SECURITY.md](SECURITY.md)를 따른다

## 권리

이 저장소에는 라이선스가 없다. 공개되어 읽을 수는 있지만, 코드를 복제, 수정, 재배포하는 권리는 주지 않는다.
보낸 기여를 받을지는 유지보수자가 프로젝트의 방향을 보고 정한다.
