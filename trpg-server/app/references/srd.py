# trpg-server/app/references/srd.py

"""
SRD 5.1 의 몬스터, 장비, 마법 물건을 참고 자료의 줄(ReferenceRecord)로 옮긴다. DB 도 모델도 모르는 순수한 함수들이다.

원본은 5e-bits/5e-database 의 src/2014/en 이다(SRD 5.1 을 JSON 으로 옮긴 것). 데이터 파일을 만들 때만 쓴다
(scripts/build_srd.py). 서버는 원본을 읽지 않는다.

서술자가 읽는 글(content)에는 수치를 넣지 않는다. 판정은 엔진이 하고, SRD 의 수치는 이 게임의 규칙이 아니다.
모델이 "DC 14", "12 의 피해" 를 읽으면 장면에 쓴다. 그래서 수치는 data 에만 둔다(기본 자산의 시트 채우기가 쓴다).
  - 문장 단위로 거른다. 수치가 든 문장(난이도, 명중, 주사위, 피해, 내성 굴림, 유리함)은 뺀다(mechanical).
  - 이름의 괄호 속 수치("Recharge 5-6", "3/Day", "Costs 2 Actions")는 지운다.
  - 값(가격, 무게)도 넣지 않는다. 이 게임의 경제가 아니다.
  - 남은 글이 상한(1,000자)을 넘으면 문장째로 자른다. 앞의 것(생김새, 종류)이 먼저 들어간다.

마법 물건의 변형(variant: 저항의 갑옷(산) 등)은 넣지 않는다. 바탕 물건 하나에 변형의 이름을 data 에 적는다.
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from app.references.records import (
    DOCUMENT_FORMAT,
    REFERENCE_CONTENT_MAX_LENGTH,
    ReferenceDocument,
    ReferenceKind,
    ReferenceOrigin,
    ReferenceRecord,
    ReferenceSource,
)

# 서술자에게 주지 않는 문장의 표시. 판정의 수치나 규칙의 낱말이다.
# 주사위는 "2d6" 뿐 아니라 "a d6" 도, 난이도는 "DC 15" 뿐 아니라 "save DC is 15" 도 뺀다.
# 주사위의 눈("On a 6", "roll a 20")도 뺀다
MECHANICS = re.compile(
    r'\bDC\b|\b\d*d\d+\b|\bon an? \d+\b|\broll(?:s|ed)? an? \d+\b|[+-]\d+\b|\bto hit\b|saving throw|\bdamage\b'
    r'|\barmor class\b|\bAC\b'
    r'|\bproficiency bonus\b|\bmodifier\b|\badvantage\b|\bdisadvantage\b|\bcharges?\b|\bhit dice\b|\bspell slots?\b',
    re.IGNORECASE,
)
# 이름 뒤의 괄호 중 수치가 든 것("(Recharge 5-6)", "(3/Day)")
NUMBERED_PARENS = re.compile(r'\s*\([^)]*\d[^)]*\)')
# 문장의 끝. 마침표, 느낌표, 물음표 뒤의 빈칸에서 나눈다. 단위의 줄임("5 ft. of it", "10 lb.")에서는 나누지 않는다
SENTENCE_END = re.compile(r'(?<=[.!?])(?<!\bft\.)(?<!\blb\.)\s+')
# 원본의 목록 줄과 표의 줄. 서술의 참고가 아니다(주문 목록, 주사위 표)
LIST_LINE = re.compile(r'^\s*([-|#*]|\d+\.)')


def sentences(text: str) -> list[str]:
    """글을 문장들로 나눈다. 목록과 표의 줄은 뺀다. 빈 문장은 없다."""
    lines = [line for line in text.splitlines() if line.strip() and not LIST_LINE.match(line)]
    return [piece.strip() for line in lines for piece in SENTENCE_END.split(line) if piece.strip()]


def mechanical(sentence: str) -> bool:
    """판정의 수치나 규칙의 낱말이 든 문장인가."""
    return MECHANICS.search(sentence) is not None


def dangling(sentence: str) -> bool:
    """뒤에 오던 목록을 뺀 탓에 끊긴 문장인가("The lich has the following wizard spells prepared:")."""
    return sentence.endswith(':')


def narrative(text: str) -> str:
    """글에서 판정의 문장과 끊긴 문장을 뺀 나머지. 남은 것이 없으면 빈 글이다."""
    return ' '.join(sentence for sentence in sentences(text) if not mechanical(sentence) and not dangling(sentence))


def plain_name(name: str) -> str:
    """이름에서 수치가 든 괄호를 지운다. "Fire Breath (Recharge 5-6)" 는 "Fire Breath" 다."""
    return NUMBERED_PARENS.sub('', name).strip()


def fit(parts: Iterable[str], limit: int = REFERENCE_CONTENT_MAX_LENGTH) -> str:
    """
    조각들을 차례대로 잇되 limit 자를 넘지 않게 한다. 넘는 조각은 문장째로 자른다.

    한 조각 안에서도 들어가는 문장까지는 넣는다. 들어가지 않는 문장이 나오면 거기서 멈춘다.
    뒤의 것이 앞의 것보다 덜 중요하다.
    """
    used: list[str] = []
    length = 0
    for part in parts:
        for sentence in SENTENCE_END.split(part.strip()):
            if not sentence:
                continue
            extra = len(sentence) + (1 if used else 0)
            if length + extra > limit:
                return ' '.join(used)
            used.append(sentence)
            length += extra
    return ' '.join(used)


def named_lines(title: str, abilities: Sequence[Mapping[str, Any]]) -> str:
    """
    특성이나 행동들을 "Title: 이름 — 설명; 이름." 한 조각으로. 설명은 판정의 문장을 뺀 것이다.

    설명이 다 빠지면 이름만 남는다. 없으면 빈 글이다.
    """
    lines = []
    for ability in abilities:
        name = plain_name(ability['name'])
        story = narrative(ability.get('desc', '')).rstrip('.')
        lines.append(f'{name} — {story}' if story else name)
    if not lines:
        return ''
    return f'{title}: {"; ".join(lines)}.'


def joined(values: Iterable[str]) -> str:
    """값들을 쉼표로 잇는다."""
    return ', '.join(value for value in values if value)


# --- 몬스터 ---


def monster_header(monster: Mapping[str, Any]) -> str:
    """ "Large aberration, lawful evil." 처럼 크기, 종류, 성향."""
    kind = monster['type']
    if monster.get('subtype'):
        kind = f'{kind} ({monster["subtype"]})'
    return f'{monster["size"]} {kind}, {monster["alignment"]}.'


def monster_senses(monster: Mapping[str, Any]) -> str:
    """움직이는 방식, 감각, 언어. 거리와 수동 감지 수치는 뺀다."""
    moves = [mode for mode, value in monster.get('speed', {}).items() if value and mode != 'hover']
    senses = [sense.replace('_', ' ') for sense in monster.get('senses', {}) if sense != 'passive_perception']
    parts = [f'Moves: {joined(moves)}.' if moves else '']
    parts.append(f'Senses: {joined(senses)}.' if senses else '')
    languages = monster.get('languages', '').strip()
    if languages and languages not in {'-', '—'}:
        parts.append(f'Languages: {NUMBERED_PARENS.sub("", languages).rstrip(".")}.')
    return ' '.join(part for part in parts if part)


def monster_content(monster: Mapping[str, Any]) -> str:
    """몬스터의 서술용 글. 생김새(있으면), 종류, 감각, 특성, 행동, 반응, 전설 행동의 차례다."""
    return fit(
        [
            monster_header(monster),
            narrative(monster.get('desc', '') or ''),
            monster_senses(monster),
            named_lines('Traits', monster.get('special_abilities', [])),
            named_lines('Actions', monster.get('actions', [])),
            named_lines('Reactions', monster.get('reactions', [])),
            named_lines('Legendary actions', monster.get('legendary_actions', [])),
        ]
    )


def armor_class(monster: Mapping[str, Any]) -> int | None:
    """원본의 방어도 중 첫 값. 없으면 None."""
    values = monster.get('armor_class') or []
    return values[0]['value'] if values else None


def proficiencies(monster: Mapping[str, Any], prefix: str) -> dict[str, int]:
    """숙련(내성 굴림, 기술)의 이름에서 보너스로. prefix 는 'saving-throw-' 나 'skill-' 이다."""
    found = {}
    for entry in monster.get('proficiencies', []):
        index = entry['proficiency']['index']
        if index.startswith(prefix):
            found[index.removeprefix(prefix)] = entry['value']
    return found


def attack_of(action: Mapping[str, Any]) -> dict[str, Any]:
    """행동 하나의 수치. 명중 보너스, 피해(주사위와 종류), 난이도(능력과 값). 없는 칸은 싣지 않는다."""
    attack: dict[str, Any] = {'name': plain_name(action['name'])}
    if 'attack_bonus' in action:
        attack['attack_bonus'] = action['attack_bonus']
    damage = [
        {'dice': part['damage_dice'], 'type': part['damage_type']['index']}
        for part in action.get('damage', [])
        if 'damage_dice' in part and 'damage_type' in part
    ]
    if damage:
        attack['damage'] = damage
    if 'dc' in action:
        attack['dc'] = {'ability': action['dc']['dc_type']['index'], 'value': action['dc']['dc_value']}
    return attack


def names_of(values: Iterable[Any]) -> list[str]:
    """원본의 목록(이름표 사전이거나 글)을 이름들로."""
    return [value['index'] if isinstance(value, Mapping) else str(value) for value in values]


def monster_data(monster: Mapping[str, Any]) -> dict[str, Any]:
    """몬스터의 수치. 서술자에게 가지 않는다. srd5 룰북의 시트를 채울 때 쓴다."""
    return {
        'size': monster['size'],
        'type': monster['type'],
        'subtype': monster.get('subtype'),
        'alignment': monster['alignment'],
        'armor_class': armor_class(monster),
        'hit_points': monster['hit_points'],
        'hit_dice': monster['hit_dice'],
        'speed': dict(monster.get('speed', {})),
        'abilities': {
            ability: monster[ability]
            for ability in ('strength', 'dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma')
        },
        'saving_throws': proficiencies(monster, 'saving-throw-'),
        'skills': proficiencies(monster, 'skill-'),
        'damage_vulnerabilities': names_of(monster.get('damage_vulnerabilities', [])),
        'damage_resistances': names_of(monster.get('damage_resistances', [])),
        'damage_immunities': names_of(monster.get('damage_immunities', [])),
        'condition_immunities': names_of(monster.get('condition_immunities', [])),
        'challenge_rating': monster['challenge_rating'],
        'xp': monster['xp'],
        'actions': [attack_of(action) for action in monster.get('actions', [])],
    }


def monster_record(monster: Mapping[str, Any]) -> ReferenceRecord:
    """몬스터 하나를 참고 자료의 줄로."""
    return ReferenceRecord(
        key=f'monsters/{monster["index"]}',
        kind=ReferenceKind.MONSTER,
        name=monster['name'],
        content=monster_content(monster),
        data=monster_data(monster),
    )


# --- 장비 ---


def equipment_kind(item: Mapping[str, Any]) -> str:
    """장비의 갈래를 글로. "Martial Melee weapon", "Heavy armor", "Waterborne Vehicles" 처럼."""
    category = item['equipment_category']['index']
    if category == 'weapon':
        return f'{item["category_range"]} weapon'
    if category == 'armor':
        return f'{item["armor_category"]} armor'
    if 'vehicle_category' in item:
        return item['vehicle_category']
    if 'tool_category' in item:
        return item['tool_category']
    if 'gear_category' in item:
        return f'Adventuring gear ({item["gear_category"]["name"]})'
    return item['equipment_category']['name']


def equipment_traits(item: Mapping[str, Any]) -> str:
    """무기가 내는 상처의 종류와 속성. 무기가 아니면 빈 글이다."""
    parts = []
    if 'damage' in item:
        # "damage" 는 판정의 낱말이라 쓰지 않는다(MECHANICS). 상처의 종류만 적는다
        parts.append(f'Deals {item["damage"]["damage_type"]["index"]} wounds.')
    properties = [prop['name'] for prop in item.get('properties', [])]
    if properties:
        parts.append(f'Properties: {joined(properties)}.')
    return ' '.join(parts)


def equipment_content(item: Mapping[str, Any]) -> str:
    """장비의 서술용 글. 갈래, 무기의 속성, 설명(판정의 문장을 뺀 것)의 차례다."""
    return fit([f'{equipment_kind(item)}.', equipment_traits(item), narrative('\n'.join(item.get('desc', [])))])


# 장비의 칸 중 그대로 옮기는 것
COPIED_EQUIPMENT_KEYS = (
    'cost',
    'weight',
    'range',
    'throw_range',
    'armor_class',
    'str_minimum',
    'stealth_disadvantage',
    'speed',
)


def equipment_data(item: Mapping[str, Any]) -> dict[str, Any]:
    """장비의 수치. 원본의 칸 중 이 게임에 옮길 만한 것만 이름을 정리해 담는다."""
    data: dict[str, Any] = {'category': item['equipment_category']['index']}
    for key in ('weapon_category', 'weapon_range', 'armor_category', 'vehicle_category', 'tool_category'):
        if key in item:
            data[key] = item[key]
    if 'gear_category' in item:
        data['gear_category'] = item['gear_category']['index']
    for key in COPIED_EQUIPMENT_KEYS:
        if key in item:
            data[key] = item[key]
    for key in ('damage', 'two_handed_damage'):
        if key in item:
            data[key] = {'dice': item[key]['damage_dice'], 'type': item[key]['damage_type']['index']}
    if item.get('properties'):
        data['properties'] = names_of(item['properties'])
    return data


def equipment_record(item: Mapping[str, Any]) -> ReferenceRecord:
    """장비 하나를 참고 자료의 줄로."""
    return ReferenceRecord(
        key=f'equipment/{item["index"]}',
        kind=ReferenceKind.ITEM,
        name=item['name'],
        content=equipment_content(item),
        data=equipment_data(item),
    )


# --- 마법 물건 ---


def magic_item_content(item: Mapping[str, Any]) -> str:
    """
    마법 물건의 서술용 글. 원본 설명의 첫 줄(갈래와 희귀도, "Wondrous item, uncommon")과 나머지 설명.

    첫 줄은 문장이 아니라 마침표를 붙인다. 첫 줄의 수치가 든 괄호("rare (+1)")는 지운다.
    """
    desc = list(item.get('desc', []))
    head = f'{plain_name(desc[0]).rstrip(".")}.' if desc else ''
    return fit([head, narrative('\n'.join(desc[1:]))])


def magic_item_data(item: Mapping[str, Any]) -> dict[str, Any]:
    """마법 물건의 수치. 갈래, 희귀도, 변형의 이름."""
    return {
        'category': item['equipment_category']['index'],
        'rarity': item['rarity']['name'],
        'variants': [variant['index'] for variant in item.get('variants', [])],
    }


def magic_item_record(item: Mapping[str, Any]) -> ReferenceRecord:
    """마법 물건 하나를 참고 자료의 줄로."""
    return ReferenceRecord(
        key=f'magic-items/{item["index"]}',
        kind=ReferenceKind.ITEM,
        name=item['name'],
        content=magic_item_content(item),
        data=magic_item_data(item),
    )


def srd_records(
    monsters: Iterable[Mapping[str, Any]],
    equipment: Iterable[Mapping[str, Any]],
    magic_items: Iterable[Mapping[str, Any]],
) -> list[ReferenceRecord]:
    """세 원본을 참고 자료의 줄들로. 몬스터, 장비, 마법 물건의 차례이고 그 안은 원본의 차례다. 변형은 뺀다."""
    records = [monster_record(monster) for monster in monsters]
    records.extend(equipment_record(item) for item in equipment)
    records.extend(magic_item_record(item) for item in magic_items if not item.get('variant'))
    return records


# 데이터 파일에 적는 출처 표시. README 의 출처 표시와 같은 글이다
SRD51_ATTRIBUTION = (
    'This work includes material taken from the System Reference Document 5.1 ("SRD 5.1") by Wizards of the Coast LLC '
    'and available at https://dnd.wizards.com/resources/systems-reference-document. '
    'The SRD 5.1 is licensed under the Creative Commons Attribution 4.0 International License '
    'available at https://creativecommons.org/licenses/by/4.0/legalcode.'
)
# 원본의 이름. SRD 5.1 을 JSON 으로 옮긴 저장소다
SRD51_DATASET = '5e-bits/5e-database src/2014/en'
# 원본을 바꾼 것. 출처 표시와 함께 보인다(CC BY 4.0)
SRD51_CHANGES = 'Rules numbers and game mechanics were removed and the text was shortened.'
SRD51_TRANSLATED = ' Names and text were translated into Korean.'


def srd_changes(records: list[ReferenceRecord]) -> str:
    """원본을 바꾼 것. 한국어로 옮긴 줄이 하나라도 있으면 그것도 적는다."""
    translated = any(record.name_ko for record in records)
    return SRD51_CHANGES + (SRD51_TRANSLATED if translated else '')


def srd_document(records: list[ReferenceRecord], revision: str) -> ReferenceDocument:
    """SRD 5.1 의 줄들을 데이터 파일 하나로. revision 은 원본 저장소의 커밋이다."""
    origin = ReferenceOrigin(
        dataset=SRD51_DATASET,
        revision=revision,
        license='CC-BY-4.0',
        attribution=SRD51_ATTRIBUTION,
        changes=srd_changes(records),
    )
    return ReferenceDocument(format=DOCUMENT_FORMAT, source=ReferenceSource.SRD51, origin=origin, entries=records)
