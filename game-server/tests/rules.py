# game-server/tests/rules.py

"""
테스트에 쓰는 규칙의 조각.

SRD5 템플릿의 부상은 SRD5 의 능력(근력, 민첩 …)을 가리킨다. 능력치를 다르게 둔 규칙을 만들어 볼 때 이것으로 부상을 뺀다.
SRD5 템플릿의 치료는 SRD5 의 난이도(어려움, 보통)와 능력(지혜)을 가리킨다. 난이도만 다르게 둔 규칙은 치료를 뺀다.
"""

from app.engine.templates import SRD5

# 부상이 없는 규칙의 칸들. 부상 표를 굴리지 않고 노려 치기도 없다
NO_INJURIES = {
    'injuries': [],
    'injury_table': None,
    'injury_triggers': {'big_hit_percent': None, 'downed': False, 'called_shot': False},
    'called_shot': None,
    'treatment': None,
}

# 치료가 없는 규칙의 칸들. 부상은 그대로 두고 어느 부상도 치료할 수 없게 한다
NO_TREATMENT = {
    'injuries': [
        {**injury, 'treat_difficulty': None, 'treat_rounds': None}
        for injury in SRD5.model_dump(mode='json')['injuries']
    ],
    'treatment': None,
}
