# 관측 규격

네 서버(`auth-server`, `game-server`, `board-server`, `billing-server`)가 로그, 메트릭, 추적 정보를 같은 모양으로 남기기 위한 약속이다.
언어와 프레임워크는 서버마다 다르지만, 밖에서 보이는 칸의 이름과 뜻은 같다.

이 문서가 기준이다. 칸의 이름이나 뜻을 바꾸려면 이 문서부터 고치고 네 서버를 함께 고친다.

## 목차

- [지금 있는 것과 없는 것](#지금-있는-것과-없는-것)
- [로그, 메트릭, 추적의 역할](#로그-메트릭-추적의-역할)
- [서비스 이름, 환경, 버전](#서비스-이름-환경-버전)
- [식별자](#식별자)
- [로그](#로그)
- [민감정보](#민감정보)
- [health 와 readiness](#health-와-readiness)
- [메트릭](#메트릭)
- [개발 환경과 운영 환경](#개발-환경과-운영-환경)
- [OpenTelemetry Collector 를 붙일 자리](#opentelemetry-collector-를-붙일-자리)
- [관리 서버의 경계](#관리-서버의-경계)
- [서버별 구현](#서버별-구현)
- [알려진 빈틈](#알려진-빈틈)

## 지금 있는 것과 없는 것

| | 상태 |
| --- | --- |
| 요청 식별자(`X-Request-ID`)와 추적 식별자(`traceparent`) | 네 서버에 구현 |
| 공통 모양의 JSON 로그 | 네 서버에 구현 |
| 민감정보를 가리는 마지막 방어선 | 네 서버에 구현 |
| 백그라운드 작업의 식별자(`job_id`) | game-server, auth-server, billing-server 에 구현. board-server 는 아직 그런 작업이 없다 |
| 메트릭 | 이름과 규칙만 정했다. 내보내는 코드는 없다 |
| 추적(span) | trace_id 를 이어 주는 것까지만 있다. span 을 만들거나 내보내지 않는다 |
| OpenTelemetry Collector, Prometheus, Loki, Tempo, Grafana | 없다 |
| 관리 서버, 관리 DB, 관리자 화면, Gemma 요약 | 없다 |

## 로그, 메트릭, 추적의 역할

셋은 서로를 대신하지 못한다. 어느 것에 무엇을 싣는지를 정해 두지 않으면 로그에 숫자를 세게 하거나 메트릭에 사용자 번호를 넣게 된다.

| | 답하는 질문 | 단위 | 값의 종류 | 예 |
| --- | --- | --- | --- | --- |
| 로그 | "그때 무슨 일이 있었나" | 사건 하나 | 얼마든지 늘어도 된다(식별자를 싣는다) | 이 요청은 왜 500 이었나 |
| 메트릭 | "얼마나 자주, 얼마나 오래" | 시간에 따라 모은 수 | 늘면 안 된다(label 의 값이 정해져 있다) | 5분 동안 5xx 의 비율 |
| 추적 | "이 요청은 어디를 거쳤고 어디서 느렸나" | 요청 하나의 경로 | 식별자로 잇는다 | 라운드 닫기가 느린 것은 임베딩인가 서술인가 |

- 경보는 메트릭으로 건다. 로그의 줄 수를 세어 경보를 걸지 않는다. 로그는 표본으로 줄일 수도, 잃을 수도 있다.
- 한 건을 파고들 때는 로그와 추적을 쓴다. 메트릭의 그래프에서 이상한 구간을 찾고, 그 구간의 로그를 `trace_id` 로 따라간다.
- 로그에서 수를 세고 싶어지면 메트릭이 빠진 것이다. 메트릭에서 "누구의 요청인가"를 알고 싶어지면 로그를 볼 차례다.

## 서비스 이름, 환경, 버전

서비스 이름은 코드에 적혀 있다. 설정으로 바꾸지 않는다. 폴더 이름과 같다.

| 서버 | `service` |
| --- | --- |
| 인증 서버 | `auth-server` |
| 게임 서버 | `game-server` |
| 게시판 서버 | `board-server` |
| 결제 서버 | `billing-server` |
| 프록시(nginx) | `proxy` |

프록시는 서버 넷 앞에 서는 nginx 다(`docker/nginx/templates/default.conf.template`). 요청이 끝난 줄만 남긴다. [프록시의 줄](#프록시의-줄)에 따로 적었다.

환경과 버전은 네 서버가 같은 이름의 환경 변수로 받는다. 비밀값이 아니다.

| 환경 변수 | 기본값 | 받는 모양 | 로그의 칸 |
| --- | --- | --- | --- |
| `APP_ENVIRONMENT` | `development` | 소문자로 시작하고 소문자, 숫자, `_`, `-` 로 된 32자 이하 | `environment` |
| `APP_VERSION` | `dev` | 영문자, 숫자, `.`, `_`, `+`, `-` 로 된 64자 이하 | `version` |
| `LOG_LEVEL` | `info` | `debug`, `info`, `warning`, `error` 가운데 하나 | 남기는 가장 낮은 수준 |

- 운영에서는 배포할 때 `APP_ENVIRONMENT=production` 과 `APP_VERSION=<git SHA 나 이미지 태그>` 를 넣는다.
  "이 오류는 어느 배포부터 났는가"를 로그만으로 알 수 있다.
- 모양이 틀리면 서버가 뜨지 않는다. 이 값들은 모든 로그 줄에 실리므로 줄바꿈이나 따옴표가 든 값을 받지 않는다.
- 설정 전체를 시작할 때 로그로 찍지 않는다. `DATABASE_URL` 같은 값이 섞여 나간다.

## 식별자

식별자는 셋이다. 모두 **로그를 찾는 데만** 쓴다.

| 이름 | 가리키는 것 | 만드는 곳 | 수명 | 모양 |
| --- | --- | --- | --- | --- |
| `request_id` | 서버 하나가 받은 HTTP 요청 하나 | 요청을 받은 서버 | 그 요청이 끝날 때까지 | 받은 것이 형식에 맞으면 그것, 아니면 UUID v4 |
| `trace_id` | 사용자의 한 동작이 여러 서버를 거치는 흐름 전체 | 흐름을 처음 받은 서버 | 흐름이 끝날 때까지. 서버와 작업을 넘어 이어진다 | 소문자 16진수 32자 |
| `job_id` | 요청과 따로 도는 작업 하나(서술, 색인, 메일 발송) | 작업을 시작하는 곳 | 그 작업이 끝날 때까지 | UUID v4 |

**식별자는 인증이나 권한 판단에 쓰지 않는다.** `request_id` 와 `trace_id` 는 부르는 쪽이 정할 수 있는 값이다.
"이 요청 식별자를 아는 사람은 이 요청의 주인이다" 같은 판단을 하지 않는다. 누구의 요청인지는 access 토큰만이 말한다.

### 요청 식별자 `X-Request-ID`

머리말 이름은 `X-Request-ID` 다. 프록시(nginx, 로드 밸런서)와 클라이언트가 가장 널리 쓰는 이름이다.

요청을 받으면:

1. `X-Request-ID` 가 **`[A-Za-z0-9._-]` 로 된 8자 이상 64자 이하**면 그대로 쓴다.
2. 없거나, 길이가 맞지 않거나, 다른 글자(공백, 줄바꿈, 제어 문자, 따옴표, 쉼표, 한글 등)가 있거나, 같은 머리말이 여러 번 왔으면 **새 UUID v4 로 바꾼다.**
   틀린 값을 잘라 쓰거나 고쳐 쓰지 않는다. 받은 값의 어느 부분도 로그에 남지 않는다.
3. 정한 값을 응답의 `X-Request-ID` 머리말로 돌려준다. 401, 404, 500 에도 실린다.

프록시(nginx)를 거쳐 오는 요청은 **프록시가 정한 값**(32자 16진수)이 온다. 클라이언트가 보낸 `X-Request-ID` 는 프록시가 버리고 제 것으로 바꿔 넘긴다.
그래서 프록시의 줄과 서버의 줄이 같은 `request_id` 로 이어진다. 프록시가 직접 답한 요청(404, 429, 502)에도 그 값이 실린다.

받는 글자를 좁게 잡은 이유는 로그 삽입이다. 줄바꿈이 든 값을 그대로 로그에 적으면 부르는 쪽이 가짜 로그 줄을 만들 수 있다.
JSON 으로 적으면 줄바꿈이 `\n` 으로 바뀌어 줄이 깨지지는 않지만, 로그를 다시 다른 도구로 옮길 때마다 그 도구의 처리를 믿어야 한다.
애초에 받지 않는 쪽이 싸다.

사용자에게 오류를 보여 줄 때 이 값을 함께 보여 주면("문의할 때 이 번호를 알려 주세요") 그 요청의 로그를 바로 찾는다.

### 추적 식별자 `traceparent`

머리말 이름은 `traceparent` 다. [W3C Trace Context](https://www.w3.org/TR/trace-context/) 의 것이고 OpenTelemetry 가 기본으로 쓴다.
따로 `X-Trace-ID` 를 만들지 않았다. 나중에 OpenTelemetry SDK 로 바꿀 때 머리말을 다시 맞출 일이 없다.

```
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             버전  trace-id (32자)                  parent-id (16자)  flags
```

요청을 받으면:

1. `traceparent` 가 버전 `00` 의 모양에 맞으면 그 `trace-id` 를 이어 쓴다. `flags` 는 그대로 기억한다.
2. 없거나 틀리면(다른 버전, 대문자, 길이가 다름, 0 으로만 된 식별자) 새 `trace-id` 를 만든다. `flags` 는 `00` 이다.
3. 로그의 `trace_id` 칸에 `trace-id` 를 적는다.

지금 구현하지 않은 것:

- `tracestate` 머리말을 읽거나 넘기지 않는다.
- span 을 만들지 않는다. 다른 서버를 부를 때 넣는 `parent-id` 는 부를 때마다 새로 만든 난수다. 실제 span 의 번호가 아니다.
- 응답에 `traceparent` 를 돌려주지 않는다. 응답으로는 `X-Request-ID` 만 준다.

### 서버끼리 부를 때

| 부르는 곳 | 넘기는 것 | 넘기지 않는 것 |
| --- | --- | --- |
| 우리 서버(지금은 인증 서버의 JWKS) | `traceparent`. `trace-id` 와 `flags` 는 그대로, `parent-id` 는 새로 | `X-Request-ID` |
| 밖의 서비스(AI provider, SMTP, 결제 대행사) | 없다 | 둘 다 |

- `X-Request-ID` 를 넘기지 않는 이유: `request_id` 는 "서버 하나가 받은 요청 하나"다. 받는 서버가 제 것을 따로 만든다.
  두 서버의 로그는 `trace_id` 로 잇는다. 넘겨받아 쓰면 한 `request_id` 가 두 서버의 서로 다른 요청을 가리키게 된다.
- 밖의 서비스에 넘기지 않는 이유: 우리 안의 흐름을 밖에 알릴 까닭이 없다. 밖의 서비스가 주는 요청 번호가 있으면 그것을 우리 로그에 적는다.
- 요청 밖에서 부르면(서버가 뜰 때 미리 키를 받는 것처럼 걸린 추적이 없으면) 아무것도 붙이지 않는다.

### 작업 식별자 `job_id`

요청과 따로 도는 작업은 요청이 끝난 뒤에도 돈다. 그래서 요청의 것과 다른 식별자를 가진다.

- 작업을 시작할 때 `job_id` 를 새로 만든다.
- 작업 안의 로그에는 `job_id` 와 `trace_id` 가 붙고 **`request_id` 는 붙지 않는다.** 붙어 있으면 이미 끝난 요청이 아직 일하는 것처럼 보인다.
- 요청이 작업을 띄웠으면 `trace_id` 를 이어받는다. 혼자 시작한 작업(워커, 예약 명령)은 새 추적을 시작한다.
- 작업을 띄우는 쪽은 "작업을 맡겼다"는 줄을 남기고, 그 줄의 `spawned_job_id` 칸에 새 작업의 번호를 적는다.
  그 줄에는 띄운 쪽의 `request_id`(또는 `job_id`)가 붙어 있으므로 "이 요청이 어느 작업을 띄웠나"가 한 줄로 이어진다.

지금 `job_id` 가 붙는 작업:

| 서버 | 작업 | `operation` |
| --- | --- | --- |
| game-server | 라운드를 닫은 뒤의 AI 서술 | `round.narrate` |
| game-server | 마감이 지난 라운드 닫기와 크레딧을 기다리는 시간이 지난 라운드 마무리(서버의 시계가 5초마다 한 바퀴. 바퀴마다 새 `job_id`. 줄에 `closed`, `credit_waits`) | `round.close_overdue` |
| game-server | 끝나지 않은 서술 값의 청구를 결제 서버에 마저 맡기기(정리 작업이 5초마다 한 바퀴. 바퀴마다 새 `job_id`) | `charge.settle` |
| game-server | 로어북 항목의 벡터 만들기 | `lore.index` |
| game-server | 지난 라운드(기억)의 벡터 만들기 | `memory.index` |
| auth-server | 발송함의 메일 보내기(워커가 한 번 훑는 것) | `mail.deliver_outgoing` |
| auth-server | 환영 크레딧을 결제 서버에 맡기기(워커가 한 번 훑는 것) | `welcome_credit.deliver` |
| auth-server | 이미 가입한 계정들에 환영 크레딧을 주라고 적어 두기(한 번 돌리는 명령) | `welcome_credit.request_existing` |
| billing-server | 만료된 홀드·주문, 사라진 무료 크레딧 닫기(정리 작업이 30초마다 한 바퀴. 바퀴마다 새 `job_id`) | `sweep.run` |
| billing-server | 장부 맞춰 보기와 오래된 결제 끝내기(하루 한 번 돌리는 명령) | `reconcile.run` |
| auth-server | 가입을 끝내지 않은 이메일의 오래된 가입 코드 지우기 | `account.delete_unverified` |
| auth-server | 보안 이벤트 요약 메일 | `security.send_digest` |

## 로그

### 한 줄의 모양

한 줄에 JSON 객체 하나다. 표준 오류(stderr)로 내보낸다. 파일에 쓰지 않는다. 모으는 일은 실행 환경(컨테이너 런타임, Collector)이 한다.

```json
{"timestamp":"2026-10-11T09:00:00.123Z","level":"info","service":"game-server","environment":"production","version":"3f2a9c1","logger":"app.observability.middleware","message":"요청을 처리했다","request_id":"0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","operation":"http.request","method":"POST","route":"/api/v1/game/tables/{table_id}/rounds/current/close","status_code":202,"duration_ms":38,"result":"success"}
```

### 모든 줄에 있는 칸

| 칸 | 자료형 | 뜻 |
| --- | --- | --- |
| `timestamp` | 글자 | RFC 3339, UTC, 천분의 1초까지. `2026-10-11T09:00:00.123Z` |
| `level` | 글자 | `debug`, `info`, `warning`, `error`, `critical` |
| `service` | 글자 | 서비스 이름 |
| `environment` | 글자 | `APP_ENVIRONMENT` |
| `version` | 글자 | `APP_VERSION` |
| `message` | 글자 | 사람이 읽는 글. 2000자에서 자른다 |

`environment` 와 `version` 은 설정을 읽기 전의 줄(설정이 틀려 뜨지 못했다)에는 없을 수 있다.

### 있을 때만 싣는 칸

값이 없으면 칸을 싣지 않는다. 빈 글자나 `null` 로 채우지 않는다. "값이 빈 글자다"와 "해당 없다"가 섞이지 않는다.

| 칸 | 자료형 | 뜻 |
| --- | --- | --- |
| `logger` | 글자 | 로그를 남긴 곳의 이름(Python 의 로거 이름, Nest 의 context). Go 에는 없다 |
| `request_id` | 글자 | 요청 안에서 남긴 줄 |
| `trace_id` | 글자 | 요청이나 작업 안에서 남긴 줄 |
| `job_id` | 글자 | 작업 안에서 남긴 줄 |
| `operation` | 글자 | 무슨 일을 하던 중인가. [이름 규칙](#operation-이름) |
| `result` | 글자 | `success`, `client_error`, `server_error`, `cancelled` |
| `duration_ms` | 정수 | 걸린 시간. 천분의 1초 |
| `error_code` | 글자 | 오류의 종류. [이름 규칙](#오류-코드) |
| `error_type` | 글자 | 예외의 종류(클래스나 타입의 이름) |
| `error_message` | 글자 | 오류의 글. 호출 기록이 없는 오류(Go 의 `error`)의 원인을 싣는다. 500자에서 자른다 |
| `stack_trace` | 글자 | 호출 기록. 16000자에서 자른다 |
| `method` | 글자 | HTTP 메서드 |
| `route` | 글자 | 요청이 맞은 주소의 **틀**. 맞은 것이 없으면 `(unmatched)` |
| `path` | 글자 | 실제 경로. `route` 가 `(unmatched)` 일 때만 싣는다. 주소 뒤의 `?a=b` 는 뺀다 |
| `status_code` | 정수 | HTTP 상태 코드 |
| `job_name` | 글자 | 작업에 붙인 사람이 읽는 이름 |
| `spawned_job_id` | 글자 | 이 줄에서 띄운 작업의 `job_id` |

이 밖의 칸을 서버가 더 실을 수 있다(`order_id`, `key_count` 등). 지킬 것은 셋이다.

- 이름은 소문자와 밑줄(`snake_case`)이다.
- 값은 글자, 숫자, 참거짓이다. 객체와 목록은 싣지 않는다([민감정보](#민감정보)).
- 위 표의 이름을 다른 뜻으로 쓰지 않는다.

`timestamp`, `level`, `service`, `environment`, `version`, `message`, `request_id`, `trace_id`, `job_id` 는 로거가 정한다.
로그를 남기는 코드가 같은 이름의 값을 넘겨도 덮어쓰지 못한다.

### 요청이 끝난 줄

요청마다, 응답이 끝났을 때 한 줄이 남는다. 미들웨어가 남긴다. 핸들러마다 적지 않는다.

- 꼭 있는 칸: 공통 칸 여섯, `request_id`, `trace_id`, `operation`(`http.request`), `method`, `route`, `status_code`, `duration_ms`, `result`.
- `route` 에는 틀을 적는다. `/api/v1/board/posts/:id` 이지 `/api/v1/board/posts/1234` 가 아니다.
  틀의 표기는 프레임워크의 것을 그대로 쓴다. FastAPI 는 `{table_id}`, Django 는 `<uuid:public_id>`, Nest 와 gin 은 `:id` 다.
  서버가 다르면 `service` 가 다르므로 섞이지 않는다.
- 맞은 틀이 없을 때(404)만 `route` 에 `(unmatched)` 를 적고 실제 경로를 `path` 에 따로 싣는다.
  `route` 는 메트릭의 label 로도 쓰일 값이다. 아무 주소나 찔러 보는 요청이 값의 종류를 끝없이 늘리게 두지 않는다.
- 머리말, 주소 뒤에 붙은 값(query string), 본문은 적지 않는다.
- 끝나지 않는 응답(게임 서버의 SSE 스트림)은 연결이 끊길 때 한 줄이 남는다. `duration_ms` 는 연결이 이어진 시간이다.

| 상태 코드 | `result` | `level` |
| --- | --- | --- |
| 100 ~ 399 | `success` | `info` |
| 400 ~ 499 | `client_error` | `info` |
| 500 ~ 599 | `server_error` | `error` |

4xx 를 `warning` 으로 올리지 않는다. 요청이 틀린 것이고 서버는 제 일을 했다.
4xx 가 갑자기 느는 것(공격, 깨진 클라이언트)은 줄의 수준이 아니라 메트릭으로 본다.

**상태 확인 주소(`/health`, `/health/ready`)는 수준이 다르다.** 관리 도구가 10초마다 부른다. 그대로 두면 서버마다 하루에 8,640줄이 쌓이고,
DB 가 죽으면 10초마다 `error` 가 난다. `route` 가 둘 중 하나면 아래를 따른다. `result` 는 위의 표 그대로다.

| 상태 코드 | `level` | 까닭 |
| --- | --- | --- |
| 503 | `warning` | 준비 안 됨. 오류가 아니라 이 주소의 답이다. 까닭(오류의 종류)은 readiness 가 따로 남긴다 |
| 그 밖의 5xx | `error` | 처리하지 못한 예외. 다른 주소와 같다 |
| 그 밖 | `debug` | 성공. 운영의 수준(`info`)에서는 남지 않는다. 확인이 오는지 보려면 `LOG_LEVEL=debug` 로 띄운다 |

네 서버의 코드: 인증·게임 `observability/middleware.py` 의 `probe_level_of`, 게시판 `request-logging.middleware.ts` 의 `probeLevelOf`, 결제 `internal/httpapi/observability.go` 의 `probeLevelOf`.
인증 서버는 Django 가 따로 남기는 줄(`django.request` 의 "Service Unavailable: /주소")도 버린다. 예외가 없는 5xx 는 미들웨어의 줄과 겹치고, Django 는 그것을 늘 `error` 로 적는다(`observability/setup.py` 의 `OnlyUnloggedServerErrors`).

### 프록시의 줄

프록시는 요청마다 한 줄을 남긴다. 칸은 공통 칸과 `request_id`, `operation`(`http.request`), `method`, `status_code`, `duration_ms`, `result` 에 `upstream` 이 더해진다.

- `upstream` 은 요청을 보낸 서버의 이름이다(`auth`, `game`, `board`, `billing`). 프록시가 직접 답한 것(막은 주소의 404)은 `proxy` 다.
  요청 수 제한의 429 는 그 서버의 이름이 실린다. 어느 서버로 가던 요청이 막혔는지 보인다.
- **경로를 적지 않는다.** 프록시는 주소의 틀(`route`)을 모른다. 실제 경로에는 사용자와 테이블의 번호가 들어 있다. 틀은 서버의 줄에 있다.
- `status_code` 는 클라이언트가 받은 값이다. 서버에 닿지 못했으면 502, 서버가 늦으면 504 이고 `level` 은 `error` 다.
- nginx 의 오류 로그는 `crit` 만 남긴다. 그 아래의 줄(요청 수 제한, 서버에 닿지 못함)에는 주소 뒤의 값(`?q=검색어`)까지 적힌다. 같은 일은 위의 줄에 상태 코드로 남는다.

### 예외가 난 줄

처리하지 못한 예외는 `error` 로 한 줄이 남는다. 꼭 있는 칸은 `request_id`(또는 `job_id`), `trace_id`, `operation`, `error_code`, `error_type`, `stack_trace` 다.
그 뒤에 요청이 끝난 줄(500, `server_error`)이 따로 남는다. 둘은 `request_id` 가 같다.

**응답에는 예외의 내용을 싣지 않는다.** 응답의 본문은 `{"detail": "..."}` 의 정해진 말이고, 호출 기록과 예외의 글은 서버의 로그에만 있다.
사용자가 볼 수 있는 것은 `X-Request-ID` 다. 그 번호로 로그를 찾는다.

게임, 게시판, 결제 서버는 `DEBUG` 를 켜도 같다. 인증 서버만 다르다. Django 는 `DEBUG=true` 면 예외의 응답에 호출 기록과 설정값을 실은 개발용 화면을 보낸다.
그래서 **`APP_ENVIRONMENT=production` 인데 `DEBUG=true` 면 인증 서버가 뜨지 않는다.**

### 작업이 끝난 줄

| 끝난 모양 | `result` | `level` |
| --- | --- | --- |
| 끝까지 돌았다 | `success` | `info`(주기적으로 도는 워커는 `debug`) |
| 서버를 끄느라 취소됐다 | `cancelled` | `warning` |
| 예외로 끝났다 | `server_error` | `error`. `error_code` 는 `job.failed` |

### 수준

| 수준 | 언제 | 예 |
| --- | --- | --- |
| `debug` | 개발할 때만 보는 것. 운영에서는 끈다 | 주기적인 워커가 할 일 없이 한 바퀴 돌았다 |
| `info` | 정상적인 일의 기록 | 요청이 끝났다(2xx ~ 4xx), 작업을 맡겼다, 서버가 떴다 |
| `warning` | 일은 계속되지만 누군가 알아야 하는 것. 스스로 낫거나 대신할 길이 있다 | JWKS 를 못 받아 기억한 키를 계속 쓴다, 임베딩을 못 만들어 키워드로만 찾는다, 결제 대행사가 답하지 않아 결과를 모르는 채로 둔다 |
| `error` | 요청이나 작업 하나가 실패했다. 사람이 봐야 한다 | 5xx, 처리하지 못한 예외, 작업이 예외로 끝났다 |
| `critical` | 프로세스가 일을 계속할 수 없다 | 지금 쓰는 곳은 없다. 서버가 뜨지 못한 것은 `error` 로 남기고 끝난다 |

고르는 기준은 "이 줄을 새벽에 누가 봐야 하는가"다. 봐야 하면 `error`, 다음 날 봐도 되면 `warning`, 안 봐도 되면 `info` 다.

### operation 이름

`<대상>.<하는 일>` 이다. 소문자와 밑줄, 점 하나로 나눈다. **정해진 수의 이름만 쓴다.**
사용자 번호, 테이블 번호, 주소처럼 계속 늘어나는 값을 이름에 넣지 않는다. 그런 값은 따로 칸에 싣는다.

| `operation` | 서버 | 뜻 |
| --- | --- | --- |
| `http.request` | 전부 | HTTP 요청 하나를 처리했다. 어느 주소인지는 `method` 와 `route` 에 있다 |
| `job.run` | game | 이름을 따로 주지 않은 작업 |
| `round.narrate` | game | 라운드의 AI 서술 |
| `round.close_overdue` | game | 마감이 지난 라운드 닫기, 크레딧을 기다리는 시간이 지난 라운드 마무리(#181) |
| `lore.index` | game | 로어북 색인 |
| `memory.index` | game | 기억 색인 |
| `charge.settle` | game | 끝나지 않은 서술 값의 청구를 결제 서버에 마저 맡기기(정리 작업의 한 바퀴) |
| `billing.hold` | game | 결제 서버에 서술 값의 홀드를 걸기 |
| `billing.capture` | game | 결제 서버에 홀드의 확정을 맡기기 |
| `billing.release` | game | 결제 서버에 홀드의 반환을 맡기기 |
| `billing.extend` | game | 결제 서버에 홀드의 연장을 맡기기(만료 전에) |
| `ledger_draft.write` | game | 서술한 장면에서 장부 초안을 쓰고 줄로 적기(서술을 맡은 작업의 끝, `round.narrate` 의 `job_id`) |
| `mail.deliver_outgoing` | auth | 발송함의 메일 보내기 |
| `welcome_credit.deliver` | auth | 환영 크레딧을 결제 서버에 맡기기 |
| `welcome_credit.request_existing` | auth | 이미 가입한 계정들에 환영 크레딧을 주라고 적어 두기 |
| `account.delete_unverified` | auth | 가입을 끝내지 않은 이메일의 오래된 가입 코드 지우기(옛 이름 그대로) |
| `security.send_digest` | auth | 보안 이벤트 요약 메일 |
| `auth.jwks_fetch` | billing | 인증 서버에서 공개키 받기 |
| `order.confirm` | billing | 주문의 결제 승인 |
| `order.refund` | billing | 주문의 청약철회(결제 취소) |
| `order.decide` | billing | 운영자가 결과를 모르던 주문의 결과를 정하기(`cmd/orders decide`). `from_status`, `outcome`, `decided_by`, `reason` 을 남긴다 |
| `server.start` | billing | 서버를 띄우기 |
| `sweep.run` | billing | 정리 작업의 한 바퀴. 만료된 홀드를 돌려주고, 사라진 무료 크레딧을 원장에 적고, 만료된 주문을 끝낸다 |
| `reconcile.run` | billing | 대사 한 번. 오래된 `confirming`·`refunding` 주문을 결제 대행사에 물어 끝내고, 장부를 맞춰 본다 |

### 오류 코드

`<영역>.<무슨 일>` 이다. 소문자와 밑줄, 점 하나로 나눈다. 예외의 글과 달리 **바뀌지 않는다.** 경보와 집계가 이 값에 기댄다.
글(`message`)은 고쳐 써도 되지만 코드는 한번 정하면 뜻을 바꾸지 않는다.

| `error_code` | 뜻 |
| --- | --- |
| `http.unhandled_exception` | 요청을 처리하다 아무도 잡지 않은 예외(패닉)가 났다 |
| `internal.error` | 그 밖의 서버 쪽 오류. 핸들러가 스스로 5xx 로 답한 것, 코드를 따로 주지 않고 예외를 남긴 것 |
| `job.failed` | 작업이 예외로 끝났다 |
| `auth.jwks_unavailable` | 인증 서버에서 공개키를 받지 못했다 |
| `payment.provider_unavailable` | 결제 대행사의 답을 받지 못했거나, 결과를 알 수 없는 답이 왔다(토스페이먼츠의 5xx, 401, "처리 중" 같은 것). 주문은 `confirming` 에 남고 다시 부르거나 대사가 조회해 끝낸다. 청약철회(`order.refund`)면 `refunding` 에 남고 다시 부르거나 대사가 같은 취소를 다시 보낸다. 가상계좌(입금 대기)를 취소하지 못했을 때도 이 코드다(`order.confirm`, `cancel_status`). `warning` |
| `billing.unavailable` | 결제 서버에 일을 맡기지 못했다. 다시 부른다. 게임 서버(홀드): 답을 받지 못했다. 서명이 거절된 것(401)이면 `error`, 그 밖에는 `warning`. 서술 뒤의 확정을 정해 둔 시간 안에 끝내지 못해 정리 작업에 넘긴 것도 이 코드다(`warning`). 인증 서버(환영 크레딧): 닿지 못했거나 2xx 가 아닌 답이 왔다. `warning` |
| `billing.rejected` | 결제 서버가 게임 서버의 요청을 받아들이지 않았다(400, 404, 409). 다시 불러도 같다. 연장이면 홀드를 그대로 두고 한 시간 뒤에 다시 부른다. 서술 뒤의 확정이 409(만료되어 돌려준 홀드)면 그 값은 받지 못한다. 홀드가 400 이면 가격표에 그 서술 등급의 이름(`narration.premium` 등)이 없는지 먼저 본다 |
| `signals.bad_signature` | 게임 서버가 서명이 맞지 않는 실시간 신호(NOTIFY)를 받아 버렸다. 같은 DB 의 다른 계정이 꾸며 보냈거나, 게임 서버들의 `SIGNAL_SECRET` 이 서로 다르다. `sender_pid` 에 보낸 연결의 프로세스 번호를 싣는다(`pg_stat_activity` 에서 계정을 찾는다). 받은 글자는 싣지 않는다. `warning` |
| `ledger_draft.failed` | 게임 서버가 서술한 장면에서 장부 초안을 쓰지 못했다(테이블을 읽기, 모델 부르기, 줄 적기 중 하나가 예외로 끝났거나 90 초가 지났다). 라운드는 이미 닫혔고 방장은 손으로 장부를 고치면 된다. `table_id`, `round`. 모델의 답을 읽지 못한 것(`not_json` 등)은 이 코드가 아니라 호출 기록에 남는다. `warning` |
| `limits.unavailable` | 게임 서버가 시도 횟수를 세는 곳(Redis)에 닿지 못했다. `limit` 에 어느 제한인지, `blocked` 에 막았는지(로비의 비밀번호) 통과시켰는지(채팅) 싣는다. `warning` |
| `server.start_failed` | 서버가 뜨지 못했다 |
| `ledger.mismatch` | 결제 서버가 남긴다. 대사에서 지금의 값(지갑, 지급 묶음, 주문, 홀드)이 원장과 맞지 않는 줄을 찾았다. 줄마다 `error` 한 줄. `check` 에 검사의 이름, `record_id` 에 그 줄의 번호. 사람이 봐야 한다 |
| `order.stuck` | 결제 서버가 남긴다. 대사가 결제 대행사에 다시 묻고도, 결과를 모르는 채(`confirming`, `refunding`)로 하루가 지난 주문이 있다. 주문마다 `warning` 한 줄. `order_id`, `status`, `since`. 사람이 상점관리자에서 확인하고 `cmd/orders decide` 로 정한다 |
| `sweep.behind` | 결제 서버가 남긴다. 대사가 셀 때, 만료된 지 한참(기본 10분) 지났는데 정리되지 않은 것이 있다. 정리 작업이 멈췄거나 밀렸다. `warning` |

`error` 이상의 줄에는 `error_code` 를 붙인다. 새 코드를 만들면 이 표에 더한다.
Python 서버들은 예외가 실린 줄(`logger.exception`)에 코드를 따로 주지 않으면 `internal.error` 를 붙인다. Nest 와 Go 는 남기는 쪽이 직접 붙인다.
이것은 **로그의** 코드다. API 응답의 `code`(`too_many_attempts` 같은 것)와 다른 것이다. 응답의 코드는 클라이언트와의 약속이고 서버마다 README 에 있다.

## 민감정보

### 로그에 적지 않는 것

- 비밀번호와 비밀번호의 해시
- access 토큰, refresh 토큰, 그 밖의 JWT 의 전체 값
- `Authorization`, `Cookie`, `Set-Cookie` 머리말
- 이메일 인증 코드, 로그인 코드
- 비밀번호 재설정 토큰
- 테이블의 초대 코드와 비밀번호
- DB 접속 주소와 비밀번호(`DATABASE_URL`, `REDIS_URL`)
- API key, 웹훅의 서명과 그 비밀
- 결제 수단의 정보, 결제 대행사의 결제 번호(`payment_key`)
- 이메일 주소의 전체
- 비공개 GM 메모와 로어의 원문
- AI provider 에 보낸 prompt 의 전체와 받은 답의 전체
- 채팅과 플레이어 선언의 원문, 게시글과 댓글의 제목과 본문

대신 적는 것:

- 누구인지는 사용자 번호(`public_id`)로 적는다. 이메일로 적지 않는다. 꼭 이메일이 필요하면 가린 것(`a***@example.com`)이나 해시를 적는다.
- 무엇인지는 번호로 적는다(`order_id`, `post_id`, `table_id`). 내용을 적지 않는다.
- AI 호출은 원문 대신 길이, 토큰 수, 모델 이름, 걸린 시간, 결과를 적는다.
  게임 서버는 이미 AI 호출마다 기록을 DB 에 남긴다(`app/ai/calls.py`). 거기에도 보낸 메시지는 없고 HMAC 지문만 있다.

### 원문을 남기는 개발 기능

원문을 로그에 남기는 기능은 지금 하나다. 인증 서버의 **콘솔 메일 백엔드**다. `SMTP_HOST` 를 적지 않으면 메일을 보내지 않고
받는 주소와 인증 코드가 든 본문을 표준 출력에 찍는다. 메일 서버 없이 개발하려고 둔 것이다.

- 기본값: `SMTP_HOST` 가 없을 때만 켜진다. 따로 켜는 설정은 없다.
- 운영: **`APP_ENVIRONMENT=production` 인데 `SMTP_HOST` 가 없으면 인증 서버가 뜨지 않는다.** 운영의 로그에 인증 코드가 찍힐 길을 막았다.

원문을 남기는 기능을 새로 만들 때의 규칙:

1. 기본은 꺼짐이다.
2. 그 기능만을 위한 설정으로 켠다. `DEBUG` 나 `LOG_LEVEL=debug` 에 묶지 않는다. 다른 이유로 켠 설정이 원문을 흘리면 안 된다.
3. `APP_ENVIRONMENT=production` 이면 켤 수 없다. 켜려고 하면 서버가 뜨지 않는다.

### 마지막 방어선

위의 규칙은 로그를 남기는 코드가 지킨다. 그래도 실수는 난다. 그래서 줄이 나가기 직전에 한 번 더 거른다. 네 서버가 같은 규칙이다.

**1. 칸의 이름을 본다.** 이름을 낱말로 쪼개(`access_token`, `accessToken`, `Access-Token` 은 모두 `access`, `token`) 다음에 걸리면 값을 `[REDACTED]` 로 바꾼다.

| 무엇 | 목록 |
| --- | --- |
| 이 낱말이 든 이름 | `password`, `passwd`, `secret`, `token`, `jwt`, `authorization`, `cookie`, `credential(s)`, `otp`, `dsn`, `email`, `prompt`, `card`, `cvc`, `cvv`, `code`, `signature` |
| 이 낱말들이 이어진 이름 | `api_key`, `private_key`, `access_key`, `payment_key`, `database_url`, `redis_url`, `set_cookie` |
| 정확히 이 이름 | `body`, `content`, `text`, `title`, `declaration`, `memo`, `note(s)`, `lore`, `completion`, `response`, `headers`, `request_body`, `response_body` |
| 가리지 않는 이름 | `error_code`, `status_code`, `exit_code`, 그리고 `hash`, `masked`, `count`, `length`, `version`, `id`, `ms`, `seconds`, `type` 으로 끝나는 이름(`email_hash`, `token_count`, `token_type`) |

**2. 값의 글을 본다.** 어느 칸이든(`message`, `stack_trace` 도) 다음 모양을 가린다.

| 모양 | 바뀐 뒤 |
| --- | --- |
| JWT(`eyJ….….…`) | `[REDACTED_JWT]` |
| `Bearer <값>`, `Basic <값>` | `Bearer [REDACTED]` |
| 주소에 든 계정과 비밀번호(`://user:pass@host`) | `://[REDACTED]@host` |
| 이메일 주소 | `a***@example.com`(첫 글자와 도메인만) |

**3. 값의 종류를 본다.** 글자, 숫자, 참거짓만 싣는다. 객체, 맵, 목록은 풀어 적지 않고 종류의 이름만 적는다(`[dict]`, `[Object]`, `[map[string]string]`).
요청 객체나 설정 객체를 통째로 넘겨도 그 안의 값이 나가지 않는다. 무엇이 들었는지 모르는 것을 끝없이 풀어 적지 않는다.

**4. 길이를 자른다.** 칸 하나는 500자, `message` 는 2000자, `stack_trace` 는 16000자다. 본문 같은 긴 글이 통째로 실리지 않는다.

이 방어선은 어림이다. 이름이 `value` 인 칸에 든 비밀번호나, 모양이 없는 비밀(초대 코드 여섯 글자)이 `message` 에 섞인 것은 걸러 내지 못한다.
**넘기지 않는 것이 규칙이고, 이것은 그 규칙이 깨졌을 때의 그물이다.**

## health 와 readiness

| 주소 | 묻는 것 | 보는 것 | 답 |
| --- | --- | --- | --- |
| `GET /health` | 프로세스가 살아 있는가 | 아무것도 보지 않는다 | 항상 `200 {"status":"ok"}` |
| `GET /health/ready` | 요청을 처리할 준비가 됐는가 | 꼭 필요한 의존성(지금은 DB) | `200 {"status":"ok"}` 또는 `503 {"status":"unavailable"}` |

- **health 는 DB 를 보지 않는다.** DB 가 죽었다고 health 까지 실패하면, 프로세스를 다시 띄워도 낫지 않는 문제에 재시작만 되풀이된다.
  health 가 실패하면 "프로세스를 다시 띄워라", readiness 가 실패하면 "이 프로세스에 요청을 보내지 마라"다.
- **readiness 에는 "없으면 일을 못 하는 것"만 넣는다.** 인증 서버(JWKS)는 넣지 않는다. 기억한 키로 계속 일할 수 있다.
  AI provider 도 넣지 않는다. 서술이 늦어질 뿐 테이블은 돈다.
- 두 주소는 API 주소(`/api/v1/...`) 밖에 있고 로그인이 필요 없다. 프록시와 관리 도구가 부른다.
- **GET 과 HEAD 를 받는다.** HEAD 에는 GET 과 같은 상태 코드로, 본문 없이 답한다. HEAD 로 확인하는 도구가 있다. 다른 메서드는 서버의 기본 답이다(405 또는 404).
- 요청이 끝난 줄은 성공이면 `debug`, 503 이면 `warning` 이다([요청이 끝난 줄](#요청이-끝난-줄)).
- 응답에는 `status` 하나만 있다. DB 주소, 계정, 예외의 글, 다른 서버의 주소를 싣지 않는다. 실패한 이유는 서버의 로그에 있다.

| 서버 | `/health` | `/health/ready` | DB 를 기다리는 시간 |
| --- | --- | --- | --- |
| game-server | 있다 | 있다(DB) | 연결 5초. 연결된 뒤 답하지 않는 DB 앞에서는 끝이 없다(#258) |
| board-server | 있다 | 있다(DB) | 3초 |
| billing-server | 있다 | 있다(DB) | 3초 |
| auth-server | 있다 | 있다(DB) | 연결 5초. 연결된 뒤 답하지 않는 DB 앞에서는 끝이 없다(아래) |

- **compose 의 healthcheck 는 `/health/ready` 를 부른다.** 그래서 `healthy` 는 "DB 에 닿는다"는 뜻이다. DB 가 죽으면 서버가 `unhealthy` 로 보인다.
  Docker 는 `unhealthy` 를 보고 재시작하지 않고, 서버의 `healthy` 를 기다리는 서비스도 없다. DB 가 돌아오면 다음 확인에서 `healthy` 로 돌아온다.
  CI 의 스택 확인(`.github/scripts/stack-smoke.sh`)도 네 서버의 레디를 본다.
- **확인하는 쪽은 healthcheck 의 `timeout`(5초)이 묶는다.** 서버의 레디가 답하지 않아도 5초가 지나면 실패로 센다.
  서버 쪽의 시간 제한은 그보다 짧게(3초) 두어 503 으로 답하게 한다. 결제(Go 의 context)와 게시판(쿼리와 타이머의 경주)이 그렇다.
- **인증 서버에는 서버 쪽의 전체 제한이 없다.** 동기 Django(psycopg)에는 쿼리 하나만 시간으로 끊는 장치가 없다.
  `statement_timeout` 은 DB 가 살아서 느릴 때만 듣고, DB 가 멈췄거나 네트워크가 끊겼을 때는 듣지 않는다. 스레드로 떼어 기다리면 멈춘 스레드가 쌓인다.
  그래서 연결 시간(5초)만 묶고, 연결된 뒤 멈춘 DB 는 healthcheck 의 5초가 실패로 센다. 그동안 그 요청이 워커를 쥐는 것은 같은 DB 앞의 보통 요청과 같다.
- **실패하면 네 서버 모두 오류의 종류만 로그에 남긴다**(결제는 `error_type` 칸). 오류의 글에는 DB 주소와 계정 이름이 들어 있다.

**응답에 서비스 이름과 버전을 더하지 않았다.** 세 서버의 테스트가 본문이 정확히 `{"status":"ok"}` 인 것을 확인하고 있고,
프록시의 상태 확인이 본문을 글자 그대로 비교하도록 설정될 수 있다. 버전은 로그의 `version` 칸으로 안다.
상태 확인 응답에도 `X-Request-ID` 머리말은 붙는다. 본문은 그대로다.

## 메트릭

**이름과 규칙만 정했다. 내보내는 코드는 아직 없다.** 붙일 때 이 표를 따른다.

### 규칙

- 이름은 소문자와 밑줄이다. Prometheus 와 OpenTelemetry 가 함께 받는 모양이다.
- **단위를 이름의 끝에 적는다.** 시간은 **초(`_seconds`)** 로 통일한다. 크기는 `_bytes`.
  로그의 `duration_ms` 는 천분의 1초다. 로그는 사람이 한 건을 읽으므로 정수 밀리초가 읽기 쉽고, 메트릭은 Prometheus 의 관례(기본 단위)를 따라 초를 쓴다.
- **쌓이는 수(counter)는 `_total` 로 끝난다.** 올라가기만 한다. 비율은 조회할 때 `rate()` 로 구한다.
- **지금의 값(gauge)은 `_total` 을 붙이지 않는다.** 오르내린다(`http_server_active_requests`).
- 분포(histogram)는 단위로 끝난다(`_seconds`). `_bucket`, `_sum`, `_count` 는 도구가 붙인다.
- 서버마다 이름을 다르게 짓지 않는다. 같은 것은 같은 이름이고 `service` label 로 가른다.

### label

label 의 값의 종류는 **정해져 있고 적어야** 한다. label 값의 조합마다 시계열이 하나씩 생긴다.

| 써도 되는 것 | 값 |
| --- | --- |
| `service` | 네 가지 |
| `method` | HTTP 메서드 |
| `route` | 주소의 틀. 로그의 `route` 와 같은 값이다. 맞은 것이 없으면 `(unmatched)` |
| `status_code` | 상태 코드 |
| `operation` | 위 표의 이름들 |
| `result`, `outcome` | 정해진 몇 가지 |
| `provider`, `model` | 설정에 적은 것들 |

**넣지 않는 것:** `user_id`, `table_id`, `order_id`, `post_id`, `request_id`, `trace_id`, `job_id`, 이메일, 실제 주소(URL 원문), 예외의 글, 사용자가 넣은 글.
이런 값은 로그에 싣는다. "어느 사용자의 요청이 느렸나"는 메트릭이 아니라 로그와 추적이 답한다.

### 목록

모든 메트릭에 `service` label 이 붙는다. 아래 표에서는 뺐다.

**HTTP (네 서버)**

| 이름 | 종류 | label | 뜻 |
| --- | --- | --- | --- |
| `http_server_requests_total` | counter | `method`, `route`, `status_code` | 끝난 요청의 수. 상태 코드별 오류 수는 이것에서 고른다(`status_code=~"5.."`) |
| `http_server_request_duration_seconds` | histogram | `method`, `route` | 요청을 받아 응답을 끝낼 때까지. SSE 스트림은 뺀다 |
| `http_server_active_requests` | gauge | 없음 | 지금 처리 중인 요청의 수 |

**DB (네 서버)**

| 이름 | 종류 | label | 뜻 |
| --- | --- | --- | --- |
| `db_up` | gauge | 없음 | readiness 가 마지막으로 본 DB 의 상태. 1 이면 닿는다 |
| `db_pool_connections` | gauge | `state`(`idle`, `in_use`) | 연결 풀의 연결 수 |
| `db_pool_connections_max` | gauge | 없음 | 풀이 가질 수 있는 가장 많은 연결 |
| `db_pool_wait_seconds` | histogram | 없음 | 연결을 얻으려고 기다린 시간 |

**백그라운드 작업 (game, auth)**

| 이름 | 종류 | label | 뜻 |
| --- | --- | --- | --- |
| `background_jobs_started_total` | counter | `operation` | 시작한 작업의 수 |
| `background_jobs_finished_total` | counter | `operation`, `result`(`success`, `server_error`, `cancelled`) | 끝난 작업의 수. 실패 수는 `result="server_error"` |
| `background_jobs_running` | gauge | `operation` | 지금 도는 작업의 수 |
| `background_jobs_queued` | gauge | `operation` | 기다리는 일의 수. 인증 서버의 발송함에 남은 메일이 여기다 |
| `background_job_duration_seconds` | histogram | `operation` | 작업 하나가 걸린 시간 |

**실시간 스트림 (game)**

| 이름 | 종류 | label | 뜻 |
| --- | --- | --- | --- |
| `sse_connections` | gauge | 없음 | 지금 열려 있는 SSE 연결의 수 |
| `sse_connections_opened_total` | counter | 없음 | 열린 연결의 수 |
| `sse_connection_duration_seconds` | histogram | 없음 | 연결이 이어진 시간 |

**AI 호출 (game)**

| 이름 | 종류 | label | 뜻 |
| --- | --- | --- | --- |
| `ai_calls_total` | counter | `operation`, `provider`, `model`, `outcome`(`ok`, `rejected`, `failed`) | AI 를 부른 수. 값은 AI 호출 기록의 것과 같다. 실패 수는 `outcome="failed"` |
| `ai_call_duration_seconds` | histogram | `operation`, `provider`, `model` | 한 번 부르는 데 걸린 시간 |
| `ai_tokens_total` | counter | `provider`, `model`, `direction`(`input`, `output`) | 쓴 토큰의 수. 비용의 근거다 |
| `ai_fallbacks_total` | counter | `operation`, `model` | 첫 모델이 실패해 다음 모델로 넘어간 수 |

**라운드 서술 (game)**

| 이름 | 종류 | label | 뜻 |
| --- | --- | --- | --- |
| `round_narrations_total` | counter | `result`(`success`, `failure`) | 끝난 서술의 수 |
| `round_narration_retries_total` | counter | 없음 | 서술을 다시 시도한 수 |
| `round_narration_duration_seconds` | histogram | 없음 | 라운드를 닫은 뒤 서술이 끝날 때까지 |
| `rounds_closed_total` | counter | `reason`(`all_declared`, `host`, `timeout`) | 닫기 시작한 라운드의 수. 마감으로 닫힌 비율이 높으면 시간 제한이 짧다 |

**서술 값 (game)**

| 이름 | 종류 | label | 뜻 |
| --- | --- | --- | --- |
| `billing_calls_total` | counter | `operation`(`hold`, `capture`, `release`, `extend`), `outcome`(`held`, `short`, `done`, `missing`, `ended`, `unavailable`, `rejected`) | 게임 서버가 결제 서버를 부른 수. 연장의 `missing`·`ended` 는 다시 건 것이다 |
| `narration_charges` | gauge | `status`(`pending`, `held`, `short`, `capture_due`, `release_due`, `failed`) | 끝나지 않은 청구의 수. `capture_due` 가 쌓이면 결제 서버가 죽어 있다. `failed` 는 사람이 봐야 한다 |

**메일과 인증 (auth)**

| 이름 | 종류 | label | 뜻 |
| --- | --- | --- | --- |
| `emails_sent_total` | counter | `kind`(인증 코드, 로그인 코드, 재설정, 요약), `result`(`success`, `failure`) | 보낸 메일의 수 |
| `auth_attempts_total` | counter | `action`(`login`, `signup`, `verify`, `reset`, `refresh`), `result`(`success`, `failure`) | 인증 시도의 수 |
| `auth_rate_limited_total` | counter | `action` | 시도 횟수 제한에 걸린 수 |

**게시판 (board)**

| 이름 | 종류 | label | 뜻 |
| --- | --- | --- | --- |
| `board_writes_total` | counter | `resource`(`post`, `comment`), `action`(`create`, `update`, `delete`), `result`(`success`, `rejected`, `rate_limited`) | 글과 댓글을 쓴 수. `rate_limited` 는 쓰기 횟수 제한에 걸린 것(429)이다 |
| `board_searches_total` | counter | `result`(`success`, `timeout`) | 글을 검색한 수. `timeout` 은 정해 둔 시간(3초)을 넘겨 멈춘 것(503)이다. 늘면 색인이나 검색 엔진이 필요하다 |
| `board_search_duration_seconds` | histogram | 없음 | 검색 하나가 걸린 시간 |
| `board_reports_total` | counter | `target`(`post`, `comment`), `result`(`success`, `rejected`, `rate_limited`) | 글과 댓글을 신고한 수. `rejected` 는 받지 않은 것(이미 신고함, 자기 것, 없는 것), `rate_limited` 는 신고 횟수 제한에 걸린 것(429)이다 |

**결제 (billing)**

| 이름 | 종류 | label | 뜻 |
| --- | --- | --- | --- |
| `billing_ledger_operations_total` | counter | `kind`(원장의 이유: `grant`, `deposit`, `spend`, `expire`, `hold`, `release`, `regroup`, `refund`, `unrefund`), `result`(`success`, `failure`) | 원장에 줄을 적은 수 |
| `billing_idempotency_total` | counter | `kind`, `outcome`(`first`, `replayed`) | 중복 방지 키의 결과. `replayed` 는 같은 키로 다시 온 것이다. 원장에 다시 적지 않았다 |
| `billing_orders_total` | counter | `status`(`paid`, `failed`, `confirming`, `expired`, `refunding`, `refunded`) | 주문이 그 상태가 된 수. 운영자가 정한 것(`cmd/orders decide`)도 센다 |
| `payment_provider_calls_total` | counter | `provider`(`fake`, `toss`), `operation`(`confirm`, `lookup`, `cancel`), `outcome`(`approved`, `declined`, `canceled`, `unknown`, `unavailable`) | 결제 대행사를 부른 수. `cancel` 은 청약철회의 취소다 |
| `payment_webhooks_total` | counter | `provider`(`fake`, `toss`), `result`(`accepted`, `ignored`, `bad_signature`, `bad_request`, `unavailable`) | 받은 알림의 수. `ignored` 는 다루지 않는 종류의 알림(토스의 입금 알림 등)이다. 토스의 알림에는 서명이 없어서 `bad_signature` 가 없다 |

## 개발 환경과 운영 환경

| | 개발 | 운영 |
| --- | --- | --- |
| `APP_ENVIRONMENT` | `development`(기본값) | `production` |
| `APP_VERSION` | `dev`(기본값) | 배포할 때 넣은 git SHA 나 이미지 태그 |
| `LOG_LEVEL` | `info`. 필요하면 `debug` | `info` |
| 로그의 모양 | JSON | JSON. 같다 |
| 로그가 가는 곳 | 터미널(stderr) | stderr. 실행 환경이 모은다 |
| 오류 응답 | 정해진 말과 `X-Request-ID` | 같다 |
| 민감정보를 가리는 것 | 한다 | 한다. 같다 |
| 인증 서버의 콘솔 메일 | `SMTP_HOST` 가 없으면 켜진다 | 켤 수 없다(뜨지 않는다) |
| `DEBUG` | 켤 수 있다(API 문서 화면, 주소 목록 출력, Django 의 오류 화면) | 끈다. 인증 서버는 켜면 뜨지 않는다 |

- 개발에서도 JSON 으로 남긴다. 사람이 읽기 좋은 모양을 따로 두지 않았다. 모양이 둘이면 운영에서만 나는 로그 문제가 생기고, 테스트가 보는 것과 운영이 내보내는 것이 달라진다.
  읽기 불편하면 `jq` 로 본다. 예: `uv run uvicorn app.main:app 2>&1 | jq -rR 'fromjson? | [.timestamp, .level, .message] | @tsv'`
- 개발과 운영에서 달라지는 것은 설정값뿐이다. 코드의 길이 갈리지 않는다. 가리는 규칙도 같다.

## OpenTelemetry Collector 를 붙일 자리

지금은 Collector 가 없다. 붙일 때 바꿀 곳을 미리 적어 둔다. 순서는 로그, 메트릭, 추적이 좋다. 뒤로 갈수록 코드를 많이 고친다.

```
서버(stderr 의 JSON) ──▶ Collector ──▶ 로그 저장소(Loki 등)
서버(OTLP)           ──▶ Collector ──▶ 메트릭 저장소(Prometheus 등), 추적 저장소(Tempo 등)
```

**1. 로그 — 코드를 고치지 않는다.**
서버는 지금처럼 stderr 에 JSON 을 쓴다. Collector 가 컨테이너의 로그를 읽어(`filelog` receiver) JSON 을 푼다.
옮길 것: `timestamp` → 시각, `level` → severity, `trace_id` → 로그 레코드의 trace id, `service`·`environment`·`version` →
resource 의 `service.name`·`deployment.environment.name`·`service.version`. 칸의 이름을 OpenTelemetry 의 이름으로 바꾸는 일은 Collector 의 설정에서 한다.

**2. 메트릭 — 서버마다 한 곳에 SDK 를 붙인다.**
위의 [목록](#목록)대로 계측한다. 내보내는 주소는 `OTEL_EXPORTER_OTLP_ENDPOINT` 로 받는다.

| 무엇 | 붙일 자리 |
| --- | --- |
| HTTP 요청 수, 시간, 처리 중인 수 | 요청이 끝난 줄을 남기는 미들웨어. 같은 값(`method`, `route`, `status_code`, 걸린 시간)을 이미 갖고 있다 |
| 작업 | game-server `app/core/jobs.py`, auth-server `observability/jobs.py` |
| AI 호출 | game-server `app/ai/calls.py` 의 `CallLog`. 기록을 받는 것을 하나 더 꽂는다 |
| DB 풀 | 서버마다 풀을 만드는 곳 |

**3. 추적 — 식별자를 다루는 코드를 SDK 로 바꾼다.**
지금의 코드는 `traceparent` 를 직접 읽고 쓴다. SDK 를 붙이면 그 일을 SDK 의 propagator 가 한다. 바꿀 곳은 서버마다 셋이다.

| | 받는 곳(미들웨어) | 들고 있는 곳 | 보내는 곳 |
| --- | --- | --- | --- |
| auth-server | `observability/middleware.py` | `observability/context.py` | `accounts/billing_client.py` 의 `outgoing_headers()` |
| game-server | `app/observability/middleware.py` | `app/observability/context.py` | `app/auth/jwks.py`, `app/billing/http_billing.py` 의 `outgoing_headers()` |
| board-server | `src/observability/request-logging.middleware.ts` | `src/observability/request-context.ts` | `src/auth/jwks.ts` 의 `outgoingHeaders()` |
| billing-server | `internal/httpapi/observability.go` | `internal/obs/context.go` | `internal/jwks/fetch.go` 의 `obs.SetOutgoingHeaders()` |

"들고 있는 곳"이 로그에 `trace_id` 를 넘긴다. SDK 를 붙이면 여기서 지금의 span 에서 trace id 를 읽게만 바꾸면 로그의 모양은 그대로다.
`request_id` 와 `job_id` 는 OpenTelemetry 에 없는 개념이라 지금의 코드가 그대로 남는다. span 의 속성으로도 싣는다.

## 관리 서버의 경계

관리 서버는 아직 없다. 만들 때 무엇을 맡고 무엇을 맡지 않는지를 먼저 정해 둔다.

### 맡을 것

- 관리자의 인증과 권한. 일반 사용자의 토큰으로 들어가지 못한다.
- 운영 집계의 조회. 저장소(메트릭, 로그, 추적)에 물어서 보여 준다.
- 서버별 장애와 부하의 표시.
- AI 호출의 품질과 비용의 집계. 게임 서버의 AI 호출 기록이 근거다.
- 보안 이벤트의 조회. 인증 서버의 보안 이벤트 기록이 근거다.
- 관리자가 한 조작의 감사 기록. 누가 언제 무엇을 했는지 지울 수 없게 남긴다.
- 이미 집계된 자료를 Gemma 에 넘겨 요약을 받고, 그 결과를 저장한다.

### 맡지 않을 것

- **모든 서버의 로그를 HTTP 로 직접 받는 수집기.** 로그는 Collector 가 모은다. 관리 서버가 죽었다고 서버들의 로그가 쌓이거나 사라지면 안 된다.
- **Prometheus, Loki, Tempo 같은 저장소의 기능을 다시 만드는 것.** 관리 서버는 그 저장소에 묻는 쪽이다.
- **AI 가 수치 기준 없이 장애인지 아닌지를 정하는 것.**
- **게임 상태와 결제 원장을 직접 고치는 것.** 고쳐야 하면 그 서버의 API 를 부른다. 규칙과 검증은 그 서버에 있다.
- **비밀값의 원문과 prompt 의 전체를 Gemma 에 넘기는 것.**

### 판정은 수치가, 설명은 Gemma 가

```
메트릭 ──▶ 경보 규칙(수치 조건) ──▶ "장애다"       ← 코드가 정한다
                │
                └─▶ 집계된 자료 ──▶ Gemma ──▶ "무슨 일인지 풀어 쓴 글"   ← 설명만 한다
```

- 장애인지, 경보를 울릴지는 **코드와 수치 조건**이 정한다(예: 5분 동안 5xx 가 2% 를 넘었다). 같은 입력에 늘 같은 답이 나오고, 왜 울렸는지 설명할 수 있다.
- Gemma 는 **이미 집계된 자료**(수, 비율, `operation`, `error_code`, 시간대)를 받아 사람이 읽을 글로 풀어 쓴다. 판정을 뒤집지 못한다.
- Gemma 에 넘기는 자료에도 [민감정보](#민감정보)의 규칙이 그대로 적용된다. 로그의 줄을 그대로 넘기지 않는다. 넘기는 것은 집계다.
- 이것은 게임 쪽의 원칙과 같다. 게임에서 판정은 엔진이 하고 LLM 은 서술만 한다. 운영에서 판정은 수치가 하고 LLM 은 설명만 한다.

## 서버별 구현

새 의존성은 없다. 언어마다 표준 기능과 이미 쓰던 것만 썼다.

| | auth-server | game-server | board-server | billing-server |
| --- | --- | --- | --- | --- |
| 로거 | 표준 `logging` + JSON formatter | 표준 `logging` + JSON formatter | Nest 의 `LoggerService` 를 구현한 `JsonLogger` | 표준 `log/slog` 의 `Handler` |
| 식별자를 들고 있는 곳 | `contextvars` | `contextvars` | `AsyncLocalStorage` | `context.Context` |
| 요청 미들웨어 | Django 미들웨어(맨 앞) | 순수 ASGI 미들웨어 | express 미들웨어 | gin 미들웨어(맨 앞) |
| 처리하지 못한 예외 | 미들웨어의 `process_exception` | `Exception` 처리기 | 전역 예외 필터 | `recover` 미들웨어 |
| 작업 | `run_as_job()` | `BackgroundJobs.spawn()` | 없다 | `jobs.Run()` |
| 코드의 자리 | `observability/` | `app/observability/` | `src/observability/` | `internal/obs/`, `internal/httpapi/observability.go` |

기존 로그는 고쳐 쓰지 않았다. `logging.getLogger(__name__)`, Nest 의 `new Logger(...)`, Go 의 표준 `log` 로 남기던 줄이 그대로 같은 JSON 으로 나간다.
프레임워크가 스스로 찍던 요청 줄(uvicorn 의 access log, Django 의 `django.server`, gin 의 `Logger`)은 껐다. 주소 뒤의 값까지 찍었고, 요청이 끝난 줄과 겹친다.

## 알려진 빈틈

- **span 이 없다.** `trace_id` 로 서버 사이의 로그를 이을 수는 있지만 "어디서 얼마나 걸렸나"를 그림으로 볼 수는 없다.
- **게임 서버의 AI 호출 기록(DB)에 `job_id` 와 `trace_id` 가 없다.** 로그의 서술 작업과 DB 의 호출 기록을 번호로 잇지 못한다. 열을 더하는 마이그레이션이 필요하다.
- **사람이 치는 명령은 JSON 이 아니다.** billing-server 의 `cmd/migrate`, `cmd/fakepg`, `cmd/prices`, `cmd/orders`, auth-server 의 관리 명령이 화면에 찍는 안내(`self.stdout`)는 그대로 글이다.
  `cmd/orders decide` 가 남기는 결정의 기록(`order.decide`)은 로그라서 JSON 이다.
  auth-server 의 워커와 예약 명령이 남기는 **로그**는 JSON 이다.
- **로거가 생기기 전의 줄.** board-server 는 설정이 틀려 뜨지 못할 때 Nest 의 기본 모양으로 찍는다. billing-server 는 `DEBUG=true` 면 gin 이 주소 목록을 글로 찍는다.
- **주기 명령을 부르는 supercronic 의 줄.** 실패한 실행만 한 줄 남긴다(`-quiet`). JSON 이지만 칸이 공통 규격과 다르다(`level`, `msg`, `time`, `job.command`).
  명령 자신이 남기는 로그는 규격의 JSON 이다. 명령이 끝에 화면에 찍는 요약(`self.stdout`, 결제의 `cmd/reconcile`)은 위의 "사람이 치는 명령"처럼 글이다.
- **nginx 가 뜨고 꺼지는 줄.** 프록시의 요청 줄은 JSON 이지만, nginx 가 뜰 때와 설정을 다시 읽을 때 남기는 줄은 nginx 의 글 모양이다.
- **마지막 방어선은 어림이다.** [민감정보](#마지막-방어선)의 끝에 적은 대로다.
- **`warning` 줄의 `error_code`.** `error` 이상에는 붙였지만, 기존의 `warning` 줄 가운데에는 코드가 없는 것이 있다(게임 서버의 JWKS, 임베딩 실패).
