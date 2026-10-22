# ai-core

언어 모델을 부르는 공용 코드다. 패키지 이름은 `ai_core` 다. 게임 서버의 `app/ai` 를 폴더째 옮겼다(#499 의 1단계).
규칙과 까닭은 [공용 코드 규칙](../../docs/architecture/shared-code.md#ai-호출-sharedai-core)에 있다.

| 쓰는 서버 | 언제부터 |
| --- | --- |
| trpg-server | #499 |
| chat-server, story-server | 모델을 부르기 시작할 때("한 번의 말", #590, #591) |

## 있는 것

| 모듈 | 하는 일 |
| --- | --- |
| `provider` | provider 의 모양(`LLMProvider`)과 메시지, 생성 설정, 결과의 타입. 어느 회사의 SDK 타입도 쓰지 않는다 |
| `openai_compat` | OpenAI 와 같은 모양의 주소를 부르는 provider. Ollama, LM Studio, vLLM, OpenAI, Z.ai, DeepInfra |
| `anthropic`, `anthropic_stream` | Claude(Messages API). SDK 없이 부르고 흘러온 답을 읽는다 |
| `gemini`, `gemini_stream` | Gemini(generateContent). SDK 없이 부르고 흘러온 답을 읽는다 |
| `http_stream` | 보내고 흘려 받는 HTTP 의 일. 시간의 상한, 실패의 이름, Retry-After |
| `streaming` | 흘려 받은 조각에서 생각 글을 걸러 낸다 |
| `thinking` | 생각할 때 출력 상한에 더하는 토큰 수 |
| `routing` | 모델의 이름으로 창구를 고른다(`ModelRouter`). 모델 목록은 쓰는 서버가 `ModelLookup` 모양으로 넘긴다 |
| `catalog_contract` | 모델 목록의 계약: 창구, 사고 방식, 받는 칸, 분류, 단가, 순수 규칙(`is_offered`, `is_retired`, 창구에 맞는 칸과 방식) |
| `catalog_file`, `model_catalog.toml` | 모델 목록의 원본 파일과 그것을 읽는 것(`load_catalog`). 서비스마다 자기 표에 들여온다(게임 서버는 `scripts.models sync`) |
| `calls` | 호출 한 번의 기록(`CallRecord`)과 기록을 받는 곳의 모양(`CallLog`), 보낸 메시지의 지문 |
| `costs` | 호출 한 번의 원가를 그날의 단가로 센다 |
| `retry_budget` | 같은 모델로 다시 부르는 예산(최근 1분의 첫 시도의 10%, 적어도 3번) |
| `embedder`, `openai_embedder` | 임베더의 모양과 OpenAI 모양의 `/embeddings` 를 부르는 구현 |
| `fake` | 가짜 provider, 임베더, 기록장. 자동 테스트는 이것만 쓴다 |

## 서버에 붙이기

1. `pyproject.toml` 에 경로 의존을 적는다. CI 는 이 줄을 읽어 공용 코드가 바뀐 PR 에서 그 서버를 검사한다.

   ```toml
   dependencies = [..., "ai-core"]

   [tool.uv.sources]
   ai-core = { path = "../shared/ai-core", editable = true }
   ```

2. Dockerfile 에서 공용 코드를 담고 설치된 모양으로 깐다. compose 는 `build.additional_contexts: shared: ./shared` 로 넘긴다.

   ```dockerfile
   COPY --from=shared ai-core/pyproject.toml /shared/ai-core/pyproject.toml
   COPY --from=shared ai-core/src /shared/ai-core/src
   COPY pyproject.toml uv.lock ./
   RUN uv sync --locked --no-dev --no-install-project --no-editable
   ```

3. 모델 목록: 원본 파일(`model_catalog.toml`)을 관리 명령으로 서버의 표에 들여오고, 표를 `ModelLookup` 모양으로 읽는 것을 만든다(게임 서버는 `app/catalog/sync.py`, `app/catalog/lookup.py`). 파일을 고치는 법은 [게임 서버 README 의 모델 목록](../../trpg-server/README.md#모델-목록)에 있다.

4. 서버가 넘기는 것: HTTP 클라이언트(서버의 것이라 span 이 걸린다), 창구마다의 주소와 키(`Endpoint`), 모델 목록(`ModelLookup` 을 따르는 것). 호출 기록을 받는 곳은 서버가 `CallLog` 모양으로 만든다(게임 서버는 `app/ai_log` 의 DB 기록장). 공용 코드는 서버의 설정(`.env`)을 읽지 않는다.

## 경계

- 서버의 모듈(`app.*`), 다른 공용 패키지(`server_core` 등), 관측의 코드(`opentelemetry`)를 가져오지 않는다(`tests/test_boundary.py`). span 은 서버가 넘긴 클라이언트가 걸고, 메트릭은 서버가 기록장을 감싸 센다.
- 모델 목록의 원본(모델, 받는 것, 은퇴일, 원가)은 여기 있다. 그것을 들여온 표와 켜고 끄기, 회사의 대체 모델, 한 서비스만 쓰는 속성, 호출 기록의 표, 프롬프트, 판매가와 고를 수 있는 모델은 쓰는 서버의 몫이다.
- 생각 글은 저장하지 않고, 오류에 본문과 키를 싣지 않는다.

## 테스트

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run pytest --cov
```

DB 도 모델도 부르지 않는다. httpx 의 가짜 전송(`MockTransport`)이 모델의 창구인 척 답한다.
DB 의 모델 목록, 호출 기록의 표, 서술자처럼 서버에 붙은 것은 쓰는 서버의 테스트가 본다.
