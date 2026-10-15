# game-server/tests/test_monster_narration.py

"""
서술자가 몬스터를 받는 것(#231 3d)을 검증한다.

보는 것은 넷이다.
  - 한 일의 줄: 몬스터의 공격 줄(맞음, 빗나감)에 굴림의 숫자와 도감의 글이 없다. 몬스터를 친 판정의 결과는
    몸 상태로만 붙고, 칠 수 없어 굴리지 않은 것은 그 까닭이 붙는다.
  - 줄의 순서: 차례가 있으면 차례 순서로 캐릭터와 몬스터의 줄을 섞고, 차례가 없는 캐릭터는 뒤에 앉은 순서로 놓는다.
  - 프롬프트의 [몬스터] 절: 네임드 몹은 한 마리씩, 일반 몹은 장소와 종류마다 마리마다의 몸 상태로 들어간다.
    몬스터가 없으면 절이 없다. 숫자(HP, 능력치)는 없다.
  - 라운드를 닫으면 가짜 서술자의 장면에 차례 순서의 줄이 나온다.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.bestiaries.models import MonsterKind
from app.assets.scenarios.snapshot import read_snapshot
from app.rounds import prompt
from app.rounds.move_lines import describe_monster_turn, describe_move, describe_target_gone, round_lines
from app.rounds.moves import to_monster_notes
from app.rounds.narration_request import to_turn_notes
from app.rounds.narrator import (
    Impact,
    MonsterNote,
    MonsterTurnNote,
    Move,
    NarrationRequest,
    NpcImpact,
    TargetGoneNote,
    TurnNote,
    Verdict,
)
from app.rounds.repository import find_round
from app.rounds.service import load_scene
from app.tables.models import NpcStatus
from app.tables.repository import find_table
from tests.sheets import make_sheet
from tests.signing import SigningKey
from tests.test_monster_turns import (
    BITE,
    FAIL,
    KICK,
    ME,
    PASS,
    REST,
    bearer,
    declare,
    kick,
    load_dice,
    monsters_of,
    rest,
    start_table,
    table_url,
)

pytestmark = pytest.mark.usefixtures('clean_tables')

HIT = MonsterTurnNote(
    name='수로 쥐 2',
    attack='물기',
    target='엘프',
    hit=True,
    impact=Impact(kind='damage', character_name='엘프', amount=3, hp=7, max_hp=10, downed=False),
)
MISS = MonsterTurnNote(name='수로 쥐 1', attack='물기', target='엘프', hit=False)
MISS_2 = MonsterTurnNote(name='수로 쥐 2', attack='물기', target='엘프', hit=False)


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 방장이다. 캐릭터는 '엘프'다."""
    return bearer(signing_key, ME)


async def scene_of(client: AsyncClient, headers: dict[str, str], table: dict) -> str:
    response = await client.get(table_url(table, '/rounds/current'), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()['scene']


# --- 한 일의 줄 ---


def test_a_monster_hit_shows_the_damage_but_not_the_roll():
    assert describe_monster_turn(HIT) == '수로 쥐 2: 엘프에게 물기 (맞음) → 엘프 피해 3 (HP 7/10)'


def test_a_monster_miss_is_a_miss():
    assert describe_monster_turn(MISS) == '수로 쥐 1: 엘프에게 물기 (빗나감)'


def test_a_hit_on_a_monster_shows_its_condition():
    verdict = Verdict(
        ability='근력',
        difficulty='보통',
        roll=20,
        modifier=0,
        total=20,
        target=15,
        success=True,
        monster_impact=NpcImpact(kind='damage', name='수로 쥐 2', amount=5, condition='죽음'),
    )

    line = describe_move(Move('엘프', KICK, verdict=verdict))

    assert line == '엘프: 쥐를 걷어찬다. (근력 판정 성공: 20 + 0 = 20, 목표 15) → 수로 쥐 2 피해 5 (죽음)'


def test_a_target_already_gone_says_why():
    assert describe_target_gone(TargetGoneNote('수로 쥐 2', 'dead')) == (
        '(겨눈 상대 수로 쥐 2: 이미 죽어 있었다. 판정하지 않았다)'
    )
    assert describe_target_gone(TargetGoneNote(None, 'elsewhere')) == '(겨눈 상대: 그 자리에 없었다. 판정하지 않았다)'


# --- 줄의 순서 ---


def test_lines_follow_the_turns():
    moves = [Move('엘프', REST), Move('드워프 기사', '노래한다.'), Move('영애', KICK)]
    turns = [TurnNote(character_name='영애'), TurnNote(monster=MISS), TurnNote(character_name='엘프')]

    lines = round_lines(moves, turns)

    assert lines == [
        f'영애: {KICK}',
        '수로 쥐 1: 엘프에게 물기 (빗나감)',
        f'엘프: {REST}',
        '드워프 기사: 노래한다.',
    ]


def test_without_turns_the_lines_keep_the_seated_order():
    moves = [Move('엘프', REST), Move('드워프 기사', '노래한다.')]

    assert round_lines(moves, []) == [f'엘프: {REST}', '드워프 기사: 노래한다.']


def test_turn_notes_drop_monsters_that_could_not_move():
    turns = [
        {'kind': 'pc', 'first': False, 'score': 10, 'tiebreak': None, 'user_id': 'x', 'character_name': '엘프'},
        {
            'kind': 'monster',
            'first': False,
            'score': 10,
            'tiebreak': None,
            'monster_id': 'y',
            'name': '수로 쥐 1',
            'outcome': {'skipped': 'dead'},
        },
        {
            'kind': 'monster',
            'first': False,
            'score': 12,
            'tiebreak': None,
            'monster_id': 'z',
            'name': '수로 쥐 2',
            'outcome': {
                'attack': BITE,
                'user_id': 'x',
                'character_name': '엘프',
                'roll': 1,
                'modifier': 0,
                'total': 1,
                'target': 15,
                'success': False,
                'effect': None,
            },
        },
    ]

    assert to_turn_notes(turns) == [TurnNote(character_name='엘프'), TurnNote(monster=MISS_2)]


# --- 프롬프트의 [몬스터] 절 ---


RATS = MonsterNote(
    name='수로 쥐',
    kind='야수',
    content='개만 한 쥐',
    place='수로 입구',
    unique=False,
    conditions=['멀쩡함', '죽음', '멀쩡함'],
)
KNIGHT = MonsterNote(
    name='해골 기사', kind='언데드', content='녹슨 창을 든 해골', place='깊은 수로', unique=True, conditions=['다침']
)


def request_with(monsters: list[MonsterNote], turns: list[TurnNote] | None = None) -> NarrationRequest:
    return NarrationRequest(
        round_number=1,
        scene='물 떨어지는 소리가 난다.',
        moves=[Move('엘프', REST)],
        monsters=monsters,
        turns=turns or [],
    )


def test_monsters_are_listed_by_kind_and_count():
    lines = prompt.monster_lines([RATS, KNIGHT])

    assert lines[0] == prompt.MONSTER_TITLE
    assert lines[2] == '- 수로 쥐(야수) 3마리 [수로 입구]: 멀쩡함 2, 죽음 1. 개만 한 쥐'
    assert lines[3] == '- 해골 기사(언데드, 네임드) [깊은 수로]: 다침. 녹슨 창을 든 해골'


def test_a_monster_of_other_kind_has_no_kind_tag():
    note = MonsterNote(name='그림자', kind='', content='', place='', unique=False, conditions=['멀쩡함'])

    assert prompt.monster_line(note) == '- 그림자 1마리: 멀쩡함'


def test_the_monster_section_comes_before_the_people():
    text = prompt.round_text(request_with([RATS]))

    assert prompt.MONSTER_TITLE in text
    assert text.index(prompt.MONSTER_TITLE) < text.index('[1 라운드에 한 일과 결과]')


def test_no_monsters_no_section():
    assert prompt.MONSTER_TITLE not in prompt.round_text(request_with([]))


def test_the_prompt_mixes_the_turns():
    text = prompt.round_text(request_with([RATS], [TurnNote(monster=MISS), TurnNote(character_name='엘프')]))

    assert text.index('수로 쥐 1: 엘프에게 물기 (빗나감)') < text.index(f'엘프: {REST}')


def test_a_lost_turn_adds_the_rule_line():
    lost = NarrationRequest(
        round_number=1, scene='물 떨어지는 소리가 난다.', moves=[Move('엘프', REST, downed=True, lost_turn='downed')]
    )

    assert prompt.LOST_TURN_NOTE in prompt.round_text(lost)
    assert prompt.LOST_TURN_NOTE not in prompt.round_text(request_with([]))


def test_the_version_is_bumped():
    # 몬스터는 narration-22 에서 붙었다. 뒤의 틀(narration-23 의 시각 …)도 몬스터를 그대로 싣는다
    assert int(prompt.PROMPT_VERSION.removeprefix('narration-')) >= 22


# --- 몬스터를 서술자에게 줄 모양으로 ---


def scene_monster(name: str, place: uuid.UUID, kind: MonsterKind, status_: str = NpcStatus.ALIVE, **definition):
    monster_id = definition.pop('monster_id', uuid.uuid4())
    state = SimpleNamespace(
        id=uuid.uuid4(),
        monster_id=monster_id,
        place_id=place,
        status=status_,
        hp=4 if status_ == 'alive' else 0,
        max_hp=4,
    )
    fields = {'name': name, 'kind': kind, 'content': '', 'unique': False, **definition}
    return SimpleNamespace(state=state, definition=SimpleNamespace(**fields), name=name)


def test_monster_notes_group_the_same_kind_at_one_place(monkeypatch: pytest.MonkeyPatch):
    gate, deep, rat = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    monsters = [
        scene_monster('수로 쥐', gate, MonsterKind.BEAST, monster_id=rat),
        scene_monster('수로 쥐', gate, MonsterKind.BEAST, NpcStatus.DEAD, monster_id=rat),
        scene_monster('수로 쥐', deep, MonsterKind.BEAST, monster_id=rat),
    ]
    places = [SimpleNamespace(id=gate, name='수로 입구'), SimpleNamespace(id=deep, name='깊은 수로')]
    # 판의 장소 항목만 바꿔 끼운다. 판 전체를 만들지 않는다
    monkeypatch.setattr('app.rounds.moves.place_entries', lambda _: places)

    notes = to_monster_notes(SimpleNamespace(), monsters)

    assert [(note.place, note.conditions) for note in notes] == [
        ('수로 입구', ['멀쩡함', '죽음']),
        ('깊은 수로', ['멀쩡함']),
    ]
    assert notes[0].kind == '야수'


def test_no_scene_monsters_no_notes():
    assert to_monster_notes(SimpleNamespace(), []) == []


async def test_the_scene_monsters_become_notes(client: AsyncClient, me: dict[str, str], session: AsyncSession):
    table = await start_table(client, me, count=2)
    game = await find_table(session, uuid.UUID(table['id']))
    round_ = await find_round(session, game.id, 1)

    scene = await load_scene(session, game, round_)
    notes = to_monster_notes(read_snapshot(game.content), scene.monsters)

    assert notes == [
        MonsterNote(
            name='수로 쥐', kind='야수', content='', place='수로 입구', unique=False, conditions=['멀쩡함', '멀쩡함']
        )
    ]


# --- 라운드를 닫으면 ---


async def test_the_fake_scene_follows_the_turns(
    client: AsyncClient,
    app: FastAPI,
    me: dict[str, str],
    narrated,
):
    # 쥐가 먼저(민첩 14). 물기 20, 피해 3. 그다음 엘프의 판정 1
    load_dice(app, [PASS, 3, FAIL])
    table = await start_table(client, me, rat_sheet=make_sheet(max_hp=4, dex=14))

    await declare(client, me, table, REST, rest())
    await narrated()

    scene = await scene_of(client, me, table)
    lines = scene.split('\n')
    assert lines[0] == '[1 라운드의 결과]'
    assert lines[1] == '수로 쥐: 엘프에게 물기 (맞음) → 엘프 피해 3 (HP 7/10)'
    assert lines[2].startswith(f'엘프: {REST} (민첩 판정 실패')


async def test_the_fake_scene_shows_the_monster_hit_by_condition(
    client: AsyncClient,
    app: FastAPI,
    me: dict[str, str],
    narrated,
):
    # 엘프가 먼저(민첩 14). 판정 20, 피해 8 로 쥐가 죽는다. 쥐는 움직이지 못해 줄이 없다
    load_dice(app, [PASS, 8])
    table = await start_table(client, me, sheet=make_sheet(dex=14))
    rat = (await monsters_of(client, me, table))[0]

    await declare(client, me, table, KICK, kick(rat['id']))
    await narrated()

    scene = await scene_of(client, me, table)
    assert scene.split('\n')[1].startswith(
        f'엘프: {KICK} (근력 판정 성공: 20 + 0 = 20, 목표 15) → 수로 쥐 피해 8 (죽음)'
    )
    assert len(scene.split('\n')) == 2
