# reference-core

trpg, chat, story 가 함께 쓰는 참고 자료의 코드다. 패키지 이름은 `reference_core` 다.
미리 넣어 둔 바깥 자료(SRD 5.1, 위키백과)를 서술과 대화의 참고로 쓴다. 게임 중에 웹을 찾지 않는다(#482).
trpg-server 가 처음 만들었고(`app/references/`), chat 과 story 도 같은 규칙으로 쓰려고 모았다(#1338).
규칙과 까닭은 [공용 코드 규칙](../../docs/architecture/shared-code.md#참고-자료-sharedreference-core)에 있다.

| 쓰는 서버 | 언제부터 |
| --- | --- |
| trpg-server | #1338(옮기기 전에는 `app/references/records.py`, `srd.py`, `texts.py`, `translations.py`, `wiki.py` 와 쿼리, 넣기, 색인, 고르기) |
| chat-server | #1338(대화마다 켠다) |
| story-server | 다음 PR(#1338) |

## 있는 것

| 모듈 | 하는 일 |
| --- | --- |
| `records` | 자료의 한 줄(`ReferenceRecord`, `StoredReference`)과 데이터 파일(`ReferenceDocument`)의 모양, 자료와 종류, 복사할 수 있는 자료(`COPYABLE_SOURCES`) |
| `srd`, `srd_build` | SRD 5.1 의 원본에서 줄을 만드는 규칙(수치 거르기)과 원본 폴더로 데이터 파일 쓰기 |
| `translations` | 한국어 번역 파일을 읽고 줄에 붙이기 |
| `wiki` | 위키백과의 출처 표시. 받는 도구와 거르는 규칙은 다음 단계에서 더한다 |
| `attributions` | 자료마다의 출처 표시 |
| `data` | 패키지에 실린 데이터 파일(`data/srd51.json`, `data/srd51.ko.json`)과 넣기가 기본으로 넣는 것(`DATA_FILES`) |
| `columns` | 표 둘의 칸과 제약(mixin `ReferenceEntryColumns`, `ReferenceEmbeddingColumns`). 서버의 ORM 클래스가 물려받는다 |
| `tables` | 서버의 표 둘(ORM 클래스)을 묶어 넘기는 꾸러미(`ReferenceTables`) |
| `repository` | 표를 읽고 쓰는 SQL. 표 둘을 맨 앞에 받는다. 커밋하지 않는다 |
| `loading` | 데이터 파일을 표에 맞추기(`load_document`). 바뀐 글만 벡터를 지운다 |
| `indexing` | 벡터가 없는 줄의 벡터 만들기(`index_references`). 모델을 부르는 동안 DB 연결을 쥐지 않는다 |
| `selection` | 장면에 넣을 줄을 고르는 순수한 규칙(다른 이름, 거리, 자리)과 기본 숫자(`ReferenceThresholds`) |
| `search` | 찾는 글 하나에 맞는 줄을 DB 에서 고르기(`find_references`). 임베딩 모델이 실패하면 다른 이름으로만 |
| `finder` | 대화 서버의 말 한 번의 찾기(`ReferenceFinder`). 3초 안에 끝나지 않거나 실패하면 빈 목록이다 |
| `prompt` | 대화 서버의 "[참고 자료]" 블록(`render_references`). 종류의 이름과 [상식]의 규칙은 trpg 도 쓴다 |
| `commands` | 관리 명령(`scripts/references.py`)의 몸통. 명령줄, 넣기(`load_files`), 색인(`index`), 찍는 줄 |

ORM 클래스와 마이그레이션, 켰는지(테이블, 대화, 세션), 로어북의 상한, 블록을 넣는 자리는 서버에 있다.

## 서버에 붙이기

1. `pyproject.toml` 에 경로 의존을 적는다. `ai-core` 에 기대므로 `ai-core` 도 함께 받는다.

   ```toml
   dependencies = [..., "ai-core", "reference-core"]

   [tool.uv.sources]
   ai-core = { path = "../shared/ai-core", editable = true }
   reference-core = { path = "../shared/reference-core", editable = true }
   ```

2. Dockerfile 에서 담는다. 데이터 파일은 `src` 안에 있어 함께 들어간다.

   ```dockerfile
   COPY --from=shared reference-core/pyproject.toml /shared/reference-core/pyproject.toml
   COPY --from=shared reference-core/src /shared/reference-core/src
   ```

3. 표 둘을 서버의 Base 로 만들고(칸은 물려받는다) 꾸러미 하나를 둔다. 마이그레이션은 자동으로 만든다(`alembic revision --autogenerate`).

   ```python
   class ReferenceEntry(ReferenceEntryColumns, Base):
       """..."""


   class ReferenceEmbedding(ReferenceEmbeddingColumns, Base):
       """..."""


   TABLES = ReferenceTables(entry=ReferenceEntry, embedding=ReferenceEmbedding)
   ```

4. 관리 명령을 둔다. 몸통을 제 표에 묶고(`partial(commands.load_files, TABLES)`), 제 설정으로 DB 와 임베더를 만든다(chat-server 의 `scripts/references.py`).
   차례는 `load` 다음 `index` 다.
5. 대화 서버는 앱에 `ReferenceFinder` 하나를 두고, 모델을 부르기 직전에 `find(찾는 글, room_after(로어북이 쓴 글자, 로어북의 상한))` 를 불러 `render_references` 의 블록을 카드에 넣는다.

## 테스트

```
cd shared/reference-core
uv run pytest
```

쿼리의 테스트는 실제 PostgreSQL(pgvector)에서 돈다. 접속 주소를 `REFERENCE_CORE_TEST_DATABASE_URL` 로 준다. 그 계정이 확장(`vector`)을 만들 수 있어야 한다.
주소가 없으면 쿼리의 테스트는 건너뛴다(CI 는 DB 를 띄워 모두 돈다). 테스트는 `reference_core_test` 스키마를 지우고 다시 만든다.
