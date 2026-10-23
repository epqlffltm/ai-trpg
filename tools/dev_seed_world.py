# tools/dev_seed_world.py

"""
견본 시나리오의 세계. 로어북 항목(장소, 물건, 인물, 사건)과 그것을 가리키는 시나리오의 칸(맵, 물건, NPC, 퀘스트, 시계).
값만 있다. 서버를 부르지 않는다. 부르는 것은 dev_seed.py 다.

화면에서 한 판을 끝까지 보려고 행동마다 쓸 거리를 하나씩 둔다(docs/operations/local-screens.md 의 "한 판 따라가기").
  - 가기: 수도원 문 → 회랑 → 부엌, 종탑. 부엌에서 지하 저장고로 가는 숨긴 길(찾기로 드러난다)
  - 줍기, 내려놓기: 수도원 문에 횃불 둘. 지하 저장고에 숨긴 은 성배(찾기로 드러난다)
  - 쓰기, 건네기: 모두 약초 하나로 시작한다. 프리젠 렌은 하나 더, 미라는 횃불
  - 공격, 지목, 훔치기, 빼앗기: 문 옆의 늙은 문지기(진짜 이름 마르타). 녹슨 열쇠를 지녔다
  - 퀘스트: 종탑에 닿으면 이룬다
"""

LOREBOOK_TITLE = '[견본] 잿빛 수도원의 로어북'

# 장소, 물건, 인물, 사건. 이름으로 서로를 가리킨다(서버의 ID 는 만들 때 받는다)
ENTRIES = (
    {
        'name': '수도원 문',
        'kind': 'place',
        'keywords': ['수도원 문', '정문'],
        'content': '비에 젖은 나무 문. 옆에 등불이 걸려 있다.',
    },
    {'name': '회랑', 'kind': 'place', 'keywords': ['회랑'], 'content': '기둥이 늘어선 긴 복도. 바닥에 물이 고였다.'},
    {
        'name': '부엌',
        'kind': 'place',
        'keywords': ['부엌'],
        'content': '식은 화덕과 뒤집힌 솥. 바닥의 판자 하나가 들떠 있다.',
    },
    {'name': '종탑', 'kind': 'place', 'keywords': ['종탑', '종'], 'content': '좁은 계단 끝의 종. 줄이 끊겼다.'},
    {
        'name': '지하 저장고',
        'kind': 'place',
        'keywords': ['저장고', '지하'],
        'content': '부엌 아래의 저장고. 누군가 숨어 지낸 흔적이 있다.',
    },
    {
        'name': '약초',
        'kind': 'item',
        'keywords': ['약초'],
        'content': '씹으면 쓴맛이 나는 잎. 상처를 조금 아물게 한다.',
    },
    {'name': '횃불', 'kind': 'item', 'keywords': ['횃불'], 'content': '송진을 바른 막대.'},
    {'name': '녹슨 열쇠', 'kind': 'item', 'keywords': ['열쇠'], 'content': '종탑 계단의 쇠창살을 여는 열쇠.'},
    {'name': '은 성배', 'kind': 'item', 'keywords': ['성배'], 'content': '수도원의 보물. 안쪽에 이름이 새겨져 있다.'},
    {
        'name': '마르타',
        'kind': 'person',
        'keywords': ['문지기', '늙은 문지기'],
        'true_names': ['마르타'],
        'content': '수도원의 늙은 문지기. 이름을 숨긴다. 종이 울리지 않게 된 밤의 일을 안다.',
    },
    {
        'name': '울리지 않는 종',
        'kind': 'event',
        'keywords': ['종'],
        'content': '종탑의 종을 다시 울리면 수도원의 노래가 그친다.',
    },
)

# 지금 세계를 담은 판인지. 시나리오에 시작 장소가 있으면 이 세계를 담았다(앞의 견본에는 맵이 없었다)
START_PLACE = '수도원 문'


def sheet(max_hp: int, **scores: int) -> dict:
    """SRD5 의 능력치 여섯. 적지 않은 것은 10(보정 0)이다."""
    keys = ('str', 'dex', 'con', 'int', 'wis', 'cha')
    return {'abilities': {key: scores.get(key, 10) for key in keys}, 'max_hp': max_hp}


def stack(ids: dict[str, str], name: str, count: int = 1) -> dict:
    return {'entry_id': ids[name], 'count': count}


def routes(ids: dict[str, str]) -> list[dict]:
    """길. 부엌에서 지하 저장고로 가는 길은 숨겼다. 지혜 보통으로 찾는다."""
    return [
        {'from_place': ids['수도원 문'], 'to_place': ids['회랑'], 'two_way': True, 'travel_minutes': 5},
        {'from_place': ids['회랑'], 'to_place': ids['부엌'], 'two_way': True, 'travel_minutes': 3},
        {'from_place': ids['회랑'], 'to_place': ids['종탑'], 'two_way': True, 'travel_minutes': 10},
        {
            'from_place': ids['부엌'],
            'to_place': ids['지하 저장고'],
            'two_way': True,
            'travel_minutes': 2,
            'visibility': 'hidden',
            'find': {'ability': 'wis', 'difficulty': 'medium'},
        },
    ]


def item_rules(ids: dict[str, str]) -> list[dict]:
    """물건의 종류와 등급. 약초는 가볍게 회복한다(SRD5 의 light)."""
    return [
        {'entry_id': ids['약초'], 'kind': 'consumable', 'rarity': 'normal', 'heals': 'light'},
        {'entry_id': ids['횃불'], 'kind': 'gear', 'rarity': 'normal'},
        {'entry_id': ids['녹슨 열쇠'], 'kind': 'gear', 'rarity': 'rare'},
        {'entry_id': ids['은 성배'], 'kind': 'gear', 'rarity': 'epic'},
    ]


def place_items(ids: dict[str, str]) -> list[dict]:
    """놓인 물건. 은 성배는 숨겼다. 지능 쉬움으로 찾는다."""
    return [
        {'place_id': ids['수도원 문'], 'entry_id': ids['횃불'], 'count': 2},
        {
            'place_id': ids['지하 저장고'],
            'entry_id': ids['은 성배'],
            'count': 1,
            'visibility': 'hidden',
            'find': {'ability': 'int', 'difficulty': 'easy'},
        },
    ]


def npc_sheets(ids: dict[str, str]) -> list[dict]:
    """늙은 문지기. 경계한다. 녹슨 열쇠를 품에 지녔고, 들키면 적대한다. 맞으면 등불을 휘두른다."""
    return [
        {
            'entry_id': ids['마르타'],
            'sheet': sheet(9, str=8, wis=14),
            'attitude': 'wary',
            'inventory': [{'entry_id': ids['녹슨 열쇠'], 'count': 1}],
            'on_caught': 'hostile',
            'attacks': [{'name': '등불 휘두르기', 'ability': 'str', 'difficulty': 'medium', 'harm': 'light'}],
        }
    ]


def quests(ids: dict[str, str]) -> list[dict]:
    """처음부터 보이는 퀘스트 하나. 종탑에 닿으면 이룬다."""
    return [
        {
            'entry_id': ids['울리지 않는 종'],
            'start': 'active',
            'conditions': [{'kind': 'reach_place', 'target': ids['종탑']}],
        }
    ]


def pregens(ids: dict[str, str]) -> list[dict]:
    return [
        {
            'name': '수도사 렌',
            'description': '말이 없다. 기도문을 외운다.',
            'sheet': sheet(12, wis=15, con=12),
            'items': [stack(ids, '약초')],
        },
        {
            'name': '사냥꾼 미라',
            'description': '활을 쓴다. 발소리가 없다.',
            'sheet': sheet(11, dex=16, wis=12),
            'items': [stack(ids, '횃불')],
        },
        {'name': '용병 도르', 'description': '도끼를 든다. 돈을 받고 왔다.', 'sheet': sheet(14, str=16, con=14)},
    ]


def world_fields(ids: dict[str, str], lorebook_id: str) -> dict:
    """시나리오에 넣을 세계의 칸. ids 는 항목의 이름에서 서버의 ID 로 간다."""
    return {
        'lorebook_ids': [lorebook_id],
        'start_place': ids[START_PLACE],
        'routes': routes(ids),
        'items': item_rules(ids),
        'place_items': place_items(ids),
        'starting_items': [stack(ids, '약초')],
        'npc_sheets': npc_sheets(ids),
        'quests': quests(ids),
        'pregens': pregens(ids),
        'clock': {'start_day': 1, 'start_hour': 22, 'round_minutes': 10},
    }
