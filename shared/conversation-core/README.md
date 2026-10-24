# conversation-core

chat 과 story 가 함께 쓰는 대화의 핵심이다. 패키지 이름은 `conversation_core` 다.
chat 서버의 `app/conversation` 을 폴더째 옮겼다(#591). 규칙과 까닭은 [공용 코드 규칙](../../docs/architecture/shared-code.md#대화의-핵심-sharedconversation-core)에 있다.

| 쓰는 서버 | 언제부터 |
| --- | --- |
| chat-server | #591(옮기기 전에는 `app/conversation`) |
| story-server | 세션과 한 번의 말을 만들 때([story 서버 설계의 만드는 순서](../../docs/architecture/story.md#만드는-순서) 1, 2) |

## 있는 것

모두 DB 도 모델도 모르는 순수한 조각이다. 표준 라이브러리만 쓴다.

| 모듈 | 하는 일 |
| --- | --- |
| `sse` | SSE 의 글자(`Frame`, `Comment`, `encode`) |
| `relay` | 모델을 부르는 작업과 SSE 응답을 잇는 통로(`Relay`). 조용하면 하트비트를 끼운다 |
| `window` | 모델에 보낼 최근 대화의 창(`select_window`). 글자의 상한 안에서 최근 말부터 |
| `lorebook` | 로어북의 항목 고르기. 상시, 키워드, 뜻으로 찾은 것의 차례와 상한(`ranked`, `with_recalled`, `chosen_entries`, `render_lore`). 항목은 `LoreEntry` 모양이면 된다 |
| `continuation` | 이어서 출력의 지시와 되풀이한 앞부분 떼기 |
| `markers` | 본문 뒤의 블록의 표식(다음 답 추천, 상태 바꾸기의 제안) |
| `suggestions` | 다음 답 추천의 지시, 흘려 받을 때 표식 뒤를 붙잡기(`MarkerHold`), 선택지 거르기 |
| `changes` | 상태 바꾸기의 제안(호감도, 선물, 이동)의 지시와 줄 읽기. 해도 되는지는 쓰는 서버의 엔진이 본다 |
| `expressions` | 표정 고르기의 지시와 답 맨 앞의 표식 떼기(`ExpressionHead`) |

## 서버에 붙이기

1. `pyproject.toml` 에 경로 의존을 적는다. CI 는 이 줄을 읽어 공용 코드가 바뀐 PR 에서 그 서버를 검사한다.

   ```toml
   dependencies = [..., "conversation-core"]

   [tool.uv.sources]
   conversation-core = { path = "../shared/conversation-core", editable = true }
   ```

2. Dockerfile 에서 공용 코드를 담고 설치된 모양으로 깐다. compose 는 `build.additional_contexts: shared: ./shared` 로 넘긴다.

   ```dockerfile
   COPY --from=shared conversation-core/pyproject.toml /shared/conversation-core/pyproject.toml
   COPY --from=shared conversation-core/src /shared/conversation-core/src
   ```

3. 서버가 넘기는 것: 항목(`LoreEntry` 모양), 고를 수 있는 표정의 이름, 창의 글자 상한. 공용 코드는 서버의 설정(`.env`)을 읽지 않는다.

## 경계

- 서버의 모듈(`app.*`), 다른 공용 패키지(`server_core`, `ai_core`), 관측의 코드(`opentelemetry`)를 가져오지 않는다(`tests/test_boundary.py`).
- 대화와 메시지의 표(ORM 모델)는 서버마다 자기 스키마에 둔다(chat 은 `chat`, story 는 `story`). 여기에 두지 않는다.
- 캐릭터 하나에만 맞는 것(카드의 모양, 호감도의 규칙, 그림)은 chat 서버에 남는다. 상태 바꾸기의 제안과 표정은 블록의 모양만 여기에 있고, 무엇을 허락하고 어떻게 반영할지는 서버가 정한다.

## 테스트

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run pytest --cov
```

DB 도 모델도 부르지 않는다. 이 조각들이 서버의 흐름(말 보내기, 이어서 출력, 로어북 검색) 안에서 맞게 쓰이는지는 쓰는 서버의 테스트가 본다.
