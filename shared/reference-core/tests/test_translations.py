# shared/reference-core/tests/test_translations.py

"""
참고 자료의 한국어 번역(reference_core/translations.py, reference_core/data/srd51.ko.json)을 검증한다.

보는 것.
  - 번역 파일: 수치가 든 번역(주사위, 주사위의 눈, 난이도)과 긴 이름은 받지 않는다. 자료에 없는 key 를 찾는다.
  - 붙이기: 한국어 이름과 글이 붙고, 한국어 이름이 다른 이름의 맨 앞에 한 번만 들어간다. 번역이 없으면 그대로다.
  - 만들기: 번역 파일이 있으면 붙이고, 원본을 바꾼 것(출처 표시)에 번역도 적는다. 모르는 key 면 쓰지 않는다.
  - 원본 거르기: "a d6", "save DC is 15", "On a 6", "roll a 20" 이 든 문장도 뺀다.
  - 쓰는 곳: 보이는 이름과 글, 벡터로 바꿀 글, 차지하는 글자 수가 한국어다. 한 글자 다른 이름은 보지 않는다.
  - 넣기: 한국어 글이 바뀌면 벡터를 다시 만든다.
  - 저장소의 파일: 모든 줄이 번역되어 있고, 이름이 겹치지 않고, 데이터 파일이 번역 파일과 같다.
"""

import json
import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError

from reference_core import srd
from reference_core.loading import plan_sync
from reference_core.records import (
    ReferenceKind,
    ReferenceRecord,
    ReferenceSource,
    StoredReference,
    read_document,
)
from reference_core.selection import alias_hits, reference_size
from reference_core.srd_build import EQUIPMENT_FILE, MAGIC_ITEMS_FILE, MONSTERS_FILE, UnknownTranslation, build
from reference_core.texts import reference_text
from reference_core.translations import (
    MECHANICS_KO,
    Translation,
    TranslationDocument,
    apply_translations,
    korean_content,
    read_translations,
    translated,
    unknown_keys,
)
from tests.test_srd import ABOLETH, DATA_FILE, TORCH

KO_FILE = DATA_FILE.with_name('srd51.ko.json')


def record(key: str = 'equipment/torch', **values) -> ReferenceRecord:
    defaults = {'kind': ReferenceKind.ITEM, 'name': 'Torch', 'content': 'A torch burns.'}
    return ReferenceRecord(key=key, **{**defaults, **values})


def translations(**entries: Translation) -> TranslationDocument:
    return TranslationDocument(format=1, source=ReferenceSource.SRD51, language='ko', entries=entries)


def stored(**values) -> StoredReference:
    defaults = {'id': uuid.uuid4(), 'key': 'equipment/torch', 'name': 'Torch', 'content': 'A torch burns.'}
    return StoredReference(**{**defaults, **values})


TORCH_KO = Translation(name='횃불', content='횃불이 탄다.')


# --- 번역 파일 ---


@pytest.mark.parametrize(
    'content',
    [
        '6면체 주사위 하나를 더한다.',
        '주사위를 한 번 더 굴린다.',
        '6이 나오면 광폭해진다.',
        '1에서 4가 나오면 멈춘다.',
        'DC 15 다.',
        '2d6 을 더한다.',
    ],
)
def test_a_translation_with_numbers_of_the_rules_is_refused(content: str):
    with pytest.raises(ValidationError, match='판정의 수치'):
        Translation(name='골렘', content=content)


def test_a_dice_set_is_not_a_number_of_the_rules():
    assert Translation(name='주사위 세트', content='게임 도구. 주사위와 카드 한 벌이 있다.').content


def test_a_name_longer_than_an_alias_is_refused():
    with pytest.raises(ValidationError):
        Translation(name='가' * 31)


def test_the_translation_file_is_read_and_unknown_keys_are_found(tmp_path: Path):
    path = tmp_path / 'ko.json'
    path.write_text(translations(**{'equipment/torch': TORCH_KO}).model_dump_json(), encoding='utf-8')
    read = read_translations(path)
    extra = translations(**{'equipment/torch': TORCH_KO, 'equipment/nothing': TORCH_KO})

    assert read.entries['equipment/torch'] == TORCH_KO
    assert unknown_keys([record()], read) == []
    assert unknown_keys([record()], extra) == ['equipment/nothing']


# --- 붙이기 ---


def test_the_korean_name_goes_first_in_the_aliases_once():
    plain = translated(record(), TORCH_KO)
    again = translated(record(aliases=['불', '횃불']), TORCH_KO)
    same = translated(record(name='횃불'), TORCH_KO)

    assert (plain.name_ko, plain.content_ko, plain.aliases) == ('횃불', '횃불이 탄다.', ['횃불'])
    assert again.aliases == ['불', '횃불']
    assert same.aliases == []
    # 원본의 이름과 글은 그대로다
    assert (plain.name, plain.content) == ('Torch', 'A torch burns.')


def test_other_korean_names_follow_the_korean_name():
    skeleton = Translation(name='스켈레톤', aliases=['해골 병사', '스켈레톤', 'Skeleton'], content='뼈만 남았다.')

    made = translated(record('monsters/skeleton', name='Skeleton', aliases=['해골 병사', '뼈']), skeleton)

    # 이미 있는 것(해골 병사), 겹친 것, 원본의 이름과 같은 것은 더하지 않는다. 원본의 다른 이름이 뒤다
    assert made.aliases == ['스켈레톤', '해골 병사', '뼈']


def test_the_aliases_stay_within_the_limit():
    many = Translation(name='용', aliases=['붉은 용', '적색 용', '레드 드래곤', '적룡'])

    made = translated(record(name='Red Dragon', aliases=['원본 하나', '원본 둘']), many)

    assert made.aliases == ['용', '붉은 용', '적색 용', '레드 드래곤', '적룡']
    with pytest.raises(ValidationError):
        Translation(name='용', aliases=['가나', '다라', '마바', '사아', '자차'])
    with pytest.raises(ValidationError):
        Translation(name='용', aliases=['가' * 31])


def test_lines_without_a_translation_stay_as_they_are():
    wolf = record('monsters/wolf', name='Wolf', kind=ReferenceKind.MONSTER)

    applied = apply_translations([record(), wolf], translations(**{'equipment/torch': TORCH_KO}))

    assert [line.name_ko for line in applied] == ['횃불', '']
    assert applied[1] == wolf


# --- 만들기 ---


def write_source(folder: Path) -> None:
    for name, items in [(MONSTERS_FILE, [ABOLETH]), (EQUIPMENT_FILE, [TORCH]), (MAGIC_ITEMS_FILE, [])]:
        (folder / name).write_text(json.dumps(items), encoding='utf-8')


def test_the_build_script_puts_the_translation_in(tmp_path: Path):
    write_source(tmp_path)
    ko = tmp_path / 'ko.json'
    ko.write_text(translations(**{'equipment/torch': TORCH_KO}).model_dump_json(), encoding='utf-8')
    output = tmp_path / 'srd51.json'

    build(tmp_path, 'abc', output, ko)

    built = read_document(output)
    torch = next(entry for entry in built.entries if entry.key == 'equipment/torch')
    assert (torch.name_ko, torch.content_ko, torch.aliases[0]) == ('횃불', '횃불이 탄다.', '횃불')
    assert 'translated into Korean' in built.origin.changes
    # 생김새 글이 없으면 그것을 더했다고 적지 않는다
    assert 'descriptions of appearance' not in built.origin.changes


def test_a_look_goes_before_the_text_and_is_noted_in_the_changes(tmp_path: Path):
    write_source(tmp_path)
    looked = Translation(name='횃불', look='나무 막대 끝에 기름 먹인 천을 감았다.', content='횃불이 탄다.')
    ko = tmp_path / 'ko.json'
    ko.write_text(translations(**{'equipment/torch': looked}).model_dump_json(), encoding='utf-8')
    output = tmp_path / 'srd51.json'

    build(tmp_path, 'abc', output, ko)

    built = read_document(output)
    torch = next(entry for entry in built.entries if entry.key == 'equipment/torch')
    assert torch.content_ko == '나무 막대 끝에 기름 먹인 천을 감았다. 횃불이 탄다.'
    assert torch.look_ko == '나무 막대 끝에 기름 먹인 천을 감았다.'
    assert built.origin.changes.endswith(srd.SRD51_DESCRIBED)


def test_a_look_follows_the_rules_of_the_text():
    only = Translation(name='횃불', look='막대 끝에서 불이 탄다.')

    assert translated(record(), only).content_ko == '막대 끝에서 불이 탄다.'
    with pytest.raises(ValidationError, match='판정의 수치'):
        Translation(name='골렘', look='DC 15 의 응시를 한다.')
    with pytest.raises(ValidationError):
        Translation(name='골렘', look='가' * 301)
    with pytest.raises(ValidationError, match='1000자'):
        Translation(name='골렘', look='가' * 300, content='나' * 700)


def test_without_a_translation_file_the_changes_do_not_mention_it(tmp_path: Path):
    write_source(tmp_path)
    output = tmp_path / 'srd51.json'

    build(tmp_path, 'abc', output, tmp_path / 'none.json')

    built = read_document(output)
    assert built.origin.changes == srd.SRD51_CHANGES
    assert all(entry.name_ko == '' for entry in built.entries)


def test_a_translation_of_an_unknown_line_stops_the_build(tmp_path: Path):
    write_source(tmp_path)
    ko = tmp_path / 'ko.json'
    ko.write_text(translations(**{'equipment/nothing': TORCH_KO}).model_dump_json(), encoding='utf-8')
    output = tmp_path / 'srd51.json'

    with pytest.raises(UnknownTranslation, match='equipment/nothing'):
        build(tmp_path, 'abc', output, ko)
    assert not output.exists()


# --- 원본 거르기 ---


@pytest.mark.parametrize(
    'sentence',
    [
        'The creature can add a d4 to its roll.',
        "The spell's save DC is 15.",
        'On a 6, the golem goes berserk.',
        'If you roll a 20, you lop off a limb.',
        'Roll a d100.',
    ],
)
def test_sentences_with_bare_dice_or_their_faces_are_left_out(sentence: str):
    assert srd.mechanical(sentence)
    assert not srd.mechanical('The golem goes berserk and attacks the nearest creature.')


# --- 쓰는 곳 ---


def test_the_shown_name_and_text_are_korean():
    reference = stored(name_ko='횃불', content_ko='횃불이 탄다.')
    english = stored()

    assert (reference.shown_name, reference.shown_content) == ('횃불', '횃불이 탄다.')
    assert (english.shown_name, english.shown_content) == ('Torch', 'A torch burns.')
    assert reference_size(reference) == len('횃불') + len('횃불이 탄다.')


def test_the_text_to_embed_uses_the_korean_text():
    text = reference_text(stored(aliases=['횃불'], content_ko='횃불이 탄다.'))

    assert text == 'Torch\n다른 이름: 횃불\n횃불이 탄다.'


def test_the_text_to_embed_is_the_name_and_the_look_when_there_is_one():
    looked = stored(aliases=['횃불'], content_ko='막대 끝에서 불이 탄다. 모험 장비.', look_ko='막대 끝에서 불이 탄다.')

    # 규칙 요약과 다른 이름을 빼고 이름과 생김새 글만이다. 서술자에게 가는 글은 그대로다
    assert reference_text(looked) == 'Torch\n막대 끝에서 불이 탄다.'
    assert looked.shown_content == '막대 끝에서 불이 탄다. 모험 장비.'


def test_a_one_letter_alias_is_not_matched():
    rat = stored(name='Rat', aliases=['쥐'])
    rats = stored(name='Swarm of Rats', aliases=['쥐 떼'])

    assert alias_hits([rat, rats], '검을 쥐었다. 쥐 떼가 몰려온다') == [rats]


# --- 넣기 ---


def test_a_changed_korean_text_needs_new_vectors_but_a_changed_korean_name_does_not():
    current = stored(key='equipment/torch', name_ko='횃불', content_ko='횃불이 탄다.')

    plan = plan_sync(
        [current, stored(key='equipment/rope', name='Rope', name_ko='밧줄', content_ko='밧줄이다.')],
        [
            record(name_ko='횃불', content_ko='횃불이 밝게 탄다.'),
            record('equipment/rope', name='Rope', name_ko='굵은 밧줄', content_ko='밧줄이다.'),
        ],
    )

    assert [line.key for line in plan.updated] == ['equipment/torch', 'equipment/rope']
    assert plan.reworded == {'equipment/torch'}


# --- 저장소의 파일 ---


def test_every_line_in_the_repository_is_translated_once():
    shipped = read_document(DATA_FILE)
    ko = read_translations(KO_FILE)

    assert unknown_keys(shipped.entries, ko) == []
    assert all(entry.key in ko.entries for entry in shipped.entries)
    names = [translation.name for translation in ko.entries.values()]
    # 한국어 이름이 겹치면 다른 이름으로 두 줄이 함께 걸린다(동물과 탈것, 독수리와 대머리수리)
    assert len(names) == len(set(names))
    assert all(not MECHANICS_KO.search(translation.content) for translation in ko.entries.values())


def test_the_data_file_carries_the_translation_file():
    shipped = read_document(DATA_FILE)
    ko = read_translations(KO_FILE)

    # 글은 생김새 글과 번역의 글을 이은 것이다
    assert [(entry.name_ko, entry.content_ko) for entry in shipped.entries] == [
        (ko.entries[entry.key].name, korean_content(ko.entries[entry.key])) for entry in shipped.entries
    ]
    assert all(entry.aliases and entry.aliases[0] == entry.name_ko for entry in shipped.entries if entry.name_ko)
    assert 'translated into Korean' in shipped.origin.changes


def test_the_shipped_lines_carry_the_other_korean_names():
    shipped = {entry.key: entry for entry in read_document(DATA_FILE).entries}
    ko = read_translations(KO_FILE)

    for key, translation in ko.entries.items():
        assert shipped[key].aliases[: 1 + len(translation.aliases)] == [translation.name, *translation.aliases]
    # 장면에서 흔히 부르는 말이 번역한 이름과 다른 줄(2026-11-24 평가)
    assert '해골 병사' in shipped['monsters/skeleton'].aliases
    assert '석궁' in shipped['equipment/crossbow-light'].aliases
    assert '붉은 용' in shipped['monsters/adult-red-dragon'].aliases
    assert '치유 물약' in shipped['magic-items/potion-of-healing'].aliases


def test_every_line_has_a_look_and_the_changes_say_so():
    shipped = read_document(DATA_FILE)
    ko = read_translations(KO_FILE)

    # 몬스터, 일반 장비, 마법 물건 모두 생김새 글이 있다
    assert all(translation.look for translation in ko.entries.values())
    assert shipped.origin.changes.endswith(srd.SRD51_DESCRIBED)
    mimic = next(entry for entry in shipped.entries if entry.key == 'monsters/mimic')
    assert mimic.content_ko.startswith(ko.entries['monsters/mimic'].look)
    assert all(entry.look_ko == ko.entries[entry.key].look for entry in shipped.entries)
