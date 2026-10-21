# trpg-server/app/references/sheets.py

"""
SRD 몬스터의 수치(참고 자료의 data)로 시나리오의 몬스터 시트를 제안한다(#482 4단계). DB 를 모르는 순수한 함수다.

제안만 한다. 저장하지 않는다(2026-10-21 유저 결정). 제작자가 보고 고쳐 시나리오의 monster_sheets 에 적는다.
SRD 의 규칙과 이 엔진의 규칙이 달라서, 숫자를 그대로 옮기지 못하는 것은 가까운 값으로 바꾸고
무엇을 바꿨는지 알린다(notes).

옮기는 법.
  - 능력치: 여섯 점수를 그대로. 규칙의 범위(srd5 는 1~20)를 넘으면 끝으로 붙인다(용의 근력 27 → 20).
  - 최대 HP: 원본의 HP 그대로. 시트의 상한(999)을 넘지 않는다.
  - 공격: 명중 보너스가 있는 행동만(숨결처럼 내성으로 막는 것은 빼고, 다중 공격도 뺀다). 5개까지.
    - 능력치: 근력과 민첩 중 명중 보너스를 더 잘 설명하는 것(보너스 - 숙련 보너스 - 그 능력치의 보정이 0 에 가까운 것).
    - 난이도: 이 엔진에서 몬스터는 "주사위 + 능력치의 보정 ≥ 난이도"로 맞힌다. SRD 는 "주사위 + 명중 보너스 ≥ 방어도"다.
      흔한 방어도(ASSUMED_ARMOR)를 두고 맞힐 확률이 같아지는 값(방어도 - 보너스 + 보정)에 가장 가까운 난이도다.
    - 피해의 등급: 원본의 피해 주사위의 평균에 평균이 가장 가까운 등급이다. 피해를 알 수 없으면 가운데 등급이다.
    - 이름: 흔한 이름은 한국어로 옮긴다(ATTACK_NAMES). 없으면 원본의 이름이다.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.assets.models import ATTACK_NAME_MAX_LENGTH, MONSTER_MAX_ATTACKS
from app.assets.scenarios.schemas import MonsterAttack
from app.engine.check import modifier_of
from app.engine.ruleset import Difficulty, Magnitude, Ruleset
from app.engine.sheet import SHEET_MAX_HP, Sheet

# 원본의 능력치 이름에서 srd5 규칙의 이름표로
ABILITY_KEYS = {
    'strength': 'str',
    'dexterity': 'dex',
    'constitution': 'con',
    'intelligence': 'int',
    'wisdom': 'wis',
    'charisma': 'cha',
}
# 맞힐 확률을 맞출 때 두는 방어도. SRD 의 낮은 레벨 캐릭터의 흔한 방어도(가죽 갑옷 + 민첩, 사슬 셔츠)쯤이다
ASSUMED_ARMOR = 13
# 원본의 피해 주사위("2d6+5", "1d12")와 정해진 피해("1")
DICE = re.compile(r'^\s*(\d+)d(\d+)\s*([+-]\s*\d+)?\s*$')
FIXED = re.compile(r'^\s*(\d+)\s*$')
# 공격의 능력치로 고르는 것. 무기와 이빨, 발톱은 근력이나 민첩으로 맞힌다(SRD 5.1)
ATTACK_ABILITIES = ('str', 'dex')
# 흔한 공격의 이름. 원본에 쓰인 횟수가 많은 것부터다. 없는 이름은 원본 그대로 둔다
ATTACK_NAMES = {
    'Bite': '물기',
    'Bites': '물기',
    'Claw': '발톱',
    'Claws': '발톱',
    'Tail': '꼬리',
    'Slam': '후려치기',
    'Hooves': '발굽',
    'Beak': '부리',
    'Shortsword': '소검',
    'Longsword': '장검',
    'Longbow': '장궁',
    'Rock': '바위',
    'Scimitar': '시미터',
    'Talons': '발톱',
    'Spear': '창',
    'Greataxe': '대도끼',
    'Gore': '들이받기',
    'Dagger': '단검',
    'Ram': '들이받기',
    'Fist': '주먹',
    'Pseudopod': '위족',
    'Sting': '침',
    'Javelin': '투창',
    'Greatsword': '대검',
    'Club': '곤봉',
    'Constrict': '조이기',
    'Morningstar': '모닝스타',
    'Mace': '철퇴',
    'Hand Crossbow': '손쇠뇌',
    'Shortbow': '단궁',
    'Heavy Crossbow': '중쇠뇌',
    'Light Crossbow': '경쇠뇌',
    'Tentacle': '촉수',
    'Tentacles': '촉수',
    'Stomp': '짓밟기',
    'Greatclub': '대곤봉',
    'Glaive': '글레이브',
    'Tusk': '엄니',
    'Horns': '뿔',
    'Pincer': '집게',
    'War Pick': '전투 곡괭이',
    'Touch': '손길',
    'Quarterstaff': '육척봉',
    'Battleaxe': '전투 도끼',
    'Warhammer': '전쟁 망치',
    'Handaxe': '손도끼',
    'Sling': '투석구',
    'Trident': '삼지창',
    'Pike': '장창',
    'Halberd': '할버드',
    'Maul': '대형 망치',
    'Flail': '도리깨',
    'Rapier': '레이피어',
    'Lance': '랜스',
    'Whip': '채찍',
    'Net': '그물',
    'Web': '거미줄',
    'Life Drain': '생명력 흡수',
    'Hurl Flame': '불꽃 던지기',
}


class RulesNotSrdError(Exception):
    """시나리오의 규칙에 SRD 의 여섯 능력치(이름표)가 없어 옮길 수 없다. missing 은 빠진 이름표다."""

    def __init__(self, missing: list[str]) -> None:
        super().__init__(', '.join(missing))
        self.missing = missing


@dataclass(frozen=True)
class Proposal:
    """제안한 시트와 공격, 그리고 원본과 다르게 옮긴 것들(사람이 읽는 글)."""

    sheet: Sheet
    attacks: list[MonsterAttack]
    notes: list[str]


def check_rules(ruleset: Ruleset) -> None:
    """규칙에 SRD 의 여섯 능력치가 있는지 본다. 없으면 RulesNotSrdError 다."""
    keys = {ability.key for ability in ruleset.abilities}
    missing = [key for key in ABILITY_KEYS.values() if key not in keys]
    if missing:
        raise RulesNotSrdError(missing)


def proposed_scores(ruleset: Ruleset, data: Mapping[str, Any]) -> tuple[dict[str, int], list[str]]:
    """
    능력치의 점수와 알릴 것. 규칙에 SRD 에 없는 능력치가 더 있으면 그 점수는 규칙의 가운데로 둔다.

    범위를 넘는 점수는 끝으로 붙인다.
    """
    original = {ABILITY_KEYS[name]: int(score) for name, score in data.get('abilities', {}).items()}
    middle = (ruleset.score_min + ruleset.score_max) // 2
    scores: dict[str, int] = {}
    notes: list[str] = []
    for ability in ruleset.abilities:
        score = original.get(ability.key, middle)
        fitted = min(max(score, ruleset.score_min), ruleset.score_max)
        if fitted != score:
            notes.append(f'{ability.name} {score} 을(를) 규칙의 범위에 맞춰 {fitted} 로 바꿨다.')
        if ability.key not in original:
            notes.append(f'{ability.name} 은(는) 원본에 없어 {middle} 로 두었다.')
        scores[ability.key] = fitted
    return scores, notes


def proposed_hp(data: Mapping[str, Any]) -> tuple[int, list[str]]:
    """최대 HP 와 알릴 것. 시트의 범위(1~999) 안이다."""
    original = int(data.get('hit_points', 1))
    fitted = min(max(original, 1), SHEET_MAX_HP)
    notes = [] if fitted == original else [f'HP {original} 을(를) 시트의 상한에 맞춰 {fitted} 로 바꿨다.']
    return fitted, notes


def proficiency_of(challenge: float) -> int:
    """도전 지수의 숙련 보너스(SRD 5.1). 0~4 는 +2, 넷마다 1 씩 오른다."""
    return 2 + max(0, (int(challenge) - 1) // 4)


def dice_average(dice: str) -> float | None:
    """피해 주사위 하나("2d6+5")나 정해진 피해("1")의 평균. 읽지 못하면 None 이다."""
    fixed = FIXED.match(dice)
    if fixed is not None:
        return float(fixed.group(1))
    found = DICE.match(dice)
    if found is None:
        return None
    count, sides, bonus = found.groups()
    return int(count) * (int(sides) + 1) / 2 + (int(bonus.replace(' ', '')) if bonus else 0)


def damage_average(action: Mapping[str, Any]) -> float | None:
    """행동의 피해 평균(여러 종류면 더한다). 피해가 없거나 읽지 못하면 None 이다."""
    averages = [dice_average(str(part.get('dice', ''))) for part in action.get('damage', [])]
    known = [average for average in averages if average is not None]
    return sum(known) if known else None


def attack_ability(ruleset: Ruleset, scores: Mapping[str, int], bonus: int, proficiency: int) -> str:
    """
    근력과 민첩 중 명중 보너스를 더 잘 설명하는 능력치(보너스 - 숙련 - 보정이 0 에 가까운 것). 같으면 근력이다.

    원본의 점수로 본다. 주문 공격(지능, 지혜, 매력)은 드물어 따로 고르지 않는다. 제작자가 고친다.
    """
    return min(
        ATTACK_ABILITIES,
        key=lambda key: (abs(bonus - proficiency - modifier_of(ruleset, scores[key])), ATTACK_ABILITIES.index(key)),
    )


def nearest_difficulty(ruleset: Ruleset, target: int) -> Difficulty:
    """목표값이 가장 가까운 난이도. 같으면 쉬운 쪽이다."""
    return min(ruleset.difficulties, key=lambda difficulty: (abs(difficulty.target - target), difficulty.target))


def magnitude_average(magnitude: Magnitude) -> float:
    """등급의 주사위의 평균."""
    return magnitude.count * (magnitude.sides + 1) / 2


def nearest_magnitude(ruleset: Ruleset, average: float | None) -> Magnitude:
    """평균이 가장 가까운 등급. 평균을 모르면 가운데 등급이다. 같으면 약한 쪽이다."""
    ordered = sorted(ruleset.magnitudes, key=magnitude_average)
    if average is None:
        return ordered[len(ordered) // 2]
    return min(ordered, key=lambda magnitude: abs(magnitude_average(magnitude) - average))


def attack_name(original: str) -> str:
    """공격의 이름. 흔한 이름은 한국어로, 아니면 원본 그대로다. 30자까지다."""
    return ATTACK_NAMES.get(original, original)[:ATTACK_NAME_MAX_LENGTH].strip()


def proposed_attack(
    ruleset: Ruleset,
    original: Mapping[str, int],
    fitted: Mapping[str, int],
    action: Mapping[str, Any],
    proficiency: int,
) -> tuple[MonsterAttack, list[str]]:
    """
    명중 보너스가 있는 행동 하나를 공격으로. 알릴 것도 돌려준다.

    능력치는 원본의 점수로 고르고, 난이도는 시트의 점수(범위에 맞춘 것)의 보정으로 맞춘다. 판정은 시트의 점수로 한다.
    """
    bonus = int(action['attack_bonus'])
    ability = attack_ability(ruleset, original, bonus, proficiency)
    difficulty = nearest_difficulty(ruleset, ASSUMED_ARMOR - bonus + modifier_of(ruleset, fitted[ability]))
    average = damage_average(action)
    magnitude = nearest_magnitude(ruleset, average)
    name = attack_name(str(action['name']))
    notes = [] if average is not None else [f'{name}: 피해를 알 수 없어 {magnitude.name} 등급으로 두었다.']
    return MonsterAttack(name=name, ability=ability, difficulty=difficulty.key, harm=magnitude.key), notes


def proposed_attacks(
    ruleset: Ruleset, original: Mapping[str, int], fitted: Mapping[str, int], data: Mapping[str, Any]
) -> tuple[list[MonsterAttack], list[str]]:
    """공격들과 알릴 것. 명중 보너스가 있는 행동만, 같은 이름은 처음 것만, 5개까지다."""
    proficiency = proficiency_of(float(data.get('challenge_rating', 0)))
    actions: Sequence[Mapping[str, Any]] = data.get('actions', [])
    attacks: list[MonsterAttack] = []
    notes: list[str] = []
    for action in actions:
        if 'attack_bonus' not in action:
            continue
        attack, attack_notes = proposed_attack(ruleset, original, fitted, action, proficiency)
        if attack.name in {chosen.name for chosen in attacks}:
            continue
        if len(attacks) == MONSTER_MAX_ATTACKS:
            notes.append(f'공격이 {MONSTER_MAX_ATTACKS}개를 넘어 앞의 {MONSTER_MAX_ATTACKS}개만 옮겼다.')
            break
        attacks.append(attack)
        notes.extend(attack_notes)
    skipped = [
        str(action['name']) for action in actions if 'attack_bonus' not in action and action['name'] != 'Multiattack'
    ]
    if skipped:
        notes.append(f'명중으로 맞히지 않는 행동은 옮기지 않았다: {", ".join(skipped)}.')
    return attacks, notes


def propose(ruleset: Ruleset, data: Mapping[str, Any]) -> Proposal:
    """몬스터의 수치(참고 자료의 data)로 이 규칙의 시트와 공격을 제안한다. SRD 의 능력치가 없으면 RulesNotSrdError."""
    check_rules(ruleset)
    fitted, score_notes = proposed_scores(ruleset, data)
    original = {ABILITY_KEYS[name]: int(score) for name, score in data.get('abilities', {}).items()}
    original = {key: original.get(key, fitted[key]) for key in fitted}
    max_hp, hp_notes = proposed_hp(data)
    attacks, attack_notes = proposed_attacks(ruleset, original, fitted, data)
    return Proposal(
        sheet=Sheet(abilities=fitted, max_hp=max_hp), attacks=attacks, notes=score_notes + hp_notes + attack_notes
    )
