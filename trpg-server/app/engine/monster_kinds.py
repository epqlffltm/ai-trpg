# trpg-server/app/engine/monster_kinds.py

"""
몬스터의 타입. 엔진이 다르게 다룰 것만 나눈다.

엔진의 규칙(app/engine/ruleset.py 의 타입마다의 면역, #886)이 이 타입을 가리켜야 해서 엔진에 둔다.
도감(app/assets/bestiaries/models.py)은 여기서 가져다 쓴다.
"""

import enum


class MonsterKind(enum.StrEnum):
    """
    몬스터의 타입. 엔진이 다르게 다룰 것만 나눈다. 자유 태그로 두지 않는다. 서버가 타입마다 다르게 다룰 수 없게 된다.

    타입마다 엔진이 하는 일(예: 언데드와 구조물에는 치료가 듣지 않는다)은 판정에 몬스터를 붙일 때 정한다.
    그때 값을 다시 본다. 지금은 값만 받는다. 세세한 생물 분류는 로어북의 종족 항목이 글로 맡는다.
    """

    # 사람처럼 생각하고 말하는 것. 도적, 고블린
    HUMANOID = 'humanoid'
    # 짐승. 늑대, 큰 거미
    BEAST = 'beast'
    # 죽었다가 움직이는 것. 해골, 망령
    UNDEAD = 'undead'
    # 만들어진 것. 골렘, 움직이는 갑옷
    CONSTRUCT = 'construct'
    # 위의 어느 것도 아닌 것. 정하지 않으면 이것이다
    OTHER = 'other'
