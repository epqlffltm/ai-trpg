# trpg-server/app/assets/scenarios/upgrades.py

"""
판의 옛 형식을 지금의 형식으로 올려 읽는 함수들.

판은 고치지 않는다. 모양이 바뀌어도 이미 굳힌 문서는 옛 모양 그대로 DB 에 남는다(app/assets/scenarios/snapshot.py).
읽을 때 형식 번호를 보고, 바로 다음 형식으로 올리는 함수(upgrade_from_N)를 차례로 거쳐 지금의 모양으로 만든다.
받은 문서를 고치지 않고 새 dict 를 만든다.

형식을 올릴 때 하는 일은 셋이다.
  1. snapshot.py 의 SNAPSHOT_FORMAT 을 올리고 그 위의 형식 목록에 한 줄을 적는다.
  2. 여기에 upgrade_from_N 을 더하고 UPGRADES 에 한 줄을 적는다.
  3. 칸이 새로 생긴 것이면, 그 칸이 없던 때의 판을 무엇으로 읽을지 정한다. 대개는 그때의 SRD5 템플릿의 값이다.
이미 내놓은 함수는 고치지 않는다. 옛 판을 읽는 길이 바뀌면 같은 판이 다르게 읽힌다.

여기의 함수는 DB 도 지금의 모양(Snapshot)도 모른다. dict 를 받아 dict 를 돌려준다.
"""

from collections.abc import Callable

from app.assets.models import (
    DEFAULT_NARRATION_STYLE,
    DEFAULT_ROUND_MINUTES,
    DEFAULT_START_DAY,
    DEFAULT_START_HOUR,
    TABLE_MAX_PLAYERS,
    LoreKind,
)
from app.engine.templates import SRD5

# 시트가 없던 때의 판을 읽을 때 채우는 숫자. 모든 능력치가 이 점수이고, 최대 HP 가 이 값이다.
# 그때의 규칙은 SRD5 템플릿뿐이었다. 10 은 그 규칙에서 보정이 0 인 점수다
BASELINE_SCORE = 10


BASELINE_MAX_HP = 10


def upgrade_from_1(document: dict) -> dict:
    """형식 1 의 문서를 형식 2 로 올린다. 하나뿐이던 도입부가 첫 번째 스타팅이 된다."""
    upgraded = {key: value for key, value in document.items() if key != 'opening'}
    upgraded['openings'] = [document['opening']]
    upgraded['format'] = 2
    return upgraded


def upgrade_from_2(document: dict) -> dict:
    """
    형식 2 의 문서를 형식 3 으로 올린다.

    그때는 추천 인원과 프리젠이 없었다. 추천 인원은 "몇 명이든 된다"로, 프리젠은 없는 것으로 읽는다.
    """
    upgraded = dict(document)
    upgraded['recommended_players'] = {'min': 1, 'max': TABLE_MAX_PLAYERS}
    upgraded['pregens'] = []
    upgraded['format'] = 3
    return upgraded


def upgrade_from_3(document: dict) -> dict:
    """
    형식 3 의 문서를 형식 4 로 올린다.

    그때는 룰북에 규칙이 없었다. 그때 만든 룰북이 지금 받았을 규칙(SRD5 템플릿)으로 읽는다.
    DB 의 룰북에도 같은 값을 채웠다(마이그레이션). 내놓은 템플릿의 값은 고치지 않으므로 읽을 때마다 같다.

    지금의 SRD5 에는 나중에 생긴 칸(magnitudes, hp_ability, point_buy, score_roll, death_save, 부상의 칸들)도 들어 있다.
    뒤의 단계가 같은 값으로 다시 채우므로 결과는 같다.
    """
    upgraded = dict(document)
    upgraded['rulebook'] = {**document['rulebook'], 'rules': SRD5.model_dump(mode='json')}
    upgraded['format'] = 4
    return upgraded


def baseline_sheet(rules: dict) -> dict:
    """규칙의 능력치를 모두 기준 점수로 채운 시트를 문서로 만든다. 시트가 없던 판을 읽을 때 쓴다."""
    abilities = {ability['key']: BASELINE_SCORE for ability in rules['abilities']}
    return {'abilities': abilities, 'max_hp': BASELINE_MAX_HP}


def upgrade_from_4(document: dict) -> dict:
    """
    형식 4 의 문서를 형식 5 로 올린다.

    그때는 캐릭터에 숫자가 없었고, 프리젠을 고를 수도 직접 만들 수도 있었다.
    두 방식을 모두 허용한 것으로 읽고, 프리젠의 시트와 기본 시트는 기준 시트로 읽는다.
    """
    sheet = baseline_sheet(document['rulebook']['rules'])
    upgraded = dict(document)
    upgraded['pregens'] = [{**pregen, 'sheet': sheet} for pregen in document['pregens']]
    # 그때 있던 방식은 이 둘이다. 글자 그대로 적는다. 방식이 나중에 늘어도 옛 판이 허용한 것은 늘지 않는다
    upgraded['character_modes'] = ['pregen', 'custom']
    upgraded['default_sheet'] = sheet
    upgraded['format'] = 5
    return upgraded


def upgrade_from_5(document: dict) -> dict:
    """
    형식 5 의 문서를 형식 6 으로 올린다.

    그때는 규칙에 양의 등급이 없었다. 그때의 규칙은 SRD5 템플릿뿐이었으므로 그 템플릿의 등급으로 읽는다.
    DB 의 룰북에도 같은 값을 채웠다(마이그레이션).
    """
    magnitudes = SRD5.model_dump(mode='json')['magnitudes']
    rulebook = document['rulebook']
    upgraded = dict(document)
    upgraded['rulebook'] = {**rulebook, 'rules': {**rulebook['rules'], 'magnitudes': magnitudes}}
    upgraded['format'] = 6
    return upgraded


def upgrade_from_6(document: dict) -> dict:
    """
    형식 6 의 문서를 형식 7 로 올린다.

    그때는 규칙에 최대 HP 에 닿는 능력치가 없었다. 그때의 규칙은 SRD5 템플릿뿐이었으므로 그 템플릿의 것으로 읽는다.
    DB 의 룰북에도 같은 값을 채웠다(마이그레이션).

    플레이어가 능력치를 정하는 방식도 없었다. 그 방식에 쓰는 값(player_made_hp)은 없는 것으로 읽는다.
    """
    rulebook = document['rulebook']
    upgraded = dict(document)
    upgraded['player_made_hp'] = None
    upgraded['rulebook'] = {**rulebook, 'rules': {**rulebook['rules'], 'hp_ability': SRD5.hp_ability}}
    upgraded['format'] = 7
    return upgraded


def upgrade_from_7(document: dict) -> dict:
    """
    형식 7 의 문서를 형식 8 로 올린다.

    그때는 규칙에 점수제가 없었다. 그때의 규칙은 SRD5 템플릿뿐이었으므로 그 템플릿의 것으로 읽는다.
    DB 의 룰북에도 같은 값을 채웠다(마이그레이션).
    규칙에 점수제가 있다고 그 판에서 점수제를 쓸 수 있는 것은 아니다. 판이 허용한 방식(character_modes)은 그대로다.
    """
    point_buy = SRD5.model_dump(mode='json')['point_buy']
    rulebook = document['rulebook']
    upgraded = dict(document)
    upgraded['rulebook'] = {**rulebook, 'rules': {**rulebook['rules'], 'point_buy': point_buy}}
    upgraded['format'] = 8
    return upgraded


def upgrade_from_8(document: dict) -> dict:
    """
    형식 8 의 문서를 형식 9 로 올린다.

    그때는 규칙에 점수를 주사위로 정하는 법이 없었다. 그때의 규칙은 SRD5 템플릿뿐이었으므로 그 템플릿의 것으로 읽는다.
    DB 의 룰북에도 같은 값을 채웠다(마이그레이션).
    규칙에 그 법이 있다고 그 판에서 주사위로 정할 수 있는 것은 아니다. 판이 허용한 방식(character_modes)은 그대로다.

    주사위로 정하는 방식이 없었으니 다시 굴리기도 없었다. 다시 굴리게 해 줄 수 없는 것으로 읽는다.
    """
    score_roll = SRD5.model_dump(mode='json')['score_roll']
    rulebook = document['rulebook']
    upgraded = dict(document)
    upgraded['reroll_allowed'] = False
    upgraded['rulebook'] = {**rulebook, 'rules': {**rulebook['rules'], 'score_roll': score_roll}}
    upgraded['format'] = 9
    return upgraded


def upgrade_from_9(document: dict) -> dict:
    """
    형식 9 의 문서를 형식 10 으로 올린다.

    그때는 규칙에 죽음의 굴림이 없었다. 쓰러진 캐릭터는 죽지 않고 쓰러진 채로 있었다.
    그때의 규칙은 SRD5 템플릿뿐이었으므로 그 템플릿의 것으로 읽는다. DB 의 룰북에도 같은 값을 채웠다(마이그레이션).
    이미 진행 중인 테이블도 이 형식으로 올려 읽는다. 그 테이블에서 쓰러져 있던 캐릭터는 다음 라운드부터 굴린다.
    """
    death_save = SRD5.model_dump(mode='json')['death_save']
    rulebook = document['rulebook']
    upgraded = dict(document)
    upgraded['rulebook'] = {**rulebook, 'rules': {**rulebook['rules'], 'death_save': death_save}}
    upgraded['format'] = 10
    return upgraded


def upgrade_from_10(document: dict) -> dict:
    """
    형식 10 의 문서를 형식 11 로 올린다.

    그때는 추천 문체가 없었다. 문체를 지시하지 않았지만, 지금 제작자가 고르지 않았을 때와 같은 정통으로 읽는다.
    이미 진행 중인 테이블도 이 형식으로 올려 읽는다. 방장이 문체를 고르지 않았으면 다음 서술부터 정통이다.
    """
    upgraded = dict(document)
    upgraded['narration_style'] = DEFAULT_NARRATION_STYLE.value
    upgraded['format'] = 11
    return upgraded


def upgrade_from_11(document: dict) -> dict:
    """
    형식 11 의 문서를 형식 12 로 올린다.

    그때는 로어북 항목에 종류가 없었다. 모두 기타로 읽는다. DB 의 항목에도 같은 값을 채웠다(마이그레이션).
    기타는 지금까지와 똑같이 다룬다. 이미 진행 중인 테이블의 서술도 바뀌지 않는다.
    """
    upgraded = dict(document)
    upgraded['lorebooks'] = [
        {**lorebook, 'entries': [{**entry, 'kind': LoreKind.OTHER.value} for entry in lorebook['entries']]}
        for lorebook in document['lorebooks']
    ]
    upgraded['format'] = 12
    return upgraded


def upgrade_from_12(document: dict) -> dict:
    """
    형식 12 의 문서를 형식 13 으로 올린다.

    그때는 NPC 에 숫자가 없었다. NPC 시트는 없는 것으로, 기본 NPC 시트는 기준 시트로 읽는다.
    인물 항목은 모두 기본 NPC 시트를 쓴다. 이미 진행 중인 테이블은 시작할 때 NPC 의 상태를 만들지 않았으므로
    읽는 모양만 바뀐다.
    """
    upgraded = dict(document)
    upgraded['npc_sheets'] = []
    upgraded['default_npc_sheet'] = baseline_sheet(document['rulebook']['rules'])
    upgraded['format'] = 13
    return upgraded


# 부상이 생길 때 규칙에 더해진 칸들
INJURY_FIELDS = ('injuries', 'injury_table', 'injury_triggers', 'called_shot')


def upgrade_from_13(document: dict) -> dict:
    """
    형식 13 의 문서를 형식 14 로 올린다.

    그때는 규칙에 부상이 없었다. 그때의 규칙은 SRD5 템플릿뿐이었으므로 그 템플릿의 부상으로 읽는다.
    DB 의 룰북에도 같은 값을 채웠다(마이그레이션). 이미 진행 중인 테이블도 다음 라운드부터 부상이 생길 수 있다.
    """
    template = SRD5.model_dump(mode='json')
    rulebook = document['rulebook']
    rules = {**rulebook['rules'], **{field: template[field] for field in INJURY_FIELDS}}
    upgraded = dict(document)
    upgraded['rulebook'] = {**rulebook, 'rules': rules}
    upgraded['format'] = 14
    return upgraded


# 치료가 없던 때의 부상에 채우는 칸들
TREATMENT_FIELDS = ('treat_difficulty', 'treat_rounds')


def with_treatment_fields(injury: dict, template_injuries: dict[str, dict]) -> dict:
    """
    부상 하나에 치료의 칸들을 채운다. 이미 있으면 그대로 둔다. 템플릿에 같은 이름의 부상이 있으면 그 값, 없으면 비운다.
    """
    source = template_injuries.get(injury['key'], {})
    return {**{field: source.get(field) for field in TREATMENT_FIELDS}, **injury}


def upgrade_from_14(document: dict) -> dict:
    """
    형식 14 의 문서를 형식 15 로 올린다.

    그때는 규칙에 치료가 없었다. 그때의 규칙은 SRD5 템플릿뿐이었으므로 그 템플릿의 치료와 부상의 치료 칸으로 읽는다.
    DB 의 룰북에도 같은 값을 채웠다(마이그레이션). 이미 진행 중인 테이블도 다음 라운드부터 치료할 수 있다.
    """
    template = SRD5.model_dump(mode='json')
    template_injuries = {injury['key']: injury for injury in template['injuries']}
    rulebook = document['rulebook']
    rules = dict(rulebook['rules'])
    rules['injuries'] = [with_treatment_fields(injury, template_injuries) for injury in rules['injuries']]
    rules['treatment'] = template['treatment']
    upgraded = dict(document)
    upgraded['rulebook'] = {**rulebook, 'rules': rules}
    upgraded['format'] = 15
    return upgraded


def upgrade_from_15(document: dict) -> dict:
    """
    형식 15 의 문서를 형식 16 으로 올린다.

    그때는 로어북 항목에 지목할 이름이 따로 없었다. 모두 비운다. 비어 있으면 항목의 이름 하나가 정답이다.
    DB 의 항목에도 같은 값을 채웠다(마이그레이션의 기본값).
    """
    upgraded = dict(document)
    upgraded['lorebooks'] = [
        {**lorebook, 'entries': [{'true_names': [], **entry} for entry in lorebook['entries']]}
        for lorebook in document['lorebooks']
    ]
    upgraded['format'] = 16
    return upgraded


def upgrade_from_16(document: dict) -> dict:
    """
    형식 16 의 문서를 형식 17 로 올린다.

    그때는 아이템 규칙도 시작 소지품도 없었다. 모두 없는 것으로 읽는다. 물건 항목은 모두 장비다.
    """
    upgraded = dict(document)
    upgraded['items'] = []
    upgraded['starting_items'] = []
    upgraded['pregens'] = [{**pregen, 'items': []} for pregen in document['pregens']]
    upgraded['format'] = 17
    return upgraded


def upgrade_from_17(document: dict) -> dict:
    """
    형식 17 의 문서를 형식 18 로 올린다.

    그때는 퀘스트 규칙이 없었다. 없는 것으로 읽는다. 사건 항목은 모두 숨긴 채로 시작하는 퀘스트다.
    """
    upgraded = dict(document)
    upgraded['quests'] = []
    upgraded['format'] = 18
    return upgraded


def upgrade_from_18(document: dict) -> dict:
    """
    형식 18 의 문서를 형식 19 로 올린다.

    그때는 맵이 없었다. 시작 장소도 길도 없는 것으로 읽는다(위치도 이동도 없는 판이다).
    """
    upgraded = dict(document)
    upgraded['start_place'] = None
    upgraded['routes'] = []
    upgraded['format'] = 19
    return upgraded


def route_visibility(route: dict) -> dict:
    """
    형식 19 의 길 하나를 형식 20 의 모양으로.

    숨긴 길은 숨긴 길, 나머지는 처음부터 아는 길이다(그때는 안개가 없었다).
    """
    upgraded = {key: value for key, value in route.items() if key != 'hidden'}
    upgraded['visibility'] = 'hidden' if route.get('hidden') else 'open'
    return upgraded


def upgrade_from_19(document: dict) -> dict:
    """
    형식 19 의 문서를 형식 20 으로 올린다.

    길의 hidden(참, 거짓)이 visibility 로 바뀌었다. 그때는 명소가 없었다.
    """
    upgraded = dict(document)
    upgraded['routes'] = [route_visibility(route) for route in document.get('routes', [])]
    upgraded['landmarks'] = []
    upgraded['format'] = 20
    return upgraded


def upgrade_from_20(document: dict) -> dict:
    """형식 20 의 문서를 형식 21 로 올린다. 그때는 몬스터가 없었다."""
    upgraded = dict(document)
    upgraded['monsters'] = []
    upgraded['format'] = 21
    return upgraded


def upgrade_from_21(document: dict) -> dict:
    """형식 21 의 문서를 형식 22 로 올린다. 그때는 조우가 없었다."""
    upgraded = dict(document)
    upgraded['encounters'] = []
    upgraded['format'] = 22
    return upgraded


def initiative_of(rules: dict) -> str | None:
    """차례를 정하는 능력치가 없던 규칙에 채울 값. 그 규칙에 SRD5 의 것(민첩)이 있으면 그것, 없으면 None 이다."""
    keys = [ability['key'] for ability in rules['abilities']]
    return SRD5.initiative_ability if SRD5.initiative_ability in keys else None


def upgrade_from_22(document: dict) -> dict:
    """
    형식 22 의 문서를 형식 23 으로 올린다.

    그때는 몬스터에 공격과 네임드 표시가 없었고, 조우에 기습이 없었고, 규칙에 차례를 정하는 능력치가 없었다.
    몬스터는 공격하지 않는 일반 몹으로, 조우는 기습 없음으로, 규칙은 SRD5 의 것(민첩)으로 읽는다.
    DB 의 룰북에도 같은 값을 채웠다(마이그레이션).
    """
    rulebook = document['rulebook']
    upgraded = dict(document)
    upgraded['monsters'] = [{**monster, 'attacks': [], 'unique': False} for monster in document.get('monsters', [])]
    upgraded['encounters'] = [{**encounter, 'surprise': 'none'} for encounter in document.get('encounters', [])]
    rules = rulebook['rules']
    upgraded['rulebook'] = {**rulebook, 'rules': {**rules, 'initiative_ability': initiative_of(rules)}}
    upgraded['format'] = 23
    return upgraded


def upgrade_from_23(document: dict) -> dict:
    """
    형식 23 의 문서를 형식 24 로 올린다. 그때는 게임 안의 시계가 없었다.

    1일째 8시에 시작하고 라운드 하나에 10분이 흐르는 것으로 읽는다. 새 시나리오의 기본값과 같다.
    """
    upgraded = dict(document)
    upgraded['clock'] = {
        'start_day': DEFAULT_START_DAY,
        'start_hour': DEFAULT_START_HOUR,
        'round_minutes': DEFAULT_ROUND_MINUTES,
    }
    upgraded['format'] = 24
    return upgraded


def lasting_in_minutes(injury: dict, template_injuries: dict[str, dict], round_minutes: int) -> dict:
    """
    부상 하나의 기간을 분으로 옮긴다(형식 25). 짧은 것은 라운드 그대로이고, 오래 가는 것만 바뀐다.

    오래 가는 것은 템플릿에 같은 이름의 부상이 있으면 그 값(며칠)으로, 없으면 라운드 수 × 판의 기본 걸음으로 읽는다.
    치료할 수 없는 부상(난이도가 비었다)은 앞당기는 시간도 비운다. 짧은 것과 결손은 치료의 칸이 없다.
    옛 형식을 템플릿으로 채워 올린 문서는 이미 분으로 적혀 있을 수 있다. 그러면 그대로 둔다.
    """
    upgraded = {key: value for key, value in injury.items() if key != 'treat_rounds'}
    if injury['healing'] != 'heals':
        return {**upgraded, 'treat_difficulty': None, 'treat_minutes': None}
    template = template_injuries.get(injury['key'], {})
    rounds = upgraded.pop('rounds', None)
    if upgraded.get('heal_minutes') is None:
        upgraded['heal_minutes'] = template.get('heal_minutes') or rounds * round_minutes
    if upgraded.get('treat_minutes') is None:
        treat_rounds = injury.get('treat_rounds')
        fallback = treat_rounds * round_minutes if treat_rounds else None
        upgraded['treat_minutes'] = template.get('treat_minutes') or fallback
    if upgraded.get('treat_difficulty') is None or upgraded['treat_minutes'] is None:
        upgraded['treat_difficulty'] = None
        upgraded['treat_minutes'] = None
    return upgraded


def delay_in_minutes(row: dict, template_rows: list[dict], round_minutes: int) -> dict:
    """
    치료 실패 표의 한 줄의 덧남을 분으로 옮긴다(형식 25). 덧남이 아니면 비운다.

    템플릿에 같은 눈과 종류의 줄이 있으면 그 값으로, 없으면 라운드 수 × 판의 기본 걸음으로 읽는다.
    """
    upgraded = {key: value for key, value in row.items() if key != 'rounds'}
    if row['kind'] != 'worsen':
        return {**upgraded, 'delay_minutes': None}
    if upgraded.get('delay_minutes') is not None:
        return upgraded
    same = next(
        (
            other
            for other in template_rows
            if (other['low'], other['high'], other['kind']) == (row['low'], row['high'], row['kind'])
        ),
        None,
    )
    upgraded['delay_minutes'] = same['delay_minutes'] if same else row['rounds'] * round_minutes
    return upgraded


def upgrade_from_24(document: dict) -> dict:
    """
    형식 24 의 문서를 형식 25 로 올린다. 그때는 오래 가는 부상과 치료의 기간이 라운드 수였다.

    이제 게임 안의 시간(분)이다. 규칙이 SRD5 템플릿에서 왔으면 그 템플릿의 값(팔 골절 14일 …)으로 읽고,
    아니면 라운드 수에 판의 기본 걸음(clock.round_minutes)을 곱해 읽는다. DB 의 룰북에도 같은 값을 채웠다(마이그레이션).
    """
    template = SRD5.model_dump(mode='json')
    from_template = document['rulebook']['rules'].get('template') == template['template']
    template_injuries = {injury['key']: injury for injury in template['injuries']} if from_template else {}
    template_rows = template['treatment']['mishaps']['rows'] if from_template else []
    round_minutes = document['clock']['round_minutes']
    rules = dict(document['rulebook']['rules'])
    rules['injuries'] = [lasting_in_minutes(injury, template_injuries, round_minutes) for injury in rules['injuries']]
    if rules.get('treatment') is not None:
        mishaps = rules['treatment']['mishaps']
        rows = [delay_in_minutes(row, template_rows, round_minutes) for row in mishaps['rows']]
        rules['treatment'] = {**rules['treatment'], 'mishaps': {**mishaps, 'rows': rows}}
    upgraded = dict(document)
    upgraded['rulebook'] = {**document['rulebook'], 'rules': rules}
    upgraded['format'] = 25
    return upgraded


def upgrade_from_25(document: dict) -> dict:
    """
    형식 25 의 문서를 형식 26 으로 올린다. 그때는 길에 걸리는 시간이 없었다.

    모두 비운 것으로 읽는다. 라운드의 걸음 안에서 간다. 그때와 같은 동작이다.
    """
    upgraded = dict(document)
    upgraded['routes'] = [{**route, 'travel_minutes': None} for route in document.get('routes', [])]
    upgraded['format'] = 26
    return upgraded


def upgrade_from_26(document: dict) -> dict:
    """
    형식 26 의 문서를 형식 27 로 올린다. 그때는 퀘스트에 기한이 없었다.

    모두 비운 것으로 읽는다. 기한 없이 방장이 끝낸다. 그때와 같은 동작이다.
    """
    upgraded = dict(document)
    upgraded['quests'] = [{**quest, 'time_limit_minutes': None} for quest in document.get('quests', [])]
    upgraded['format'] = 27
    return upgraded


def upgrade_from_27(document: dict) -> dict:
    """
    형식 27 의 문서를 형식 28 로 올린다. 그때는 규칙에 쉬기가 없었다. HP 는 회복의 행동과 소모품으로만 돌아왔다.

    룰북은 템플릿에서만 만들므로 SRD5 템플릿의 것으로 읽는다. DB 의 룰북에도 같은 값을 채웠다(마이그레이션).
    이미 진행 중인 테이블도 이 형식으로 올려 읽는다. 다음 라운드부터 쉴 수 있다.
    """
    rest = SRD5.model_dump(mode='json')['rest']
    rulebook = document['rulebook']
    upgraded = dict(document)
    upgraded['rulebook'] = {**rulebook, 'rules': {**rulebook['rules'], 'rest': rest}}
    upgraded['format'] = 28
    return upgraded


def upgrade_from_28(document: dict) -> dict:
    """
    형식 28 의 문서를 형식 29 로 올린다. 그때는 몬스터에 드롭이 없었다.

    모두 비운 것으로 읽는다. 쓰러뜨려도 아무것도 나오지 않는다. 그때와 같은 동작이다.
    """
    upgraded = dict(document)
    upgraded['monsters'] = [{**monster, 'drops': []} for monster in document.get('monsters', [])]
    upgraded['format'] = 29
    return upgraded


def upgrade_from_29(document: dict) -> dict:
    """
    형식 29 의 문서를 형식 30 으로 올린다. 그때는 퀘스트에 이루는 조건이 없었다. 방장이 손으로 성공시켰다.

    조건이 없는 것으로 읽는다. 사람이 성공시키는 길은 없어졌으므로 옛 판의 퀘스트는 성공하지 않는다.
    기한이 있으면 실패는 그대로 엔진이 정한다.
    """
    upgraded = dict(document)
    upgraded['quests'] = [{**quest, 'conditions': [], 'match': 'all'} for quest in document.get('quests', [])]
    upgraded['format'] = 30
    return upgraded


def upgrade_from_30(document: dict) -> dict:
    """
    형식 30 의 문서를 형식 31 로 올린다. 그때는 퀘스트에 드러나는 조건이 없었다. 방장이 손으로 드러냈다.

    조건이 없는 것으로 읽는다. 사람이 드러내는 길은 없어졌으므로 옛 판의 숨긴 퀘스트는 이루어야만 드러난다.
    """
    upgraded = dict(document)
    upgraded['quests'] = [{**quest, 'reveal': [], 'reveal_match': 'all'} for quest in document.get('quests', [])]
    upgraded['format'] = 31
    return upgraded


def upgrade_from_31(document: dict) -> dict:
    """
    형식 31 의 문서를 형식 32 로 올린다. 그때는 장소에 놓인 물건이 없었다. 찾은 물건은 방장이 손으로 줬다.

    없는 것으로 읽는다. 그때와 같은 동작이다.
    """
    upgraded = dict(document)
    upgraded['place_items'] = []
    upgraded['format'] = 32
    return upgraded


def without_consume(condition: dict) -> dict:
    """그때의 조건 하나. 이룰 때 아무것도 가져가지 않았다."""
    return {**condition, 'consume': False}


def upgrade_from_32(document: dict) -> dict:
    """
    형식 32 의 문서를 형식 33 으로 올린다. 그때는 물건 갖기를 이뤄도 물건이 그대로 남았다.

    모든 조건을 가져가지 않는 것으로 읽는다. 그때와 같은 동작이다.
    """
    upgraded = dict(document)
    upgraded['quests'] = [
        {
            **quest,
            'conditions': [without_consume(condition) for condition in quest.get('conditions', [])],
            'reveal': [without_consume(condition) for condition in quest.get('reveal', [])],
        }
        for quest in document.get('quests', [])
    ]
    upgraded['format'] = 33
    return upgraded


def carried_from_drops(monster: dict) -> dict:
    """그때의 몬스터 하나. 드롭이 소지품이 되고 장비는 없다."""
    upgraded = {key: value for key, value in monster.items() if key != 'drops'}
    return {**upgraded, 'equipment': [], 'inventory': monster.get('drops', [])}


def upgrade_from_33(document: dict) -> dict:
    """
    형식 33 의 문서를 형식 34 로 올린다. 그때는 몬스터가 지닌 물건이 없었다. 드롭은 따로 적은 표였다.

    드롭을 소지품으로 읽는다. 줄마다 같은 개수와 확률이라, 쓰러뜨렸을 때 나오는 것이 그때와 같다.
    """
    upgraded = dict(document)
    upgraded['monsters'] = [carried_from_drops(monster) for monster in document.get('monsters', [])]
    upgraded['format'] = 34
    return upgraded


def upgrade_from_34(document: dict) -> dict:
    """형식 34 의 문서를 형식 35 로 올린다. 그때는 물건에 등급이 없었다. 모두 노말로 읽는다."""
    upgraded = dict(document)
    upgraded['items'] = [{**rule, 'rarity': 'normal'} for rule in document.get('items', [])]
    upgraded['format'] = 35
    return upgraded


def upgrade_from_35(document: dict) -> dict:
    """
    형식 35 의 문서를 형식 36 으로 올린다. 그때는 규칙에 훔치기가 없었고 몬스터에 둔한지가 없었다.

    룰북은 템플릿에서만 만들므로 SRD5 템플릿의 훔치기로 읽는다. DB 의 룰북에도 같은 값을 채웠다(마이그레이션).
    이미 진행 중인 테이블도 다음 라운드부터 훔칠 수 있다. 몬스터는 둔하지 않은 것으로 읽는다.
    """
    steal = SRD5.model_dump(mode='json')['steal']
    rulebook = document['rulebook']
    upgraded = dict(document)
    upgraded['rulebook'] = {**rulebook, 'rules': {**rulebook['rules'], 'steal': steal}}
    upgraded['monsters'] = [{**monster, 'dull': False} for monster in document.get('monsters', [])]
    upgraded['format'] = 36
    return upgraded


def upgrade_from_36(document: dict) -> dict:
    """형식 36 의 문서를 형식 37 로 올린다. 그때는 NPC 에 태도가 없었다. 모두 중립으로 읽는다."""
    upgraded = dict(document)
    upgraded['npc_sheets'] = [{**npc_sheet, 'attitude': 'neutral'} for npc_sheet in document.get('npc_sheets', [])]
    upgraded['format'] = 37
    return upgraded


def upgrade_from_37(document: dict) -> dict:
    """형식 37 의 문서를 형식 38 로 올린다. 그때는 NPC 가 아무것도 지니지 않았고 둔하지 않았다."""
    upgraded = dict(document)
    upgraded['npc_sheets'] = [
        {**npc_sheet, 'equipment': [], 'inventory': [], 'dull': False} for npc_sheet in document.get('npc_sheets', [])
    ]
    upgraded['format'] = 38
    return upgraded


def upgrade_from_38(document: dict) -> dict:
    """형식 38 의 문서를 형식 39 로 올린다. 그때는 훔치다 들켰을 때를 적지 않았다. 모두 적대만 한다."""
    upgraded = dict(document)
    upgraded['npc_sheets'] = [{**npc_sheet, 'on_caught': 'hostile'} for npc_sheet in document.get('npc_sheets', [])]
    upgraded['format'] = 39
    return upgraded


def upgrade_from_39(document: dict) -> dict:
    """
    형식 39 의 문서를 형식 40 으로 올린다. 그때는 빼앗긴 NPC 가 깨어날 때의 반응이 규칙에 없었다.

    룰북은 템플릿에서만 만들므로 SRD5 템플릿의 것으로 읽는다. DB 의 룰북에도 같은 값을 채웠다(마이그레이션).
    """
    robbed_wake = SRD5.model_dump(mode='json')['robbed_wake']
    rulebook = document['rulebook']
    upgraded = dict(document)
    upgraded['rulebook'] = {**rulebook, 'rules': {**rulebook['rules'], 'robbed_wake': robbed_wake}}
    upgraded['format'] = 40
    return upgraded


def upgrade_from_40(document: dict) -> dict:
    """형식 40 의 문서를 형식 41 로 올린다. 그때는 NPC 시트에 공격이 없었다. 모두 공격하지 않는다."""
    upgraded = dict(document)
    upgraded['npc_sheets'] = [{**npc_sheet, 'attacks': []} for npc_sheet in document.get('npc_sheets', [])]
    upgraded['format'] = 41
    return upgraded


def upgrade_from_41(document: dict) -> dict:
    """
    형식 41 의 문서를 형식 42 로 올린다. 그때는 세계관에 참고 자료의 허용이 없었다. 허용하지 않은 것으로 읽는다.

    세계관이 없는 판은 그대로다. 세계관이 없으면 막을 설정이 없어 켤 수 있다(app/references/policy.py).
    """
    upgraded = dict(document)
    if document.get('world') is not None:
        upgraded['world'] = {**document['world'], 'references_allowed': False}
    upgraded['format'] = 42
    return upgraded


def upgrade_from_42(document: dict) -> dict:
    """
    형식 42 의 문서를 형식 43 으로 올린다. 그때는 퀘스트에 실패하는 조건이 없었다. 기한 말고는 방장이 손으로 실패시켰다.

    조건이 없는 것으로 읽는다. 사람이 실패시키는 길은 없어졌으므로(#367) 옛 판의 퀘스트는 기한으로만 실패한다.
    """
    upgraded = dict(document)
    upgraded['quests'] = [{**quest, 'fail': [], 'fail_match': 'all'} for quest in document.get('quests', [])]
    upgraded['format'] = 43
    return upgraded


def upgrade_from_43(document: dict) -> dict:
    """
    형식 43 의 문서를 형식 44 로 올린다. 그때는 사건 규칙이 없었다. 길로 이어지지 않은 이동은 방장이 손으로 옮겼다.

    사건 규칙이 없는 것으로 읽는다. 방장이 옮기는 길은 없어졌으므로(#367) 옛 판에서는 길로만 다닌다.
    """
    upgraded = dict(document)
    upgraded['happenings'] = []
    upgraded['format'] = 44
    return upgraded


def upgrade_from_44(document: dict) -> dict:
    """
    형식 44 의 문서를 형식 45 로 올린다. 그때는 규칙에 서술 지침이 없었다.

    지침이 없는 것(None)으로 읽는다. SRD5 템플릿의 지침(판타지의 분위기)을 채우지 않는다.
    그때까지 SRD5 의 규칙은 장르를 가리지 않고 쓰였다. SF 나 현대물의 판에 판타지의 분위기를 얹지 않는다.
    지침이 없으면 서술은 지금처럼 공통의 지시만으로 한다. DB 의 룰북에도 같은 값을 채웠다(마이그레이션).
    """
    upgraded = dict(document)
    rulebook = document['rulebook']
    upgraded['rulebook'] = {**rulebook, 'rules': {**rulebook['rules'], 'narration': None}}
    upgraded['format'] = 45
    return upgraded


def upgrade_from_45(document: dict) -> dict:
    """
    형식 45 의 문서를 형식 46 으로 올린다. 그때는 돈이 없었다(#278).

    화폐가 없는 판으로 읽는다. 물건에는 값이 없고, 상인도 프리젠의 돈도 퀘스트의 돈의 보상도 없다.
    캐릭터의 돈은 0 이고 늘 0 이다. 거래를 선언하지 못한다.
    """
    upgraded = dict(document)
    upgraded['currency'] = None
    upgraded['items'] = [{**rule, 'price': None} for rule in document.get('items', [])]
    upgraded['pregens'] = [{**pregen, 'money': 0} for pregen in document['pregens']]
    upgraded['quests'] = [{**quest, 'reward_money': 0} for quest in document.get('quests', [])]
    upgraded['npc_sheets'] = [{**npc_sheet, 'merchant': False} for npc_sheet in document.get('npc_sheets', [])]
    upgraded['format'] = 46
    return upgraded


def upgrade_from_46(document: dict) -> dict:
    """
    형식 46 의 문서를 형식 47 로 올린다. 그때는 장비의 칸이 없었다(#276).

    칸이 없는 규칙으로 읽는다. SRD5 템플릿의 칸(주손, 보조손, 몸, 머리)을 채우지 않는다. 서술 지침(형식 45)과 같다.
    그때까지 SRD5 의 규칙은 장르를 가리지 않고 쓰였다. 물건은 착용하지 않고, 시작할 때도 착용하지 않는다.
    DB 의 룰북에도 같은 값을 채웠다(마이그레이션).
    """
    upgraded = dict(document)
    rulebook = document['rulebook']
    upgraded['rulebook'] = {**rulebook, 'rules': {**rulebook['rules'], 'equipment_slots': []}}
    upgraded['items'] = [{**rule, 'slots': [], 'slot_count': 1} for rule in document.get('items', [])]
    upgraded['starting_items'] = [{**stack, 'wear': []} for stack in document.get('starting_items', [])]
    upgraded['pregens'] = [
        {**pregen, 'items': [{**stack, 'wear': []} for stack in pregen.get('items', [])]}
        for pregen in document['pregens']
    ]
    upgraded['quests'] = [
        {**quest, 'reward': [{**stack, 'wear': []} for stack in quest.get('reward', [])]}
        for quest in document.get('quests', [])
    ]
    upgraded['format'] = 47
    return upgraded


def unarmed_holder(holder: dict) -> dict:
    """
    NPC 시트나 몬스터 하나를 장비의 효과가 없던 때의 모양으로(#276). 지닌 물건은 착용하지 않았고 공격은 맨몸이다.

    형식 48 로 올릴 때 쓴다.
    """
    return {
        **holder,
        'equipment': [{**line, 'wear': []} for line in holder.get('equipment', [])],
        'inventory': [{**line, 'wear': []} for line in holder.get('inventory', [])],
        'attacks': [{**attack, 'weapon': None} for attack in holder.get('attacks', [])],
    }


def upgrade_from_47(document: dict) -> dict:
    """
    형식 47 의 문서를 형식 48 로 올린다. 그때는 장비가 공격과 방어에 들지 않았다(#276).

    방어 방식이 없는 규칙(armor: None)으로 읽는다. 방어구가 막지 않고 부위도 굴리지 않는다. 칸이 맞을 가중치는 1 이다.
    물건에는 공격 보정과 방어가 없고, NPC 와 몬스터는 착용하지 않았고 맨몸으로 치며 타고난 방어가 없다.
    DB 의 룰북에도 같은 값을 채웠다(마이그레이션).
    """
    upgraded = dict(document)
    rulebook = document['rulebook']
    rules = rulebook['rules']
    slots = [{**slot, 'hit_weight': 1} for slot in rules['equipment_slots']]
    upgraded['rulebook'] = {**rulebook, 'rules': {**rules, 'equipment_slots': slots, 'armor': None}}
    upgraded['items'] = [{**rule, 'attack': None, 'defense': None, 'guard': None} for rule in document.get('items', [])]
    upgraded['npc_sheets'] = [unarmed_holder(npc_sheet) for npc_sheet in document.get('npc_sheets', [])]
    upgraded['monsters'] = [
        {**unarmed_holder(monster), 'natural_armor': []} for monster in document.get('monsters', [])
    ]
    upgraded['format'] = 48
    return upgraded


def armor_with_pierce(armor: dict | None) -> dict | None:
    """방어 방식에 세이브의 목표값(없음)과 관통의 기준값(10)을 더한다. 방어 방식이 없으면 그대로 없다."""
    if armor is None:
        return None
    return {**armor, 'save_target': None, 'pierce_base': 10}


def upgrade_from_48(document: dict) -> dict:
    """
    형식 48 의 문서를 형식 49 로 올린다. 그때는 세이브와 관통이 없었다(#276).

    방어 방식은 그대로이고(그때는 ac 와 reduce 뿐이다), 관통의 기준값은 그 뒤의 기본값(10)이다.
    물건에는 관통력과 불굴 세이브가 없고, 몬스터에는 타고난 불굴 세이브가 없다.
    DB 의 룰북에도 같은 값을 채웠다(마이그레이션).
    """
    upgraded = dict(document)
    rulebook = document['rulebook']
    rules = rulebook['rules']
    upgraded['rulebook'] = {**rulebook, 'rules': {**rules, 'armor': armor_with_pierce(rules['armor'])}}
    upgraded['items'] = [{**rule, 'ap': None, 'ward': None} for rule in document.get('items', [])]
    upgraded['monsters'] = [{**monster, 'ward': None} for monster in document.get('monsters', [])]
    upgraded['format'] = 49
    return upgraded


def upgrade_from_49(document: dict) -> dict:
    """
    형식 49 의 문서를 형식 50 으로 올린다. 그때는 인물의 자리가 없었다(#282).

    자리를 적은 인물이 없는 것으로 읽는다. 인물은 모두 지금처럼 장면의 글에 나왔는지로 장면에 든다.
    사건의 효과는 캐릭터 옮기기(move)뿐이었으므로 그대로 읽는다.
    """
    upgraded = dict(document)
    upgraded['npc_places'] = []
    upgraded['format'] = 50
    return upgraded


def upgrade_from_50(document: dict) -> dict:
    """형식 50 의 문서를 형식 51 로 올린다. 그때는 장소마다의 커버가 없었다(#276 의 커버 세이브)."""
    upgraded = dict(document)
    upgraded['covers'] = []
    upgraded['format'] = 51
    return upgraded


def upgrade_from_51(document: dict) -> dict:
    """
    형식 51 의 문서를 형식 52 로 올린다. 그때는 길에 조건이 없었다(#281).

    넘기 판정도 자물쇠도 없는 것으로 읽는다. 알기만 하면 누구나 지나가던 그대로다.
    """
    upgraded = dict(document)
    upgraded['routes'] = [{**route, 'cross': None, 'lock': None} for route in document.get('routes', [])]
    upgraded['format'] = 52
    return upgraded


def upgrade_from_52(document: dict) -> dict:
    """
    형식 52 의 문서를 형식 53 으로 올린다. 그때는 문을 여는 길이 열쇠뿐이었다(#281).

    빗장도 부수는 판정도 없고, 자물쇠는 따지 못하는 것으로 읽는다.
    """
    upgraded = dict(document)
    upgraded['routes'] = [
        {**route, 'lock': with_no_pick(route.get('lock')), 'bar': None, 'force': None}
        for route in document.get('routes', [])
    ]
    upgraded['format'] = 53
    return upgraded


def with_no_pick(lock: dict | None) -> dict | None:
    """형식 52 의 자물쇠에 따는 판정이 없다고 적는다. 자물쇠가 없으면 None."""
    return None if lock is None else {**lock, 'pick': None}


def upgrade_from_53(document: dict) -> dict:
    """
    형식 53 의 문서를 형식 54 로 올린다. 그때는 사건이 길의 문을 다루지 못했다(#281).

    사건의 효과는 캐릭터 옮기기와 인물 옮기기뿐이었으므로 그대로 읽는다. 문을 다루는 장치(device)는 없다.
    """
    upgraded = dict(document)
    upgraded['happenings'] = [
        {**rule, 'effects': [{**effect, 'device': None} for effect in rule['effects']]}
        for rule in document.get('happenings', [])
    ]
    upgraded['format'] = 54
    return upgraded


def upgrade_from_54(document: dict) -> dict:
    """
    형식 54 의 문서를 형식 55 로 올린다. 그때는 부서진 문을 고치는 판정이 없었다(#281).

    고치는 판정이 없는 것으로 읽는다. 사람이 부서진 문을 고치지 못한다(판의 사건 repair_route 는 그대로 고친다).
    """
    upgraded = dict(document)
    upgraded['routes'] = [{**route, 'repair': None} for route in document.get('routes', [])]
    upgraded['format'] = 55
    return upgraded


def upgrade_from_55(document: dict) -> dict:
    """
    형식 55 의 문서를 형식 56 으로 올린다. 그때는 문에 다는 새 자물쇠가 없었다(#281).

    어느 물건도 자물쇠가 아닌 것으로 읽는다. 문의 자물쇠를 바꾸지 못한다.
    """
    upgraded = dict(document)
    upgraded['items'] = [{**rule, 'lock': None} for rule in document.get('items', [])]
    upgraded['format'] = 56
    return upgraded


# 형식 번호와, 그 형식을 바로 다음 형식으로 올리는 함수.
# 형식을 올릴 때마다 한 줄씩 더한다. 옛 문서는 이 함수들을 차례로 거쳐 지금의 모양이 된다
UPGRADES: dict[int, Callable[[dict], dict]] = {
    1: upgrade_from_1,
    2: upgrade_from_2,
    3: upgrade_from_3,
    4: upgrade_from_4,
    5: upgrade_from_5,
    6: upgrade_from_6,
    7: upgrade_from_7,
    8: upgrade_from_8,
    9: upgrade_from_9,
    10: upgrade_from_10,
    11: upgrade_from_11,
    12: upgrade_from_12,
    13: upgrade_from_13,
    14: upgrade_from_14,
    15: upgrade_from_15,
    16: upgrade_from_16,
    17: upgrade_from_17,
    18: upgrade_from_18,
    19: upgrade_from_19,
    20: upgrade_from_20,
    21: upgrade_from_21,
    22: upgrade_from_22,
    23: upgrade_from_23,
    24: upgrade_from_24,
    25: upgrade_from_25,
    26: upgrade_from_26,
    27: upgrade_from_27,
    28: upgrade_from_28,
    29: upgrade_from_29,
    30: upgrade_from_30,
    31: upgrade_from_31,
    32: upgrade_from_32,
    33: upgrade_from_33,
    34: upgrade_from_34,
    35: upgrade_from_35,
    36: upgrade_from_36,
    37: upgrade_from_37,
    38: upgrade_from_38,
    39: upgrade_from_39,
    40: upgrade_from_40,
    41: upgrade_from_41,
    42: upgrade_from_42,
    43: upgrade_from_43,
    44: upgrade_from_44,
    45: upgrade_from_45,
    46: upgrade_from_46,
    47: upgrade_from_47,
    48: upgrade_from_48,
    49: upgrade_from_49,
    50: upgrade_from_50,
    51: upgrade_from_51,
    52: upgrade_from_52,
    53: upgrade_from_53,
    54: upgrade_from_54,
    55: upgrade_from_55,
}
