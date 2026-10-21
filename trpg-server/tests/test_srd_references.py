# trpg-server/tests/test_srd_references.py

"""
SRD 5.1 을 참고 자료의 줄로 옮기는 것(app/references/srd.py)과 데이터 파일의 모양(app/references/records.py)을 검증한다.

DB 도 모델도 쓰지 않는다. 원본의 모양을 줄인 표본으로 본다.

보는 것.
  - 서술자가 읽는 글에 수치가 없다. 수치가 든 문장, 목록과 표의 줄, 끊긴 문장을 빼고, 이름의 수치 괄호를 지운다.
    단위의 줄임("5 ft. of it")에서 문장을 나누지 않는다. 상한을 넘으면 문장째로 자른다.
  - 원본의 수치는 data 에 남는다(기본 자산이 쓴다).
  - 마법 물건의 변형은 넣지 않는다.
  - 데이터 파일: key 가 겹치면 받지 않는다. 쓰고 읽으면 같다. 저장소에 든 SRD 파일이 모양과 규칙을 지킨다.
"""

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.references import srd
from app.references.records import (
    REFERENCE_CONTENT_MAX_LENGTH,
    ReferenceDocument,
    ReferenceKind,
    ReferenceOrigin,
    ReferenceRecord,
    ReferenceSource,
    read_document,
    write_document,
)
from scripts.build_srd import EQUIPMENT_FILE, MAGIC_ITEMS_FILE, MONSTERS_FILE, build

# 판정의 수치. 서술자가 읽는 글에 있으면 안 된다
NUMBERS = re.compile(r'\bDC\s*\d+|\b\d*d\d+\b|[+-]\d+\b|\bto hit\b', re.IGNORECASE)
DATA_FILE = Path(__file__).resolve().parents[1] / 'data' / 'references' / 'srd51.json'

ABOLETH = {
    'index': 'aboleth',
    'name': 'Aboleth',
    'size': 'Large',
    'type': 'aberration',
    'alignment': 'lawful evil',
    'armor_class': [{'type': 'natural', 'value': 17}],
    'hit_points': 135,
    'hit_dice': '18d10',
    'speed': {'walk': '10 ft.', 'swim': '40 ft.', 'hover': True},
    'strength': 21,
    'dexterity': 9,
    'constitution': 15,
    'intelligence': 18,
    'wisdom': 15,
    'charisma': 18,
    'proficiencies': [
        {'value': 6, 'proficiency': {'index': 'saving-throw-con'}},
        {'value': 10, 'proficiency': {'index': 'skill-perception'}},
    ],
    'damage_vulnerabilities': [],
    'damage_resistances': ['cold'],
    'damage_immunities': [],
    'condition_immunities': [{'index': 'charmed', 'name': 'Charmed'}],
    'senses': {'darkvision': '120 ft.', 'passive_perception': 20},
    'languages': 'Deep Speech, telepathy 120 ft.',
    'challenge_rating': 10,
    'xp': 5900,
    'special_abilities': [
        {'name': 'Amphibious', 'desc': 'The aboleth can breathe air and water.'},
        {
            'name': 'Mucous Cloud',
            'desc': 'While underwater, the aboleth is surrounded by transformative mucus. A creature within 5 ft. of '
            'it must make a DC 14 Constitution saving throw. The diseased creature can breathe only underwater.',
        },
    ],
    'actions': [
        {
            'name': 'Tentacle',
            'desc': 'Melee Weapon Attack: +9 to hit, reach 10 ft., one target. Hit: 12 (2d6 + 5) bludgeoning damage.',
            'attack_bonus': 9,
            'damage': [{'damage_dice': '2d6+5', 'damage_type': {'index': 'bludgeoning'}}],
            'dc': {'dc_type': {'index': 'con'}, 'dc_value': 14},
        },
    ],
    'legendary_actions': [{'name': 'Psychic Drain (Costs 2 Actions)', 'desc': 'One creature charmed by the aboleth.'}],
}
LONGSWORD = {
    'index': 'longsword',
    'name': 'Longsword',
    'equipment_category': {'index': 'weapon', 'name': 'Weapon'},
    'weapon_category': 'Martial',
    'weapon_range': 'Melee',
    'category_range': 'Martial Melee',
    'cost': {'quantity': 15, 'unit': 'gp'},
    'damage': {'damage_dice': '1d8', 'damage_type': {'index': 'slashing'}},
    'weight': 3,
    'properties': [{'index': 'versatile', 'name': 'Versatile'}],
}
TORCH = {
    'index': 'torch',
    'name': 'Torch',
    'equipment_category': {'index': 'adventuring-gear', 'name': 'Adventuring Gear'},
    'gear_category': {'index': 'standard-gear', 'name': 'Standard Gear'},
    'cost': {'quantity': 1, 'unit': 'cp'},
    'weight': 1,
    'desc': [
        'A torch burns for 1 hour, providing bright light in a 20-foot radius. '
        'If you make a melee attack with a burning torch and hit, it deals 1 fire damage.'
    ],
}
ARMOR = {
    'index': 'armor',
    'name': 'Armor, +1, +2, or +3',
    'equipment_category': {'index': 'armor'},
    'rarity': {'name': 'Varies'},
    'variant': False,
    'variants': [{'index': 'armor-1'}],
    'desc': ['Armor (light, medium, or heavy), rare (+1), very rare (+2)', 'You have a +1 bonus to AC. It gleams.'],
}
ARMOR_1 = {**ARMOR, 'index': 'armor-1', 'name': 'Armor, +1', 'variant': True, 'variants': []}


def record(key: str = 'monsters/aboleth', **values) -> ReferenceRecord:
    return ReferenceRecord(key=key, kind=ReferenceKind.MONSTER, name='Aboleth', **values)


def document(records: list[ReferenceRecord]) -> ReferenceDocument:
    origin = ReferenceOrigin(dataset='test', revision='abc', license='CC-BY-4.0', attribution='SRD 5.1')
    return ReferenceDocument(format=1, source=ReferenceSource.SRD51, origin=origin, entries=records)


# --- 거르기 ---


def test_sentences_with_numbers_of_the_rules_are_left_out():
    text = (
        'The bag is larger inside. Make a DC 15 Strength check. It sleeps for 1d4 hours. You gain +2 to hit.\n'
        '- Cantrips (at will): mage hand\n| d100 | Effect |\nThe lich has the following spells prepared:'
    )

    assert srd.narrative(text) == 'The bag is larger inside.'


def test_a_unit_does_not_end_a_sentence():
    assert srd.sentences('It reaches 5 ft. of it and stops. Then it sleeps.') == [
        'It reaches 5 ft. of it and stops.',
        'Then it sleeps.',
    ]


def test_only_numbered_parentheses_are_removed_from_names():
    assert srd.plain_name('Fire Breath (Recharge 5-6)') == 'Fire Breath'
    assert srd.plain_name('Bite (3/Day)') == 'Bite'
    assert srd.plain_name('Shape (goblinoid)') == 'Shape (goblinoid)'


def test_a_long_text_is_cut_between_sentences():
    parts = ['One two three.', 'Four five. Six seven eight nine.']

    assert srd.fit(parts, limit=26) == 'One two three. Four five.'
    assert srd.fit(parts, limit=10) == ''


# --- 몬스터, 장비, 마법 물건 ---


def test_a_monster_is_told_without_numbers_and_keeps_them_in_data():
    aboleth = srd.monster_record(ABOLETH)

    assert aboleth.key == 'monsters/aboleth' and aboleth.kind == ReferenceKind.MONSTER
    assert aboleth.content == (
        'Large aberration, lawful evil. Moves: walk, swim. Senses: darkvision. '
        'Languages: Deep Speech, telepathy 120 ft. '
        'Traits: Amphibious — The aboleth can breathe air and water; Mucous Cloud — While underwater, the aboleth '
        'is surrounded by transformative mucus. The diseased creature can breathe only underwater. '
        'Actions: Tentacle. Legendary actions: Psychic Drain — One creature charmed by the aboleth.'
    )
    data = aboleth.data
    assert (data['armor_class'], data['hit_points'], data['abilities']['strength']) == (17, 135, 21)
    assert (data['saving_throws'], data['skills']) == ({'con': 6}, {'perception': 10})
    assert data['condition_immunities'] == ['charmed'] and data['damage_resistances'] == ['cold']
    assert data['actions'] == [
        {
            'name': 'Tentacle',
            'attack_bonus': 9,
            'damage': [{'dice': '2d6+5', 'type': 'bludgeoning'}],
            'dc': {'ability': 'con', 'value': 14},
        }
    ]


def test_equipment_is_told_by_its_kind_without_price():
    sword = srd.equipment_record(LONGSWORD)
    torch = srd.equipment_record(TORCH)

    assert sword.content == 'Martial Melee weapon. Deals slashing wounds. Properties: Versatile.'
    assert sword.data['cost'] == {'quantity': 15, 'unit': 'gp'}
    assert sword.data['damage'] == {'dice': '1d8', 'type': 'slashing'}
    assert torch.content == (
        'Adventuring gear (Standard Gear). A torch burns for 1 hour, providing bright light in a 20-foot radius.'
    )
    assert torch.data['gear_category'] == 'standard-gear'


def test_magic_items_drop_numbers_and_variants():
    records = srd.srd_records([], [], [ARMOR, ARMOR_1])

    (armor,) = records
    assert armor.content == 'Armor (light, medium, or heavy), rare, very rare. It gleams.'
    assert armor.data == {'category': 'armor', 'rarity': 'Varies', 'variants': ['armor-1']}


def test_the_build_script_writes_a_document_from_the_source_folder(tmp_path: Path):
    for name, items in [(MONSTERS_FILE, [ABOLETH]), (EQUIPMENT_FILE, [TORCH]), (MAGIC_ITEMS_FILE, [ARMOR, ARMOR_1])]:
        (tmp_path / name).write_text(json.dumps(items), encoding='utf-8')
    output = tmp_path / 'out' / 'srd51.json'

    assert build(tmp_path, 'abc123', output) == 3
    built = read_document(output)
    assert [entry.key for entry in built.entries] == ['monsters/aboleth', 'equipment/torch', 'magic-items/armor']
    assert built.origin.revision == 'abc123' and built.origin.license == 'CC-BY-4.0'


# --- 데이터 파일 ---


def test_a_document_with_the_same_key_twice_is_refused():
    with pytest.raises(ValidationError, match='겹치는 key'):
        document([record(), record(content='다른 글')])


def test_a_document_reads_back_as_written(tmp_path: Path):
    written = document([record(aliases=['아볼레스'], content='Large aberration.', data={'hit_points': 135})])
    path = tmp_path / 'refs.json'

    write_document(written, path)

    assert read_document(path) == written
    # 한 줄에 한 항목이다. 다시 만들면 바뀐 항목만 diff 에 보인다
    assert sum(1 for line in path.read_text(encoding='utf-8').splitlines() if '"key"' in line) == 1


def test_an_unknown_format_is_refused():
    with pytest.raises(ValidationError):
        ReferenceDocument.model_validate({**document([]).model_dump(), 'format': 2})


def test_the_srd_file_in_the_repository_keeps_the_rules():
    shipped = read_document(DATA_FILE)

    kinds = [entry.kind for entry in shipped.entries]
    assert (kinds.count(ReferenceKind.MONSTER), kinds.count(ReferenceKind.ITEM)) == (334, 476)
    assert shipped.origin.license == 'CC-BY-4.0' and 'SRD 5.1' in shipped.origin.attribution
    assert all(len(entry.content) <= REFERENCE_CONTENT_MAX_LENGTH for entry in shipped.entries)
    # 판정의 수치(난이도, 주사위, 보너스, 명중)가 든 글이 없다.
    # "damage" 라는 낱말은 이름과 갈래에 남는다("Damage Transfer")
    assert [entry.key for entry in shipped.entries if NUMBERS.search(entry.content)] == []
