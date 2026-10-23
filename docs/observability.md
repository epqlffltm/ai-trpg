# 관측 규격

서버들(`auth-server`, `trpg-server`, `board-server`, `billing-server`, `notification-server`)이 로그, 메트릭, 추적 정보를 같은 모양으로 남기기 위한 약속이다.
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
- [수집기(Grafana Alloy)를 붙일 자리](#수집기grafana-alloy를-붙일-자리)
- [관리 서버의 경계](#관리-서버의-경계)
- [서버별 구현](#서버별-구현)
- [알려진 빈틈](#알려진-빈틈)

## 지금 있는 것과 없는 것

| | 상태 |
| --- | --- |
| 요청 식별자(`X-Request-ID`)와 추적 식별자(`traceparent`) | 일곱 서버에 구현(asset 과 chat 은 `shared/server-core`) |
| 공통 모양의 JSON 로그 | 일곱 서버에 구현 |
| 민감정보를 가리는 마지막 방어선 | 일곱 서버에 구현 |
| 백그라운드 작업의 식별자(`job_id`) | 일곱 서버 모두 구현 |
| 메트릭 | billing-server(HTTP 셋, DB 넷, 작업 넷, 업무 다섯. 본보기, [아래](#붙인-것-결제-서버의-메트릭-본보기)), notification-server(Python 의 본보기, [아래](#붙인-것-알림-서버의-메트릭-python-의-본보기)), trpg-server(실시간 스트림, AI 호출, 라운드와 서술, 서술 값, [아래](#붙인-것-trpg-서버의-메트릭)), auth-server(메일, 시도 횟수 제한, 워커와 예약 명령, [아래](#붙인-것-인증-서버의-메트릭)), board-server(쓰기와 신고, 검색, [아래](#붙인-것-게시판-서버의-메트릭))에 구현. asset-server 와 chat-server 는 HTTP 와 DB 만 낸다(`shared/server-core`). 일곱 서버가 모두 내보낸다. 보내는 길과 저장소는 [아래](#2-메트릭--서버는-otlp-로-밀고-인프라는-alloy-가-긁는다) |
| DB 와 Redis 의 메트릭 | Alloy 안의 exporter 가 긁는다([아래](#붙인-것-db-와-redis)). DB 에는 통계만 읽는 계정(`monitor`)으로 붙는다 |
| 대시보드 | 일곱 서버, postgres, redis(`docker/grafana/dashboards/`, [아래](#대시보드)). 서버에 메트릭을 붙이는 PR 이 그 서버의 대시보드를 함께 더한다 |
| 경보 | 수집 쪽, DB 와 Redis, 일곱 서버의 규칙(`docker/prometheus/rules/`)과 Alertmanager(Discord, Slack, Telegram, 메일, [아래](#경보)). 서버에 메트릭을 붙이는 PR 이 그 서버의 규칙을 함께 더한다 |
| 추적(span) | 일곱 서버 모두 span 을 만든다(요청, 서버 사이의 호출, DB 의 쿼리, 작업. 본보기는 [Go](#붙인-것-결제-서버의-추적-본보기)와 [Python](#붙인-것-알림-서버의-추적-python-의-본보기), [TRPG 서버에서 다른 것](#붙인-것-trpg-서버의-추적), [인증 서버에서 다른 것](#붙인-것-인증-서버의-추적), [게시판 서버(Node)](#붙인-것-게시판-서버의-추적)). 받는 길과 저장소(Alloy → Tempo, Grafana 에서 로그와 오간다)는 [아래](#붙인-것-추적의-인프라) |
| 로그 모으기(Grafana Alloy, Loki, Grafana) | compose 의 프로필 `observability` 에 구현(#25, [아래](#붙인-것-로그)). 켜는 법은 [README 의 로그와 메트릭 모으기](../README.md#로그와-메트릭-모으기) |
| 메트릭의 저장소(Prometheus)와 OTLP 로 받는 길 | compose 의 프로필 `observability` 에 구현([아래](#붙인-것-메트릭의-인프라)) |
| Tempo | compose 의 프로필 `observability` 에 구현(`grafana/tempo:3.1.0`, 한 프로세스, 14일, [아래](#붙인-것-추적의-인프라)) |
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
| 게임 서버 | `trpg-server` |
| 게시판 서버 | `board-server` |
| 결제 서버 | `billing-server` |
| 알림 서버 | `notification-server` |
| 자산 서버 | `asset-server` |
| chat 서버 | `chat-server` |
| 프록시(nginx) | `proxy` |

만들 서버(계획, [서비스 구조 명세](architecture/services.md#계획인-것)). 같은 규칙이라 폴더 이름이 곧 `service` 다.

| 서버 | `service` |
| --- | --- |
| story 서버 | `story-server`. 2026-10-21 에 chat 서버의 모드에서 서버로 나뉘었다. chat 과 story 는 `service` 로 가른다 |
| 관리 서버 | 이름을 정할 때 같은 규칙으로(`ops-server` 후보) |

- 게임 서버의 `service` 는 2026-10-19 에 `game-server` 에서 `trpg-server` 로 바뀌었다(폴더 이름을 바꿈, #480). 그 앞의 로그와 메트릭까지 찾을 때는 두 이름을 함께 찾는다(`{service=~"game-server|trpg-server"}`). 토큰의 대상, 스키마, 환경 변수, 주소는 그대로다([서비스 구조 명세](architecture/services.md#구현된-것)).
- 서버의 워커와 주기 명령(`auth-mail`, `billing-sweeper` 등)은 그 서버의 `service` 를 쓴다. 어느 컨테이너인지는 수집기가 붙이는 `container` 로 안다([수집기](#수집기grafana-alloy를-붙일-자리)).

프록시는 서버 넷 앞에 서는 nginx 다(`docker/nginx/templates/`, 줄의 모양은 `http.inc.template` 의 `log_format`). 요청이 끝난 줄만 남긴다. [프록시의 줄](#프록시의-줄)에 따로 적었다.

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
- span 밖에서 다른 서버를 부를 때(보낼 곳을 비워 span 을 내보내지 않을 때) 넣는 `parent-id` 는 부를 때마다 새로 만든 난수다. 실제 span 의 번호가 아니다.
  span 안에서 부르면 그 호출의 span(client span)의 번호를 넣는다([결제 서버의 추적](#붙인-것-결제-서버의-추적-본보기)).
- 응답에 `traceparent` 를 돌려주지 않는다. 응답으로는 `X-Request-ID` 만 준다.

### 서버끼리 부를 때

| 부르는 곳 | 넘기는 것 | 넘기지 않는 것 |
| --- | --- | --- |
| 우리 서버(인증 서버의 JWKS, 결제 서버가 보내는 알림) | `traceparent`. `trace-id` 와 `flags` 는 그대로, `parent-id` 는 새로(span 을 만드는 서버는 그 호출의 span 번호) | `X-Request-ID` |
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
| trpg-server | 라운드를 닫은 뒤의 AI 서술 | `round.narrate` |
| trpg-server | 마감이 지난 라운드 닫기, 크레딧을 기다리는 시간이 지난 라운드 마무리, 서술이 사라진 라운드 다시 맡기기(서버의 시계가 5초마다 한 바퀴. 바퀴마다 새 `job_id`. 줄에 `closed`, `credit_waits`, `recovered`, `gave_up`) | `round.close_overdue` |
| trpg-server | 끝나지 않은 서술 값의 청구를 결제 서버에 마저 맡기기(정리 작업이 5초마다 한 바퀴. 바퀴마다 새 `job_id`) | `charge.settle` |
| trpg-server | 서술 모델의 은퇴를 알리고, 은퇴하면 같은 회사의 다른 모델로 바꾸기(지켜보기가 한 시간마다 한 바퀴. 바퀴마다 새 `job_id`. 줄에 `noticed`, `replaced`, `stranded`, `failed`) | `model.retirement` |
| trpg-server | 발송함의 알림을 알림 서버에 보내기(5초마다 한 바퀴. 바퀴마다 새 `job_id`. 줄에 `sent`, `retried`, `rejected`, `failed`, `dropped`) | `notification.send` |
| trpg-server | 로어북 항목의 벡터 만들기 | `lore.index` |
| trpg-server | 지난 라운드(기억)의 벡터 만들기 | `memory.index` |
| auth-server | 발송함의 메일 보내기(워커가 한 번 훑는 것) | `mail.deliver_outgoing` |
| auth-server | 환영 크레딧을 결제 서버에 맡기기(워커가 한 번 훑는 것) | `welcome_credit.deliver` |
| auth-server | 결제 자격(성년이 되는 날, 보호자 동의)을 결제 서버에 알리기(같은 워커가 한 번 훑는 것) | `payment_eligibility.deliver` |
| auth-server | 마치기 하루 전의 탈퇴에 메일을 한 통 더 보내기(같은 워커가 한 번 훑는 것, #624) | `withdrawal.remind` |
| auth-server | 유예가 지난 탈퇴를 마치기(같은 워커가 한 번 훑는 것, #603) | `withdrawal.complete` |
| auth-server | 탈퇴를 다른 서버에 알리기(같은 워커가 한 번 훑는 것, #603) | `withdrawal.deliver` |
| billing-server | 만료된 홀드·주문, 사라진 무료 크레딧 닫기, 보호자와 사용자에게 알릴 일 보내기(정리 작업이 30초마다 한 바퀴. 바퀴마다 새 `job_id`. 줄에 `user_notices_queued`, `_sent`, `_retried`, `_rejected`, `_expired`, `_purged`) | `sweep.run` |
| billing-server | 장부 맞춰 보기와 오래된 결제 끝내기(하루 한 번 돌리는 명령) | `reconcile.run` |
| auth-server | 가입을 끝내지 않은 이메일의 오래된 가입 코드 지우기 | `account.delete_unverified` |
| board-server | 발송함의 알림을 알림 서버에 보내기(5초마다 한 바퀴. 바퀴마다 새 `job_id`. 줄에 `sent`, `retried`, `rejected`, `failed`, `dropped`) | `notification.send` |
| notification-server | 보관 기간(기본 30일)이 지난 알림 지우기(정리 작업이 한 시간마다 한 바퀴. 바퀴마다 새 `job_id`. 줄에 `deleted`, `retention_days`) | `notification.prune` |
| auth-server | 보안 이벤트 요약 메일 | `security.send_digest` |

## 로그

### 한 줄의 모양

한 줄에 JSON 객체 하나다. 표준 오류(stderr)로 내보낸다. 파일에 쓰지 않는다. 모으는 일은 실행 환경(컨테이너 런타임, 수집기)이 한다.

```json
{"timestamp":"2026-10-11T09:00:00.123Z","level":"info","service":"trpg-server","environment":"production","version":"3f2a9c1","logger":"app.observability.middleware","message":"요청을 처리했다","request_id":"0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","operation":"http.request","method":"POST","route":"/api/v1/game/tables/{table_id}/rounds/current/close","status_code":202,"duration_ms":38,"result":"success"}
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

- `upstream` 은 요청을 보낸 서버의 이름이다(`auth`, `game`, `board`, `billing`, `notification`). 프록시가 직접 답한 것(막은 주소의 404)은 `proxy` 다.
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
그래서 **`APP_ENVIRONMENT` 가 `staging` 이나 `production` 인데 `DEBUG=true` 면 인증 서버가 뜨지 않는다**(#466).

### 작업이 끝난 줄

| 끝난 모양 | `result` | `level` |
| --- | --- | --- |
| 끝까지 돌았다 | `success` | `info`(주기적으로 도는 워커는 `debug`) |
| 서버를 끄느라 취소됐다 | `cancelled` | `warning` |
| 예외로 끝났다 | `server_error` | `error`. `error_code` 는 `job.failed` |

게임 서버는 작업의 종류마다 동시에 도는 수가 정해져 있어 차례를 기다릴 수 있다(#275). 끝난 줄에 기다린 시간 `queue_ms`(정수, 천분의 1초)를 `duration_ms` 와 따로 싣는다.
차례를 기다리다 취소되면 `cancelled` 줄에 `queue_ms` 만 있다.

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
| `round.close_overdue` | game | 마감이 지난 라운드 닫기, 크레딧을 기다리는 시간이 지난 라운드 마무리(#181), 서술이 사라진 라운드 다시 맡기기(#275) |
| `round.recover` | game | 서술이 사라진 라운드 하나를 다시 맡기거나 그만두기(서버의 시계의 한 바퀴 안. `table_id`, `round`, `auto_retries`) |
| `lore.index` | game | 로어북 색인 |
| `memory.index` | game | 기억 색인 |
| `charge.settle` | game | 끝나지 않은 서술 값의 청구를 결제 서버에 마저 맡기기(정리 작업의 한 바퀴) |
| `model.retirement` | game | 서술 모델의 은퇴를 알리고 바꾸기(지켜보기의 한 바퀴, 한 시간마다. 라운드가 열린 뒤 그 테이블 하나도 본다) |
| `notification.send` | game, billing, board | 알림 서버에 알림을 보내기. 게임·게시판 서버는 발송함 작업의 한 바퀴(5초마다), 결제 서버는 정리 작업(`sweep.run`) 안에서 못 보낸 알림마다 한 줄이다. 못 보낸 알림마다 발송함의 번호(게임 `notification_id`, 결제 `notice_id`), `kind`, `reason` 을 싣는다. 받는 사람과 `payload` 는 싣지 않는다 |
| `ai_log.prune` | game | AI 호출 기록에서 보관 기간(기본 30일)이 지난 원문 비우기(정리 작업의 한 바퀴, 한 시간마다. `cleared`, `retention_days`) |
| `notification.put` | notification | 다른 서버가 서명한 요청으로 알림을 넣기. `source`, `kind`, `notification_id`, `outcome`(`created`, `existing`, `muted`). 표에 맞지 않아 받지 않았으면 `notification.kind_refused` 다. 받는 사람과 `payload` 는 싣지 않는다 |
| `notification.prune` | notification | 보관 기간(기본 30일)이 지난 알림 지우기(정리 작업의 한 바퀴, 한 시간마다. `deleted`, `retention_days`) |
| `board.withdrawal` | board | 인증 서버가 서명해 알린 탈퇴로 그 사람의 글과 댓글의 글쓴이, 신고한 사람을 비우고 닉네임과 보낼 알림 지우기(#603. `blanked_posts`, `blanked_comments`, `blanked_reports`, `deleted_authors`, `deleted_notifications`). 사람은 싣지 않는다 |
| `notification.withdrawal` | notification | 인증 서버가 서명해 알린 탈퇴로 그 사람의 알림과 끈 종류 지우기(#603. `deleted_notifications`, `deleted_mutes`). 사람은 싣지 않는다 |
| `billing.hold` | game | 결제 서버에 서술 값의 홀드를 걸기 |
| `billing.capture` | game | 결제 서버에 홀드의 확정을 맡기기 |
| `billing.release` | game | 결제 서버에 홀드의 반환을 맡기기 |
| `billing.extend` | game | 결제 서버에 홀드의 연장을 맡기기(만료 전에) |
| `operator.act` | game | 운영자가 제재했다(#392). `operator_id`, `action`(`scenario_sanction`, `table_end`, `publishing_ban`, `publishing_unban`), `target_id`. 사유는 싣지 않는다. 원본은 DB 의 `operator_actions` 다 |
| `operator.read` | game | 운영자가 남의 테이블이나 시나리오를 운영자 API 로 보았다(#391). `operator_id`, `target_kind`, `target_id`, `target_number`. 사유는 싣지 않는다(자유 글). 원본은 DB 의 감사 기록(`operator_reads`)이다 |
| `mail.deliver_outgoing` | auth | 발송함의 메일 보내기 |
| `welcome_credit.deliver` | auth | 환영 크레딧을 결제 서버에 맡기기 |
| `payment_eligibility.deliver` | auth | 결제 자격을 결제 서버에 알리기 |
| `withdrawal.remind` | auth | 마치기 하루 전의 탈퇴에 메일을 한 통 더 보내기(요청마다 한 통) |
| `withdrawal.complete` | auth | 유예가 지난 탈퇴를 마치기(계정을 비우고 알릴 줄을 적는다) |
| `withdrawal.deliver` | auth | 탈퇴를 다른 서버에 알리기 |
| `account.delete_unverified` | auth | 가입을 끝내지 않은 이메일의 오래된 가입 코드 지우기(옛 이름 그대로) |
| `security.send_digest` | auth | 보안 이벤트 요약 메일 |
| `auth.jwks_fetch` | billing | 인증 서버에서 공개키 받기 |
| `auth.revocations_fetch` | game, billing, notification | 인증 서버에서 끊긴 세션의 목록 받기(30초마다) |
| `order.confirm` | billing | 주문의 결제 승인 |
| `order.refund` | billing | 주문의 청약철회(결제 취소) |
| `order.decide` | billing | 운영자가 결과를 모르던 주문의 결과를 정하기(`cmd/orders decide`). `from_status`, `outcome`, `decided_by`, `reason` 을 남긴다 |
| `grant.event` | billing | 운영자가 명단에 이벤트 실버를 주기(`cmd/grants give -apply`). `grant_key`, `silver`, `listed`, `given`, `already`, `granted_by`, `reason` 을 남긴다. 중간에 멈추면 `warn` 과 `error` |
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
| `job.refused` | 게임 서버가 작업을 맡지 않았다. 그 종류(`operation`)의 돌거나 기다리는 작업이 상한(`capacity`)에 닿았다. 서술은 서버의 시계가, 색인은 다음 검색이 다시 맡긴다. `warning` |
| `round.stalled` | 게임 서버가 서술이 되풀이해 사라진 라운드를 더 다시 맡기지 않고 실패(`stalled`)로 적었다. 같은 서술이 할 때마다 서버를 죽이고 있을 수 있다. `table_id`, `round`, `auto_retries`. 방장이 다시 맡길 수 있다. `warning` |
| `auth.jwks_unavailable` | 인증 서버에서 공개키를 받지 못했다. 게임 서버, 결제 서버, 알림 서버는 마지막으로 받은 지 30분이 지나 기억한 키를 버릴 때 `error` 로 남긴다(그 뒤 인증이 필요한 요청은 503). 사람이 인증 서버를 봐야 한다 |
| `auth.revocations_unavailable` | 게임 서버, 결제 서버, 게시판 서버, 알림 서버가 남긴다. 인증 서버에서 끊긴 세션의 목록(`/api/v1/auth/session-revocations`)을 받지 못했다. 마지막으로 받은 목록을 그대로 쓴다. 30초마다 다시 받으므로 인증 서버가 죽어 있으면 그만큼 줄이 쌓인다. `reason` 에 종류를 싣는다. `warning` |
| `payment.provider_unavailable` | 결제 대행사의 답을 받지 못했거나, 결과를 알 수 없는 답이 왔다(토스페이먼츠의 5xx, 401, "처리 중" 같은 것). 주문은 `confirming` 에 남고 다시 부르거나 대사가 조회해 끝낸다. 청약철회(`order.refund`)면 `refunding` 에 남고 다시 부르거나 대사가 같은 취소를 다시 보낸다. 가상계좌(입금 대기)를 취소하지 못했을 때도 이 코드다(`order.confirm`, `cancel_status`). `warning` |
| `withdrawal.undelivered` | 인증 서버가 탈퇴를 다른 서버에 알리지 못했다(닿지 못했거나 `200` `processed` 가 아닌 답). 다시 보낸다. `warning`. `target` 에 그 서버, `withdrawal_notice_id` 에 줄의 번호 |
| `billing.unavailable` | 결제 서버에 일을 맡기지 못했다. 다시 부른다. 게임 서버(홀드): 답을 받지 못했다. 서명이 거절된 것(401)이면 `error`, 그 밖에는 `warning`. 서술 뒤의 확정을 정해 둔 시간 안에 끝내지 못해 정리 작업에 넘긴 것도 이 코드다(`warning`). 인증 서버(환영 크레딧): 닿지 못했거나 2xx 가 아닌 답이 왔다. `warning` |
| `billing.rejected` | 결제 서버가 게임 서버의 요청을 받아들이지 않았다(400, 404, 409). 다시 불러도 같다. 연장이면 홀드를 그대로 두고 한 시간 뒤에 다시 부른다. 서술 뒤의 확정이 409(만료되어 돌려준 홀드)면 그 값은 받지 못한다. 홀드가 400 이면 가격표에 그 모델의 가격표 이름(`narration.<이름표>.i0.o0`)이 없는지 먼저 본다 |
| `notification.unavailable` | 게임 서버, 결제 서버(정리 작업), 게시판 서버가 알림 서버에 알림을 넣지 못했다(연결 실패, 시간 초과, 401, 408, 429, 5xx). 발송함에 남아 늘어나는 간격으로 다시 보낸다. 서명이 거절된 것(401, `reason: unauthorized`)이면 `error`, 그 밖에는 `warning` |
| `notification.rejected` | 알림 서버가 게임·결제·게시판 서버의 알림을 받지 않았다(409 같은 열쇠로 다른 알림, 413, 422 등). 다시 보내도 같다. 발송함에 `failed` 로 남는다. `reason` 에 답의 코드. 버그다. `error` |
| `notification.kind_refused` | 알림 서버가 서명은 맞지만 알림의 종류 표(`notification-server/app/notifications/catalog.py`)에 맞지 않는 알림을 받지 않았다(422). `refusal` 에 까닭(`kind_unknown`, `kind_not_allowed`, `payload_missing_fields`), `missing_fields` 에 빠진 칸의 이름을 싣는다. 넣는 서버의 버그이거나 남의 알림을 넣으려 한 것이다. 넣는 서버 쪽에는 `notification.rejected` 가 남는다. `warning` |
| `signals.bad_signature` | 게임 서버가 서명이 맞지 않는 실시간 신호(NOTIFY)를 받아 버렸다. 같은 DB 의 다른 계정이 꾸며 보냈거나, 게임 서버들의 `SIGNAL_SECRET` 이 서로 다르다. `sender_pid` 에 보낸 연결의 프로세스 번호를 싣는다(`pg_stat_activity` 에서 계정을 찾는다). 받은 글자는 싣지 않는다. `warning` |
| `limits.unavailable` | 게임 서버가 시도 횟수를 세는 곳(Redis)에 닿지 못했다. `limit` 에 어느 제한인지, `blocked` 에 막았는지(로비의 비밀번호) 통과시켰는지(채팅) 싣는다. `warning` |
| `server.start_failed` | 서버가 뜨지 못했다 |
| `security.event` | 인증 서버가 보안 이벤트(시도 제한에 막히기 시작함, 계정 정지와 풀기, 버린 메일, 본인인증의 막힘)를 DB 에 적었다. 저장한 뒤에 한 줄. `security_event` 에 종류, `security_event_id` 에 그 줄의 번호, 계정이 있으면 `user_id`(공개 ID). IP 와 운영자의 사유는 싣지 않는다(DB 가 원본이다). `warning` |
| `ledger.mismatch` | 결제 서버가 남긴다. 대사에서 지금의 값(지갑, 지급 묶음, 주문, 홀드)이 원장과 맞지 않는 줄을 찾았다. 줄마다 `error` 한 줄. `check` 에 검사의 이름, `record_id` 에 그 줄의 번호. 사람이 봐야 한다 |
| `order.stuck` | 결제 서버가 남긴다. 대사가 결제 대행사에 다시 묻고도, 결과를 모르는 채(`confirming`, `refunding`)로 하루가 지난 주문이 있다. 주문마다 `warning` 한 줄. `order_id`, `status`, `since`. 사람이 상점관리자에서 확인하고 `cmd/orders decide` 로 정한다 |
| `pricing.review_due` | 결제 서버가 남긴다. 대사가 셀 때, 공급사 가격 변경의 할 일(`announce` D-30, `notice` D-14, `final` D-1) 가운데 때가 되었는데 끝내지 않은 것이 있다. 할 일마다 `warning` 한 줄. `review_id`, `subject`, `step`, `stage`(`d30`·`d14`·`d1`·`overdue`), `days_left`, `changes_at`. 끝냈다고 적을 때까지(`cmd/pricereviews done`) 날마다 나온다 |
| `database.timeout` | 결제 서버가 남긴다. DB 가 시간 제한(`lock_timeout` 이나 `statement_timeout`, SQLSTATE `55P03`·`57014`)으로 쿼리를 끊었다. 그 쿼리는 적히지 않았고 주소는 503 으로 답했다. 다시 보내면 된다. 잦으면 잠금을 오래 쥔 쪽이나 느린 쿼리를 찾는다 |
| `request.timeout` | 결제 서버가 남긴다. 요청이 마감(10초) 안에 끝나지 않았다. 연결 풀을 기다린 시간을 포함한다. 쿼리 중이었으면 취소했고 적히지 않았다. 주소는 503 으로 답했다. 다시 보내면 된다. 잦으면 연결 풀이 모자란지(결제 서버 README 의 "연결 풀의 크기") 먼저 본다 |
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
  게임 서버는 이미 AI 호출마다 기록을 DB 에 남긴다(기록의 모양은 `shared/ai-core` 의 `ai_core/calls.py`). 거기에도 보낸 메시지는 없고 HMAC 지문만 있다.

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
| trpg-server | 있다 | 있다(DB) | 연결 5초. 연결된 뒤 답하지 않는 DB 앞에서는 끝이 없다(#258) |
| board-server | 있다 | 있다(DB) | 3초 |
| billing-server | 있다 | 있다(DB) | 3초 |
| auth-server | 있다 | 있다(DB) | 연결 5초. 연결된 뒤 답하지 않는 DB 앞에서는 끝이 없다(아래) |
| notification-server | 있다 | 있다(DB) | 3초 |

- **compose 의 healthcheck 는 `/health/ready` 를 부른다.** 그래서 `healthy` 는 "DB 에 닿는다"는 뜻이다. DB 가 죽으면 서버가 `unhealthy` 로 보인다.
  Docker 는 `unhealthy` 를 보고 재시작하지 않고, 서버의 `healthy` 를 기다리는 서비스도 없다. DB 가 돌아오면 다음 확인에서 `healthy` 로 돌아온다.
  CI 의 스택 확인(`.github/scripts/stack-smoke.sh`)도 모든 서버의 레디를 본다.
- **확인하는 쪽은 healthcheck 의 `timeout`(5초)이 묶는다.** 서버의 레디가 답하지 않아도 5초가 지나면 실패로 센다.
  서버 쪽의 시간 제한은 그보다 짧게(3초) 두어 503 으로 답하게 한다. 결제(Go 의 context)와 게시판(쿼리와 타이머의 경주)이 그렇다.
- **인증 서버에는 서버 쪽의 전체 제한이 없다.** 동기 Django(psycopg)에는 쿼리 하나만 시간으로 끊는 장치가 없다.
  `statement_timeout` 은 DB 가 살아서 느릴 때만 듣고, DB 가 멈췄거나 네트워크가 끊겼을 때는 듣지 않는다. 스레드로 떼어 기다리면 멈춘 스레드가 쌓인다.
  그래서 연결 시간(5초)만 묶고, 연결된 뒤 멈춘 DB 는 healthcheck 의 5초가 실패로 센다. 그동안 그 요청이 워커를 쥐는 것은 같은 DB 앞의 보통 요청과 같다.
- **실패하면 네 서버 모두 오류의 종류만 로그에 남긴다**(결제는 `error_type` 칸). 오류의 글에는 DB 주소와 계정 이름이 들어 있다.

**응답에 서비스 이름과 버전을 더하지 않았다.** 세 서버의 테스트가 본문이 정확히 `{"status":"ok"}` 인 것을 확인하고 있고,
프록시의 상태 확인이 본문을 글자 그대로 비교하도록 설정될 수 있다. 버전은 로그의 `version` 칸으로 안다.
상태 확인 응답에도 `X-Request-ID` 머리말은 붙는다. 본문은 그대로다.

### 워커의 상태

워커는 요청을 받지 않으므로 `/health/ready` 가 없다. 대신 **심장박동 파일**로 상태를 알린다(#258).

- 계속 도는 워커가 한 바퀴를 DB 에 닿아 끝낼 때마다 파일(`HEARTBEAT_FILE`)의 시각을 지금으로 바꾼다.
  DB 에 닿지 못한 바퀴는 바꾸지 않는다. 바꾸지 못해도 워커는 멈추지 않는다(`warning` 한 줄)
- compose 의 healthcheck(`x-worker-heartbeat`)가 그 시각이 2분 안인지 본다. 그래서 워커의 `healthy` 는 "DB 에 닿으며 돈다"는 뜻이다.
  파일이 없거나(아직 한 바퀴도 못 돌았다) 오래됐으면 `unhealthy` 다. 서버처럼 Docker 는 `unhealthy` 를 보고 재시작하지 않는다
- 2분은 정리 작업의 간격(30초)과, 메일 서버나 결제 서버가 느린 한 묶음보다 넉넉한 길이다. 그보다 오래 걸린 묶음은 그동안 `unhealthy` 로 보인다
- `HEARTBEAT_FILE` 이 비어 있으면 파일을 쓰지 않는다. PC 에서 워커를 직접 돌릴 때다
- CI 의 스택 확인이 워커 셋의 `healthy` 를 기다리고 확인한다

| 서버 | 워커 | 심장박동 |
| --- | --- | --- |
| auth-server | 메일(`send_outgoing_mail`), 환영 크레딧(`send_welcome_credits`) | 있다(`observability/heartbeat.py`) |
| billing-server | 정리 작업(`cmd/sweeper`) | 있다(`internal/jobs/heartbeat.go`) |
| auth-server, billing-server | 주기 명령(supercronic) | 없다. 하루 한 번이라 심장박동으로 볼 것이 없다. 실패는 `job.failed` 로그가 알린다 |
| trpg-server | 서버 안의 작업(라운드 시계, 청구 정리) | 없다. 서버 프로세스 안에서 돈다. 서술이 사라진 라운드는 시계가 찾아 다시 맡긴다(#275, `round.recover`) |
| notification-server | 서버 안의 작업(지난 알림 지우기, 끊긴 세션 목록 받기) | 없다. 서버 프로세스 안에서 돈다. 실패는 `job.failed`(지우기)와 `auth.revocations_unavailable`(목록) 로그가 알린다 |

DB 에 닿으며 도는 것이 아니라 날짜로 상태를 보는 컨테이너도 있다. 심장박동 대신 그 일의 결과(파일과 그 시각)를 본다.

| 컨테이너 | 하는 일 | `healthy` 의 뜻 |
| --- | --- | --- |
| `db-backup` | DB 를 날마다 한 파일로 뜬다(`docker/backup/db-backup.sh`) | 25시간 안에 뜬 백업 파일이 있다 |
| `certbot`(staging) | 인증서를 12시간마다 갱신한다(`docker/certbot/`) | nginx 가 쓰는 인증서가 14일 넘게 남았다(`cert_check.py`). 갱신이 2주 넘게 실패하면 `unhealthy` |
| `backup-offsite`(staging) | 덤프를 age 로 잠가 S3 에 올리고, 일주일에 한 번 버킷의 것을 받아 풀어 본다(`docker/backup-offsite/`) | 26시간 안에 올렸고, 일주일 하루 안에 풀어 보기에 성공했다. 풀어 보기가 실패하면 곧바로 `unhealthy` |

**HTTP 주소를 열지 않고 파일을 쓴다.** 워커마다 작은 HTTP 서버를 띄우면 서버와 같은 모양이 되지만, 워커마다 포트와 코드가 는다.
파일은 Python 과 Go 가 같은 몇 줄로 쓰고, healthcheck 는 셸의 `stat` 과 `date` 로 본다. 파일은 compose 만 본다.
대시보드와 알림까지 가려면 작업의 마지막 성공 시각을 메트릭으로 내보낸다(아래 메트릭의 `db_up` 과 작업 메트릭, #25).

## 메트릭

**일곱 서버가 내보낸다. 새 서버(story, 관리)는 붙일 때 이 표를 따른다.**
보내는 길(OTLP → Alloy → Prometheus)과 계측기를 만드는 법은 [수집기의 2. 메트릭](#2-메트릭--서버는-otlp-로-밀고-인프라는-alloy-가-긁는다)에 있다.

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
| `service` | 서버의 수만큼(지금 일곱) |
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

**HTTP (일곱 서버)**

| 이름 | 종류 | label | 뜻 |
| --- | --- | --- | --- |
| `http_server_requests_total` | counter | `method`, `route`, `status_code` | 끝난 요청의 수. 상태 코드별 오류 수는 이것에서 고른다(`status_code=~"5.."`) |
| `http_server_request_duration_seconds` | histogram | `method`, `route` | 요청을 받아 응답을 끝낼 때까지. SSE 스트림은 뺀다(요청 수에는 끊길 때 든다) |
| `http_server_active_requests` | gauge | 없음 | 지금 처리 중인 요청의 수. SSE 스트림은 뺀다(`sse_connections` 가 센다) |

**DB (일곱 서버)** — 인증 서버에는 연결 풀이 없다(요청마다 연결을 맺고 닫는 Django 의 기본). 그래서 `db_up` 만 낸다

| 이름 | 종류 | label | 뜻 |
| --- | --- | --- | --- |
| `db_up` | gauge | 없음 | readiness 가 마지막으로 본 DB 의 상태. 1 이면 닿는다 |
| `db_pool_connections` | gauge | `state`(`idle`, `in_use`) | 연결 풀의 연결 수 |
| `db_pool_connections_max` | gauge | 없음 | 풀이 가질 수 있는 가장 많은 연결 |
| `db_pool_wait_seconds` | histogram | 없음 | 연결을 얻으려고 기다린 시간 |

**백그라운드 작업 (game, auth, board, billing, notification)**

| 이름 | 종류 | label | 뜻 |
| --- | --- | --- | --- |
| `background_jobs_started_total` | counter | `operation` | 시작한 작업의 수 |
| `background_jobs_finished_total` | counter | `operation`, `result`(`success`, `server_error`, `cancelled`) | 끝난 작업의 수. 실패 수는 `result="server_error"` |
| `background_jobs_running` | gauge | `operation` | 지금 도는 작업의 수 |
| `background_jobs_queued` | gauge | `operation` | 기다리는 일의 수. 인증 서버의 발송함에 남은 메일(`mail.deliver_outgoing`), 비울 시각이 지났는데 비우지 않은 탈퇴(`withdrawal.complete`), 비밀을 적은 서버에 아직 알리지 못한 탈퇴(`withdrawal.deliver`)가 여기다. 워커가 바퀴의 끝에 센다 |
| `background_job_duration_seconds` | histogram | `operation` | 작업 하나가 걸린 시간 |

**실시간 스트림 (game)**

| 이름 | 종류 | label | 뜻 |
| --- | --- | --- | --- |
| `sse_connections` | gauge | 없음 | 지금 열려 있는 SSE 연결의 수 |
| `sse_connections_opened_total` | counter | 없음 | 열린 연결의 수 |
| `sse_connection_duration_seconds` | histogram | 없음 | 연결이 이어진 시간. 구간은 1초에서 4시간까지다(`1, 10, 60, 300, 900, 1800, 3600, 7200, 14400`) |

**AI 호출 (game)**

| 이름 | 종류 | label | 뜻 |
| --- | --- | --- | --- |
| `ai_calls_total` | counter | `operation`, `provider`, `model`, `outcome`(`ok`, `rejected`, `failed`) | AI 를 부른 수. 값은 AI 호출 기록의 것과 같다. 실패 수는 `outcome="failed"` |
| `ai_call_duration_seconds` | histogram | `operation`, `provider`, `model` | 한 번 부르는 데 걸린 시간 |
| `ai_tokens_total` | counter | `provider`, `model`, `direction`(`input`, `output`) | 쓴 토큰의 수. 비용의 근거다 |
| `ai_fallbacks_total` | counter | `operation`, `model` | 모델이 실패해 다음 모델로 넘어간 수. `model` 은 실패해 떠난 모델이다. 방장이 고른 모델은 넘어갈 모델이 없어 모델이 없는 옛 라운드에서만 생긴다 |

**라운드 서술 (game)**

| 이름 | 종류 | label | 뜻 |
| --- | --- | --- | --- |
| `round_narrations_total` | counter | `result`(`success`, `failure`) | 끝난 서술의 수. 닫기를 마무리했으면 `success`, 실패를 적었으면 `failure` 다(서술 값을 잡지 못한 것도). 할 일이 없던 것(이미 닫힘)과 서버가 꺼져 멈춘 것은 세지 않는다 |
| `round_narration_retries_total` | counter | 없음 | 같은 모델로 서술을 다시 시도한 수 |
| `round_context_duration_seconds` | histogram | 없음 | 서술 전에 로어북, 지난 일, 인물의 이력, 참고 자료를 고르는 데 걸린 시간 전체(#628). 로어북 다음의 셋은 함께 돌아 넷을 더한 것보다 짧다. 서술까지의 시간(`round_narration_duration_seconds`) 가운데 검색의 몫이다 |
| `round_context_part_duration_seconds` | histogram | `part`(`lore`, `memories`, `histories`, `references`), `result`(`success`, `timeout`, `failure`) | 고르는 것 하나가 걸린 시간. `timeout` 은 정해 둔 시간이 다 된 것, `failure` 는 예외로 끝난 것이다(둘 다 없이 서술한다). 취소된 것은 재지 않는다 |
| `round_narration_duration_seconds` | histogram | 없음 | 라운드를 닫기 시작한 뒤 서술이 끝날 때까지. 성공한 것만 잰다. 작업이 차례를 기다린 시간도 든다 |
| `rounds_closed_total` | counter | `reason`(`all_declared`, `host`, `timeout`) | 닫기 시작한 라운드의 수. 저장한 뒤에 센다. 실패한 서술을 다시 맡긴 것은 세지 않는다. 마감으로 닫힌 비율이 높으면 시간 제한이 짧다 |

**서술 값 (game)**

| 이름 | 종류 | label | 뜻 |
| --- | --- | --- | --- |
| `billing_calls_total` | counter | `operation`(`hold`, `capture`, `release`, `extend`), `outcome`(`held`, `short`, `gold_required`, `done`, `missing`, `ended`, `unavailable`, `rejected`) | 게임 서버와 chat 서버가 결제 서버를 부른 수(서버마다 `service` 로 나뉜다). 걸기는 `held`·`short`·`gold_required`, 나머지 셋이 된 것은 `done` 이다. 연장의 `missing`·`ended` 는 정리 작업이 새 이름표로 다시 건다. `unavailable` 은 답을 받지 못한 것(다시 부른다), `rejected` 는 받아들이지 않은 것(그 청구는 `failed`, 사람이 본다) |
| `narration_charges` | gauge | `status`(`pending`, `held`, `short`, `capture_due`, `release_due`) | 끝나지 않은 청구의 수. 청구 정리(5초마다)가 바퀴의 끝에 센다. 없는 상태도 0 이다. 서버들이 같은 수를 내므로 `max` 로 본다. `capture_due` 가 쌓이면 결제 서버가 죽어 있다. `failed` 는 세지 않는다(한 번 되면 남아 쌓이고 색인이 없다). `failed` 가 되는 것은 `billing_calls_total` 의 `rejected` 로 본다 |

**메일과 인증 (auth)**

| 이름 | 종류 | label | 뜻 |
| --- | --- | --- | --- |
| `emails_sent_total` | counter | `kind`(메일의 종류: `signup_code`, `login_code`, `already_registered`, `password_reset`, `password_changed`, `security_digest`, `guardian_consent`, `guardian_consented`, `guardian_revoked`, `minor_guardian`, `guardian_payment`, `withdrawal_requested`, `withdrawal_reminder`, `withdrawal_completed`, `signup_refused`, `other`), `result`(`sent`, `retried`, `discarded`) | 메일 한 통을 보내 본 결과의 수. 시도마다 센다. `retried` 는 메일 서버가 받지 않아 다시 보낼 것, `discarded` 는 버린 것(받는 사람이 받지 못했다)이다. 종류는 발송함의 칸 `kind` 다(`accounts.models.MailKind`). 메일 서버 없이 바로 찍는 것(inline)은 `sent` 만 센다 |
| `auth_rate_limited_total` | counter | `limit`(제한의 이름: `login-ip`, `login-fail-account-ip`, `login-ip-block`, `signup-ip`, `password-reset-ip`, `password-change-fail-user`) | 시도 횟수 제한에 걸린 수 |
| `auth_rate_limits_unavailable_total` | counter | `limit` | Redis 에 묻지 못해 세지 않고 통과시킨 수. 0 이 아니면 그동안 시도 제한이 꺼져 있었다 |
| `auth_network_blocked_total` | counter | `endpoint`(`signup`, `login`, `refresh`) | 운영자가 막은 IP 에서 와서 거절한 요청의 수(#638, `block_network`). 막은 사람이 되돌아오려는지 본다 |

인증 시도의 성공과 실패는 따로 세지 않는다. 주소마다 상태 코드로 본다(`http_server_requests_total{service="auth-server", route="/api/v1/auth/login"}` 의 `status_code`). 같은 수를 두 번 세지 않는다.

**게시판 (board)**

| 이름 | 종류 | label | 뜻 |
| --- | --- | --- | --- |
| `board_writes_total` | counter | `resource`(`post`, `comment`), `action`(`create`, `update`, `delete`), `result`(`success`, `rejected`, `rate_limited`) | 글과 댓글을 쓴 수. `rate_limited` 는 쓰기 횟수 제한에 걸린 것(429)이다 |
| `board_searches_total` | counter | `result`(`success`, `timeout`) | 글을 검색한 수. `timeout` 은 정해 둔 시간(3초)을 넘겨 멈춘 것(503)이다. 늘면 색인이나 검색 엔진이 필요하다 |
| `board_search_duration_seconds` | histogram | 없음 | 검색 하나가 걸린 시간 |
| `board_reports_total` | counter | `target`(`post`, `comment`), `result`(`success`, `rejected`, `rate_limited`) | 글과 댓글을 신고한 수. `rejected` 는 받지 않은 것(이미 신고함, 자기 것, 없는 것), `rate_limited` 는 신고 횟수 제한에 걸린 것(429)이다 |

**알림 (notification)**

| 이름 | 종류 | label | 뜻 |
| --- | --- | --- | --- |
| `notifications_received_total` | counter | `source`(`game`, `billing`, `board`), `outcome`(`created`, `existing`, `muted`, `refused`, `conflict`) | 다른 서버가 넣은 알림의 수. `existing` 은 같은 알림을 다시 보낸 것(200), `muted` 는 받는 사람이 그 종류를 꺼서 적지 않은 것(200), `refused` 는 그 서버가 넣을 수 없는 종류이거나 칸이 빠진 것(422), `conflict` 는 같은 열쇠의 다른 알림(409)이다. 둘은 넣은 서버의 버그다. 서명을 확인한 것만 센다. 서명이 틀린 요청의 `source` 는 믿을 수 없어 label 로 쓰지 않는다 |

**결제 (billing)**

| 이름 | 종류 | label | 뜻 |
| --- | --- | --- | --- |
| `billing_ledger_operations_total` | counter | `reason`(원장의 이유: `grant`, `deposit`, `spend`, `expire`, `hold`, `release`, `regroup`, `refund`, `unrefund`, `forfeit`), `result`(`success`, `failure`) | 원장에 적은 일의 수. 줄이 아니라 한 번의 변경(작업 번호 `operation_id`)을 하나로 센다. 줄을 적지 않은 일(거절된 쓰기, 사라질 것이 없던 정리)은 세지 않는다. 트랜잭션이 끝난 뒤에 센다: 커밋되면 `success`, 적었다가 되돌렸으면 `failure` 다. 쓰기가 거절되면 지갑을 잠글 때 함께 적은 `expire` 도 되돌려져 `failure` 가 된다(다음 변경 때 다시 적는다). label 이름은 원장의 칸 `kind`(`paid`, `free`)와 헷갈리지 않게 `reason` 이다 |
| `billing_idempotency_total` | counter | `kind`(`order`, `hold`), `outcome`(`first`, `replayed`, `conflict`) | 중복 방지 키의 결과. 주문은 `Idempotency-Key`, 홀드는 부르는 서버의 이름표(source + reference)가 키다. `replayed` 는 같은 키, 같은 내용으로 다시 온 것이다(새로 만들지 않았고 원장에 다시 적지 않았다). `conflict` 는 같은 키에 다른 내용으로 온 것이다(409, 부르는 쪽의 버그). 키를 보기 전에 끝난 요청(모양이 틀린 키, 모자란 크레딧, DB 오류)은 세지 않는다 |
| `billing_orders_total` | counter | `status`(`paid`, `failed`, `confirming`, `expired`, `refunding`, `refunded`) | 주문이 그 상태가 된 수. 상태를 바꾼 프로세스(서버, 정리 작업, 대사)가 커밋한 뒤에 센다. 다른 요청이 먼저 바꿔 이번에 바꾸지 않은 것은 세지 않는다. 청약철회가 거절되어 `paid` 로 돌아온 것도 `paid` 로 센다. 운영자가 정한 것(`cmd/orders decide`)은 세지 않는다(사람이 치는 명령은 메트릭을 내지 않는다. 로그의 `order.decide` 로 본다) |
| `billing_user_notices_total` | counter | `kind`(`order.paid`, `order.refunded`, `credit.welcome`, `credit.expiring`, `credit.short`), `outcome`(`queued`, `duplicate`, `sent`, `retried`, `rejected`) | 사용자의 알림함에 보낼 일. `queued` 는 새로 적은 것이다. 정리 작업이 주문과 지급 묶음에서 찾아 적은 것과, 서버가 홀드를 거절한 자리에서 적은 크레딧 부족(`credit.short`)을 함께 센다. `duplicate` 는 같은 사람의 같은 날 크레딧 부족이라 적지 않은 것이다. `sent`, `retried`, `rejected` 는 정리 작업이 알림 서버에 보낸 결과다(받았다, 닿지 못해 다시 보낸다, 받지 않았다). 오래되어 보내지 않은 것과 지운 것은 세지 않는다(정리 작업의 바퀴 로그에 있다) |
| `payment_provider_calls_total` | counter | `provider`(`fake`, `toss`), `operation`(`confirm`, `lookup`, `cancel`), `outcome`(받은 상태: `approved`, `declined`, `pending`, `canceled`, `awaiting_deposit`. 답을 받지 못했으면 `unknown`(돈이 나갔을 수 있다), 그 밖의 오류로 묻지 못했으면 `unavailable`) | 결제 대행사를 부른 수. `cancel` 은 청약철회와 가상계좌의 취소다. 거절의 이유(코드)는 label 이 아니다. 결제 대행사가 정하는 값이라 종류가 끝이 없다 |
| `payment_webhooks_total` | counter | `provider`(`fake`, `toss`), `result`(`accepted`, `ignored`, `bad_signature`, `bad_request`, `unavailable`) | 받은 알림의 수. `ignored` 는 200 으로 받았지만 다루지 않는 알림(토스의 입금 알림, 다른 종류의 알림, 이 서버의 주문 번호가 아닌 것)이다. 토스의 알림에는 서명이 없어서 `bad_signature` 가 없다 |

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

## 수집기(Grafana Alloy)를 붙일 자리

수집기를 붙일 때 정한 것과 바꿀 곳을 적어 둔다(#25). 순서는 로그, 메트릭, 추적이다. 뒤로 갈수록 서버 코드를 많이 고친다.
셋 모두 일곱 서버에 붙였다. 로그([붙인 것](#붙인-것-로그)), 메트릭([2. 메트릭](#2-메트릭--서버는-otlp-로-밀고-인프라는-alloy-가-긁는다)), 추적([3. 추적](#3-추적--식별자를-다루는-코드를-sdk-로-바꾼다))이다.

```
서버(stderr 의 JSON) ─▶ Docker(json-file) ─▶ Alloy ─▶ Loki        ─┐
서버(OTLP)                              ─▶ Alloy ─▶ Prometheus   ─┼─▶ Grafana ◀─ 관리 서버(문)
                                                 └▶ Tempo       ─┘
```

### 정한 것 (2026-10-19)

| 항목 | 정한 것 | 까닭 |
| --- | --- | --- |
| 수집기 | **Grafana Alloy** | Docker 를 직접 살펴 compose 의 서비스 이름을 붙인다(컨테이너가 스물이 넘는다). 로그, 메트릭(Prometheus 수집과 OTLP), 추적(OTLP)을 하나로 받아 단계마다 수집기를 바꾸지 않는다. 보여 주는 쪽을 Grafana 로 정해서 맞추는 품이 가장 적다 |
| 고르지 않은 것 | OpenTelemetry Collector(contrib), Vector, Fluent Bit, Promtail | Collector 는 업체에 묶이지 않지만 로그 파일에 컨테이너 번호만 있어 이름을 붙이는 설정이 길다. Vector 와 Fluent Bit 는 추적까지 가면 수집기가 하나 더 필요하다. Promtail 은 지원이 끝났다(2026-03-02) |
| 자리 | 지금은 서버들과 **같은 VM**. 문제가 생기면 로그와 메트릭을 S3 에 따로 두고 VM 을 나눈다 | 혼자 쓰는 동안 비용을 늘리지 않는다. 옮길 때 서버 코드와 수집기의 설정은 거의 그대로고 보내는 주소와 저장소만 바뀐다 |
| 보관 | Loki **14일**(`staging`). 정식 공개 전에 30일 + 그보다 오래된 것은 압축해 S3 에 90일로 다시 본다 | 장애는 보통 며칠 안에 알아챈다. 오래 남겨야 하는 기록(운영자의 접속과 조작, 보안 이벤트, 결제)은 각 서버의 DB 가 원본이다(아래) |
| Grafana 를 여는 곳 | 관리 서버가 생기기 전에는 **사설망(Tailscale)으로만**(2026-10-21, #539). VM 의 `127.0.0.1:3000` 을 `tailscale serve` 가 사설망에 넘긴다. 생긴 뒤에는 **관리 서버가 문**이다(Grafana 의 auth proxy) | 바깥에 Grafana 의 로그인 화면을 열지 않는다. VM 은 이미 Tailscale 에 있다(집 PC 의 Ollama). SSH 터널을 매번 열지 않고 휴대폰으로도 본다. 운영자 확인은 관리 서버가 토큰의 `roles` 로 한 번만 한다 |
| 켜는 법 | compose 의 프로필 `observability`. 로컬은 기본으로 꺼 두고 `staging` 에서 켠다 | 개발 PC 를 무겁게 하지 않는다 |

### 1. 로그 — 서버 코드를 고치지 않는다

서버는 지금처럼 stderr 에 JSON 을 쓰고, Docker 가 json-file 로 적는다(`docker-compose.yml` 의 `x-logging`). Alloy 가 Docker 에서 컨테이너 목록과 로그를 읽어 Loki 로 보낸다.

- **컨테이너의 이름.** compose 의 서비스 이름(`auth-server`, `auth-mail`, `billing-sweeper` …)을 붙인다. 서버의 `service` 칸과 다를 수 있다(워커와 주기 명령은 그 서버의 `service` 를 쓴다). 둘 다 남긴다.
- **Docker 소켓.** 컨테이너 목록을 보려면 Docker 의 API 가 필요하다. 소켓을 Alloy 에 그대로 붙이면 그 컨테이너가 VM 의 관리자 권한을 갖는다. **읽기만 허용하는 소켓 프록시**(컨테이너 목록과 로그만)를 앞에 둔다.
- **JSON 을 푼다.** 옮길 것: `level` → 수준, `trace_id` 와 `request_id`, `job_id` → 줄의 값, `service`·`environment`·`version` → 줄의 출처. 칸의 이름을 바꾸는 일은 Alloy 의 설정에서 한다. 시각은 서버의 `timestamp` 가 아니라 Docker 의 것을 쓰기로 했다([붙인 것](#붙인-것-로그)).
- **JSON 이 아닌 줄도 모은다.** 본문을 그대로 두고 JSON 이 아니라는 표시만 붙인다. PostgreSQL, Redis, certbot, nginx 가 뜨고 꺼지는 줄, supercronic 의 줄, 사람이 치는 명령의 안내([알려진 빈틈](#알려진-빈틈))가 여기 든다. 버리면 DB 가 죽는 순간이 보이지 않는다.
- **수집이 늦어도 잃지 않게.** 서비스마다 Docker 의 로그는 50MB(10MB × 5)까지라 Alloy 가 멈춘 동안 파일이 돌아 버리면 그 구간을 잃는다. Alloy 가 읽은 자리를 디스크에 기억하게 하고, 줄이 많은 서비스(나중의 chat)만 상한을 키운다.
- **수집 쪽이 죽어도 서버는 돈다.** 서버는 stderr 에 쓰기만 한다. Alloy 나 Loki 가 멈춰도 요청은 영향을 받지 않는다.

**Loki 의 label.** label 하나의 값마다 저장 단위(스트림)가 생긴다. 메트릭의 [label](#label) 처럼 값의 종류가 정해진 것만 쓴다.

| label 로 쓰는 것 | 값 |
| --- | --- |
| `service` | 로그를 낸 서버(위의 표) |
| `container` | compose 의 서비스 이름 |
| `environment` | `development`, `staging`, `production` |
| `level` | `debug`, `info`, `warning`, `error`, `critical` |

- `request_id`, `trace_id`, `job_id`, `user_id`, `table_id`, `order_id`, 대화방 번호는 **label 로 쓰지 않는다.** 줄의 값(structured metadata)이나 본문으로 둔다. Grafana 에서 `trace_id` 로 찾는 것은 그래도 된다.
- 민감정보의 규칙([민감정보](#민감정보))은 그대로다. 로그에 적지 않는 것은 모은 뒤에도 없다. 대화의 원문, 캐릭터 설정, prompt 는 서버가 싣지 않는다.
- 스트리밍(서술, 나중의 chat)은 조각마다 줄을 남기지 않는다. 한 번의 서술이나 턴이 끝날 때 한 줄이다.

#### 붙인 것 (로그)

| 파일 | 하는 일 |
| --- | --- |
| `docker-compose.yml` 의 "로그와 메트릭 모으기" | `docker-socket-proxy`, `alloy`, `loki`, `grafana`. 모두 프로필 `observability` 이고 `logging: *logging` 을 쓴다 |
| `docker/alloy/config.alloy` | 컨테이너 찾기 → `container` 붙이기 → 로그 읽기 → JSON 풀기 → Loki 로 보내기 |
| `docker/loki/config.yaml` | 한 프로세스, 볼륨에 파일로. 14일 뒤에 지운다 |
| `docker/grafana/provisioning/datasources/loki.yaml` | Grafana 가 뜰 때 Loki 를 데이터 소스(uid `loki`)로 붙인다. 화면에서 고치지 못한다 |
| `.github/scripts/stack-smoke.sh` 의 `check_logs` | CI(`stack`)가 PR 마다 아래를 본다 |

- **줄을 어떻게 옮기는가.** `service`, `environment`, `level` 은 label 이다. `request_id`, `trace_id`, `job_id`, `version` 은 줄의 값이다.
  `version` 은 값의 종류가 적지만 배포할 때마다 스트림이 새로 생기므로 label 로 두지 않았다. 칸의 이름은 바꾸지 않았다. 서버의 칸 이름이 그대로 Loki 의 이름이다.
- **시각은 Docker 의 것이다.** 서버의 `timestamp` 로 바꾸지 않았다. Docker 가 그 줄을 받은 때라 서버의 값과 천분의 몇 초 차이다.
  JSON 이 아닌 줄과 같은 시계로 줄을 세워야 DB 가 죽은 순간과 서버의 오류가 같은 순서로 보인다. 서버의 `timestamp` 는 본문에 그대로 있다.
- **공통 모양인지 표시한다.** `service` 칸이 있는 줄은 줄의 값 `log_format="standard"`, 없는 줄(DB, Redis, Loki, supercronic 등)은 `"other"` 다. 본문은 그대로다.
  다른 프로그램의 줄도 JSON 이고 `level` 칸이 있으면(supercronic, Alloy, Grafana) 그 값이 label `level` 로 붙는다. `warn` 처럼 규격 밖의 값이 있을 수 있다.
- **Loki 가 스스로 만드는 label `service_name` 은 껐다**(`discover_service_name: []`). `service` 가 없는 줄에 컨테이너의 이름을 넣어서 두 뜻이 섞인다.
- **이 compose 프로젝트의 컨테이너만 모은다.** 같은 PC 의 다른 프로젝트는 모으지 않는다(`com.docker.compose.project` 로 거른다).
- **소켓 프록시가 넘기는 것.** 컨테이너(`CONTAINERS`)와 네트워크(`NETWORKS`)의 GET, 기본으로 열린 `PING`, `VERSION`, `EVENTS` 뿐이다. 쓰기(POST, DELETE)와 이미지, 볼륨, 비밀, exec 는 403 이다.
  컨테이너의 GET 에는 inspect 가 들어 있어 **컨테이너의 환경 변수(비밀)가 읽힌다.** 그래서 프록시는 Alloy 만 있는 망(`docker-api`, 바깥으로 나가지 못한다)에 둔다.
- **망을 나눴다.** 서버들은 기본 망(`default`)에만 있어서 소켓 프록시에도 Loki 에도 닿지 않는다. Alloy, Loki, Grafana 는 `observability` 망이다. Grafana 의 포트를 열려고 그 망은 `internal` 이 아니다.
- **root 가 아니다.** Alloy 는 이미지가 만들어 둔 사용자(473)로 띄운다. 로그를 파일이 아니라 Docker 의 API 로 읽으므로 root 가 필요 없다. Loki 와 Grafana 는 이미지가 처음부터 root 가 아니다.
- **Loki 가 멈추면.** Alloy 가 끝없이 다시 보낸다(`max_backoff_retries = 0`). 그동안 읽기도 멈추고 읽은 자리는 볼륨(`alloydata`)에 남는다. Docker 의 로그가 그 사이에 돌아 버리면 그 구간은 잃는다.
- **CI 가 보는 것.** 서버의 줄을 `service`, `container`, `level` 로 찾는다. 추적 식별자를 실어 부른 요청의 줄을 `trace_id` 로 거른다. DB 의 줄이 `log_format="other"` 로 들어온다.
  label 이 위의 다섯뿐이다. Grafana 가 Loki 에 닿는다. 소켓 프록시가 컨테이너 목록은 넘기고 컨테이너 만들기(POST)와 이미지 목록은 403 으로 막는다. 서버들이 소켓 프록시와 Loki 에 닿지 않는다.

**오래 남겨야 하는 기록은 Loki 가 원본이 아니다.**

| 기록 | 원본 | 기간 |
| --- | --- | --- |
| 운영 로그(요청, 오류, 작업) | Loki | 위의 보관 기간 |
| 개인정보를 다루는 시스템에 들어간 사람의 기록(운영자의 조회와 조작, 관리자 화면) | 각 서버의 DB(`operator_actions`, 인증 서버의 보안 이벤트, [운영자 권한](architecture/operators.md)) | 1년 이상. 정보주체 5만 명 이상이거나 민감정보·고유식별정보를 다루면 2년 이상(개인정보의 안전성 확보조치 기준 8조). 공개 전에 처리방침과 함께 다시 확인한다(법률 검토가 아니다) |
| 결제와 청약철회 | 결제 서버의 원장(DB, 덧붙이기만) | 지우지 않는다 |

**나중에 S3 로 옮길 때.** Loki 는 저장소 설정만 바꿔 S3 에 쓴다. Prometheus 는 스스로 S3 에 쓰지 못한다. 메트릭은 Mimir 로 바꿔 S3 에 쓴다([Mimir 로 옮길 수 있게](#mimir-로-옮길-수-있게-지키는-것)).

### 2. 메트릭 — 서버는 OTLP 로 밀고, 인프라는 Alloy 가 긁는다

```
서버, 워커, cron ─(OTLP, HTTP 4318)─▶ Alloy ─(remote write)─▶ Prometheus ─▶ Grafana
PostgreSQL, Redis ◀─(긁기, Alloy 안의 exporter)─ Alloy ┘
```

#### 정한 것 (2026-10-19)

| 항목 | 정한 것 | 까닭 |
| --- | --- | --- |
| 서버가 보내는 법 | **OTLP 로 Alloy 에 민다**(HTTP, protobuf, 4318). 서버, 워커, cron 모두 같다 | 계속 도는 워커가 넷, 하루 한 번 도는 cron 이 둘이다. 긁기로 가면 워커마다 HTTP 서버를 붙이고(워커의 상태를 파일로 정한 까닭과 같다, [워커의 상태](#워커의-상태)), cron 은 긁을 수 없어 Pushgateway 가 하나 더 든다. 추적(3단계)도 같은 SDK 라 내보내기 하나만 더하면 된다. gunicorn 의 프로세스를 늘려도(`WEB_CONCURRENCY`) 프로세스마다 따로 보내면 된다 |
| 방향 | 서버 → Alloy 한쪽만. 서버와 Alloy 만 있는 망 `telemetry` 를 새로 둔다. Alloy 는 서버의 포트에 닿지 않는다 | 긁기는 Alloy 가 모든 서버의 API 포트에 닿아야 한다. Alloy 가 뚫리면 모든 API 를 부를 수 있다. 서버들은 지금처럼 Loki, Grafana, 소켓 프록시에 닿지 않는다 |
| 인프라 | PostgreSQL, Redis 는 **Alloy 안의 exporter 가 긁는다**(`prometheus.exporter.postgres`, `prometheus.exporter.redis`). 컨테이너를 늘리지 않는다 | 서버 코드가 아니라 고칠 수 없다. 컨테이너의 CPU·메모리(cAdvisor)는 VM 의 `/sys` 와 Docker 의 폴더를 읽어야 해서 권한을 따로 정한다(나중) |
| 저장소 | **Prometheus 단독**, 보관 **14일**. 받기만 한다(remote write 수신). Prometheus 는 아무것도 긁지 않는다 | 시계열이 1~2만 개 안쪽이라 한 프로세스로 넉넉하다. 로그와 기간이 같아야 같은 시각을 함께 본다. **S3 가 필요해지면 Mimir(한 프로세스)로 바꾼다.** 그때 서버 코드와 계측은 그대로다(아래) |
| 순서 | ① 인프라(Prometheus, Alloy 의 OTLP 수신, 망, Grafana 의 데이터 소스) → ② 결제 서버(본보기) → ③ PostgreSQL·Redis → ④ 나머지 서버는 그 서버를 맡은 세션이 본보기대로 | 인프라는 서버 코드 없이 시험 지표 하나로 CI 에서 확인한다. 실패하면 원인이 인프라뿐이다. 서버마다의 PR 은 작고 다른 세션과 겹치지 않는다 |

| 고르지 않은 것 | 까닭 |
| --- | --- |
| 서버의 `/metrics` 를 Alloy 가 긁기 | 위의 워커와 cron, Alloy 가 서버의 API 포트에 닿는 것. Python 은 gunicorn 의 프로세스가 여럿이면 multiprocess 모드가 따로 든다 |
| Prometheus 가 직접 긁기 | 위와 같고, 컨테이너를 찾으려고 Prometheus 에도 Docker 의 API 가 든다. 수집기가 둘이 된다 |
| 서버 → Prometheus(또는 Mimir)의 OTLP 수신으로 바로 | 저장소를 바꾸면 서버마다 설정을 고친다. OTLP 의 이름을 Prometheus 의 이름으로 바꾸는 규칙이 저장소마다 달라 이름이 흔들린다 |
| 로그(요청이 끝난 줄)에서 Alloy 가 메트릭을 만들기 | 서버 코드를 고치지 않지만 로그에 있는 것만 된다. 처리 중인 요청 수, DB 풀 같은 지금의 값을 만들지 못한다. 로그가 밀리면 메트릭도 밀린다 |
| 처음부터 Mimir, VictoriaMetrics, Thanos | Mimir 는 이 규모에 무겁다(메모리 1GB 안팎, 설정이 많다). VictoriaMetrics 는 질의가 MetricsQL 이라 PromQL 과 조금 다르다. Thanos 는 부품이 셋 는다 |
| Grafana Cloud 무료 | 메트릭(서버 이름, 주소의 틀)이 바깥으로 나가고 계정에 묶인다 |

#### Mimir 로 옮길 수 있게 지키는 것

Prometheus 에 쓰는 것은 Alloy 하나, 읽는 것은 Grafana 하나다. 이 둘의 주소만 바꾸면 옮겨지게 아래를 지킨다.

1. **Prometheus 는 받기만 한다.** `scrape_configs` 를 두지 않는다. 긁는 일은 모두 Alloy 가 하고 `prometheus.remote_write` 로 보낸다. Mimir 도 remote write(`/api/v1/push`)로 받는다.
2. **OTLP 의 이름을 Prometheus 의 이름으로 바꾸는 일은 Alloy 가 한다**(`otelcol.exporter.prometheus`). Prometheus 나 Mimir 의 OTLP 수신을 쓰지 않는다. 바꾸는 곳이 Alloy 하나라 저장소를 바꿔도 메트릭의 이름과 label 이 그대로다.
3. **Grafana 의 데이터 소스는 uid `prometheus` 로 고정한다.** 대시보드와 경보는 uid 로 찾는다. 옮길 때 같은 uid 에 주소만 Mimir 의 것(`http://mimir:9009/prometheus`, 시작 안내의 포트)으로 바꾼다.
4. **기록 규칙과 경보 규칙은 Prometheus 의 규칙 파일 형식으로 따로 둔다.** Mimir 의 ruler 가 같은 형식을 받는다. Prometheus 의 실행 인자에만 있는 기능에 기대지 않는다.
5. **tenant 는 하나다.** Alloy 는 tenant 머리말(`X-Scope-OrgID`)을 보내지 않는다. Mimir 는 `multitenancy_enabled: false` 로 띄운다.
6. **늦게 온 점을 받는다.** 미는 방식이라 점이 몇 초 늦거나 순서가 바뀔 수 있다. Prometheus 의 `out_of_order_time_window` 를 10분으로 둔다. Mimir 에도 같은 이름의 한도가 있다.
7. **보관 기간은 한 값이다.** Prometheus 의 설정 파일의 `storage.tsdb.retention.time: 14d` 가 Mimir 의 `compactor_blocks_retention_period: 14d` 가 된다. 실행 인자(`--storage.tsdb.retention.time`)는 3.15 에서 낡은 것이 되어 쓰지 않는다. 볼륨은 따로(`prometheusdata`) 둔다.
8. **옮기는 법.** Alloy 의 `prometheus.remote_write` 에 보낼 곳을 둘(Prometheus, Mimir) 두고 14일 동안 함께 쓴다. 그다음 Grafana 의 데이터 소스를 Mimir 로 바꾸고 Prometheus 를 끈다. 지난 데이터를 옮기지 않아도 14일이면 같아진다. 옮겨야 하면 mimirtool 의 backfill 로 Prometheus 의 블록을 올린다.

#### 붙인 것 (메트릭의 인프라)

| 파일 | 하는 일 |
| --- | --- |
| `docker-compose.yml` 의 `prometheus` | `prom/prometheus:v3.15.0-busybox`. 받기만 한다(`--web.enable-remote-write-receiver`). 포트를 열지 않는다. healthcheck 는 `/-/ready` |
| `docker/prometheus/prometheus.yml` | 긁는 설정이 없다. 늦게 온 점 10분, 보관 14일. 경보 규칙(`rules/`)을 15초마다 평가해 Alertmanager 로 넘긴다([경보](#경보)) |
| `docker/alloy/metrics.alloy` | OTLP 받기(HTTP 4318) → 묶기 → 이름 바꾸기 → label `service` 붙이기 → remote write. 수집 쪽 자신(alloy, loki, prometheus, alertmanager, grafana)을 15초마다 긁는다 |
| `docker/grafana/provisioning/datasources/prometheus.yaml` | 데이터 소스 uid `prometheus`. 화면에서 고치지 못한다 |
| 망 `telemetry` | Alloy 하나만 있다(internal). 서버의 프로세스는 그 서버에 메트릭을 붙이는 PR 에서 더한다 |
| `.github/scripts/stack-smoke.sh` 의 `check_metrics` | CI(`stack`)가 PR 마다 아래를 본다 |

- **Alloy 는 폴더를 읽는다.** `docker/alloy/` 를 통째로 붙이고 그 안의 `config.alloy`(로그)와 `metrics.alloy`(메트릭)를 함께 읽는다. 단계마다 파일이 하나씩이다.
- **수집 쪽 자신의 메트릭은 `job` 으로 가른다.** `service` 는 서버의 메트릭에만 붙는다. `up{job="loki"}` 처럼 찾는다.
- **라이브러리의 이름은 label 이 아니다**(`include_scope_labels = false`). OTLP 의 계측 범위(`otel_scope_name`)가 모든 메트릭에 붙지 않게 한다.
- **Prometheus 가 멈추면.** Alloy 의 remote write 가 볼륨(`alloydata`)의 WAL 에 남겼다가 돌아오면 보낸다. Alloy 가 받은 OTLP 는 그 전에 묶음(batch)에 있어서, Alloy 가 죽는 순간의 묶음은 잃는다.
- **CI 가 보는 것.** Prometheus 가 root 가 아니고 다시 뜨지 않는다. Grafana 가 Prometheus 에 닿는다. Prometheus 가 아무것도 긁지 않는다.
  telemetry 망에서 OTLP(JSON)로 민 시험 지표 `stack_smoke_probe` 가 `stack_smoke_probe_total{service="stack-smoke", instance="<이 실행의 값>"}` 으로 들어온다(이름 바꾸기와 label 을 함께 본다).
  `up{job=…}` 이 alloy, loki, prometheus, grafana 모두 1 이다. 게임 서버가 Prometheus 에 닿지 않는다.

#### 붙인 것 (DB 와 Redis)

| 파일 | 하는 일 |
| --- | --- |
| `docker/alloy/metrics.alloy` 의 `prometheus.exporter.postgres`, `prometheus.exporter.redis` | Alloy 안의 exporter(postgres_exporter, redis_exporter)가 15초마다 읽는다. 컨테이너를 늘리지 않는다. 이름표는 `job="postgres", instance="db"`, `job="redis", instance="redis"` 다 |
| `docker/postgres/init/07-monitor-role.sql` | DB 의 메트릭을 읽는 계정 `monitor`. 내장 역할 `pg_monitor`(통계와 설정)만 받는다. 스키마의 권한이 없어 서버들의 표를 읽지 못하고, 읽기 전용(`default_transaction_read_only`)이라 쓰지 못한다. 연결은 셋까지, 문장 하나는 10초까지다 |
| 루트 `.env` 의 `MONITOR_DB_PASSWORD` | 그 계정의 비밀번호. DB(계정을 만든다)와 Alloy(붙는다)만 받는다(`secret_scope.py` 의 `ROOT_SECRETS`). 비어 있으면 계정을 만들지 않는다. 주소에 그대로 들어가므로 영문과 숫자로만 짓는다 |
| 망 `datastore-metrics` | DB, Redis, Alloy 만 있다(internal). Alloy 는 서버들의 망(`default`)에 없어서 서버의 API 에 닿지 않는다 |

- **서버의 계정을 빌리지 않는다.** 슈퍼유저로 붙으면 Alloy 가 DB 를 통째로 지울 수 있는 비밀번호를 쥔다. Alloy 는 Docker 의 API 까지 닿는 컨테이너라 뚫리면 피해가 가장 크다. 서버의 계정은 그 스키마를 읽고 쓰고, 다른 스키마의 통계는 일부만 보인다.
- **Alloy 를 기본 망에 넣지 않는다.** 넣으면 모든 서버의 API 를 부를 수 있다. 메트릭을 OTLP 로 밀게 한 까닭(서버 → Alloy 한쪽만)이 사라진다.
- **DB 는 한 곳(`trpg`)만 읽는다**(`autodiscovery` 를 끈다). 서버들은 한 DB 의 스키마를 나눠 쓴다. 표마다의 통계(`pg_stat_user_tables_*`)는 스키마(`schemaname`)와 표(`relname`)를 label 로 단다. 표의 수만큼이라 끝이 있다. 사용자나 주문 번호처럼 끝없이 느는 값이 아니다.
- **이미 있는 볼륨에서는 계정을 직접 만든다.** 초기화 스크립트는 볼륨이 비어 있는 첫 기동 때만 돈다. 루트 README 의 "로그와 메트릭 모으기"에 명령이 있다. 다시 돌려도 된다(있으면 비밀번호만 맞춘다).
- **CI 가 보는 것.** `pg_up{job="postgres", instance="db"} == 1`, `redis_up{job="redis", instance="redis"} == 1` 이 들어온다. `monitor` 가 통계는 읽고, 결제 서버의 표(`billing.wallets`)는 읽지 못하고, 표를 만들지 못한다. Alloy 가 `default` 망에 없다.

#### 붙인 것 (디스크)

디스크가 차서 DB 와 저장소가 쓰기를 멈추는 일을 막는다(#539, 2026-10-21). 디스크를 나누는 것은 [배포 설계의 디스크](architecture/deployment.md#디스크)에 있다.

| 파일 | 하는 일 |
| --- | --- |
| `docker/alloy/metrics.alloy` 의 `prometheus.exporter.unix "disks"` | Alloy 안의 node_exporter(파일시스템만)가 1분마다 잰다. 새 컨테이너도, 호스트의 폴더도 붙이지 않는다. 컨테이너 안의 마운트 셋이 놓인 디스크를 잰다: `/etc/alloy`(기본 디스크, `disk="system"`), staging 의 `/disks/db`, `/disks/observability`(그 디스크의 빈 폴더 probe 를 읽기 전용으로). 그 밖의 마운트는 버린다. 이름표는 `job="disks", instance="host", disk` 다 |
| `docker/prometheus/rules/ai-trpg.yml` 의 `disks` | node_exporter 의 경보 묶음(node-mixin)을 따른다. `DiskSpaceLow`(남은 15% 밑, 30분), `DiskSpaceCritical`(5% 밑, 5분), `DiskFillingUp`(40% 밑이고 지난 6시간의 속도면 24시간 안에 찬다, 1시간), `DiskFillingUpFast`(20% 밑이고 4시간 안, 1시간), `DiskMetricsMissing`(기본 디스크의 지표가 15분 없다). 읽기만 하는 디스크는 보지 않는다 |
| `docker/grafana/dashboards/disks.json` | 디스크마다 남은 비율과 양, 지금 속도면 가득 차기까지, 쓴 양, 하루에 느는 양 |
| `docker/prometheus/prometheus.yml` 의 `retention.size` | 메트릭의 크기 상한 8GB. 14일과 둘 가운데 먼저 닿는 쪽이 지운다 |

- **비율 하나로 보지 않는다.** 남은 비율만 보면 천천히 차는 디스크에는 너무 일찍, 갑자기 차는 디스크에는 너무 늦게 울린다. 그래서 지난 6시간의 기울기로 "곧 찬다"를 함께 본다. 잠깐 늘었다 주는 일(백업 파일, 압축)에 속지 않게 한 시간 넘게 이어질 때만 울린다.
- **저장소마다의 크기.** 저장소가 스스로 내는 숫자를 쓴다. Prometheus 는 낸다(`prometheus_tsdb_storage_blocks_bytes`, `prometheus_tsdb_wal_storage_size_bytes`). Loki 3.7 과 Tempo 3.1 은 디스크에 둔 양을 내지 않는다(실제로 띄워 지표를 보았다). 관측 데이터를 따로 둔 디스크의 사용량이 셋의 합이다. 볼륨마다의 내역은 손으로 본다([staging VM 준비](operations/staging-vm.md)의 11번).
- **CI 가 보는 것.** 경보의 시험(promtool)이 다섯 경보마다 울리는 때와 울리지 않는 때를 본다. 스택에서 기본 디스크의 지표가 들어오고 마운트가 하나만 남는다. Prometheus 의 보관에 크기의 상한이 걸렸다. staging 의 데이터 디스크 폴더(`docker/disks/prepare-disks.sh`)의 주인이 컨테이너가 실제로 도는 uid 와 같다.

#### 대시보드

Grafana 가 뜰 때 `docker/grafana/dashboards/` 의 JSON 을 읽어 폴더 `ai-trpg` 에 붙인다(`docker/grafana/provisioning/dashboards/dashboards.yaml`).
**저장소의 파일이 원본이다.** 화면에서 고치지 못한다(`allowUiUpdates: false`). 화면에서 고친 것은 다시 뜨면 사라지고, 무엇을 왜 바꿨는지 PR 에 남지 않는다.
고치려면 화면에서 새 대시보드로 만들어 보고, Export(바깥에 나누는 것이 아닌 그냥 Export)로 내보낸 JSON 으로 그 파일을 바꾸는 PR 을 낸다. 파일이 바뀌면 30초 안에 다시 읽는다.

| 규칙 | 까닭 |
| --- | --- |
| 서버마다 파일 하나. 파일 이름과 uid 는 서비스 이름이다(`billing-server.json`, uid `billing-server`). Alloy 가 긁는 인프라는 그 job 의 이름이다(`postgres.json`, `redis.json`) | 주소(`/d/billing-server`)가 바뀌지 않는다. 관리 서버가 링크를 걸 수 있다 |
| 데이터 소스는 uid(`prometheus`, `loki`)로 부른다. `${DS_PROMETHEUS}` 같은 자리, `__inputs` 를 두지 않는다 | 저장소를 Mimir 로 바꿀 때 데이터 소스의 주소만 바뀐다(아래의 "Mimir 로 옮길 수 있게 지키는 것" 3) |
| Prometheus 의 쿼리는 모든 선택자에 그 서버의 `service` 를 건다. 인프라는 그 `job` 을 건다 | 서버들이 같은 이름(`http_server_requests_total`, `db_up` …)을 쓴다. 빠뜨리면 다른 서버의 것이 섞인다 |
| 시간 창은 `$__rate_interval` 이다 | 수집 간격(15초)과 화면의 시간 범위에 맞춰 Grafana 가 고른다. 고정한 `[1m]` 은 넓은 범위에서 점을 건너뛴다 |
| 짧게 돌고 끝나는 프로세스(대사)는 `last_over_time(…[1d])` 로 본다. `rate` 로 보지 않는다 | 끝날 때 한 번만 민다. 실행마다 `instance` 가 새것이라 시계열마다 점이 하나뿐이고, `rate`, `increase` 는 점 둘이 있어야 값이 난다. 그래서 `rate` 를 쓰는 패널은 `instance!~"reconcile-.+"` 로 대사를 빼고, 대사는 따로 둔다 |
| 경보는 대시보드에 걸지 않는다(Grafana 의 경보를 쓰지 않는다) | 규칙은 Prometheus 의 규칙 파일이다([아래](#경보)). 대시보드의 패널과 경보의 조건이 같을 필요가 없다 |

`notification-server` 는 한눈에(DB, 5xx 비율, 넣은 알림, 받지 않은 알림), 요청, DB 연결, 알림, 정리 작업의 다섯 줄이다.
`trpg-server` 는 한눈에(DB, 5xx 비율, 열린 스트림, 서술 실패), 요청, DB 연결, 실시간 스트림, 라운드와 서술, AI 호출, 서술 값, 뒤에서 도는 작업의 여덟 줄이다.
`auth-server` 는 한눈에(DB, 5xx 비율, 버린 메일, 세지 못한 시도 제한), 요청, 메일, 시도 횟수 제한, 워커와 예약 명령의 다섯 줄이다. 연결 풀이 없어 DB 연결의 줄이 없다.
`board-server` 는 한눈에(DB, 5xx 비율, 횟수 제한에 걸린 쓰기, 멈춘 검색), 요청, DB 연결, 쓰기와 신고, 검색, 알림 보내기의 여섯 줄이다.
`billing-server` 의 대시보드는 한눈에(DB, 5xx 비율, 결과를 모르는 결제 대행사 호출, 되돌린 원장의 일), 요청, DB 연결, 결제, 원장, 정리 작업과 대사의 여섯 줄이다.
`postgres` 는 한눈에(DB, 연결 / 최대, DB 의 크기, 교착), 연결과 트랜잭션, 읽기와 쓰기(캐시 적중률, 행, 임시 파일, 스키마마다의 크기), 표(큰 표, 죽은 행이 많은 표)다.
`asset-server` 와 `chat-server` 는 한눈에(DB, 5xx 비율), 요청, DB 연결의 세 줄이다. 업무의 메트릭이 붙으면 그 줄을 더한다.
`redis` 는 한눈에(Redis, 메모리, 연결된 클라이언트, AOF 의 마지막 쓰기), 명령(명령마다, 키 적중률, 오류와 거절), 메모리와 키(사라진 키, 내쫓긴 키)다.
대시보드의 규칙은 `.github/scripts/dashboard_scope.py` 가 보고, 그 규칙 자체는 `test_dashboard_scope.py` 가 본다.
CI(`stack`)는 거기에 더해 Grafana 가 파일의 대시보드를 모두 읽었는지, 모든 Prometheus 쿼리가 Grafana 의 데이터 소스 프록시를 거쳐 오류 없이 도는지 본다.
값이 없는 것(CI 에 결제가 없어 생기지 않은 메트릭)은 오류가 아니다. 이름이나 PromQL 이 틀린 것을 잡는다.

#### 경보

```
Prometheus(규칙을 15초마다 평가) ─▶ Alertmanager(묶기, 되풀이, 누르기, 잠시 끄기) ─▶ Discord, Slack, Telegram, 메일
```

켜는 법과 받는 곳을 만드는 법은 [README 의 로그와 메트릭 모으기](../README.md#로그와-메트릭-모으기)에 있다.

| 항목 | 정한 것 | 까닭 |
| --- | --- | --- |
| 규칙을 돌리는 곳 | Prometheus 의 규칙 파일(`docker/prometheus/rules/ai-trpg.yml`). Grafana 의 경보를 쓰지 않는다 | 규칙이 저장소의 파일이라 PR 로 고치고 promtool 로 시험한다. Mimir 의 ruler 가 같은 파일을 읽는다(위의 "Mimir 로 옮길 수 있게 지키는 것" 4). Grafana 의 경보는 Grafana 의 DB 에 남아 대시보드처럼 무엇을 왜 바꿨는지 PR 에 남지 않는다 |
| 보내는 곳 | Alertmanager 하나(`prom/alertmanager:v0.34.1`). 받는 곳 넷을 한 받는 쪽(`operator`)에 둔다 | 같은 경보가 넷에 함께 간다. 하나가 막혀도(웹후크를 지웠다, 메일이 스팸함에 갔다) 나머지로 안다 |
| 켜는 법 | 루트 `.env` 의 `ALERT_*` 에 적은 것만 켠다. 시작 명령(`docker/alertmanager/entrypoint.sh`)이 그 값으로 설정 파일을 만든다. 하나를 반쯤 적으면(Telegram 의 토큰만) 뜨지 않는다 | Alertmanager 의 설정 파일은 환경 변수를 펼치지 않는다. 설정 파일을 저장소에 두면 비밀을 적거나, 받는 곳을 바꿀 때마다 파일을 고쳐야 한다 |
| 비밀 | 웹후크 주소, 봇 토큰, 메일 비밀번호는 설정 파일이 아니라 주인만 읽는 파일에 둔다(`webhook_url_file`, `api_url_file`, `bot_token_file`, `auth_password_file`). Alertmanager 만 받는다(`secret_scope.py` 의 `ROOT_SECRETS`) | 설정을 찍거나(amtool, 로그) 옮겨도 비밀이 함께 가지 않는다. 웹후크 주소는 아는 사람이 누구나 그 채널에 쓰므로 비밀이다 |
| 메일 | Gmail 의 SMTP 를 그대로 쓴다. 앱 비밀번호는 서버들이 사용자에게 보내는 메일(인증 서버의 `SMTP_PASSWORD`)과 따로 만든다 | 운영자 한 사람만 받는다. 사용자에게 보내는 메일은 운영에서 다른 메일 서비스로 바꾼다. 나눠 두면 하나가 새도 그것만 지운다 |
| 묶기 | `alertname`, `service`, `job` 으로 묶는다. 처음 30초를 모아 보내고, 묶음이 바뀌면 5분, 그대로면 4시간마다 다시 보낸다. 풀리면 풀렸다고 보낸다 | 한 서버의 프로세스 여럿(`instance`)이 함께 울려도 알림은 하나다 |
| 누르기 | `PostgresDown` 이 울리는 동안 `…DatabaseUnreachable` 은 보내지 않는다 | 원인 하나에 알림 하나다. 서버마다 DB 경보를 붙이면 이름을 `<서버>DatabaseUnreachable` 로 짓는다 |
| 바깥 감시 | 늘 울리는 `Watchdog` 을 바깥 감시의 주소(`ALERT_HEARTBEAT_WEBHOOK_URL`, healthchecks.io 의 ping 주소 등)로만 1~2분마다 보낸다. 신호가 끊기면 그 서비스가 제 알림으로 알린다. 적지 않으면 `Watchdog` 은 버린다 | 위의 받는 곳은 Prometheus, Alertmanager, PC 나 VM, 인터넷이 살아 있어야 간다. 그것들이 죽은 것은 바깥에서만 알 수 있다. 주소 하나만 받으므로 서비스를 바꿔도(Better Stack, Uptime Kuma) 코드는 그대로다 |
| 보는 곳 | 포트를 열지 않는다. 울리는 것과 잠시 끄기(silence)는 Grafana 의 Alerting 화면에서 데이터 소스 `alertmanager` 를 골라 본다 | Alertmanager 의 화면에는 로그인이 없다. 열면 누구나 경보를 끈다 |

| 고르지 않은 것 | 까닭 |
| --- | --- |
| Grafana 의 경보(Grafana-managed alerts) | 위의 "규칙을 돌리는 곳". 규칙을 돌리는 곳이 Grafana 가 되어 Grafana 가 죽으면 경보도 멈춘다 |
| 받는 곳마다 받는 쪽(receiver)을 나누고 severity 로 고르기 | 운영자가 한 사람이라 모두 같은 곳으로 간다. 사람이 늘면 `route` 에 `routes` 를 더해 나눈다 |
| 설정 파일을 저장소에 두고 비밀만 파일로 붙이기 | 받는 곳을 켜고 끌 때마다 설정 파일을 고친다. 붙일 비밀 파일을 VM 에 따로 만들어야 한다 |

규칙(`severity` 가 `critical` 이면 바로, `warning` 이면 그날 안에 본다):

| 묶음 | 경보 | severity | 조건 |
| --- | --- | --- | --- |
| watchdog | `Watchdog` | none | 늘 울린다. 바깥 감시에만 간다. Prometheus 가 멈추면 4분쯤 뒤 Alertmanager 에서 사라지고, 바깥 감시의 기다림(5분 + 여유 5분을 권한다)이 지나면 그쪽이 알린다 |
| watchdog | `AlertDeliveryFailing` | warning | 지난 15분에 받는 곳(Discord, Slack, Telegram, 메일) 가운데 하나로 보내지 못했다. 나머지 받는 곳으로 간다. 바깥 감시(webhook)의 실패는 세지 않는다 |
| collectors | `MetricsCollectorDown` | critical | Alloy 의 `up` 이 끊겼다(10분쯤 뒤에 울린다, 아래). 다른 경보가 모두 멈춘다 |
| collectors | `ObservabilityComponentDown` | warning | loki, grafana, alertmanager 의 `up` 이 5분 동안 0 이다 |
| disks | `DiskSpaceLow` | warning | 디스크에 남은 공간이 15% 밑으로 30분 이어진다 |
| disks | `DiskSpaceCritical` | critical | 디스크에 남은 공간이 5% 밑으로 5분 이어진다 |
| disks | `DiskFillingUp` | warning | 남은 공간이 40% 밑이고, 지난 6시간의 속도면 24시간 안에 찬다(1시간 이어진다) |
| disks | `DiskFillingUpFast` | critical | 남은 공간이 20% 밑이고, 지난 6시간의 속도면 4시간 안에 찬다(1시간 이어진다) |
| disks | `DiskMetricsMissing` | warning | 기본 디스크의 크기가 15분 동안 들어오지 않는다 |
| datastores | `PostgresDown`, `RedisDown` | critical | exporter 가 1분 동안 붙지 못한다 |
| datastores | `RedisAOFWriteFailing` | critical | AOF 의 마지막 쓰기가 1분 동안 실패다 |
| datastores | `RedisEvictingKeys` | warning | 지난 10분에 메모리(64MB)가 차서 키를 내쫓았다. 시도 횟수를 잃어 제한이 느슨해졌다 |
| datastores | `PostgresConnectionsNearLimit` | warning | 연결이 `max_connections` 의 80% 를 10분 동안 넘는다 |
| datastores | `PostgresDeadlocks` | warning | 지난 10분에 `trpg` 에 교착이 있었다 |
| billing-server | `BillingDatabaseUnreachable` | critical | `db_up` 이 1분 동안 0 이다 |
| billing-server | `BillingServerErrors` | warning | 5xx 가 10분 동안 5% 를 넘는다. 요청이 분당 3번 미만이면 세지 않는다. 상태 확인(`/health`, `/health/ready`)은 세지 않는다(#645) |
| billing-server | `BillingPaymentOutcomeUnknown` | warning | 지난 15분에 결제 대행사가 답하지 않은 호출(`outcome="unknown"`)이 있다. 돈이 나갔을 수 있다 |
| billing-server | `BillingPaymentProviderUnavailable` | warning | 지난 15분에 결제 대행사를 부르지 못한 것이 세 번을 넘는다 |
| billing-server | `BillingLedgerRollbacks` | warning | 지난 15분에 원장에 적었다가 되돌린 일이 있다(`expire` 는 뺀다. [목록](#목록)의 뜻) |
| billing-server | `BillingSweepStalled` | warning | 결제 서버가 떠 있는데 정리 작업이 10분 넘게 성공하지 않았다 |
| billing-server | `BillingReconcileMissed` | warning | 지난 이레 안에 돈 대사가 지난 26시간에는 돌지 않았다. 한 번도 돈 적이 없으면 울리지 않는다 |
| billing-server | `BillingReconcileFailed` | warning | 지난 하루의 대사가 성공하지 못했다 |
| notification-server | `NotificationDatabaseUnreachable` | critical | `db_up` 이 1분 동안 0 이다 |
| notification-server | `NotificationServerErrors` | warning | 5xx 가 10분 동안 5% 를 넘는다. 요청이 분당 3번 미만이면 세지 않는다. 상태 확인(`/health`, `/health/ready`)은 세지 않는다(#645) |
| notification-server | `NotificationsRejected` | warning | 지난 15분에 받지 않은 알림(`refused`, `conflict`)이 있다. 넣은 서버와 결과마다 울린다 |
| notification-server | `NotificationPruneFailing` | warning | 지난 세 시간에 정리 작업이 실패했다 |
| trpg-server | `TrpgDatabaseUnreachable` | critical | `db_up` 이 1분 동안 0 이다. Redis 만 닿지 않을 때는 울리지 않는다 |
| trpg-server | `TrpgServerErrors` | warning | 5xx 가 10분 동안 5% 를 넘는다. 요청이 분당 3번 미만이면 세지 않는다. 상태 확인(`/health`, `/health/ready`)은 세지 않는다(#645) |
| trpg-server | `TrpgNarrationsFailing` | warning | 지난 30분의 서술이 셋 이상이고 20% 넘게 실패한 것이 5분 이어진다 |
| trpg-server | `TrpgChargesNotCaptured` | warning | 확정할 청구(`capture_due`)가 30분 동안 남아 있다. 결제 서버가 죽어 있다 |
| trpg-server | `TrpgBillingRejected` | warning | 지난 15분에 결제 서버가 받아들이지 않은 부르기가 있다. 일(`operation`)마다 울린다 |
| auth-server | `AuthDatabaseUnreachable` | critical | `db_up` 이 1분 동안 0 이다 |
| auth-server | `AuthServerErrors` | warning | 5xx 가 10분 동안 5% 를 넘는다. 요청이 분당 3번 미만이면 세지 않는다. 상태 확인(`/health`, `/health/ready`)은 세지 않는다(#645) |
| auth-server | `AuthMailWorkerStalled` | warning | 인증 서버가 떠 있는데 메일 워커가 10분 넘게 한 바퀴도 성공하지 않았다 |
| auth-server | `AuthMailBacklog` | warning | 발송함에 메일이 15분 동안 남아 있다. 메일 서버가 받지 않는다 |
| auth-server | `AuthMailDiscarded` | warning | 지난 15분에 버린 메일이 있다. 종류(`kind`)마다 울린다 |
| auth-server | `AuthRateLimitsUnavailable` | warning | 지난 5분에 시도 횟수를 세지 못하고 통과시킨 것이 있다. 제한(`limit`)마다 울린다 |
| auth-server | `AuthWelcomeCreditsWorkerStalled` | warning | 인증 서버가 떠 있는데 결제 쪽 워커(`auth-welcome-credits`)가 10분 넘게 한 바퀴도 성공하지 않았다. 환영 크레딧, 결제 자격, 탈퇴가 멈춘다 |
| auth-server | `AuthWithdrawalsOverdue` | warning | 비울 시각이 지난 탈퇴가 30분 동안 남아 있다(#603) |
| auth-server | `AuthWithdrawalNoticesWaiting` | warning | 다른 서버에 알리지 못한 탈퇴가 2시간 동안 남아 있다. 비밀을 적지 않은 서버의 것은 세지 않는다 |
| board-server | `BoardDatabaseUnreachable` | critical | `db_up` 이 1분 동안 0 이다 |
| board-server | `BoardServerErrors` | warning | 5xx 가 10분 동안 5% 를 넘는다. 요청이 분당 3번 미만이면 세지 않는다. 상태 확인(`/health`, `/health/ready`)은 세지 않는다(#645). 멈춘 검색(503)도 든다 |
| board-server | `BoardSearchTimeouts` | warning | 지난 15분에 멈춘 검색이 셋을 넘는다 |
| board-server | `BoardNotificationRoundsFailing` | warning | 지난 15분에 알림 보내기의 바퀴가 통째로 실패했다 |
| asset-server | `AssetDatabaseUnreachable` | critical | `db_up` 이 1분 동안 0 이다 |
| asset-server | `AssetServerErrors` | warning | 5xx 가 10분 동안 5% 를 넘는다. 요청이 분당 3번 미만이면 세지 않는다. 상태 확인(`/health`, `/health/ready`)은 세지 않는다(#645) |
| chat-server | `ChatDatabaseUnreachable` | critical | `db_up` 이 1분 동안 0 이다 |
| chat-server | `ChatServerErrors` | warning | 5xx 가 10분 동안 5% 를 넘는다. 요청이 분당 3번 미만이면 세지 않는다. 상태 확인(`/health`, `/health/ready`)은 세지 않는다(#645) |

- **규칙마다 시험이 있다**(`docker/prometheus/rules/tests/ai-trpg.test.yml`). 지어낸 시계열을 넣고 정한 때에 울리는지, 울리지 않을 때(요청이 아주 적다, 다른 서버의 것이다) 조용한지 본다. 규칙을 고치면 시험도 고친다.
  `docker compose --profile observability exec prometheus promtool test rules /etc/prometheus/rules/tests/ai-trpg.test.yml`
- **"없어졌다"는 5분 늦다.** 받기만 하는 Prometheus 는 마지막 값을 5분 동안 살아 있는 것으로 본다(긁을 때처럼 끊긴 표시가 오지 않는다). 그래서 `MetricsCollectorDown` 은 그 5분과 `for: 5m` 뒤에 울린다.
- **짧게 도는 대사는 `last_over_time` 으로 본다.** 끝날 때 한 번만 밀어서 `increase` 로는 값이 나지 않는다(대시보드의 규칙과 같은 까닭).
- **서버에 메트릭을 붙이는 PR 이 그 서버의 규칙을 함께 더한다.** 묶음의 이름은 서비스 이름(`billing-server`)이고 경보의 이름은 서버의 이름으로 시작한다(`Billing…`). 시험도 함께 더한다.
- **CI 가 보는 것.** 규칙의 시험이 통과한다. Prometheus 가 규칙 파일의 묶음을 모두 읽었고 Alertmanager 를 찾았다. `Watchdog` 이 울린다. 건강한 스택에서 그 밖에 울리는 경보가 없다(선택자가 틀린 규칙이 여기서 울린다).
  Alertmanager 가 root 가 아니고, 받는 곳 넷을 모두 적은 설정이 맞고(`amtool check-config`), 반쯤 적으면 뜨지 않고, 봇 토큰이 설정 파일에 없다. Grafana 가 Alertmanager 에 닿는다.
  받는 곳의 흉내(`.github/scripts/alert_sink.py`)를 띄우고 시험 경보를 넣어, Discord, Slack, Telegram 의 주소로 넘어가는지 본다. 메일은 보내 보지 않는다(설정만 본다).
  `Watchdog` 이 바깥 감시의 흉내(`/heartbeat`)로 가고, 운영자의 받는 곳에는 가지 않는다.

#### 계측기를 만드는 법

위의 [목록](#목록)대로 계측한다. 새로 만드는 서버(story, 관리)는 처음부터 SDK 를 붙이고 시작한다(asset 과 chat 은 `shared/server-core` 로 붙였다). 나중에 고치는 것보다 싸다.

| 무엇 | 붙일 자리 |
| --- | --- |
| HTTP 요청 수, 시간, 처리 중인 수 | 요청이 끝난 줄을 남기는 미들웨어. 같은 값(`method`, `route`, `status_code`, 걸린 시간)을 이미 갖고 있다 |
| 작업 | trpg-server `app/core/jobs.py`, auth-server `observability/jobs.py`, billing-server `internal/jobs/jobs.go`, notification-server 와 asset-server `server_core/observability/metrics.py` 의 `measured_job` |
| AI 호출 | `shared/ai-core` 의 `ai_core/calls.py` 의 `CallLog`. 기록장을 감싸 센다(`app/ai_log/metered.py`) |
| DB 풀 | 서버마다 풀을 만드는 곳 |

- **이름.** 계측기의 이름은 표의 이름에서 `_total` 과 단위(`_seconds`, `_bytes`)를 뗀 것이고, 단위는 계측기의 단위로 준다(초 `s`, 바이트 `By`). Alloy 가 단위와 `_total` 을 붙여 표의 이름이 된다.
  예: 이름 `http_server_request_duration`, 단위 `s` → `http_server_request_duration_seconds`. 셀 수에는 단위를 비운다(`1` 을 주면 gauge 에 `_ratio` 가 붙는다). CI 가 표의 이름으로 찾는다.
- **`service` label.** 서비스 이름은 OTLP 의 `service.name`(코드에 적힌 이름, [서비스 이름](#서비스-이름-환경-버전))이다. Alloy 가 이것을 모든 메트릭의 label `service` 로 옮긴다. 워커와 cron 도 그 서버의 이름이다.
- **프로세스마다 `service.instance.id` 가 다르다.** 같으면 두 프로세스의 수가 서로 덮어쓴다. 조회는 `sum by (service, …)` 로 합친다.
- **히스토그램의 구간을 정한다.** SDK 의 기본 구간은 밀리초를 가정한 숫자라 초로 재면 거의 모두 첫 칸에 든다. 시간은 `0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10` 초다. 서술과 AI 호출처럼 긴 것은 그 계측기만 `… 30, 60, 120` 을 더한다.
- **주소.** `OTEL_EXPORTER_OTLP_ENDPOINT`(compose 에서 `http://alloy:4318`)로 받는다. **비어 있으면 내보내지 않는다.** 계측은 그대로 돌고 보내기만 없다. PC 에서 띄운 서버가 없는 주소로 보내며 오류를 남기지 않는다.
- **간격은 15초다**(`OTEL_METRIC_EXPORT_INTERVAL=15000`). SDK 의 기본(60초)이면 `rate(…[1m])` 에 점이 하나뿐이다.
- **gunicorn 은 워커가 갈라진 뒤에 켠다.** 인증 서버는 앱을 워커가 갈라진 뒤에 불러오고(`preload_app = False`) 앱이 뜰 때 켠다(`observability/apps.py`). 갈라지기 전에 켜면 내보내는 스레드가 워커에 따라오지 않아 조용히 아무것도 가지 않는다.
- **cron 처럼 짧게 도는 명령은 끝날 때 한 번 내보낸다**(SDK 의 `shutdown`/`force_flush`). 간격을 기다리기 전에 끝나면 아무것도 가지 않는다.
- **Alloy 가 멈춰도 요청은 영향을 받지 않는다.** 내보내기는 뒤에서 돌고, 다시 보내다 안 되면 그 묶음을 버린다. 메모리에 쌓아 두지 않는다.
- **테스트.** SDK 의 메모리 수집기(in-memory reader)로 계측기의 이름, 단위, label 을 본다. 끝에서 끝까지(Prometheus 에서 찾아지는가)는 CI 의 `stack` 이 본다.
- **`service.instance.id` 는 `<프로세스>-<8자>` 다**(`server-3f2a9c1d`, `sweeper-…`). Prometheus 의 label `instance` 가 되어, 같은 `service` 안에서 서버와 워커를 가른다. 뒤의 글자는 띄울 때마다 새로 정한다.
- **출처(resource)에는 정해 둔 넷만 싣는다**: `service.name`, `service.version`, `service.instance.id`, `deployment.environment.name`. SDK 가 스스로 붙이는 호스트 이름과 프로세스 번호는 싣지 않는다. Prometheus 에서는 `target_info` 에 있다.
- **compose.** 메트릭을 미는 서비스는 `x-telemetry-environment` 를 environment 에 더하고, `networks: [default, telemetry]` 를 적는다. 주소는 루트 `.env` 의 `OTEL_EXPORTER_OTLP_ENDPOINT` 에서 온다. 프로필 observability 를 켤 때만 적는다.
- **CI.** `.github/scripts/stack-smoke.sh` 의 `METRIC_SERVERS` 에 서버를 더하면 그 서버의 요청 수, 요청 시간, `db_up`, 연결 풀이 Prometheus 에 있는지 본다.

#### 붙인 것 (결제 서버의 메트릭, 본보기)

다른 서버가 따라 할 모양이다. 언어가 달라도 자리와 이름, 테스트하는 법이 같다.

| 파일 | 하는 일 |
| --- | --- |
| `internal/metrics/metrics.go` | MeterProvider 를 만든다. 주소가 비면 noop, 있으면 OTLP(HTTP, protobuf) + 15초 간격. 출처, 구간(`DurationBuckets`), 끌 때 한 번 보내기(`Shutdown`, 5초 안) |
| `internal/metrics/metricstest/` | 테스트가 계측한 값을 이름과 label 로 읽는다(ManualReader) |
| `internal/config/config.go` 의 `LoadMetrics` | `OTEL_EXPORTER_OTLP_ENDPOINT`(경로 없이), `OTEL_METRIC_EXPORT_INTERVAL`(밀리초, 1000 이상) |
| `internal/httpapi/metrics.go` | HTTP 셋(맨 앞의 미들웨어)과 `db_up`(준비 상태 확인). 메서드는 정한 것만, 그 밖은 `_OTHER` |
| `internal/database/metrics.go` | `NewMeteredPool`: 연결 수(Stat 을 읽는 관측 gauge)와 연결을 기다린 시간(pgxpool 의 AcquireTracer) |
| `internal/jobs/metrics.go` | 작업 넷. 로그처럼 프로세스에 하나를 둔다(`jobs.Measure`) |
| `internal/txn/txn.go` | 커밋한 뒤에 할 일을 실어 나르는 트랜잭션(`txn.Run`, `txn.AfterCommit`). 원장의 메트릭이 쓴다 |
| `internal/wallet/metrics.go`, `internal/order/metrics.go`, `internal/payment/metrics.go`, `internal/hold/metrics.go`, `internal/metrics/idempotency.go` | 업무 메트릭. 서비스마다 `Measure(meter)` 로 켠다(`app.MeasureServices`). 결제 대행사는 감싸서 센다(`payment.Measured`) |
| `cmd/server`, `cmd/sweeper`, `cmd/reconcile` | 메트릭을 켜고(`app.StartMetrics`) 끌 때 보낸다(`app.CloseMetrics`). 사람이 치는 명령은 켜지 않는다 |

- **전역(otel.SetMeterProvider)에 두지 않는다.** 만든 쪽이 Meter 를 넘긴다. 테스트가 라우터마다 제 Meter 를 넣는다. 작업만 프로세스에 하나다(로그의 기본 로거와 같다).
- **메트릭 때문에 서버가 뜨지 못하지 않는다.** 계측기를 만들지 못하면 까닭을 남기고 세지 않는다. 수집기가 죽어 있어도 뜬다.
- **트랜잭션 안의 일은 커밋한 뒤에 센다.** 결제 서버는 `internal/txn` 의 `txn.Run` 으로 트랜잭션을 열고, 안의 코드는 셀 것을 트랜잭션의 바구니에 담는다(`txn.AfterCommit`). 연 쪽이 커밋했으면 담긴 일을 `success` 로, 되돌렸으면 `failure` 로 센다. 바구니는 context 가 아니라 트랜잭션에 붙어 다닌다. 다른 서버도 트랜잭션 안의 일을 셀 때 같은 모양을 쓴다(바로 세면 되돌린 것까지 센다).

#### 붙인 것 (알림 서버의 메트릭, Python 의 본보기)

TRPG 서버와 인증 서버가 따라 할 모양이다. 이름, 단위, label, 구간은 [결제 서버](#붙인-것-결제-서버의-메트릭-본보기)와 같다.
새 의존성은 없다. 추적과 같은 `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http` 를 쓴다.
2026-10-21 부터 이 파일들은 공용 코드 `shared/server-core` 에 있고 알림 서버와 asset 서버가 함께 쓴다(#588, [공용 코드 규칙](architecture/shared-code.md#서버의-공통부-sharedserver-core)).
서버만의 계측기는 공용 코드가 열어 둔 자리(`InstrumentSet`)에 서버가 더한다(알림 서버의 `app/notifications/metrics.py`).

| 파일 | 하는 일 |
| --- | --- |
| `shared/server-core/src/server_core/observability/metrics.py` | 계측기 한 묶음(`Instruments`)과 MeterProvider. 주소가 있으면 OTLP(HTTP, protobuf, `/v1/metrics`) + `OTEL_METRIC_EXPORT_INTERVAL`(15초) 간격으로 민다. 끌 때 한 번 보낸다(`shutdown_metrics`, 5초 안). 구간은 `DURATION_BUCKETS`(계측기의 advisory) |
| `shared/server-core/src/server_core/observability/request_metrics.py` | HTTP 셋의 ASGI 미들웨어. 맨 바깥이다(span 과 로그를 거는 시간까지 잰다). 메서드는 정한 것만, 그 밖은 `_OTHER`. 서버가 넘긴 스트림(`streams.py`)은 끝난 수에만 든다 |
| `shared/server-core/src/server_core/observability/pool_metrics.py` | 연결을 기다린 시간을 재는 풀(`MeteredPool`)과 풀의 지금 값(`pool_stats`) |
| `app/api/readiness.py` | `db_up` |
| `app/notifications/retention.py` | 정리 작업의 한 바퀴를 `measured_job` 으로 감싼다 |
| `app/notifications/metrics.py`, `app/notifications/router.py` | 넣은 알림(`notifications_received_total`). 계측기는 공용 코드의 `InstrumentSet` 에 더한다 |
| `server_core/testing/metrics.py`, `server_core/testing/collector.py` | 메모리에 모으는 것(InMemoryMetricReader)과, span 과 메트릭을 함께 받는 가짜 수집기. 서버들의 테스트가 함께 쓴다 |

- **OpenTelemetry 의 전역에 두지 않는다.** 추적과 같은 까닭이다. 바꿔 끼우면(`use_meter_provider`) 계측기를 그것으로 다시 만든다. 세는 곳은 `instruments()` 나 `record_*` 로 그때의 것을 꺼낸다.
- **span 과 메트릭이 한 출처다.** 앱이 뜰 때 출처를 한 번 만들어 둘에 준다(`app/main.py`). 같은 프로세스의 span 과 메트릭이 같은 `service.instance.id` 다.
- **SQLAlchemy 의 풀에는 "꺼내기 시작"의 이벤트가 없다.** 그래서 풀의 꺼내는 자리(`_do_get`)를 감싼 풀을 쓴다. 안쪽 이름이라 SQLAlchemy 의 판이 바뀌면 깨질 수 있어 테스트가 지킨다. 풀의 크기는 설정(`DB_POOL_SIZE` + `DB_MAX_OVERFLOW`, 기본 5 + 10)이고 그 합을 `db_pool_connections_max` 로 낸다. 서버마다의 값은 compose 가 준다([DB 와 Redis 의 한도](architecture/services.md#db-와-redis-의-한도)).
- **연결 풀의 값은 수집할 때 읽는다**(observable gauge). 앱이 뜰 때 풀 하나를 건다(`watch_pool`).
- **트랜잭션 안의 일은 커밋한 뒤에 센다.** 알림 넣기는 커밋한 뒤에 센다. 결제 서버의 규칙과 같다.
- **FastAPI 가 스스로 내는 메트릭은 끈다**(추적과 같은 `FASTAPI_TELEMETRY`). 테스트가 가짜 수집기로 우리가 만든 메트릭만 가는 것을 본다.
- **CI.** `METRIC_SERVERS` 에 notification 을 더했다. 정리 작업의 메트릭(`notification.prune`)과, 게시판 서버가 넣은 알림(`source="board", outcome="created"`)이 Prometheus 에 있는지도 본다.

#### 붙인 것 (TRPG 서버의 메트릭)

> #589 로 요청, DB, 작업, SSE 의 계측기와 보내는 길은 `shared/server-core` 의 것을 쓴다. 게임 서버에는 그만의 계측기(AI 호출, 서술, 라운드, 결제 서버)를 `InstrumentSet` 으로 더하는 `app/observability/metrics.py` 만 남았다. 아래는 붙일 때의 기록이다.

[알림 서버](#붙인-것-알림-서버의-메트릭-python-의-본보기)의 모양을 그대로 가져왔다(`metrics.py`, `request_metrics.py`, `pool_metrics.py`, `tests/metrics.py`, `tests/collector.py`).
그 위에 실시간 스트림, AI 호출, 라운드와 서술, 서술 값을 더했다. 새 의존성은 없다.

| 파일 | 하는 일 |
| --- | --- |
| `app/observability/metrics.py` | 계측기 한 묶음과 MeterProvider. 세는 곳은 `record_*`, `measured_job`, `measured_stream` 을 부른다. 긴 것(AI 호출, 서술)의 구간은 `LONG_DURATION_BUCKETS`, 스트림은 `STREAM_BUCKETS` 다 |
| `app/observability/request_metrics.py` | HTTP 셋. 테이블의 스트림은 끝난 요청의 수에만 든다(`request_spans.is_stream`) |
| `app/api/readiness.py` | `db_up`. DB 와 Redis 를 따로 본다. Redis 만 닿지 않으면 503 이어도 `db_up` 은 1 이다 |
| `app/core/jobs.py` | 맡긴 작업(`round.narrate`, `lore.index`, `memory.index`)을 차례가 온 뒤부터 센다. 기다린 시간은 들지 않는다 |
| `app/rounds/clock.py`, `app/billing/settler.py`, `server_core/notifications/dispatcher.py`, `app/ai_log/retention.py`, `app/tables/retirement_watch.py` | 도는 작업의 한 바퀴를 `measured_job` 으로 감싼다 |
| `app/realtime/router.py` | SSE 셋. 응답을 시작한 뒤부터 끊길 때까지다 |
| `app/ai_log/metered.py` | 호출 기록장(`DbCallLog`)을 감싸 AI 호출 셋을 센다. 기록장에 쓰지 못해도 센다 |
| `app/rounds/retrying_narrator.py` | 같은 모델로 다시 부른 것과 다음 모델로 넘어간 것 |
| `app/rounds/service.py`, `app/rounds/closing.py` | 닫기 시작한 라운드(저장한 뒤)와 끝난 서술 |
| `app/billing/metered.py` | 결제 서버를 부르는 것(`HttpBilling`)을 감싸 센다. 결제 서버를 쓰지 않으면(`FreeBilling`) 감싸지 않는다 |
| `app/billing/repository.py` 의 `count_unfinished` | 끝나지 않은 청구의 수. 청구 정리의 바퀴가 센다 |

- **AI 를 부르는 코드(`shared/ai-core`)는 메트릭을 모른다.** 공용 코드라 경계를 지킨다(`shared/ai-core/tests/test_boundary.py`). 기록장과 결제 서버를 부르는 것을 밖에서 감싸 센다. 그래서 AI 호출의 수는 호출 기록(`ai_invocations`)의 수와 같다.
- **끝나지 않은 청구를 세는 쿼리는 두 부분 색인만 읽는다.** 조건을 색인의 조건 둘(`DUE_STATUSES` 또는 `OPEN_STATUSES`)로 나눠 적어야 PostgreSQL 이 둘을 합쳐 읽는다(BitmapOr). 다섯 상태를 `IN` 하나로 적으면 표 전체를 읽는다. 끝난 청구는 쌓이기만 하므로 5초마다 표 전체를 읽게 둘 수 없다. 테스트가 계획을 본다.
- **서버가 여럿이면 `narration_charges` 를 모두 같은 수로 낸다.** 대시보드와 경보는 `max` 로 본다. 더하면(`sum`) 서버의 수만큼 부풀려진다.
- **라운드는 커밋한 뒤에 센다.** 결제 서버의 규칙과 같다. 서술은 작업 안에서 끝난 모양(마무리, 실패를 적음)으로 센다.
- **CI.** `METRIC_SERVERS` 에 trpg 를 더했다. 청구 정리의 작업 메트릭(`charge.settle`)과 끝나지 않은 청구(`narration_charges`, 청구가 없어 0)가 Prometheus 에 있는지도 본다. 서술과 AI 호출은 CI 에 모델이 없어 값이 생기지 않는다(대시보드의 쿼리는 오류 없이 도는지만 본다).

#### 붙인 것 (인증 서버의 메트릭)

[알림 서버](#붙인-것-알림-서버의-메트릭-python-의-본보기)와 같은 모양을 Django 에 맞춰 옮겼다. 새 의존성은 없다.

| 파일 | 하는 일 |
| --- | --- |
| `observability/metrics.py` | 계측기 한 묶음과 MeterProvider. 간격은 `OTEL_METRIC_EXPORT_INTERVAL`(설정 파일이 1000 이상을 지킨다). 프로세스가 끝날 때 남은 것을 한 번 보낸다(SDK 의 `shutdown_on_exit`) |
| `observability/request_metrics.py` | HTTP 셋. `MIDDLEWARE` 의 맨 앞이다(span 보다 앞) |
| `observability/apps.py` | 프로세스가 뜰 때 span 과 메트릭을 한 출처로 켠다(`start_telemetry`). 테스트에서는 켜지 않는다 |
| `observability/jobs.py` | `run_as_job` 이 작업의 메트릭도 센다. 워커의 바퀴와 예약 명령 한 번이 작업 하나다 |
| `config/health.py` | `db_up` |
| `accounts/outbox.py` | 보내 본 결과(`emails_sent_total`)와 발송함에 남은 메일의 수(`count_waiting_mail`) |
| `accounts/management/commands/send_outgoing_mail.py` | 바퀴마다 남은 메일을 `background_jobs_queued{operation="mail.deliver_outgoing"}` 로 적는다 |
| `accounts/management/commands/send_welcome_credits.py`, `accounts/withdrawal.py` | 바퀴마다 밀린 탈퇴(`count_overdue_withdrawals`)와 알리지 못한 탈퇴(`count_waiting_notices`)를 `background_jobs_queued{operation="withdrawal.complete"}`, `{operation="withdrawal.deliver"}` 로 적는다 |
| `accounts/attempt_limits.py` | 막은 시도와 세지 못하고 통과시킨 시도 |
| `accounts/models.py` 의 `MailKind`, 마이그레이션 `0020` | 발송함의 줄에 메일의 종류를 적는다. 이미 있던 줄은 `other` 다 |

- **프로세스마다 출처가 다르다.** `service.instance.id` 의 앞부분이 프로세스다(`server-…`, `send_outgoing_mail-…`, `send_welcome_credits-…`, 예약 명령은 `send_security_digest-…`, `delete_unverified_users-…`). gunicorn 의 워커도 저마다 다르다.
- **예약 명령은 끝날 때 한 번 민다.** 간격(15초)을 기다리기 전에 끝나므로 SDK 가 프로세스가 끝날 때 보낸다. `rate` 로는 값이 나지 않아 대시보드는 `last_over_time` 으로 본다(결제 서버의 대사와 같다).
- **메일의 종류는 발송함에 적는다.** 보내는 것은 워커라 문구를 만든 곳(`accounts/mail.py`)을 모른다. 그래서 줄에 칸 하나를 더했다. 종류를 더하면 `MailKind` 와 위의 표에 함께 더한다.
- **인증 시도는 따로 세지 않는다.** 주소와 상태 코드로 같은 것을 본다. 처음 목록의 `auth_attempts_total` 은 빼고 그 대신 Redis 에 묻지 못한 것(`auth_rate_limits_unavailable_total`)을 더했다. 제한이 꺼진 것을 아는 길이 그것뿐이다.
- **CI.** `METRIC_SERVERS` 에 auth 를 더하고, 연결 풀이 없는 서버(`POOLLESS_SERVERS`)는 풀을 보지 않는다. 메일 워커의 작업 메트릭과 남은 메일, 예약 명령(`account.delete_unverified`)이 끝날 때 민 것도 본다.

#### 붙인 것 (게시판 서버의 메트릭)

알림 서버의 모양을 Node 로 옮겼다. 새 의존성은 `@opentelemetry/sdk-metrics`, `@opentelemetry/exporter-metrics-otlp-proto`(추적과 같은 판)다.

| 파일 | 하는 일 |
| --- | --- |
| `src/observability/metrics.ts` | 계측기 한 묶음과 MeterProvider. 간격은 `OTEL_METRIC_EXPORT_INTERVAL`(1000 이상). 앱이 닫힐 때 한 번 보낸다(`shutdownMetrics`) |
| `src/observability/request-metrics.middleware.ts` | HTTP 셋. 미들웨어의 맨 앞이다. 응답이 닫힐 때(close) 센다 |
| `src/observability/pool-metrics.ts`, `src/database/pool-watch.ts` | 연결을 기다린 시간을 재는 pg 의 풀(`MeteredPool`)과 앱이 뜬 뒤 풀을 거는 것 |
| `src/health/readiness.controller.ts` | `db_up` |
| `src/observability/jobs.ts` | `runAsJob` 이 작업의 메트릭도 센다 |
| `src/observability/counted.interceptor.ts` | 글과 댓글을 쓴 것, 신고한 것. 컨트롤러의 핸들러에 붙인다(`countWrite`, `countReport`) |
| `src/posts/posts-search.service.ts` | 검색의 결과와 걸린 시간 |

- **쓰기의 결과는 핸들러가 끝난 모양으로 정한다.** 인터셉터는 본문을 보는 파이프까지 감싸므로 모양이 틀린 쓰기(400)도 `rejected` 다. 5xx 는 세지 않는다. 로그인하지 않은 쓰기(401)는 가드에서 끝나 세지 않는다.
- **TypeORM 에는 Pool 만 바꾼 pg 를 넘긴다**(`driver: meteredPg()`). pg 를 펼쳐 복사하지 않고 물려받는다. 펼치면 pg-native 를 불러오는 getter 를 읽는다.
- **풀은 TypeORM 의 안쪽 이름(`driver.master`)으로 찾는다.** 사라지면 풀의 메트릭만 빠지고 앱은 뜬다. 앱의 테스트가 풀이 걸렸는지 본다.
- **JS SDK 는 보내는 간격보다 답을 오래 기다리지 못한다.** 간격을 5초보다 짧게 적으면 답을 기다리는 시간도 간격만큼으로 줄인다. 그러지 않으면 SDK 가 예외를 내 서버가 뜨지 못한다.
- **CI.** `METRIC_SERVERS` 에 board 를 더하고, 알림 보내기의 작업 메트릭(`notification.send`)을 본다.

### 3. 추적 — 식별자를 다루는 코드를 SDK 로 바꾼다

지금의 코드는 `traceparent` 를 직접 읽고 쓴다. SDK 를 붙이면 그 일을 SDK 의 propagator 가 한다. 바꿀 곳은 서버마다 셋이다.

| | 받는 곳(미들웨어) | 들고 있는 곳 | 보내는 곳 |
| --- | --- | --- | --- |
| auth-server | `observability/middleware.py` | `observability/context.py` | `accounts/billing_client.py` 의 `outgoing_headers()` |
| trpg-server | `app/observability/middleware.py` | `server_core/observability/context.py` | `server_core/auth/jwks.py`, `server_core/auth/revocations.py`, `app/billing/http_billing.py` 의 `outgoing_headers()` |
| board-server | `src/observability/request-logging.middleware.ts` | `src/observability/request-context.ts` | `src/auth/jwks.ts` 의 `outgoingHeaders()` |
| billing-server | `internal/httpapi/observability.go` | `internal/obs/context.go` | `internal/jwks/fetch.go` 의 `obs.SetOutgoingHeaders()` |
| notification-server, asset-server | `server_core/observability/middleware.py` | `server_core/observability/context.py` | `server_core/auth/jwks.py`, `server_core/auth/revocations.py` 의 `outgoing_headers()` |

"들고 있는 곳"이 로그에 `trace_id` 를 넘긴다. SDK 를 붙이면 여기서 지금의 span 에서 trace id 를 읽게만 바꾸면 로그의 모양은 그대로다.
`request_id` 와 `job_id` 는 OpenTelemetry 에 없는 개념이라 지금의 코드가 그대로 남는다. span 의 속성으로도 싣는다.

```
서버, 워커, cron ─(OTLP, HTTP 4318, 메트릭과 같은 길)─▶ Alloy ─(OTLP gRPC 4317)─▶ Tempo ─▶ Grafana ◀─▶ Loki(trace_id)
```

#### 정한 것 (2026-10-19)

| 항목 | 정한 것 | 까닭 |
| --- | --- | --- |
| 저장소 | **Tempo 3.1, 한 프로세스**(`-target=all`), 로컬 디스크(볼륨 `tempodata`), 보관 **14일** | 로그, 메트릭과 기간이 같아야 같은 시각을 함께 본다. Tempo 3 은 여럿으로 나누면 Kafka 가 들지만 한 프로세스는 들지 않는다. S3 가 필요해지면 `storage.trace.backend` 만 바꾼다 |
| 보내는 길 | 메트릭과 같다. **서버 → Alloy(OTLP HTTP 4318) → Tempo(OTLP gRPC 4317)**. 서버의 설정은 이미 있는 `OTEL_EXPORTER_OTLP_ENDPOINT` 하나다 | 서버가 Tempo 로 바로 보내면 저장소를 바꿀 때 서버마다 고친다. 서버는 telemetry 망에서 Alloy 에만 닿는다(Tempo 에 닿지 않는다) |
| 표본 | **모두 남긴다** | 지금의 요청 수로는 넉넉하다. 많아지면 Alloy 에서 꼬리 표본(오류와 느린 것만 남기기, `otelcol.processor.tail_sampling`)을 더한다. 서버에서 비율로 줄이면 오류가 난 요청을 놓친다 |
| 로그와 잇기 | 로그의 `trace_id`(Loki 의 줄의 값)와 span 의 trace id 가 같다. Grafana 에서 추적 → 로그(`tracesToLogsV2`), 로그 → 추적(`derivedFields`)으로 건너간다 | 한 건을 파고들 때 그래프(메트릭) → 추적 → 로그로 이어 간다([역할](#로그-메트릭-추적의-역할)) |
| span 에서 만드는 메트릭 | 만들지 않는다(Tempo 의 metrics-generator 를 끈다) | 요청 수와 시간은 서버가 이미 메트릭으로 낸다. 같은 수를 두 곳에서 세지 않는다 |

| 고르지 않은 것 | 까닭 |
| --- | --- |
| Jaeger | 화면이 따로 있어 Grafana 의 로그·메트릭과 오가기 어렵다. 저장소(Elasticsearch, Cassandra)가 따로 든다 |
| Tempo 2.x | 3.0 이 나온 뒤라 옮겨야 할 일만 남는다. 한 프로세스로 띄우는 법은 같다 |
| Grafana Cloud | 요청의 경로(서버 이름, 주소의 틀)가 바깥으로 나가고 계정에 묶인다 |

#### 붙인 것 (추적의 인프라)

| 파일 | 하는 일 |
| --- | --- |
| `docker-compose.yml` 의 `tempo` | `grafana/tempo:3.1.0`. 셸이 없는 이미지라 상태 확인은 `/tempo -health` 다. 사용자 10001 로 돈다. 포트를 열지 않는다 |
| `docker/tempo/config.yaml` | 받기는 OTLP gRPC 4317 하나, 저장은 로컬, 보관 14일(`backend_scheduler`, `backend_worker` 의 `block_retention: 336h`), 사용 통계를 보내지 않는다 |
| `docker/alloy/traces.alloy` | 메트릭과 같은 OTLP 받기(`metrics.alloy` 의 `otelcol.receiver.otlp.servers`)에서 traces 를 받아 묶고 Tempo 로 보낸다. Tempo 의 메트릭(`job="tempo"`)도 긁는다 |
| `docker/grafana/provisioning/datasources/tempo.yaml` | 데이터 소스 uid `tempo`. 추적에서 그 trace_id 의 로그로(`{service=~".+"} \| trace_id="…"`), 메트릭으로 건너간다 |
| `docker/grafana/provisioning/datasources/loki.yaml` 의 `derivedFields` | 로그의 `trace_id` 를 "추적 보기" 링크로 바꾼다 |
| `docker/prometheus/rules/ai-trpg.yml` | `ObservabilityComponentDown` 이 tempo 도 본다 |

- **CI 가 보는 것.** Tempo 가 healthy 이고 root 가 아니며 다시 뜨지 않는다. Grafana 가 Tempo 에 닿는다. telemetry 망에서 OTLP(JSON)로 민 시험 span(`stack_smoke.probe`)이 Alloy 를 거쳐 Tempo 에서 그 추적 번호로 찾아진다. `up{job="tempo"}` 이 1 이다. 결제 서버가 Tempo 에 닿지 않는다.
- **일곱 서버가 모두 span 을 내보낸다.** 서버끼리 부른 추적은 끊기지 않고 한 그림이다(게시판 서버의 알림 보내기 → 알림 서버의 요청).

#### 붙인 것 (결제 서버의 추적, 본보기)

다른 서버가 따라 할 모양이다. 언어가 달라도 span 의 이름, 싣는 것과 싣지 않는 것, 테스트하는 법이 같다.

| 파일 | 하는 일 |
| --- | --- |
| `internal/tracing/tracing.go` | TracerProvider 를 만든다. 주소가 비면 noop, 있으면 OTLP(HTTP, protobuf, `/v1/traces`) + 묶어 보내기. 출처는 메트릭과 같다(`service.instance.id` 까지). 끌 때 남은 것을 보낸다(`Shutdown`, 5초 안). 표본은 `Sampler`(모두 남긴다) |
| `internal/tracing/transport.go` | 다른 곳을 부르는 `http.Client` 의 Transport. 부모 span 이 있을 때만 client span 을 건다. 우리 서버면 traceparent 를 그 span 으로 붙인다 |
| `internal/tracing/tracingtest/` | 테스트가 남긴 span 을 메모리에서 읽는다(SpanRecorder). 전역을 바꾸므로 그 테스트는 `t.Parallel` 을 쓰지 않는다 |
| `internal/httpapi/tracing.go` | 서버 span. 미들웨어의 맨 앞이다. 받은 traceparent 가 맞으면 그 아래에 붙는다. 상태 확인은 걸지 않는다 |
| `internal/obs/span.go` | 받은 traceparent 를 span 의 부모로 바꾸고(받는 규칙은 지금과 같다), span 에서 로그의 `trace_id` 를 읽는다 |
| `internal/database/tracing.go` | 쿼리마다 span(pgx 의 QueryTracer). 연결을 기다린 시간을 재는 것(AcquireTracer)과 한 tracer 로 묶는다 |
| `internal/jobs/jobs.go` | 작업 한 번이 span 하나다(`jobs.Run`). 새 추적으로 시작한다 |
| `cmd/server`, `cmd/sweeper`, `cmd/reconcile` | 추적을 켜고(`app.StartTracing`) 끌 때 보낸다(`app.CloseTracing`). 사람이 치는 명령은 켜지 않는다 |

| span | 이름 | 싣는 것 | 오류로 표시하는 것 |
| --- | --- | --- | --- |
| 요청(server) | `GET /api/v1/billing/orders/:id`(메서드와 주소의 틀, 맞은 것이 없으면 `(unmatched)`) | `http.request.method`, `http.route`, `http.response.status_code`, `request_id` | 5xx |
| 다른 곳을 부르는 것(client) | `HTTP POST` | `http.request.method`, `server.address`(호스트 이름), `http.response.status_code` | 닿지 못한 것, 5xx |
| 쿼리(client) | `db GetWallet`(sqlc 가 붙인 이름, 손으로 쓴 것은 `db query`) | `db.system.name=postgresql`, `db.operation.name` | 실패. 설명은 SQLSTATE(`23505`)만 |
| 작업(internal) | `operation`(`sweep.run`, `reconcile.run`) | `result`, `job_id` | `server_error`. 설명은 `job.failed` |

- **로그와 같은 번호.** span 이 있으면 로그의 `trace_id` 가 그 span 의 trace id 다(요청은 `requestLogging`, 작업은 `obs.WithJob`). span 이 없으면(PC, 상태 확인) 지금처럼 정한다. 그래서 주소를 비워도 로그는 그대로다.
- **전역(otel.SetTracerProvider)에 둔다.** 메트릭과 다르다. span 은 요청, 호출, 쿼리, 작업에 두루 걸려 그 모든 곳에 Tracer 를 넘기면 함수마다 인자가 는다. 계측하는 곳은 `tracing.Tracer()` 로 가져다 쓴다.
- **부른 쪽의 "기록하지 않음"을 따르지 않는다.** 보낼 곳을 비운 서버는 flags `00` 을 보낸다. 따르면 그 서버가 부른 요청의 span 이 다 버려진다. 일곱 서버가 모두 span 을 내보내게 되었으니, 표본을 줄일 때(꼬리 표본) 따를지 함께 정한다.
- **부모 없는 것은 남기지 않는다.** 요청이나 작업 밖의 쿼리(풀이 연결을 확인하는 것)와 호출(끊긴 세션의 목록을 30초마다 받는 것)은 저마다 새 추적이 되어 Tempo 를 메운다.
- **작업은 새 추적이다.** 정리 작업은 30초마다 돈다. 프로세스의 한 추적 아래에 두면 끝없이 길어진다.
- **싣지 않는 것.** 주소의 경로와 뒤의 값(결제 대행사의 주소에는 결제 번호가 있다), 머리말, 본문, SQL 의 문장과 값, 오류의 글. [민감정보](#민감정보)의 규칙과 같다. 테스트가 이것을 본다.
- **결제 대행사에는 traceparent 를 보내지 않는다.** span 은 건다(대행사의 답을 기다린 시간을 본다).
- **새 의존성은 `otlptracehttp` 하나다.** gin, net/http, pgx 의 계측 패키지(otelgin, otelhttp, otelpgx)는 쓰지 않았다. 이름과 속성을 우리가 정해야 하고(경로, 문장을 싣지 않는다), 셋 다 합쳐도 짧다.
- **CI 가 보는 것.** 서버의 테스트가 이름, 부모, 싣는 것과 싣지 않는 것, 오류 표시를 본다(쿼리는 실제 DB 로). 스택의 확인(`stack-smoke.sh` 의 `check_server_spans`)이 `TRACE_SERVERS` 의 서버마다 flags `00` 의 traceparent 로 부른 요청의 span 이 그 추적에 들어오는지, 그 줄의 `trace_id` 가 같은지, 정리 작업의 span 아래에 쿼리의 span 이 있는지, 서버가 Tempo 에 닿지 않는지 본다. 서버에 span 을 붙이면 `TRACE_SERVERS`, `TRACE_PROBES`, `TRACE_JOBS` 에 더한다.

#### 붙인 것 (알림 서버의 추적, Python 의 본보기)

게임 서버와 인증 서버가 따라 할 모양이다. span 의 이름과 싣는 것, 싣지 않는 것은 [결제 서버](#붙인-것-결제-서버의-추적-본보기)와 같다.
의존성은 `opentelemetry-sdk` 와 `opentelemetry-exporter-otlp-proto-http` 둘이다. 계측 패키지(opentelemetry-instrumentation-fastapi, -httpx, -sqlalchemy)는 쓰지 않았다. 결제 서버와 까닭이 같다.
2026-10-21 부터 이 파일들은 공용 코드 `shared/server-core/src/server_core/observability/` 에 있고 알림 서버와 asset 서버가 함께 쓴다(#588).
그때 게임 서버의 것에 있던 것(할 일 없던 바퀴 버리기, 스트림인 주소, 부르는 쪽이 붙인 traceparent 만 잇기, 걸린 span 아래의 작업)을 함께 올렸다.

| 파일(`server_core/observability/`) | 하는 일 |
| --- | --- |
| `spans.py` | OpenTelemetry 의 API 만 쓴다. span 을 만드는 것을 하나 둔다(`use_provider`, `tracer`). 받은 traceparent 를 부모로(`remote_parent`, 받는 규칙은 `identifiers.traceparent_parts`), span 에서 로그의 추적과 보낼 traceparent 를 읽는다. 작업 한 바퀴의 span(`job_span`) |
| `tracing.py` | SDK. 주소가 있으면 TracerProvider(OTLP HTTP `/v1/traces`, 묶어 보내기, 모두 남기기 `SAMPLER`)를 만들어 끼운다(`configure_tracing`). 끌 때 보낸다(`shutdown_tracing`, 5초) |
| `request_spans.py` | 서버 span 의 ASGI 미들웨어. 맨 바깥에 둔다. 경로의 틀은 처리가 끝난 뒤에 알아 이름을 끝에 고친다 |
| `http_spans.py` | httpx 의 transport(`TracingTransport`). 부모가 있을 때만 client span, 우리 서버면 traceparent 를 그 span 으로 |
| `db_spans.py` | SQLAlchemy 의 엔진 이벤트(`before_cursor_execute`, `after_cursor_execute`, `handle_error`). 이름은 `db SELECT notifications` |
| `context.py`, `middleware.py` | 로그의 `trace_id` 와 보내는 traceparent 가 span 을 먼저 본다. 요청의 span 에 `request_id` 를 싣는다 |

- **OpenTelemetry 의 전역에 두지 않는다.** `trace.set_tracer_provider` 는 프로세스에 한 번만 바꿀 수 있어 테스트가 바꿔 끼우지 못한다. `spans.py` 에 하나 두고 서버가 뜰 때와 테스트가 바꾼다. 지금의 span 을 읽는 것(`trace.get_current_span`)은 contextvars 라 그대로 쓴다.
- **SQLAlchemy 의 비동기에서도 지금의 span 이 보인다.** 안에서 greenlet 으로 갈아타도 contextvars 가 따라간다. 테스트가 실제 DB 로 부모를 본다.
- **보내는 traceparent 의 flags 는 `03` 일 수 있다.** Python SDK 는 "기록함"(01)에 "무작위 번호"(02, W3C Trace Context 2)를 더한다. 일곱 서버가 받는 규칙(`[0-9a-f]{2}`)에 맞는다.
- **FastAPI 가 스스로 하는 관측은 끈다**(`FastAPI(telemetry=FASTAPI_TELEMETRY)`, `tracing.py`). FastAPI 는 `OTEL_EXPORTER_OTLP_ENDPOINT` 가 있고 SDK 가 깔려 있으면 OpenTelemetry 의 전역을 스스로 채워 span, 메트릭, 로그를 그 주소로 민다(0.142 는 기본으로 켜져 있고 0.143 부터는 `FASTAPI_OTEL_AUTO_CONFIGURE=true` 일 때). 그 span 은 정한 이름과 싣는 것을 따르지 않고, 메트릭은 정하지 않은 이름으로, 로그는 Loki 의 것과 겹쳐 나간다. 테스트가 가짜 수집기로 `/v1/traces` 말고는 오지 않는 것을 본다.
- **보내기는 따로 도는 스레드다**(BatchSpanProcessor). 끌 때 남은 것을 보내는 일(`provider.shutdown`)은 막히므로 lifespan 에서 `asyncio.to_thread` 로 부른다.
- **compose.** `notification-server` 가 `x-telemetry-environment` 와 망 `telemetry` 를 붙였다. 메트릭은 아직 없다.

#### 붙인 것 (TRPG 서버의 추적)

> #589 로 추적의 코드는 모두 `shared/server-core` 의 `server_core/observability/` 를 쓴다. 테이블의 스트림은 `app/main.py` 의 `TABLE_STREAMS` 로 넘긴다. 아래는 붙일 때의 기록이다.

알림 서버의 것(`app/observability/` 의 `spans.py`, `tracing.py`, `request_spans.py`, `http_spans.py`, `db_spans.py`)을 옮겼다. 다른 것은 셋이다.

- **traceparent 는 부르는 쪽이 붙였을 때만 그 span 으로 바꾼다.** 이 서버는 한 클라이언트로 우리 서버(인증, 결제, 알림)와 바깥(AI 모델의 창구)을 함께 부른다. 우리 서버를 부르는 곳은 이미 `outgoing_headers()` 를 붙인다(`server_core/auth/`, `app/billing/`, `app/notifications/`). transport 는 그 머리말이 있을 때만 client span 의 것으로 바꾸고, 없으면(AI 모델의 창구) 붙이지 않는다. 어디가 우리 서버인지는 부르는 쪽이 안다. client span 은 둘 다 건다(모델의 답을 기다린 시간을 본다).
- **작업의 span 은 걸린 span 아래에 놓인다**(`job_span`). 요청이 맡긴 서술(`round.narrate`)은 그 요청의 추적에, 시계의 한 바퀴(`round.close_overdue`)가 맡긴 서술은 그 바퀴의 추적에 이어진다. 로그의 `trace_id` 도 같은 것을 이어 쓴다(`job_scope`). 서버가 뜰 때 시작한 정리 작업의 바퀴(`round.close_overdue`, `charge.settle`, `notification.send`, `ai_log.prune`, `model.retirement`)에는 걸린 span 이 없어 바퀴마다 새 추적이다. 알림 서버의 정리 작업도 같은 결과다(부모가 없다).
- **테이블의 스트림(`/api/v1/game/tables/{table_id}/stream`)은 span 을 걸지 않는다.** 응답이 몇 시간씩 끝나지 않고, 그동안 새 이벤트마다 도는 쿼리가 한 span 아래에 쌓인다. 상태 확인처럼 실제 경로로 가른다(`request_spans.STREAM_PATH`). 스트림 안의 쿼리는 부모가 없어 span 이 없다.

- **`ai_core` 는 span 의 코드를 가져오지 않는다**(`shared/ai-core/tests/test_boundary.py`). 모델을 부르는 것은 밖에서 넘긴 클라이언트(`app.state.http_client`)로 부르므로 transport 가 client span 을 건다.
- **5초마다 도는 바퀴가 셋이다**(시계, 청구 정리, 알림 보내기). 할 일이 없던 바퀴의 추적은 보내지 않는다. 그대로 두면 하루에 추적이 오만 개를 넘는다.
  인증 서버와 같은 `DropIdleRounds`(`app/observability/idle_rounds.py`)다. 바퀴는 찾아낸 것의 수를 더하고(`spans.add_handled`), `job_span` 이 그 합을 `handled` 로 싣는다.
  찾아낸 것은 마감이 지난 테이블, 크레딧을 기다리는 테이블, 서술이 사라진 테이블, 돌려줄 것으로 바꾼 청구와 차례가 된 청구, 지운 알림과 보낼 알림이다.
  하다가 실패한 것도 찾아낸 것에 들어 그 추적은 남는다(실패의 로그에서 "추적 보기"가 빈 곳으로 가지 않는다). 바퀴가 통째로 실패하면 0 이어도 남는다.
  `add_handled` 를 부르지 않는 작업(서술 하나, 한 시간마다 도는 AI 호출 기록의 정리와 모델의 은퇴 지켜보기)은 `handled` 가 없어 늘 남는다.
  바퀴가 맡긴 서술(`round.narrate`)은 바퀴가 끝난 뒤에 끝난다. 그 추적은 바퀴가 끝날 때 이미 넘겼으므로 바로 넘긴다.
- **CI 의 스택 확인에서 TRPG 서버의 작업은 `ai_log.prune` 이다.** 서버가 뜨면 바로 한 바퀴 돌고 늘 남는다. 시계의 바퀴(`round.close_overdue`)는 할 일이 없어 버려진다.

#### 붙인 것 (인증 서버의 추적)

알림 서버의 것(`spans.py`, `tracing.py`, `request_spans.py`, `http_spans.py`, `db_spans.py`)을 `observability/` 로 옮겼다. 이름, 싣는 것과 싣지 않는 것은 같다. Django 라서 다는 자리가 다르고, 할 일 없는 바퀴를 버리는 것이 더 있다.

| 파일(`observability/`) | 하는 일 |
| --- | --- |
| `apps.py` | 앱(`ObservabilityConfig`)이 뜰 때 연결마다 쿼리 span 을 다는 신호(`connection_created`)를 걸고 추적을 켠다. 프로세스의 이름은 관리 명령이면 그 이름(`send_outgoing_mail`), 아니면 `server` 다. 테스트(`manage.py test`)는 켜지 않는다 |
| `request_spans.py` | 서버 span 의 Django 미들웨어. `MIDDLEWARE` 의 맨 앞(요청 로그의 미들웨어보다 앞)이다. 경로의 틀(`resolver_match`)은 처리가 끝난 뒤에 알아 이름을 끝에 고친다 |
| `db_spans.py` | 연결의 `execute_wrappers`. 이름은 `db SELECT accounts_user`(문장의 FROM, INTO, UPDATE 뒤의 첫 테이블). 실패는 SQLSTATE 만(psycopg 의 오류, Django 가 감싼 것은 `__cause__`) |
| `http_spans.py` | 표준 라이브러리(urllib)로 부르는 곳이 쓰는 `client_span()`. 결제 서버를 부르는 `accounts/billing_client.py` 의 `_post` 가 그 안에서 머리말을 만든다. 그래서 traceparent 가 그 span 을 가리킨다 |
| `idle_rounds.py` | 할 일이 없던 작업의 추적을 버리는 SpanProcessor(`DropIdleRounds`). 묶어 보내기의 앞에 끼운다 |
| `jobs.py` | `run_as_job()` 이 작업의 span(`job_span`)과 로그의 `job_id` 를 함께 건다 |

- **할 일이 없던 워커의 바퀴는 보내지 않는다.** 메일 워커와 환영 크레딧 워커는 1초마다 돈다. 바퀴마다 추적을 남기면 하루에 십만 개를 훌쩍 넘는다. 워커가 처리한 수를 작업의 span 에 싣고(`spans.record_handled`, 속성 `handled`), `DropIdleRounds` 가 그 수가 0 이고 실패하지 않은 추적을 통째로 버린다. 처리한 수는 작업의 span 이 끝나야 알고 그 아래의 쿼리 span 은 먼저 끝난다. 그래서 작업이 부모 없이 시작한 추적의 span 은 작업이 끝날 때까지 들고 있다가 함께 넘기거나 버린다. 요청의 추적은 들지 않는다. 처리한 수를 싣지 않는 작업(주기 명령)은 늘 남는다.
  Alloy 의 꼬리 표본에 맡기지 않은 까닭: "할 일이 있었나"는 서버만 안다(꼬리 표본은 오류와 시간만 본다). TRPG 서버와 게시판 서버의 5초 바퀴도 같은 것을 쓴다.
- **주기 명령은 끝날 때 보낸다.** 명령은 한 번 돌고 끝난다. TracerProvider 가 끝날 때(atexit) 남은 것을 보낸다(5초 안).
- **로그의 `trace_id` 와 보내는 traceparent 가 span 을 먼저 본다**(`context.py`, `middleware.py`). 요청의 span 에 `request_id` 를 싣는다.
- **span 의 부모가 생긴다.** 환영 크레딧의 워커가 부른 결제 서버의 span 이 그 워커의 작업 span 아래에 놓인다. 다른 서버가 공개키(`/api/v1/auth/jwks`)와 끊긴 세션의 목록을 받으러 온 요청도 그 서버의 span 아래에 놓인다.
- **compose.** `auth-server`, `auth-mail`, `auth-welcome-credits`, `auth-cron` 이 `x-telemetry-environment` 와 망 `telemetry` 를 붙였다. 마이그레이션(`auth-migrate`)은 붙이지 않았다(요청도 작업도 없다).
- **CI 의 스택 확인.** `TRACE_SERVERS` 에 auth 를 더했다. 부르는 주소는 `GET /api/v1/auth/jwks`, 작업은 주기 명령의 `security.send_digest` 다(워커와 주기 명령의 검사가 먼저 한 번 돌린다). 워커의 작업은 할 일이 없어 버려지므로 쓰지 않는다.

#### 붙인 것 (게시판 서버의 추적)

Node(Nest)라 SDK 가 다르지만 span 의 이름, 싣는 것과 싣지 않는 것, 테스트하는 법은 [결제 서버](#붙인-것-결제-서버의-추적-본보기)와 같다.
의존성은 `@opentelemetry/api`, `@opentelemetry/sdk-trace`, `@opentelemetry/exporter-trace-otlp-proto`, `@opentelemetry/resources`, `@opentelemetry/context-async-hooks` 다.
자동 계측(`@opentelemetry/auto-instrumentations-node`, instrumentation-express, -pg, -undici)은 쓰지 않았다. 이름과 싣는 것을 우리가 정해야 하고, 자동 계측은 모듈을 불러올 때 고쳐 쓰는(monkey patch) 방식이라 ESM 에서 불러오는 순서를 맞춰야 한다.

| 파일(`src/observability/`) | 하는 일 |
| --- | --- |
| `spans.ts` | API 만 쓴다. span 을 만드는 것을 하나 둔다(`useProvider`, `tracer`). 지금의 span 을 들고 있는 것(AsyncLocalStorage 의 context manager)은 전역에 한 번 건다. 받은 traceparent 를 부모로(`remoteParent`), 작업 한 바퀴의 span(`inJobSpan`) |
| `tracing.ts` | SDK. 주소가 있으면 TracerProvider(OTLP HTTP protobuf `/v1/traces`, 묶어 보내기, 모두 남기기 `SAMPLER`, `DropIdleRounds`)를 만들어 끼운다(`configureTracing`, `main.ts`) |
| `observability.module.ts` | 앱이 닫힐 때 모아 둔 것을 보낸다(`shutdownTracing`). 서버는 SIGTERM 에 앱을 닫는다(`main.ts` 의 `enableShutdownHooks`) |
| `request-spans.middleware.ts` | 서버 span 의 express 미들웨어. 요청 로그의 미들웨어보다 앞이다. 경로의 틀은 처리가 끝난 뒤에 알아 응답이 닫힐 때(`close`) 이름을 고친다 |
| `http-spans.ts` | fetch 를 감싼 `tracedFetch`. 부모가 있을 때만 client span, 부르는 쪽이 traceparent 를 붙였으면 그 span 으로 바꾼다(TRPG 서버와 같은 규칙). 공개키, 끊긴 세션의 목록, 알림 서버를 부르는 곳이 쓴다 |
| `db-spans.ts` | pg 의 `Client` 를 이은 `TracedClient`. TypeORM 의 풀이 이것으로 연결을 맺는다(`database.options.ts` 의 `extra.Client`). 이름은 `db SELECT posts` |
| `jobs.ts`, `idle-rounds.ts` | 알림 보내기의 한 바퀴에 span 과 `job_id` 를 건다(`runAsJob`). 처리한 수가 0 인 바퀴의 추적은 보내지 않는다(인증 서버와 같은 `DropIdleRounds`) |

- **pg 를 통째로 고쳐 쓰지 않는다.** 풀에 연결의 클래스를 넘기는 자리(`pg.Pool` 의 `Client`)를 쓴다. 이 서버의 풀이 맺은 연결에만 걸리고, 콜백이나 스트림으로 부른 것은 그대로 넘긴다.
- **알림 보내기에 `job_id` 가 생겼다.** 전에는 그 바퀴의 줄에 식별자가 없었다. 이제 `job_id` 와 그 span 의 `trace_id` 가 붙는다. 알림 서버를 부를 때 `traceparent` 를 넣어 알림 서버의 span 이 그 아래에 붙는다. 서명은 메서드, 경로, 본문에 하므로 머리말을 더해도 그대로 맞는다.
- **보낼 알림이 없던 바퀴는 보내지 않는다.** 5초마다 돌아 하루에 만칠천 개가 넘는다. 처리한 수(`handled`)에 보낸 것, 다시 보낼 것, 받지 않은 것, 예외, 오래되어 지운 것을 모두 센다.
- **API 주소 아래의 없는 주소도 `(unmatched)` 다.** Nest 는 그 주소를 받으려고 `*path` 라는 틀을 건다. 요청 로그의 `route` 에도 이 틀이 적혀 있었다. 이제 span 과 로그 모두 `(unmatched)` 와 실제 경로(`path`, 로그만)다.
- **compose.** `board-server` 가 `x-telemetry-environment` 와 망 `telemetry` 를 붙였다. 마이그레이션(`board-migrate`)은 붙이지 않았다.
- **CI 의 스택 확인.** `TRACE_SERVERS` 에 board 를 더했다. 부르는 주소는 `GET /api/v1/board/me`(401), 작업은 `notification.send` 다. 보낼 것이 없는 바퀴는 버려지므로 확인 전에 발송함에 알림 하나를 적는다(`queue_board_notification`). 그 알림을 받은 알림 서버의 span 이 게시판 서버의 작업 span 아래에 있는지도 본다.

## 관리 서버의 경계

관리 서버는 아직 없다. 만들 때 무엇을 맡고 무엇을 맡지 않는지를 먼저 정해 둔다.

### 맡을 것

- 관리자의 인증과 권한. 일반 사용자의 토큰으로 들어가지 못한다.
- Grafana 로 들어가는 문. 관리 서버가 운영자인지 확인한 뒤 사용자 이름을 머리말에 실어 Grafana(auth proxy 모드)로 넘긴다. Grafana 는 바깥에서 바로 닿지 못한다.
- 운영 집계의 조회. 저장소(메트릭, 로그, 추적)에 물어서 보여 준다.
- 서버별 장애와 부하의 표시.
- AI 호출의 품질과 비용의 집계. 게임 서버의 AI 호출 기록이 근거다.
- 보안 이벤트의 조회. 인증 서버의 보안 이벤트 기록이 근거다.
- 관리자가 한 조작의 감사 기록. 누가 언제 무엇을 했는지 지울 수 없게 남긴다.
- 이미 집계된 자료를 Gemma 에 넘겨 요약을 받고, 그 결과를 저장한다.

### 맡지 않을 것

- **모든 서버의 로그를 HTTP 로 직접 받는 수집기.** 로그는 수집기(Alloy)가 모은다. 관리 서버가 죽었다고 서버들의 로그가 쌓이거나 사라지면 안 된다.
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

로그와 식별자에는 새 의존성이 없다. 언어마다 표준 기능과 이미 쓰던 것만 썼다. 메트릭과 추적은 OpenTelemetry 의 SDK 를 쓴다(아래 표의 마지막 두 줄).

| | auth-server | trpg-server | board-server | billing-server |
| --- | --- | --- | --- | --- |
| 로거 | 표준 `logging` + JSON formatter | 표준 `logging` + JSON formatter | Nest 의 `LoggerService` 를 구현한 `JsonLogger` | 표준 `log/slog` 의 `Handler` |
| 식별자를 들고 있는 곳 | `contextvars` | `contextvars` | `AsyncLocalStorage` | `context.Context` |
| 요청 미들웨어 | Django 미들웨어(맨 앞) | 순수 ASGI 미들웨어 | express 미들웨어 | gin 미들웨어(맨 앞) |
| 처리하지 못한 예외 | 미들웨어의 `process_exception` | `Exception` 처리기 | 전역 예외 필터 | `recover` 미들웨어 |
| 작업 | `run_as_job()` | `BackgroundJobs.spawn()` | `runAsJob()` | `jobs.Run()` |
| 코드의 자리 | `observability/` | `app/observability/` | `src/observability/` | `internal/obs/`, `internal/httpapi/observability.go` |
| 메트릭 | OpenTelemetry Python SDK(`observability/metrics.py`, [다른 것](#붙인-것-인증-서버의-메트릭)) | OpenTelemetry Python SDK(`app/observability/metrics.py`, [다른 것](#붙인-것-trpg-서버의-메트릭)) | OpenTelemetry JS SDK(`src/observability/metrics.ts`, [다른 것](#붙인-것-게시판-서버의-메트릭)) | OpenTelemetry Go SDK(`internal/metrics/`, [본보기](#붙인-것-결제-서버의-메트릭-본보기)) |
| 추적(span) | OpenTelemetry Python SDK(`observability/`, [다른 것](#붙인-것-인증-서버의-추적)) | OpenTelemetry Python SDK(`app/observability/`, [다른 것](#붙인-것-trpg-서버의-추적)) | OpenTelemetry JS SDK(`src/observability/`, [다른 것](#붙인-것-게시판-서버의-추적)) | OpenTelemetry Go SDK(`internal/tracing/`, [본보기](#붙인-것-결제-서버의-추적-본보기)) |

notification-server 는 trpg-server 의 것(`app/observability/`)을 그대로 가져왔다. 뒤에서 도는 작업이 정리 작업 하나라 `BackgroundJobs` 는 없고, 정리 작업이 바퀴마다 `job_scope` 를 건다.
2026-10-21 에 알림 서버와 asset 서버의 것을 공용 코드 `shared/server-core` 로 옮겼다(#588). 공용 코드가 남긴 줄의 `logger` 는 `server_core.*` 다(예: `server_core.observability.middleware`, 전에는 `app.observability.middleware`). 칸의 모양과 `service` 는 그대로다. 게임 서버는 나중에 옮긴다(#589).
추적(span)과 메트릭은 notification-server 가 먼저 붙였다(OpenTelemetry Python SDK, 본보기는 [추적](#붙인-것-알림-서버의-추적-python-의-본보기)과 [메트릭](#붙인-것-알림-서버의-메트릭-python-의-본보기)).

기존 로그는 고쳐 쓰지 않았다. `logging.getLogger(__name__)`, Nest 의 `new Logger(...)`, Go 의 표준 `log` 로 남기던 줄이 그대로 같은 JSON 으로 나간다.
프레임워크가 스스로 찍던 요청 줄(uvicorn 의 access log, Django 의 `django.server`, gin 의 `Logger`)은 껐다. 주소 뒤의 값까지 찍었고, 요청이 끝난 줄과 겹친다.

## 알려진 빈틈

- **게임 서버의 AI 호출 기록(DB)에 `job_id` 와 `trace_id` 가 없다.** 로그의 서술 작업과 DB 의 호출 기록을 번호로 잇지 못한다. 열을 더하는 마이그레이션이 필요하다.
- **사람이 치는 명령은 JSON 이 아니다.** billing-server 의 `cmd/migrate`, `cmd/fakepg`, `cmd/prices`, `cmd/orders`, `cmd/grants`, auth-server 의 관리 명령이 화면에 찍는 안내(`self.stdout`)는 그대로 글이다.
  `cmd/orders decide` 가 남기는 결정의 기록(`order.decide`)과 `cmd/grants` 의 지급 기록(`grant.event`)은 로그라서 JSON 이다.
  auth-server 의 워커와 예약 명령이 남기는 **로그**는 JSON 이다.
- **로거가 생기기 전의 줄.** board-server 는 설정이 틀려 뜨지 못할 때 Nest 의 기본 모양으로 찍는다. billing-server 는 `DEBUG=true` 면 gin 이 주소 목록을 글로 찍는다.
- **주기 명령을 부르는 supercronic 의 줄.** 실패한 실행만 한 줄 남긴다(`-quiet`). JSON 이지만 칸이 공통 규격과 다르다(`level`, `msg`, `time`, `job.command`).
  명령 자신이 남기는 로그는 규격의 JSON 이다. 명령이 끝에 화면에 찍는 요약(`self.stdout`, 결제의 `cmd/reconcile`)은 위의 "사람이 치는 명령"처럼 글이다.
- **nginx 가 뜨고 꺼지는 줄.** 프록시의 요청 줄은 JSON 이지만, nginx 가 뜰 때와 설정을 다시 읽을 때 남기는 줄은 nginx 의 글 모양이다.
- **마지막 방어선은 어림이다.** [민감정보](#마지막-방어선)의 끝에 적은 대로다.
- **바깥 감시를 적지 않으면 경보를 보내는 쪽이 죽은 것을 알리지 못한다.** Prometheus 나 Alertmanager, VM 이 통째로 죽으면 알릴 곳이 없다. 루트 `.env` 의 `ALERT_HEARTBEAT_WEBHOOK_URL` 을 적으면 바깥 감시가 알린다([경보](#경보)). 모든 받는 곳이 한꺼번에 막힌 것(`AlertDeliveryFailing` 도 갈 곳이 없다)도 바깥 감시는 알지 못한다
- **주기 명령과 게임 서버 안의 작업에 상태 신호가 없다.** 계속 도는 워커 셋만 심장박동이 있다. DB 의 백업, 인증서, 바깥 백업은 결과의 날짜로 본다([워커의 상태](#워커의-상태)). 컨테이너의 `unhealthy` 를 경보로 잇는 일은 아직 없다(#25)
- **끝나고 바로 사라지는 컨테이너의 로그는 모이지 않을 수 있다.** Alloy 는 도는 컨테이너만 15초마다 찾는다. 그 전에 끝나는 마이그레이션(`*-migrate`)의 줄은 Loki 에 없을 수 있다. `docker compose logs <서비스>` 로 본다.
- **Alloy 가 읽고 아직 보내지 못한 줄.** Alloy 가 그 순간에 죽으면 메모리에 있던 줄(Loki 로 보내려고 모은 묶음)은 잃는다. 읽은 자리는 이미 넘어갔다.
- **`warning` 줄의 `error_code`.** `error` 이상에는 붙였지만, 기존의 `warning` 줄 가운데에는 코드가 없는 것이 있다(게임 서버의 JWKS, 임베딩 실패).
