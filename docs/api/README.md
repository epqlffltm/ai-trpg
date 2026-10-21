# API 목록

서버마다 받는 요청과 돌려주는 응답의 목록(OpenAPI)이다(#557). 화면의 타입과 디자인 도구(Stitch)에 넘길 API 목록이 이 파일들이다([화면 명세의 프런트 구조](../product/screens.md#프런트-구조)).

| 파일 | 서버 | 만드는 법 |
| --- | --- | --- |
| [trpg.openapi.json](trpg.openapi.json) | trpg-server (FastAPI) | 앱이 내는 것을 그대로 |
| [notification.openapi.json](notification.openapi.json) | notification-server (FastAPI) | 앱이 내는 것을 그대로 |
| (없음) | auth-server (Django REST framework) | #558 |
| (없음) | board-server (NestJS) | #559 |
| [billing.openapi.json](billing.openapi.json) | billing-server (Go, Gin) | 손으로 쓴 목록(`billing-server/api/openapi.yaml`). 테스트가 라우터와 응답을 견준다 |

## 쓰는 법

- **고치지 않는다.** 서버의 코드에서 뽑은 것이다. 서버의 API 를 바꾸면 저장소 루트에서 다시 뽑아 함께 커밋한다.

  ```
  uv run --no-project python tools/export_openapi.py              # 모든 서버
  uv run --no-project python tools/export_openapi.py trpg         # 한 서버만
  uv run --no-project python tools/export_openapi.py --check      # 쓰지 않고 같은지만 본다
  ```

  서버를 띄우지 않고 DB 에도 닿지 않는다. 서버마다 그 서버의 uv 환경에서 앱을 불러온다(처음에는 의존성을 받느라 조금 걸린다).
  결제 서버는 손으로 쓴 목록을 Go 로 읽어 검사한다(`go run ./cmd/openapi`). Go 가 깔려 있어야 한다.
- **결제 서버는 목록을 먼저 고친다.** 결제 서버의 목록은 코드에서 나오지 않는다. API 를 바꾸면 `billing-server/api/openapi.yaml` 을 고치고 뽑는다.
  고치지 않으면 결제 서버의 테스트가 실패한다([결제 서버의 API](../../billing-server/README.md#api)).
- **CI 가 본다.** 목록을 내는 서버를 고친 PR 에서 관문의 `api-docs` 가 목록이 지금의 서버와 같은지 본다. 다르면 실패하고 위의 명령을 알린다.
- **누가 부르는가.** 요청마다 `x-audience` 를 적는다. 화면은 `user` 만 부른다.

  | 값 | 주소의 모양 | 부르는 쪽 |
  | --- | --- | --- |
  | `user` | 그 밖의 모두 | 화면(로그인한 사람, 일부는 로그인 전) |
  | `service` | `/service/` 가 들어간 것 | 서버끼리(서명 비밀). 프록시가 바깥에서 막는다 |
  | `operator` | `/admin/` 이 들어간 것 | 운영자(토큰의 `roles`). 관리자 화면 |
  | `webhook` | `/webhooks/` 가 들어간 것 | 바깥 업체(결제 대행사) |
  | `infra` | `/health` 로 시작하는 것 | 컨테이너의 상태 확인과 수집기 |

- **화면의 타입.** 프런트를 만들 때 `openapi-typescript` 로 이 파일에서 타입을 만든다. 손으로 쓴 타입은 두지 않는다.
- **운영 서버는 열지 않는다.** 서버의 `/docs`, `/openapi.json` 은 개발(DEBUG)에서만 열린다. 바깥에 나가는 목록은 이 파일들뿐이다.

## 서버를 더할 때

1. 그 서버가 OpenAPI 를 표준 출력에 내는 명령을 만든다(서버를 띄우지 않고).
2. `tools/export_openapi.py` 의 `SOURCES` 에 그 서버의 폴더와 명령을 더한다.
3. `.github/scripts/changed-servers.sh` 의 `openapi_tool` 이 고르는 서버와 `.github/workflows/ci.yml` 의 `api-docs` 가 도는 조건에 그 서버를 더한다.
4. 위 표의 줄을 고친다.
