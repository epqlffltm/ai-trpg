# game-server/app/engine/templates.py

"""
미리 채워 둔 규칙(템플릿).

룰북을 만들 때 템플릿 하나를 고른다. 그 값이 룰북에 복사된다(app/assets/rulebooks/service.py).
복사한 뒤에는 룰북의 것이다. 템플릿을 다시 보지 않는다.

이미 내놓은 템플릿의 값은 고치지 않는다. 고치고 싶으면 새 이름으로 하나 더 낸다.
옛 판을 읽을 때 "그때의 규칙"으로 이 값을 쓰기 때문이다(app/assets/scenarios/snapshot.py).

지금은 하나뿐이다. 제작자가 값을 고쳐 자기 규칙을 만드는 것은 나중에 더한다.
"""

import enum

from app.engine.ruleset import Ability, Difficulty, Modifier, Ruleset


class Template(enum.StrEnum):
    """고를 수 있는 템플릿."""

    # d20 판정. System Reference Document 5.1 을 본떴다
    SRD5 = 'srd5'


# 능력치 여섯, d20, 난이도 다섯 단계.
# 능력치의 구성과 보정을 구하는 방법, 난이도의 숫자는 System Reference Document 5.1 을 따랐다.
# SRD 5.1 은 Wizards of the Coast LLC 가 CC BY 4.0 으로 공개한 문서다. 출처 표시는 README 에 있다.
# 직업, 레벨, 숙련은 가져오지 않았다. 최대 HP 는 제작자가 시트에 직접 적는다
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
)

TEMPLATES: dict[Template, Ruleset] = {Template.SRD5: SRD5}

# 룰북을 만들 때 템플릿을 고르지 않으면 쓰는 것
DEFAULT_TEMPLATE = Template.SRD5


def from_template(template: Template) -> Ruleset:
    """템플릿의 규칙을 돌려준다. 규칙은 고칠 수 없는 값이라 그대로 내줘도 된다."""
    return TEMPLATES[template]
