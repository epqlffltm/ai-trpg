# trpg-server/tests/sheets.py

"""
테스트에 쓰는 캐릭터 시트.

게시하려면 시트가 있어야 한다(기본 시트, 프리젠의 시트). 시트가 주제가 아닌 테스트는 여기 것을 그대로 쓴다.
SRD5 템플릿의 규칙에 맞는 시트다. 테스트의 룰북은 모두 그 템플릿으로 만든다.
"""

# 모든 능력치가 10(보정 0)이고 최대 HP 가 10 인 시트
SHEET = {'abilities': {'str': 10, 'dex': 10, 'con': 10, 'int': 10, 'wis': 10, 'cha': 10}, 'max_hp': 10}


def make_sheet(max_hp: int = 10, **scores: int) -> dict:
    """SHEET 에서 몇 능력치의 점수와 최대 HP 만 바꾼 시트를 만든다. 예: make_sheet(str=16, max_hp=12)."""
    return {'abilities': {**SHEET['abilities'], **scores}, 'max_hp': max_hp}


def as_character(sheet: dict) -> dict:
    """캐릭터의 시트로 읽어 돌려줄 때의 모양. 아는 기술(#805)을 적지 않았으면 빈 목록이 붙는다."""
    return {'skills': [], **sheet}


def handed_out(sheet: dict) -> dict:
    """
    테이블이 이 시트를 막 줬을 때 응답에 실리는 모양. 게임을 시작할 때의 시트다.

    그 사람의 첫 캐릭터이고, HP 는 가득 차 있고, 죽음의 굴림은 센 것이 없고, 살아 있고, 입은 부상이 없다.
    판에 시작 소지품이 없으면 가진 것도 없다. 판에 화폐가 없으면 돈도 없다. 판에 맵이 없으면 서 있는 곳도 없다.
    판에 시작할 때의 착용이 없으면 착용한 것도 없다. 규칙에 수치(#804)가 없으면 수치도 없다.
    시트에 아는 기술(#805)이 적혀 있지 않으면 아는 기술도 없다.
    """
    fresh = {'number': 1, 'hp': sheet['max_hp'], 'death_successes': 0, 'death_failures': 0, 'dead': False}
    return {
        'skills': [],
        **sheet,
        **fresh,
        'injuries': [],
        'items': [],
        'worn': [],
        'money': 0,
        'place_id': None,
        'resources': [],
    }
