# server-core

FastAPI 서버들이 함께 쓰는 공통부다. 토큰 검증, 관측(로그, 메트릭, 추적), 서버끼리의 서명, DB 연결, 뒤에서 도는 일의 틀,
알림 서버로 보내는 발송함이 있다.
규칙과 까닭은 [공용 코드 규칙](../../docs/architecture/shared-code.md#서버의-공통부-sharedserver-core)에 있다.

| 쓰는 서버 | 언제부터 |
| --- | --- |
| notification-server, asset-server | #588 |
| chat-server, story-server | 처음부터(#590, #591) |
| trpg-server | 나중에 옮긴다(#589) |

## 서버에 붙이기

1. `pyproject.toml` 에 경로 의존을 적는다. CI 는 이 줄을 읽어 공용 코드가 바뀐 PR 에서 그 서버를 검사한다.

   ```toml
   dependencies = [..., "server-core"]

   [tool.uv.sources]
   server-core = { path = "../shared/server-core", editable = true }
   ```

2. Dockerfile 에서 공용 코드를 담고 설치된 모양으로 깐다. compose 는 `build.additional_contexts: shared: ./shared` 로 넘긴다.

   ```dockerfile
   COPY --from=shared server-core/pyproject.toml /shared/server-core/pyproject.toml
   COPY --from=shared server-core/src /shared/server-core/src
   COPY pyproject.toml uv.lock ./
   RUN uv sync --locked --no-dev --no-install-project --no-editable
   ```

3. 설정은 `CoreSettings` 를 물려받아 이름과 기본값을 준다.

   ```python
   class Settings(CoreSettings):
       service_name: ClassVar[str] = 'chat-server'
       db_schema: str = Field(default='chat', pattern=SCHEMA_PATTERN)
       jwt_audience: str = 'ai-trpg-chat'
   ```

4. 앱을 만들 때 관측을 걸고(`configure_logging`, `configure_tracing`, `configure_metrics`), 미들웨어 셋을 붙이고
   (`RequestLoggingMiddleware`, `RequestSpanMiddleware`, `RequestMetricsMiddleware` 의 차례), `app.state` 에 `settings`, `jwks`, `revocations`,
   `session_factory` 를 붙인다. asset-server 의 `app/main.py` 가 가장 작은 예다.

## 열어 둔 자리

서버는 아래로만 바꿔 쓴다. 공용 코드의 클래스를 상속해 덮어쓰거나 복사해 고치지 않는다. 자리가 모자라면 여기에 연다.

| 자리 | 쓰는 법 |
| --- | --- |
| 설정 값 | 토큰의 대상, 서비스 이름, 스키마는 설정에. 풀의 크기는 환경 변수 `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` 로 compose 가 준다([DB 와 Redis 의 한도](../../docs/architecture/services.md#db-와-redis-의-한도)). search_path 에 더할 스키마는 `create_engine(settings, extra_schemas=...)` |
| 스트림인 주소 | `StreamRoutes.of(r'/api/v1/chat/conversations/[^/]+/messages')` 를 `RequestSpanMiddleware` 와 `RequestMetricsMiddleware` 에 `streams=` 로 넘긴다. SSE 연결은 `measured_stream()` 으로 센다 |
| 서버만의 계측기 | `InstrumentSet(build)` 을 모듈에 하나 두고 `get()` 으로 꺼낸다(알림 서버의 `app/notifications/metrics.py`) |
| span 을 보내기 전 | `configure_tracing(settings, resource, wrap=...)`. 기본은 할 일 없던 바퀴를 버리는 `DropIdleRounds` 다 |
| 작업 한 바퀴 | `job_span`, `job_scope`, `measured_job` 으로 감싼다. 찾아낸 것의 수는 `add_handled` 로 더한다(0 이면 추적을 보내지 않는다) |
| 토큰의 주인 | `CurrentUser`(없거나 틀리면 401), `OptionalUser`(보내지 않았으면 None). `adult_content`, `is_operator` 가 실린다 |
| 다른 서버를 부르기 | `traced_client()` 를 앱에 하나 두고, 우리 서버를 부를 때만 `outgoing_headers()` 를 붙인다. 바깥(AI 모델의 창구)에는 붙이지 않는다 |
| 알림 보내기 | 아래 [알림 보내기](#알림-보내기) |

## 알림 보내기

사람에게 알릴 일을 알림 서버([notification-server](../../notification-server/README.md))에 넣는 발송함이다(`server_core/notifications/`, #678).
trpg-server 의 `app/notifications/` 에서 뽑았다. 쓰는 서버는 asset-server 이고, chat-server 가 다음이다. trpg-server 는 옮길 때(#589) 이것으로 바꾼다.

| 서버가 하는 것 | 공용 코드가 하는 것 |
| --- | --- |
| 표를 만든다: `class OutgoingNotification(OutgoingNotificationColumns, Base)` 와 마이그레이션(trpg-server 와 같은 모양) | 칸, 이름 붙은 제약, 기다리는 것만 담는 색인(`models.py`) |
| 무엇을 누구에게 알릴지 정하고, 그 일과 같은 트랜잭션에서 `repository.put` 으로 적는다. 탈퇴하면 `repository.drop_for_user` | 쿼리. 바꾸는 것은 아직 기다리는 줄만(`repository.py`) |
| 설정에 `NotificationSettings` 를 물려받는다(`NOTIFICATION_URL`, `NOTIFICATION_SECRET`, `NOTIFICATION_TIMEOUT_SECONDS`) | 주소를 적으면 비밀이 32자 이상이어야 뜬다(`settings.py`) |
| 앱에 `build_notifications(settings, http_client, '<서버 이름>')` 과 `NotificationDispatcher(SqlOutboxStore(session_factory, 표), ...)` 를 붙이고 lifespan 에서 `dispatcher.start` 한다 | 서명해 넣기와 답의 뜻(`client.py`), 5초마다 보내기, 10초에서 두 배씩 1시간까지 다시 보내기, 받지 않은 것은 실패로 남기기, 7일 지난 것 지우기, 로그(`notification.send`)와 추적, 메트릭(`dispatcher.py`) |

서버 이름(`asset`, `chat`)은 알림 서버의 주소에 들어가고, 알림 서버는 그 이름의 비밀(`ASSET_SERVER_SECRET` 등)로 서명을 본다.
알림의 종류는 알림 서버의 목록에 그 서버의 것으로 있어야 받는다.

## 테스트

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run pytest --cov
```

DB 없이 돈다. DB 에 닿는 것(쿼리의 span, 연결을 기다린 시간, DB 의 응답, 발송함의 쿼리)은 쓰는 서버의 테스트가 실제 DB 로 본다.
보내는 작업은 메모리의 가짜 발송함으로 본다(`tests/test_notifications.py`). 발송함의 쿼리(`repository.py`, `store.py`)는 asset-server 의 테스트가 본다.
`tests/test_boundary.py` 가 공용 코드가 서버의 모듈(`app.*`)이나 다른 공용 패키지를 가져오지 않는지, 운영 코드가 `server_core.testing` 을 가져오지 않는지 본다.

서버들의 테스트는 `server_core.testing` 의 도구를 함께 쓴다.

| 도구 | 하는 일 |
| --- | --- |
| `testing.tokens` | 서명 키, 토큰, 키 목록과 끊긴 세션의 목록을 내주는 가짜 인증 서버(`FakeAuthServer`) |
| `testing.spans` | span 을 메모리에 모으는 것(`recording`, `SpanRecorder`). 서버와 같은 `DropIdleRounds` 를 거친다 |
| `testing.metrics` | 메트릭을 메모리에 모으는 것(`recording`, `MetricsRecorder`) |
| `testing.collector` | OTLP 를 받는 가짜 수집기(`serving`) |
| `testing.logs` | 로그 한 줄을 서버가 내보내는 JSON 으로 읽는 것(`rendered`, `make_record`) |
