# shared/reference-core/tests/test_looks.py

"""
위키백과의 생김새 글 파일(reference_core/looks.py)과 실린 파일을 검증한다.

보는 것.
  - 읽기: 빈 글, 300자를 넘는 글, 판정의 수치가 든 글, 다른 칸은 받지 않는다
  - 붙이기: look_ko 만 바꾼다. 글과 다른 이름은 그대로다. 없는 줄은 그대로다
  - 알림: 생김새 글이 없는 줄, 자료에 없는 줄의 생김새 글
  - 실린 파일: 위키백과의 줄마다 생김새 글이 있고, 데이터 파일의 look_ko 가 그것과 같다. 벡터 글이 이름과 생김새 글이다
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from reference_core.data import WIKIPEDIA_FILE, WIKIPEDIA_LOOKS_FILE
from reference_core.looks import LooksDocument, apply_looks, read_looks, unknown_look_keys, unlooked_keys, with_look
from reference_core.records import ReferenceKind, ReferenceRecord, ReferenceSource, read_document

BELLOWS = ReferenceRecord(
    key='ko/풀무',
    kind=ReferenceKind.TOPIC,
    name='풀무',
    aliases=['풀무'],
    content='풀무는 바람을 일으키는 기구이다.',
    data={'lang': 'ko'},
)
ANVIL = BELLOWS.model_copy(update={'key': 'ko/모루', 'name': '모루', 'aliases': ['모루'], 'content': '모루다.'})


def looks(entries: dict[str, str], source: str = 'wikipedia') -> LooksDocument:
    return LooksDocument.model_validate({'format': 1, 'source': source, 'entries': entries})


def test_a_look_file_is_read(tmp_path: Path):
    path = tmp_path / 'looks.json'
    path.write_text(json.dumps({'format': 1, 'source': 'wikipedia', 'entries': {'ko/풀무': ' 바람을 불어 넣는다. '}}))

    document = read_looks(path)

    assert document.entries == {'ko/풀무': '바람을 불어 넣는다.'}


@pytest.mark.parametrize('look', ['', '   ', '가' * 301, '바람을 2d6 만큼 분다.', '난이도 15 의 풀무'])
def test_a_wrong_look_is_refused(look: str):
    with pytest.raises(ValidationError):
        looks({'ko/풀무': look})


def test_another_field_is_refused():
    with pytest.raises(ValidationError):
        LooksDocument.model_validate({'format': 1, 'source': 'wikipedia', 'entries': {}, 'language': 'ko'})


def test_only_the_look_changes():
    document = looks({'ko/풀무': '가죽 주머니를 눌러 바람을 넣는다.'})

    looked = with_look(BELLOWS, document)

    assert looked.look_ko == '가죽 주머니를 눌러 바람을 넣는다.'
    # 서술자에게 가는 글과 다른 이름은 그대로다
    assert (looked.content, looked.content_ko, looked.aliases) == (BELLOWS.content, '', ['풀무'])
    assert with_look(ANVIL, document) == ANVIL
    assert apply_looks([ANVIL, BELLOWS], document) == [ANVIL, looked]


def test_missing_and_unknown_looks_are_listed():
    document = looks({'ko/풀무': '바람을 넣는다.', 'ko/없음': '없는 줄이다.'})

    assert unlooked_keys([BELLOWS, ANVIL], document) == ['ko/모루']
    assert unknown_look_keys([BELLOWS, ANVIL], document) == ['ko/없음']


# --- 실린 파일 ---


def test_every_shipped_wikipedia_line_has_its_look():
    document = read_looks(WIKIPEDIA_LOOKS_FILE)
    shipped = read_document(WIKIPEDIA_FILE)

    assert document.source == ReferenceSource.WIKIPEDIA
    assert set(document.entries) == {record.key for record in shipped.entries}
    assert all(record.look_ko == document.entries[record.key] for record in shipped.entries)
    # 생김새 글을 더한 것을 출처 표시의 "바꾼 것"에 적었다
    assert 'descriptions of appearance' in shipped.origin.changes


def test_a_wrong_article_is_not_shipped():
    # "수정구" 는 수정 구슬이 아니라 도시의 구(행정 구역) 문서였다. 실제 세계의 장소라 뺐다
    shipped = read_document(WIKIPEDIA_FILE)

    assert 'ko/수정구' not in {record.key for record in shipped.entries}
    assert not any('성남' in record.content for record in shipped.entries)
