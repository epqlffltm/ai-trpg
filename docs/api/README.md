# API 목록

서버마다 받는 요청과 돌려주는 응답의 목록(OpenAPI)이다(#557). 화면의 타입과 디자인 도구(Stitch)에 넘길 API 목록이 이 파일들이다([화면 명세의 프런트 구조](../product/screens.md#프런트-구조)).

| 파일 | 서버 | 만드는 법 |
| --- | --- | --- |
| [trpg.openapi.json](trpg.openapi.json) | trpg-server (FastAPI) | 앱이 내는 것을 그대로 |
| [notification.openapi.json](notification.openapi.json) | notification-server (FastAPI) | 앱이 내는 것을 그대로 |
| [auth.openapi.json](auth.openapi.json) | auth-server (Django REST framework) | 뷰에 적은 모양에서(drf-spectacular). 테스트가 받은 응답을 견준다 |
| [board.openapi.json](board.openapi.json) | board-server (FastAPI) | 앱이 내는 것을 그대로 |
| [asset.openapi.json](asset.openapi.json) | asset-server (FastAPI) | 앱이 내는 것을 그대로 |
| [chat.openapi.json](chat.openapi.json) | chat-server (FastAPI) | 앱이 내는 것을 그대로 |
| [story.openapi.json](story.openapi.json) | story-server (FastAPI) | 앱이 내는 것을 그대로 |
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
  인증 서버는 `manage.py spectacular` 로 만든다. 서명 키와 DB 없이 뜬다. 모양을 적지 않은 뷰가 있으면 실패한다.
- **인증 서버는 뷰의 모양을 함께 고친다.** 뷰의 `@extend_schema`(모양은 `auth-server/accounts/api_schema.py`)가 목록이 된다.
  응답을 바꾸고 모양을 고치지 않으면 인증 서버의 테스트가 실패한다([인증 서버의 API 목록](../../auth-server/README.md#api-목록)).
- **결제 서버는 목록을 먼저 고친다.** 결제 서버의 목록은 코드에서 나오지 않는다. API 를 바꾸면 `billing-server/api/openapi.yaml` 을 고치고 뽑는다.
  고치지 않으면 결제 서버의 테스트가 실패한다([결제 서버의 API](../../billing-server/README.md#api)).
- **CI 가 본다.** 목록을 내는 서버를 고친 PR 에서 관문의 `api-docs` 가 목록이 지금의 서버와 같은지 본다. 다르면 실패하고 위의 명령을 알린다.
- **누가 부르는가.** 요청마다 `x-audience` 를 적는다. 화면은 `user` 만 부른다.
  서버가 직접 적어 둔 것은 도구가 덮지 않는다. 게시판의 운영자 API(신고 처리, 글 고정)는 주소에 `/admin/` 이 없어서 서버가 `operator` 를 적는다.

  | 값 | 주소의 모양 | 부르는 쪽 |
  | --- | --- | --- |
  | `user` | 그 밖의 모두 | 화면(로그인한 사람, 일부는 로그인 전) |
  | `service` | `/service/` 가 들어간 것 | 서버끼리(서명 비밀). 프록시가 바깥에서 막는다 |
  | `operator` | `/admin/` 이 들어간 것 | 운영자(토큰의 `roles`). 관리자 화면 |
  | `webhook` | `/webhooks/` 가 들어간 것 | 바깥 업체(결제 대행사) |
  | `infra` | `/health` 로 시작하는 것 | 컨테이너의 상태 확인과 수집기 |

- **화면의 타입.** 프런트를 만들 때 `openapi-typescript` 로 이 파일에서 타입을 만든다. 손으로 쓴 타입은 두지 않는다.
- **운영 서버는 열지 않는다.** 서버의 `/docs`, `/openapi.json` 은 개발(DEBUG)에서만 열린다. 바깥에 나가는 목록은 이 파일들뿐이다.

## 오류의 모양

실패의 본문은 모든 서버가 `{"detail": "문장"}` 이다. 필요할 때 `code`(갈래를 나누는 이름), `retry_after`(기다릴 초)가 붙는다.
`detail` 에는 서버가 적은 문장만 싣는다. 라이브러리의 글과 사용자가 보낸 값은 싣지 않는다.

**칸이 틀린 입력 오류**는 `errors` 에 칸의 이름(점으로 이은 경로)마다 까닭을 싣는다.

```json
{ "detail": "입력이 올바르지 않습니다.", "errors": { "action.kind": ["Field required"] } }
```

상태 코드는 서버의 계약이다. 서버마다 정한 코드를 그대로 지키고, 프레임워크를 바꿔도 바꾸지 않는다.

| 서버 | 입력 오류의 코드 | 만드는 곳 |
| --- | --- | --- |
| trpg, chat, asset, notification, story (FastAPI) | 422 | `shared/server-core` 의 `use_input_errors` |
| auth (Django REST framework) | 400 | `auth-server/accounts/exception_handlers.py` |
| board (FastAPI) | 400 | `board-server/app/core/errors.py` |
| billing (Go) | 400 | 칸을 가르지 않는다. `errors` 없이 `detail`(서비스끼리는 `code`)이 고칠 것을 말한다 |

화면은 상태 코드가 아니라 **`errors` 가 있는지로** 입력 오류를 알아본다(`web/apps/web/src/api/errors.ts` 의 `isInputError`).
같은 코드(422)를 서버가 정한 거절(trpg 의 `{field, reason}` 같은 것)에도 쓰므로, 코드만으로는 "칸을 고치면 되는가"를 가를 수 없다.

## 서버를 더할 때

1. 그 서버가 OpenAPI 를 표준 출력에 내는 명령을 만든다(서버를 띄우지 않고).
2. `tools/export_openapi.py` 의 `SOURCES` 에 그 서버의 폴더와 명령을 더한다.
3. `.github/scripts/changed-servers.sh` 의 `openapi_tool` 이 고르는 서버와 `.github/workflows/ci.yml` 의 `api-docs` 가 도는 조건에 그 서버를 더한다.
4. 위 표의 줄을 고친다.
