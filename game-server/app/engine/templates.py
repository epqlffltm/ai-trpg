# game-server/app/engine/templates.py

"""
미리 채워 둔 규칙(템플릿).

룰북을 만들 때 템플릿 하나를 고른다. 그 값이 룰북에 복사된다(app/assets/rulebooks/service.py).
복사한 뒤에는 룰북의 것이다. 템플릿을 다시 보지 않는다.

이미 내놓은 템플릿의 값은 고치지 않는다. 고치고 싶으면 새 이름으로 하나 더 낸다.
옛 판을 읽을 때 "그때의 규칙"으로 이 값을 쓰기 때문이다(app/assets/scenarios/snapshot.py).
규칙의 모양에 칸이 새로 생기면 템플릿에도 그 칸을 더한다. 있던 값은 그대로 둔다.
그 칸이 없던 때의 룰북과 판에는 같은 값을 채운다(마이그레이션, 판의 올려 읽기).

지금은 하나뿐이다. 제작자가 값을 고쳐 자기 규칙을 만드는 것은 나중에 더한다.
"""

import enum

from app.engine.ruleset import (
    Ability,
    CalledShot,
    CalledShotMode,
    DeathSave,
    Difficulty,
    Effect,
    EffectKind,
    Healing,
    Injury,
    InjuryTable,
    InjuryTriggers,
    Magnitude,
    Modifier,
    PointBuy,
    PointCost,
    Ruleset,
    ScoreRoll,
    TableRow,
)


class Template(enum.StrEnum):
    """고를 수 있는 템플릿."""

    # d20 판정. System Reference Document 5.1 을 본떴다
    SRD5 = 'srd5'


# 능력치 여섯, d20, 난이도 다섯 단계.
# 능력치의 구성과 보정을 구하는 방법, 난이도의 숫자는 System Reference Document 5.1 을 따랐다.
# SRD 5.1 은 Wizards of the Coast LLC 가 CC BY 4.0 으로 공개한 문서다. 출처 표시는 README 에 있다.
# 직업, 레벨, 숙련은 가져오지 않았다. 최대 HP 는 제작자가 시트에 직접 적는다.
# 양의 등급(magnitudes)은 SRD 의 표를 옮긴 것이 아니다. 기준 시트의 최대 HP(10)에 맞춰 이 프로젝트가 정한 값이다.
# 점수제(point_buy)의 총점과 값표는 System Reference Document 5.2.1 을 따랐다. SRD 5.1 에는 점수제가 실려 있지 않다.
# 점수를 주사위로 정하는 법(score_roll)도 같은 문서를 따랐다.
# 죽음의 굴림(death_save)은 SRD 5.1 의 것이다. 눈 1 과 눈 20 의 특별한 결과는 옮기지 않았다(판정과 같다)
# SRD 5.2.1 도 Wizards of the Coast LLC 가 CC BY 4.0 으로 공개한 문서다. 출처 표시는 README 에 있다
# 부상 중 짧은 것(기절, 중독, 실명, 귀먹음)은 SRD 5.1 의 상태 이상(conditions)을 본떴다.
# 효과는 이 엔진의 세 종류로 옮겼고, 풀리기까지의 라운드 수는 이 프로젝트가 정했다.
# 오래 가는 부상, 결손, 후유증, 부상 표, 노려 치기는 SRD 5.1 에 없다. 이 프로젝트가 정한 값이다


def disadvantage(*abilities: str) -> Effect:
    """그 능력들(비우면 모든 능력)의 판정에서 주사위를 두 번 굴려 낮은 눈을 쓴다."""
    return Effect(kind=EffectKind.DISADVANTAGE, abilities=abilities)


def penalty(amount: int, *abilities: str) -> Effect:
    """그 능력들의 판정에 보정 -amount."""
    return Effect(kind=EffectKind.PENALTY, abilities=abilities, amount=amount)


def rows(*entries: tuple[int, int, str | None]) -> tuple[TableRow, ...]:
    """(낮은 눈, 높은 눈, 부상) 들을 표의 줄로."""
    return tuple(TableRow(low=low, high=high, injury=injury) for low, high, injury in entries)


SRD5_INJURIES = (
    # --- 짧은 것. SRD 5.1 의 상태 이상을 본떴다 ---
    Injury(
        key='stunned',
        name='기절',
        fact='정신이 아득해 몸을 가누지 못한다. 아무것도 하지 못한다.',
        effects=(Effect(kind=EffectKind.NO_ACTIONS),),
        healing=Healing.ROUNDS,
        rounds=1,
    ),
    Injury(
        key='poisoned',
        name='중독',
        fact='독이 돌아 몸이 무겁고 속이 뒤집힌다.',
        effects=(disadvantage(),),
        healing=Healing.ROUNDS,
        rounds=3,
    ),
    Injury(
        key='blinded',
        name='실명',
        fact='눈에 피가 들어가 앞을 보지 못한다.',
        effects=(disadvantage('dex', 'wis'),),
        healing=Healing.ROUNDS,
        rounds=3,
    ),
    Injury(
        key='deafened',
        name='귀먹음',
        fact='귀가 멍해 소리를 듣지 못한다.',
        healing=Healing.ROUNDS,
        rounds=3,
    ),
    # --- 오래 가는 것. 나을 때 후유증 표를 굴린다 ---
    Injury(
        key='broken_arm',
        name='팔 골절',
        fact='한쪽 팔이 부러져 제대로 쓰지 못한다.',
        effects=(disadvantage('str'),),
        healing=Healing.HEALS,
        rounds=30,
        aftermath=InjuryTable(sides=20, rows=rows((1, 5, 'crooked_arm'), (6, 20, None))),
        aimable=True,
    ),
    Injury(
        key='leg_wound',
        name='다리 부상',
        fact='다리를 깊이 다쳐 절뚝거린다.',
        effects=(disadvantage('dex'),),
        healing=Healing.HEALS,
        rounds=20,
        aftermath=InjuryTable(sides=20, rows=rows((1, 3, 'limp'), (4, 20, None))),
        aimable=True,
    ),
    # --- 결손과 후유증. 낫지 않는다 ---
    Injury(
        key='lost_left_hand',
        name='왼손 잃음',
        fact='왼손이 없다. 왼손을 쓸 수 없다.',
        effects=(disadvantage('dex'),),
        healing=Healing.PERMANENT,
        aimable=True,
    ),
    Injury(
        key='lost_right_hand',
        name='오른손 잃음',
        fact='오른손이 없다. 오른손을 쓸 수 없다.',
        effects=(disadvantage('dex'),),
        healing=Healing.PERMANENT,
        aimable=True,
    ),
    Injury(
        key='lost_eye',
        name='한쪽 눈 잃음',
        fact='한쪽 눈을 잃어 거리를 잘 가늠하지 못한다.',
        effects=(penalty(2, 'wis'),),
        healing=Healing.PERMANENT,
        aimable=True,
    ),
    Injury(key='deep_scar', name='깊은 흉터', fact='얼굴에 깊은 흉터가 남았다.', healing=Healing.PERMANENT),
    Injury(
        key='crooked_arm',
        name='굽은 팔',
        fact='부러졌던 팔이 굽은 채로 붙었다.',
        effects=(penalty(1, 'str'),),
        healing=Healing.PERMANENT,
    ),
    Injury(
        key='limp', name='절뚝거림', fact='다친 다리를 전다.', effects=(penalty(1, 'dex'),), healing=Healing.PERMANENT
    ),
)

# 큰 타격이나 쓰러짐에 굴리는 표. 절반은 부상이 없다. 손을 잃는 것은 표에 없다. 노려 쳐야만 생긴다
SRD5_INJURY_TABLE = InjuryTable(
    sides=20,
    rows=rows(
        (1, 10, None),
        (11, 12, 'stunned'),
        (13, 13, 'blinded'),
        (14, 14, 'deafened'),
        (15, 16, 'leg_wound'),
        (17, 18, 'broken_arm'),
        (19, 19, 'deep_scar'),
        (20, 20, 'lost_eye'),
    ),
)

SRD5 = Ruleset(
    template=Template.SRD5,
    abilities=(
        Ability(key='str', name='근력'),
        Ability(key='dex', name='민첩'),
        Ability(key='con', name='건강'),
        Ability(key='int', name='지능'),
        Ability(key='wis', name='지혜'),
        Ability(key='cha', name='매력'),
    ),
    score_min=1,
    score_max=20,
    modifier=Modifier(base=10, step=2),
    die=20,
    difficulties=(
        Difficulty(key='very_easy', name='매우 쉬움', target=5),
        Difficulty(key='easy', name='쉬움', target=10),
        Difficulty(key='medium', name='보통', target=15),
        Difficulty(key='hard', name='어려움', target=20),
        Difficulty(key='very_hard', name='매우 어려움', target=25),
    ),
    default_difficulty='medium',
    magnitudes=(
        Magnitude(key='light', name='가벼움', count=1, sides=4),
        Magnitude(key='moderate', name='보통', count=1, sides=8),
        Magnitude(key='heavy', name='심함', count=2, sides=8),
    ),
    # 건강이 최대 HP 에 닿는다. SRD 에서도 건강의 보정이 HP 에 더해진다
    hp_ability='con',
    # 27점으로 8~15 를 산다. 13 까지는 한 점에 1, 14 와 15 는 한 점에 2 다
    point_buy=PointBuy(
        budget=27,
        costs=(
            PointCost(score=8, cost=0),
            PointCost(score=9, cost=1),
            PointCost(score=10, cost=2),
            PointCost(score=11, cost=3),
            PointCost(score=12, cost=4),
            PointCost(score=13, cost=5),
            PointCost(score=14, cost=7),
            PointCost(score=15, cost=9),
        ),
    ),
    # 4d6 을 굴려 높은 셋을 더한다. 3~18 이 나온다. 능력치가 여섯이라 여섯 번 굴린다
    score_roll=ScoreRoll(count=4, sides=6, keep=3),
    # 쓰러진 채로 라운드가 닫힐 때마다 d20 을 굴린다. 10 이상이면 성공이다. 실패 셋이면 죽고, 성공 셋이면 고비를 넘긴다
    death_save=DeathSave(target=10, successes=3, failures=3),
    injuries=SRD5_INJURIES,
    injury_table=SRD5_INJURY_TABLE,
    # 한 번에 최대 HP 의 절반 이상을 잃을 피해와, 쓰러질 때 표를 굴린다. 노려 치기도 된다
    injury_triggers=InjuryTriggers(big_hit_percent=50, downed=True, called_shot=True),
    # 노려 치면 목표값이 5 오른다
    called_shot=CalledShot(mode=CalledShotMode.TARGET_PLUS, amount=5),
)

TEMPLATES: dict[Template, Ruleset] = {Template.SRD5: SRD5}

# 룰북을 만들 때 템플릿을 고르지 않으면 쓰는 것
DEFAULT_TEMPLATE = Template.SRD5


def from_template(template: Template) -> Ruleset:
    """템플릿의 규칙을 돌려준다. 규칙은 고칠 수 없는 값이라 그대로 내줘도 된다."""
    return TEMPLATES[template]
