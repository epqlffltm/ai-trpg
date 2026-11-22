# tools/vm_seed_content.py

"""
VM 테스트(T3~T12)에 쓸 작품의 값. 한 세계(안개항)를 TRPG, chat, story 가 함께 쓴다.
값만 있다. 서버를 부르지 않는다. 부르는 것은 vm_seed.py 다.

  - TRPG "꺼진 등대": 룰북(light), 로어북, 몬스터 모음, 시나리오(맵, 잠긴 문, 거래, 전투, 퀘스트, 업적 둘)
  - chat "하람": 장소 둘, 물건 하나, 호감도, 업적 셋. 로어북은 asset 서버의 것(TRPG 의 로어북과 따로다)
  - chat "무진": story 의 인물로 쓰려고 만든다. 대화도 할 수 있다
  - story "소금 시장의 밤": 장소 셋, 인물 둘(무진, 하람), 업적 둘

서버의 ID 는 만들 때 받는다. TRPG 의 칸은 로어북 항목의 이름에서 ID 로 가는 표(ids)를 받아 채운다.
asset 서버의 장소·물건·인물은 작품 안의 키(영문)로 서로를 가리킨다.
"""

# --- TRPG: 꺼진 등대 ---

RULEBOOK_TITLE = '안개항 라이트'
LOREBOOK_TITLE = '안개항 안내서'
BESTIARY_TITLE = '안개항의 몬스터'
SCENARIO_TITLE = '꺼진 등대'

# 로어북 항목. 이름으로 서로를 가리킨다
ENTRIES = (
    {'name': '부두', 'kind': 'place', 'keywords': ['부두', '선창'],
     'content': '그물과 젖은 밧줄이 쌓인 선창. 등대로 가는 둑길이 여기서 시작된다.'},
    {'name': '소금 시장', 'kind': 'place', 'keywords': ['소금 시장', '시장', '장터'],
     'content': '밤에도 등불 몇 개가 켜진 장터. 상인 무진의 수레가 있다.'},
    {'name': '둑길', 'kind': 'place', 'keywords': ['둑길', '방파제'],
     'content': '부두에서 등대까지 바다 위로 난 좁은 돌길. 안개가 짙은 밤에는 무언가가 기어오른다.'},
    {'name': '붉은 등대', 'kind': 'place', 'keywords': ['등대', '붉은 등대'],
     'content': '둑길 끝의 붉은 탑. 아래 문은 잠겨 있다.'},
    {'name': '등대 꼭대기', 'kind': 'place', 'keywords': ['꼭대기', '등실'],
     'content': '나선 계단 끝의 등실. 큰 등과 기름통이 있다.'},
    {'name': '하람', 'kind': 'person', 'keywords': ['하람', '등대지기'],
     'content': '등대지기. 서른 남짓, 말수가 적고 꼼꼼하다. 오늘 밤 등대에 오른 뒤 내려오지 않았다.'},
    {'name': '무진', 'kind': 'person', 'keywords': ['무진', '상인', '떠돌이 상인'],
     'content': '소금 시장의 떠돌이 상인. 능글맞고 셈이 빠르다. 하람이 맡겨 둔 열쇠를 갖고 있다.'},
    {'name': '붕대', 'kind': 'item', 'keywords': ['붕대'], 'content': '소금물에 삶아 말린 천. 상처를 감는다.'},
    {'name': '기름 등불', 'kind': 'item', 'keywords': ['등불', '기름 등불'], 'content': '손에 드는 작은 등불.'},
    {'name': '갈고리 칼', 'kind': 'item', 'keywords': ['갈고리 칼', '칼'], 'content': '그물을 끊는 데 쓰는 굽은 칼.'},
    {'name': '녹슨 열쇠', 'kind': 'item', 'keywords': ['열쇠', '녹슨 열쇠'], 'content': '붉은 등대 아래 문의 열쇠.'},
    {'name': '등대의 불을 켜라', 'kind': 'event', 'keywords': ['등대의 불', '꺼진 불'],
     'content': '등대의 불이 꺼졌다. 안개가 짙어지기 전에 꼭대기의 큰 등을 다시 켜야 한다.'},
)  # fmt: skip

MONSTER = {
    'name': '안개 게',
    'kind': 'beast',
    'content': '안개가 짙은 밤 둑길에 올라오는 개만 한 게. 집게가 날카롭지만 불빛을 싫어한다.',
}

RULEBOOK = {'title': RULEBOOK_TITLE, 'template': 'light', 'description': 'VM 테스트용(가벼운 모험 템플릿 그대로)'}
LOREBOOK = {'title': LOREBOOK_TITLE, 'description': '안개항의 장소, 인물, 물건'}
BESTIARY = {'title': BESTIARY_TITLE, 'description': '안개항의 둑길에 나오는 것'}

START_PLACE = '부두'
CURRENCY = {'name': '은전', 'unit': '닢', 'starting': 20, 'sell_percent': 50}
QUEST = '등대의 불을 켜라'


def sheet(max_hp: int, body: int = 2, wits: int = 2, heart: int = 2, skills: tuple[str, ...] = ()) -> dict:
    """가벼운 모험(light)의 능력치 셋(1~5)과 최대 HP. 기술은 룰북의 키(arcane_bolt 같은 것)다."""
    made = {'abilities': {'body': body, 'wits': wits, 'heart': heart}, 'max_hp': max_hp}
    return {**made, 'skills': list(skills)} if skills else made


def stack(ids: dict[str, str], name: str, count: int = 1, wear: tuple[str, ...] = ()) -> dict:
    made = {'entry_id': ids[name], 'count': count}
    return {**made, 'wear': list(wear)} if wear else made


def routes(ids: dict[str, str]) -> list[dict]:
    """길. 둑길에서 등대로 들어가는 문은 잠겼다. 녹슨 열쇠로 열거나 재치 어려움으로 딴다."""
    return [
        {'from_place': ids['부두'], 'to_place': ids['소금 시장'], 'two_way': True, 'travel_minutes': 5},
        {'from_place': ids['부두'], 'to_place': ids['둑길'], 'two_way': True, 'travel_minutes': 5},
        {
            'from_place': ids['둑길'],
            'to_place': ids['붉은 등대'],
            'two_way': True,
            'travel_minutes': 2,
            'lock': {'key': ids['녹슨 열쇠'], 'locked': True, 'pick': {'ability': 'wits', 'difficulty': 'hard'}},
        },
        {'from_place': ids['붉은 등대'], 'to_place': ids['등대 꼭대기'], 'two_way': True, 'travel_minutes': 5},
    ]


def item_rules(ids: dict[str, str]) -> list[dict]:
    """
    물건의 종류와 값. 붕대는 가볍게 회복하고, 치료를 거들면 +2 이고 늘 하나 없어진다.
    녹슨 열쇠는 무진이 8닢에 판다(값이 없으면 사고팔 수 없다).
    """
    return [
        {
            'entry_id': ids['붕대'],
            'kind': 'consumable',
            'rarity': 'normal',
            'price': 5,
            'effects': [{'kind': 'heal', 'magnitude': 'light'}],
            'aids': [{'act': 'treat', 'bonus': 2, 'wear': 'always'}],
        },
        {
            'entry_id': ids['기름 등불'],
            'kind': 'gear',
            'rarity': 'normal',
            'price': 12,
            'slots': ['main_hand', 'off_hand'],
        },
        {
            'entry_id': ids['갈고리 칼'],
            'kind': 'gear',
            'rarity': 'normal',
            'price': 15,
            'slots': ['main_hand', 'off_hand'],
            'attack': 2,
        },
        {'entry_id': ids['녹슨 열쇠'], 'kind': 'gear', 'rarity': 'rare', 'price': 8},
    ]


def npc_sheets(ids: dict[str, str]) -> list[dict]:
    """무진은 상인이다. 소지품이 곧 재고다. 하람은 꼭대기에서 다리를 다쳐 앉아 있다."""
    return [
        {
            'entry_id': ids['무진'],
            'sheet': sheet(6, body=1, wits=3, heart=2),
            'attitude': 'friendly',
            'merchant': True,
            'inventory': [stack(ids, '붕대', 3), stack(ids, '기름 등불'), stack(ids, '녹슨 열쇠')],
        },
        {'entry_id': ids['하람'], 'sheet': sheet(8), 'attitude': 'friendly'},
    ]


def npc_places(ids: dict[str, str]) -> list[dict]:
    """자리가 있는 인물은 캐릭터가 그 장소에 있을 때만 나온다. 하람은 꼭대기에 올라가야 보인다."""
    return [
        {'entry_id': ids['무진'], 'place_id': ids['소금 시장']},
        {'entry_id': ids['하람'], 'place_id': ids['등대 꼭대기']},
    ]


def monster_sheets(monster_id: str) -> list[dict]:
    """안개 게. HP 가 낮고 집게로 가볍게 다치게 한다."""
    return [
        {
            'monster_id': monster_id,
            'sheet': sheet(4, body=2, wits=1, heart=1),
            'attacks': [{'name': '집게', 'ability': 'body', 'difficulty': 'medium', 'harm': 'light'}],
            'xp': 10,
        }
    ]


def encounters(ids: dict[str, str], monster_id: str) -> list[dict]:
    """둑길에 안개 게 두 마리. 기습은 없다."""
    return [{'place_id': ids['둑길'], 'monster_id': monster_id, 'count': 2}]


def quests(ids: dict[str, str]) -> list[dict]:
    """처음부터 보이는 퀘스트 하나. 등대 꼭대기에 닿으면 이룬다. 보상 30닢."""
    return [
        {
            'entry_id': ids[QUEST],
            'start': 'active',
            'conditions': [{'kind': 'reach_place', 'target': ids['등대 꼭대기']}],
            'reward_money': 30,
        }
    ]


def achievements(ids: dict[str, str]) -> list[dict]:
    """
    업적 둘. "불을 밝힌 자"는 퀘스트를 이루면, 숨긴 "셈 빠른 손님"은 일행이 붕대를 둘 넘게 가지면 받는다.
    도윤이 붕대 하나로 시작하므로 무진에게서 하나를 사면 채워진다. 그림은 붙이지 않는다(VM 은 그림을 올리지 못한다)
    """
    return [
        {
            'id': 'lit-the-light',
            'name': '불을 밝힌 자',
            'description': '꺼진 등대의 불을 다시 켰다.',
            'when': [{'kind': 'quest_succeeded', 'target': ids[QUEST]}],
        },
        {
            'id': 'quick-buyer',
            'name': '셈 빠른 손님',
            'description': '일행이 붕대를 두 개 넘게 챙겼다.',
            'hidden': True,
            'when': [{'kind': 'hold_item', 'target': ids['붕대'], 'count': 2}],
        },
    ]


def pregens(ids: dict[str, str]) -> list[dict]:
    return [
        {
            'name': '도윤',
            'description': '선원. 힘이 세고 말이 짧다.',
            'sheet': sheet(12, body=4, wits=2, heart=1),
            'items': [stack(ids, '갈고리 칼', wear=('main_hand',)), stack(ids, '붕대')],
        },
        {
            'name': '세아',
            'description': '견습 마법사. 마력 화살과 치유의 손길을 안다.',
            'sheet': sheet(9, body=1, wits=2, heart=4, skills=('arcane_bolt', 'healing_touch')),
            'items': [stack(ids, '기름 등불', wear=('off_hand',))],
        },
    ]


def scenario_body(
    rulebook_id: str, model: str, lorebook_id: str, bestiary_id: str, ids: dict[str, str], monster_id: str
) -> dict:
    """시나리오의 모든 칸. ids 는 로어북 항목의 이름에서 서버의 ID 로 간다."""
    return {
        'title': SCENARIO_TITLE,
        'rulebook_id': rulebook_id,
        'narration_model': model,
        'description': '등대의 불이 꺼졌다. 등대지기 하람은 오르고 나서 내려오지 않았다.',
        'openings': [
            '안개가 부두를 덮은 밤, 붉은 등대의 불이 꺼져 있다. 등대지기 하람은 해 질 녘에 올라간 뒤 내려오지 않았다. '
            '멀리 소금 시장의 등불 몇 개가 흔들린다.'
        ],
        'rating': 'all',
        'recommended_players': {'min': 2, 'max': 2},
        'character_modes': ['pregen', 'point_buy'],
        'default_sheet': sheet(10),
        'player_made_hp': {'base': 10, 'cap': 15},
        'lorebook_ids': [lorebook_id],
        'bestiary_ids': [bestiary_id],
        'start_place': ids[START_PLACE],
        'routes': routes(ids),
        'items': item_rules(ids),
        'npc_sheets': npc_sheets(ids),
        'npc_places': npc_places(ids),
        'monster_sheets': monster_sheets(monster_id),
        'encounters': encounters(ids, monster_id),
        'quests': quests(ids),
        'achievements': achievements(ids),
        'pregens': pregens(ids),
        'clock': {'start_day': 1, 'start_hour': 21, 'round_minutes': 10},
        'currency': CURRENCY,
    }


LISTING = {
    'tagline': '꺼진 등대의 불을 안개가 짙어지기 전에 다시 켜라',
    'description': (
        '안개가 걷히지 않는 작은 항구. 등대의 불이 꺼졌고, 등대지기는 내려오지 않았다.\n\n2인용 짧은 모험이다.'
    ),
    'genre': 'mystery',
    'tags': ['안개항', '등대'],
}

# --- asset 서버(chat 과 story): 로어북, 하람, 무진, 소금 시장의 밤 ---

ASSET_LOREBOOK_NAME = '안개항 안내서'
HARAM_NAME = '하람'
MUJIN_NAME = '무진'
WORLD_NAME = '소금 시장의 밤'

ASSET_LOREBOOK = {
    'name': ASSET_LOREBOOK_NAME,
    'description': '안개항의 장소와 인물',
    'entries': [
        {
            'id': 'harbor',
            'name': '부두',
            'kind': 'place',
            'keywords': ['부두', '선창'],
            'content': '그물과 젖은 밧줄이 쌓인 선창. 등대로 가는 둑길이 시작된다.',
        },
        {
            'id': 'salt-market',
            'name': '소금 시장',
            'kind': 'place',
            'keywords': ['소금 시장', '시장'],
            'content': '밤에도 등불 몇 개가 켜진 장터. 상인 무진의 수레가 있다.',
        },
        {
            'id': 'lighthouse',
            'name': '붉은 등대',
            'kind': 'place',
            'keywords': ['등대'],
            'content': '둑길 끝의 붉은 탑. 아래 문은 잠겨 있고 꼭대기에 큰 등이 있다.',
        },
        {
            'id': 'haram',
            'name': '하람',
            'kind': 'person',
            'keywords': ['하람', '등대지기'],
            'content': '등대지기. 서른 남짓, 말수가 적고 꼼꼼하다. 아버지에게서 등대를 물려받았다.',
        },
        {
            'id': 'mujin',
            'name': '무진',
            'kind': 'person',
            'keywords': ['무진', '상인'],
            'content': '소금 시장의 떠돌이 상인. 능글맞고 셈이 빠르다. 값을 깎으면 한 번은 웃으며 받아 준다.',
        },
        {
            'id': 'fog-crab',
            'name': '안개 게',
            'kind': 'species',
            'keywords': ['안개 게', '게'],
            'content': '안개가 짙은 밤 둑길에 올라오는 개만 한 게. 집게가 날카롭지만 불빛을 싫어한다.',
        },
        {
            'id': 'rusty-key',
            'name': '녹슨 열쇠',
            'kind': 'item',
            'keywords': ['열쇠'],
            'content': '등대 아래 문의 열쇠. 하람이 시장의 무진에게 맡겨 두곤 한다.',
        },
    ],
}

HARAM_STAGES = [{'name': '낯섦', 'at': 0}, {'name': '편함', 'at': 20}, {'name': '믿음', 'at': 60}]
MUJIN_STAGES = [{'name': '손님', 'at': 0}, {'name': '단골', 'at': 40}]


def haram_body(lorebook_id: str) -> dict:
    """하람. 등대 아래 방에서 시작하고 꼭대기에 오를 수 있다. 차를 건네면 처음 한 번 호감이 오른다."""
    return {
        'name': HARAM_NAME,
        'genre': 'mystery',
        'rating': 'all',
        'age': '서른 남짓',
        'tags': ['안개항', '등대지기'],
        'intro_html': (
            '<p>안개항 붉은 등대의 등대지기.</p>'
            '<p>말수가 적고 꼼꼼하다. 짧은 문장, 존댓말 반 혼잣말 반. 바다와 날씨 이야기를 할 때만 말이 길어진다. '
            '무서운 것을 숨기려고 농담을 한다.</p>'
            '<p>아버지에게서 등대를 물려받았다. 불이 꺼졌던 밤의 일은 아끼듯 조금씩만 꺼낸다.</p>'
        ),
        'greeting': '…문은 열려 있었어요? 바람 때문에 잘 안 닫히거든요. 차 드릴까요. 안개가 걷히려면 한참 걸려요.',
        'speech_examples': '손님: 불은 왜 꺼졌던 거예요?\n하람: 기름 탓이라고 해 두죠. 그쪽이 듣기 편하니까.',
        'starts': [
            {
                'title': '안개 낀 밤의 손님',
                'situation': '안개가 짙은 밤, 등대 아래 방의 문을 두드린다. 하람이 주전자를 올려 둔 채 문을 연다.',
                'hour': 21,
            }
        ],
        'places': [
            {'id': 'keeper-room', 'name': '등대 아래 방', 'description': '난로와 주전자, 젖은 장화가 있는 작은 방.'},
            {
                'id': 'lighthouse-top',
                'name': '등대 꼭대기',
                'description': '큰 등과 기름통이 있는 등실. 항구가 보인다.',
            },
        ],
        'paths': [{'a': 'keeper-room', 'b': 'lighthouse-top', 'minutes': 5}],
        'start_place': 'keeper-room',
        'items': [
            {'id': 'barley-tea', 'name': '보리차', 'description': '난로 위에서 데운 보리차 한 잔.', 'consumable': True}
        ],
        'start_items': [{'item': 'barley-tea', 'count': 1}],
        'affection': {
            'stages': HARAM_STAGES,
            'rules': [
                {'id': 'gave-tea', 'on': {'kind': 'give_item', 'target': 'barley-tea'}, 'change': 20, 'once': True}
            ],
        },
        'lorebooks': [lorebook_id],
        'achievements': [
            {
                'id': 'good-company',
                'name': '말벗',
                'description': '하람에게 말을 열 번 건넸다.',
                'when': {'items': [{'kind': 'messages_at_least', 'count': 10}]},
            },
            {
                'id': 'cup-of-tea',
                'name': '차 한 잔',
                'description': '하람과 조금 편해졌다.',
                'hidden': True,
                'when': {'items': [{'kind': 'affection_stage', 'value': '편함'}]},
            },
            {
                'id': 'top-of-the-tower',
                'name': '등대 꼭대기',
                'description': '등대 꼭대기에 올라가 보았다.',
                'when': {'items': [{'kind': 'visited_place', 'target': 'lighthouse-top'}]},
            },
        ],
    }


def mujin_body(lorebook_id: str) -> dict:
    """무진. story 의 인물로 쓴다. 대화도 할 수 있게 시작 상황을 하나 둔다."""
    return {
        'name': MUJIN_NAME,
        'genre': 'mystery',
        'rating': 'all',
        'tags': ['안개항', '상인'],
        'intro_html': (
            '<p>소금 시장의 떠돌이 상인.</p>'
            '<p>능글맞고 셈이 빠르다. 무엇이든 값을 매긴다. 값을 깎으면 한 번은 웃으며 받아 준다.</p>'
        ),
        'greeting': '어서 와요. 오늘 밤엔 붕대가 잘 나가네. 뭐가 필요해요?',
        'speech_examples': '손님: 하람 씨 못 봤어요?\n무진: 봤지. 그 얘기는 공짜가 아닌데.',
        'starts': [
            {
                'title': '등불 아래 수레',
                'situation': '소금 시장의 등불 아래, 무진이 수레의 물건을 늘어놓는다.',
                'hour': 22,
            }
        ],
        'lorebooks': [lorebook_id],
    }


def world_body(lorebook_id: str, mujin_id: str, haram_id: str) -> dict:
    """
    소금 시장의 밤. 부두에서 시작한다. 무진은 소금 시장에, 하람은 등대 꼭대기에 있다.
    업적: 소금 시장에 닿으면 "시장의 단골", 등대 꼭대기(하람이 있는 곳)에 닿으면 숨긴 "등대의 진실"
    """
    return {
        'name': WORLD_NAME,
        'genre': 'mystery',
        'rating': 'all',
        'tags': ['안개항', '소금 시장'],
        'intro_html': (
            '<p>등대의 불이 꺼진 바로 그 밤. 새내기 기자는 소금 시장에서 등대지기 하람의 행방을 묻는다.</p>'
            '<p>상인 무진은 무언가를 알면서 값을 매긴다.</p>'
        ),
        'places': [
            {'id': 'harbor', 'name': '부두', 'description': '그물과 젖은 밧줄이 쌓인 선창.'},
            {'id': 'salt-market', 'name': '소금 시장', 'description': '밤에도 등불 몇 개가 켜진 장터.'},
            {'id': 'lighthouse-top', 'name': '등대 꼭대기', 'description': '큰 등이 꺼진 등실.'},
        ],
        'paths': [
            {'a': 'harbor', 'b': 'salt-market', 'minutes': 5},
            {'a': 'harbor', 'b': 'lighthouse-top', 'minutes': 15},
        ],
        'start_place': 'harbor',
        'cast': [
            {'id': 'mujin', 'character_id': mujin_id, 'home': 'salt-market', 'affection': {'stages': MUJIN_STAGES}},
            {'id': 'haram', 'character_id': haram_id, 'home': 'lighthouse-top', 'affection': {'stages': HARAM_STAGES}},
        ],
        'lorebooks': [lorebook_id],
        'achievements': [
            {
                'id': 'market-regular',
                'name': '시장의 단골',
                'description': '밤의 소금 시장에 들렀다.',
                'when': {'items': [{'kind': 'reach_place', 'target': 'salt-market'}]},
            },
            {
                'id': 'lighthouse-truth',
                'name': '등대의 진실',
                'description': '등대 꼭대기에서 하람을 찾았다.',
                'hidden': True,
                'when': {'items': [{'kind': 'reach_place', 'target': 'lighthouse-top'}]},
            },
        ],
    }
