# catalog-core

chat, story, trpg 가 함께 쓰는 모델 목록의 표 코드다. 패키지 이름은 `catalog_core` 다.
세 서버가 세 벌로 갖던 쿼리, 모델 하나 찾기, 원본 파일 들여오기, 거절의 까닭을 모았다(#1266).
규칙과 까닭은 [공용 코드 규칙](../../docs/architecture/shared-code.md#모델-목록의-표-sharedcatalog-core)에 있다.

| 쓰는 서버 | 언제부터 |
| --- | --- |
| trpg-server, chat-server, story-server | #1266(옮기기 전에는 서버마다 `app/catalog/sync.py`, `lookup.py`, `errors.py`) |

## 있는 것

| 모듈 | 하는 일 |
| --- | --- |
| `tables` | 서버의 표 셋(ORM 클래스)을 묶어 넘기는 꾸러미(`CatalogTables`)와 회사가 바뀔 때 서버의 칸을 고칠 자리(`on_vendor_change`) |
| `errors` | 거절의 까닭(`ModelNotFoundError`, `CatalogConflictError`, `Conflict`) |
| `repository` | 표를 읽고 적는 SQL. 표 셋을 맨 앞에 받는다. 커밋하지 않는다 |
| `lookup` | 모델 하나를 찾아 세션과 떨어진 값(`CatalogModel`)으로 돌려주는 것(`DbModelLookup`). `ai_core` 의 `ModelLookup` 모양이다 |
| `sync` | 원본 파일(`ai_core/model_catalog.toml`)을 표에 들여오기(`sync_catalog`). 트랜잭션 하나, 모델마다 줄을 잠근다 |

표(ORM 클래스와 마이그레이션), 켜기와 끄기, 고를 수 있는 모델과 그 값(`service`, `offers`)은 서버에 있다.

## 서버에 붙이기

1. `pyproject.toml` 에 경로 의존을 적는다. `ai-core` 에 기대므로 `ai-core` 도 함께 받는다. CI 는 이 줄을 읽어 공용 코드가 바뀐 PR 에서 그 서버를 검사한다.

   ```toml
   dependencies = [..., "ai-core", "catalog-core"]

   [tool.uv.sources]
   ai-core = { path = "../shared/ai-core", editable = true }
   catalog-core = { path = "../shared/catalog-core", editable = true }
   ```

2. Dockerfile 에서 `ai-core` 와 함께 담고 설치된 모양으로 깐다.

   ```dockerfile
   COPY --from=shared catalog-core/pyproject.toml /shared/catalog-core/pyproject.toml
   COPY --from=shared catalog-core/src /shared/catalog-core/src
   ```

3. 서버의 `app/catalog/models.py` 에 표 셋을 하나 만든다. 표는 칸의 이름이 같아야 한다(`catalog_core/tables.py`).

   ```python
   TABLES = CatalogTables(AiModel, AiModelCost, AiModelSnapshot)
   ```

   회사에 묶인 서버만의 칸이 있으면 고칠 자리를 넘긴다(trpg 의 회사의 대체 모델).

   ```python
   TABLES = CatalogTables(AiModel, AiModelCost, AiModelSnapshot, on_vendor_change=drop_vendor_fallback)
   ```

4. 서버의 `app/catalog/repository.py` 에서 쿼리를 제 표에 묶는다. 서버의 코드는 표를 넘기지 않고 부른다.

   ```python
   get_model = partial(shared.get_model, TABLES)
   ```

5. 찾기와 들여오기에는 표 셋을 넘긴다.

   ```python
   lookup = DbModelLookup(session_factory, TABLES)
   report = await sync_catalog(TABLES, session, load_catalog(), dry_run=False)
   ```

## 테스트

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run pytest --cov
```

DB 없이 메모리의 SQLite 로 돈다(`tests/tables.py` 의 표). 들여오기의 규칙, 쿼리의 차례, 찾기를 본다.
PostgreSQL 에만 있는 것(줄 잠금으로 둘이 동시에 들여오기, `DISTINCT ON` 의 결과, 표의 CHECK)은 쓰는 서버의
`tests/test_catalog_sync.py`, `tests/test_model_catalog.py` 가 실제 DB 로 본다.
`tests/test_boundary.py` 가 서버의 모듈(`app.*`), `ai_core` 밖의 공용 패키지, 관측의 코드를 가져오지 않는지 본다.
