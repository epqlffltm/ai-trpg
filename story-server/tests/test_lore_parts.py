# story-server/tests/test_lore_parts.py

"""
로어북을 뜻으로 찾는 일의 순수한 부분(app/lore/texts.py, recall.py 의 nearest, setup.py)을 검증한다. DB 가 없다.

보는 것.
  - 벡터로 바꿀 항목은 로어북의 id 와 항목의 id 가 있는 것이다. 글은 이름, 키워드, 내용의 줄이다
  - 이미 벡터가 있는 것과 같은 열쇠의 두 번째 것은 뺀다. 묶음은 BATCH_SIZE 개씩이다
  - 가까운 것: 거리 상한 안에서 가까운 것부터, 고른 것은 빼고, 상한 개수까지
  - 임베더는 설정으로 고른다. llm 이면 주소와 모델이 있어야 뜬다
"""

import uuid

import httpx
import pytest
from ai_core.fake import FakeEmbedder
from ai_core.openai_embedder import OpenAICompatEmbedder
from pydantic import ValidationError

from app.core.config import Settings
from app.lore.recall import MAX_DISTANCE, indexable, nearest
from app.lore.setup import build_embedder
from app.lore.texts import BATCH_SIZE, KeyedEntry, batches, entry_text, keyed_entries, missing_entries
from app.turns.briefing import LoreText, read_briefing
from tests.engine_worlds import document

BOOK = uuid.UUID('0c1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d')


def entry(entry_id: str, keywords: list[str] | None = None) -> dict:
    return {'id': entry_id, 'name': entry_id, 'keywords': keywords or [], 'content': f'{entry_id}의 내용'}


def test_only_entries_with_both_ids_get_vectors():
    briefing = read_briefing(
        document(
            lorebooks=[
                {'id': str(BOOK), 'entries': [entry('tower', ['마탑']), entry('')]},
                {'entries': [entry('river')]},
            ]
        )
    )

    keyed = keyed_entries(briefing)

    assert [item.key for item in keyed] == [(BOOK, 'tower')]
    # 로어북의 id 가 없는 항목(river)도 카드에는 넣는다. 벡터만 만들지 않는다. 이름이 빈 항목은 어디에도 없다
    assert [text.name for text in briefing.lore_entries()] == ['tower', 'river']
    assert entry_text(keyed[0].entry) == 'tower\n키워드: 마탑\ntower의 내용'
    assert entry_text(LoreText(name='강', content='흐른다.')) == '강\n흐른다.'


def test_missing_entries_skip_done_and_repeated_keys():
    first, again, other = (KeyedEntry((BOOK, name), LoreText(name=name)) for name in ('a', 'a', 'b'))

    assert missing_entries([first, again, other], set()) == [first, other]
    assert missing_entries([first, other], {(BOOK, 'a')}) == [other]
    assert [len(batch) for batch in batches([first] * (BATCH_SIZE + 1))] == [BATCH_SIZE, 1]


def test_nearest_takes_close_entries_outside_the_chosen_ones():
    keys = [(BOOK, 'a'), (BOOK, 'b'), (BOOK, 'c'), (None, 'd'), (BOOK, 'e')]
    distances = {(BOOK, 'a'): 0.1, (BOOK, 'b'): 0.2, (BOOK, 'c'): MAX_DISTANCE + 0.01, (BOOK, 'e'): 0.05}

    assert nearest(keys, distances, exclude={0}) == [4, 1]
    assert nearest(keys, distances, exclude=set(), limit=1) == [4]
    assert indexable(keys) == 4


def test_the_embedder_follows_the_settings(settings: Settings):
    client = httpx.AsyncClient()

    assert build_embedder(settings.model_copy(update={'embedder': 'off'}), client) is None
    assert isinstance(build_embedder(settings.model_copy(update={'embedder': 'fake'}), client), FakeEmbedder)
    real = settings.model_copy(update={'embedder': 'llm', 'embedding_base_url': 'http://ollama:11434/v1'})
    assert isinstance(build_embedder(real, client), OpenAICompatEmbedder)


def test_llm_needs_an_address(settings: Settings):
    with pytest.raises(ValidationError):
        Settings.model_validate({**settings.model_dump(), 'embedder': 'llm', 'embedding_base_url': ''})
