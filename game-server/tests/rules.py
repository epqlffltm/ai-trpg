# game-server/tests/rules.py

"""
테스트에 쓰는 규칙의 조각.

SRD5 템플릿의 부상은 SRD5 의 능력(근력, 민첩 …)을 가리킨다. 능력치를 다르게 둔 규칙을 만들어 볼 때 이것으로 부상을 뺀다.
"""

# 부상이 없는 규칙의 칸들. 부상 표를 굴리지 않고 노려 치기도 없다
NO_INJURIES = {
    'injuries': [],
    'injury_table': None,
    'injury_triggers': {'big_hit_percent': None, 'downed': False, 'called_shot': False},
    'called_shot': None,
}
