# ai-core

언어 모델을 부르는 공용 코드다. 패키지 이름은 `ai_core` 다. 게임 서버의 `app/ai` 를 폴더째 옮겼다(#499 의 1단계).
규칙과 까닭은 [공용 코드 규칙](../../docs/architecture/shared-code.md#ai-호출-sharedai-core)에 있다.

| 쓰는 서버 | 언제부터 |
| --- | --- |
| trpg-server | #499 |
| chat-server | 모델 목록의 파일을 자기 표에 들여온다(#590 의 "한 번의 말" 첫 PR). 모델을 부르는 것은 그 뒤의 PR 이다 |
| story-server | 모델을 부르기 시작할 때(#591) |

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
| `image_provider` | 그림 provider 의 모양(`ImageProvider`)과 요청, 참고 그림, 결과의 타입(#983) |
| `gemini_image` | Gemini 의 그림 모델(Nano Banana)을 부르는 provider. 참고 그림(인물 4장, 물건 10장까지), 막힘은 `refused` |
| `comfyui` | 로컬 ComfyUI 로 Stable Diffusion 계열 모델을 돌리는 provider. 연구·개발·시험용이다. 참고 그림은 받지 않는다 |
| `image_http` | 그림 provider 들의 HTTP 의 일. 실패의 이름은 글 모델과 같고, 그림의 크기에 상한을 둔다 |
| `fake` | 가짜 provider, 임베더, 그림 provider, 기록장. 자동 테스트는 이것만 쓴다 |

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

## 로컬 Stable Diffusion(연구·개발용, #983)

운영의 장면 그림은 외부 API(Nano Banana)로 만든다. 로컬 모델은 API 값 없이 지시 글과 흐름을 시험하는 데 쓴다.
같은 모양(`ImageProvider`)이라 서버에서도 개발할 때 바꿔 끼울 수 있다.

1. 그림을 그릴 PC(RTX 3090 같은 GPU)에 [ComfyUI](https://github.com/comfyanonymous/ComfyUI) 를 깔고 띄운다. 기본 주소는 `http://127.0.0.1:8188` 이다.
2. 체크포인트(모델 파일)를 `ComfyUI/models/checkpoints/` 에 둔다. 기본 흐름은 SDXL 계열의 글→그림이다.
   모델마다 상업 이용 조건(라이선스)이 다르다. 받기 전에 확인하고, 운영에 쓸 모델은 따로 정한다.
3. 그림 한 장을 만들어 본다. 걸린 시간과 씨앗이 찍힌다.

   ```powershell
   cd shared/ai-core; uv run python scripts/try_image.py comfyui --checkpoint sd_xl_base_1.0.safetensors --prompt "rainy library, a librarian by the window" --out rain.png
   ```

4. 다른 흐름(IP-Adapter 로 얼굴 맞추기 같은 것)은 ComfyUI 에서 "API 형식으로 저장"한 JSON 을 `--workflow` 로 넘긴다.
   흐름 안의 글이 정확히 `{{prompt}}`, `{{negative}}`, `{{seed}}` 인 칸을 바꿔 넣는다.
5. Nano Banana 와 견줘 보려면 키를 환경 변수에 넣고 같은 지시로 부른다(장마다 값이 든다).

   ```powershell
   cd shared/ai-core; $env:GEMINI_API_KEY = "<키>"; uv run python scripts/try_image.py gemini --prompt "rainy library, a librarian by the window" --ref face.png --out rain-nb.png
   ```

- 로컬 모델에는 공급자의 안전 필터가 없다. 성인 등급에 쓰려면 지시 거르기, 그림 분류기, 인물 나이 확인과 법률 확인을 먼저 갖춘다(#983).
- GPU 하나는 한 번에 한 장을 그린다. 로컬 글 모델(Ollama)과 같은 GPU 를 나눠 쓰면 서로 기다린다.
