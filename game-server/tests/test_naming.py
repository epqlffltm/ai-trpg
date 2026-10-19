# game-server/tests/test_naming.py

"""
지목(인물의 진짜 이름을 짚는 것)을 검증한다.

장면은 스타팅이다. 악역영애(진짜 이름은 비올레타)가 나오고, 드워프는 나오지 않는다(tests/test_npc_actions.py).
지목은 주사위를 굴리지 않는다. 그래서 주사위를 꽂지 않는다. 굴렸다면 남은 눈이 줄어든다.

보는 것은 다섯이다.
  - 받을 때: 행동의 모양, 장면에 없는 인물을 겨눈 것, 이미 드러난 인물. 받을 때는 맞고 틀림을 알려 주지 않는다.
  - 닫을 때: 맞으면 진짜 이름이 드러나고(named_round), 틀리면 아무 일도 없다. 장면에 없는 인물도 짚을 수 있다.
  - 드러난 뒤: 이번 장면의 인물과 로어북 검색이 진짜 이름으로 부른다.
  - 내보내는 것: 결과와 이벤트. 틀린 결과에는 정답의 흔적이 없다.
  - 서술: 결과 줄과 다루는 법 한 줄.
맨 아래에는 DB 를 쓰지 않는 작은 함수들과 로어북의 정답 칸(true_names), 판의 형식의 테스트가 있다.
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import LORE_ENTRY_MAX_TRUE_NAMES, LORE_TRUE_NAME_MAX_LENGTH, LoreKind
from app.assets.scenarios.snapshot import EntrySnapshot, read_snapshot
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_15
from app.engine.action import NAME_GUESS_MAX_LENGTH, ActionKind, NameAction, read_action
from app.lore.retrieval import load_candidates, scene_labels
from app.main import API_PREFIX
from app.rounds import prompt
from app.rounds.move_lines import describe_move, describe_naming
from app.rounds.naming import answers_of, find_named, matches, normalize
from app.rounds.narrator import Move, NamingNote, NarrationRequest
from app.rounds.router import TARGET_ERRORS
from app.tables.models import TableNpc
from tests.signing import SigningKey
from tests.test_npc_actions import (
    LAUGH,
    PASS,
    RecordingNarrator,
    bearer,
    declare,
    events_of,
    load_dice,
    people,
    punch,
    send,
    start_table,
    table_url,
)
from tests.test_treatment import make_format_14

pytestmark = pytest.mark.usefixtures('clean_tables')

# 판에 태도를 적지 않은 인물은 중립이다
NEUTRAL = {'attitude': 'neutral'}

LOREBOOKS_URL = f'{API_PREFIX}/lorebooks'
ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')

POINT = '악역영애를 가리키며 이름을 부른다.'
SHOUT = '허공에 대고 이름을 외친다.'


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 방장이다. 캐릭터는 '엘프'다."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """두 번째로 앉는 사람. 캐릭터는 '드워프 기사'다."""
    return bearer(signing_key, FRIEND)


def name(guess: str, npc: str | None = None) -> dict:
    """이름을 짚는다. npc 를 적으면 그 인물의 이름이라고 짚는다."""
    action = {'kind': 'name', 'name': guess}
    return action if npc is None else {**action, 'npc': npc}


def naming(round_: dict, index: int = 0) -> dict:
    """라운드의 선언에 적힌 지목의 결과."""
    return round_['declarations'][index]['outcome']['naming']


async def named_round(session: AsyncSession, table: dict, entry: dict) -> int | None:
    """DB 에 적힌, 그 인물의 진짜 이름이 드러난 라운드."""
    query = select(TableNpc.named_round).where(
        TableNpc.table_id == uuid.UUID(table['id']), TableNpc.entry_id == uuid.UUID(entry['id'])
    )
    return await session.scalar(query.execution_options(populate_existing=True))


# --- 받을 때 ---


async def test_naming_someone_off_the_scene_by_id_is_rejected(client: AsyncClient, me: dict[str, str]):
    world = await start_table(client, me)

    response = await send(client, me, world['table'], POINT, name('드워프', world['dwarf']['id']))

    # 드워프는 장면에 나오지 않았다. 겨눌 수는 없지만, 이름만으로는 짚을 수 있다(아래)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()['detail'] == TARGET_ERRORS['npc']


@pytest.mark.parametrize(
    'action',
    [
        {'kind': 'name', 'name': ''},
        {'kind': 'name', 'name': '   '},
        {'kind': 'name', 'name': '가' * (NAME_GUESS_MAX_LENGTH + 1)},
        {'kind': 'name'},
        {'kind': 'name', 'name': '비올레타', 'ability': 'str'},
    ],
)
async def test_a_malformed_naming_is_rejected(client: AsyncClient, me: dict[str, str], action: dict):
    world = await start_table(client, me)

    response = await send(client, me, world['table'], POINT, action)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_accepting_does_not_tell_whether_it_is_right(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me, friend)

    right = await declare(client, me, world['table'], POINT, name('비올레타', world['lady']['id']))

    # 아직 열려 있다. 결과도, 드러난 것도 없다. 받을 때 알려 주면 마감 전에 이름을 바꿔 가며 캘 수 있다
    assert right['status'] == 'open'
    assert right['declarations'][0]['outcome'] is None
    assert await named_round(session, world['table'], world['lady']) is None


async def test_naming_someone_already_named_is_rejected(
    client: AsyncClient, app: FastAPI, me: dict[str, str], narrated
):
    world = await start_table(client, me)
    app.state.narrator = RecordingNarrator()
    await declare(client, me, world['table'], POINT, name('비올레타', world['lady']['id']))
    await narrated()

    response = await send(client, me, world['table'], POINT, name('비올레타', world['lady']['id']))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'already_named'


# --- 닫을 때 ---


async def test_a_right_guess_reveals_the_true_name(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)
    dice = load_dice(app, [PASS])

    closing = await declare(client, me, world['table'], POINT, name('비올레타', world['lady']['id']))

    assert naming(closing) == {
        'guess': '비올레타',
        'correct': True,
        'entry_id': world['lady']['id'],
        'name': '비올레타',
        'label': '악역영애',
        'newly': True,
    }
    assert await named_round(session, world['table'], world['lady']) == 1
    # 주사위를 굴리지 않았다
    assert dice.remaining == 1


async def test_a_guess_ignores_case_spaces_and_width(client: AsyncClient, me: dict[str, str]):
    world = await start_table(client, me)

    closing = await declare(client, me, world['table'], POINT, name(' 비 올레타 ', world['lady']['id']))

    # 앞뒤 공백은 받을 때 뗀다. 가운데 빈칸은 견줄 때 가리지 않는다
    assert (naming(closing)['guess'], naming(closing)['correct']) == ('비 올레타', True)


async def test_a_wrong_guess_changes_nothing_and_leaks_nothing(
    client: AsyncClient, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)

    closing = await declare(client, me, world['table'], POINT, name('로즈', world['lady']['id']))

    assert naming(closing) == {
        'guess': '로즈',
        'correct': False,
        'entry_id': world['lady']['id'],
        'name': None,
        'label': '악역영애',
        'newly': False,
    }
    assert await named_round(session, world['table'], world['lady']) is None
    assert '비올레타' not in str(closing)


async def test_the_true_name_of_someone_else_is_wrong_for_this_person(client: AsyncClient, me: dict[str, str]):
    world = await start_table(client, me)

    closing = await declare(client, me, world['table'], POINT, name('드워프', world['lady']['id']))

    # 드워프는 있는 인물이지만 악역영애의 이름은 아니다
    assert naming(closing)['correct'] is False


async def test_naming_freely_finds_someone_off_the_scene(
    client: AsyncClient, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)

    closing = await declare(client, me, world['table'], SHOUT, name('드워프'))

    # 장면에 없는 인물이라 부르던 이름이 없다
    assert naming(closing) == {
        'guess': '드워프',
        'correct': True,
        'entry_id': world['dwarf']['id'],
        'name': '드워프',
        'label': None,
        'newly': True,
    }
    assert await named_round(session, world['table'], world['dwarf']) == 1


async def test_naming_freely_someone_in_the_scene_carries_the_label(client: AsyncClient, me: dict[str, str]):
    world = await start_table(client, me)

    closing = await declare(client, me, world['table'], SHOUT, name('비올레타'))

    assert (naming(closing)['entry_id'], naming(closing)['label']) == (world['lady']['id'], '악역영애')


async def test_a_wrong_free_guess_points_at_no_one(client: AsyncClient, me: dict[str, str]):
    world = await start_table(client, me)

    closing = await declare(client, me, world['table'], SHOUT, name('우주 고속도로'))

    # 고속도로는 장소다. 인물만 지목할 수 있다
    assert naming(closing) == {
        'guess': '우주 고속도로',
        'correct': False,
        'entry_id': None,
        'name': None,
        'label': None,
        'newly': False,
    }


async def test_two_right_guesses_in_one_round_reveal_once(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me, friend)
    await declare(client, me, world['table'], POINT, name('비올레타', world['lady']['id']))

    closing = await declare(client, friend, world['table'], SHOUT, name('비올레타'))

    # 들어온 순서로 판정한다. 뒷사람도 맞았지만 처음 드러낸 것은 앞사람이다
    assert [naming(closing, index)['newly'] for index in range(2)] == [True, False]
    assert [naming(closing, index)['correct'] for index in range(2)] == [True, True]
    assert await named_round(session, world['table'], world['lady']) == 1


async def test_naming_and_a_check_in_one_round(client: AsyncClient, app: FastAPI, me: dict[str, str], friend):
    world = await start_table(client, me, friend)
    load_dice(app, [PASS, 4])
    await declare(client, me, world['table'], POINT, name('비올레타', world['lady']['id']))

    closing = await declare(client, friend, world['table'], '악역영애에게 주먹을 날린다.', punch(world['lady']['id']))

    # 판정의 결과에는 지목이 없고, 지목의 결과에는 굴림이 없다
    assert 'roll' not in closing['declarations'][0]['outcome']
    assert closing['declarations'][1]['outcome']['npc_effect']['name'] == '악역영애'


async def test_people_without_states_cannot_be_named(client: AsyncClient, me: dict[str, str], session: AsyncSession):
    world = await start_table(client, me)
    # NPC 의 상태가 생기기 전에 시작한 테이블. 맞혀도 적어 둘 곳이 없다
    await session.execute(text('DELETE FROM table_npcs'))
    await session.commit()

    closing = await declare(client, me, world['table'], SHOUT, name('드워프'))

    assert (naming(closing)['correct'], naming(closing)['name']) == (False, None)


# --- 드러난 뒤 ---


async def test_the_named_person_is_listed_by_the_true_name(
    client: AsyncClient, app: FastAPI, me: dict[str, str], narrated
):
    world = await start_table(client, me)
    # 다음 장면도 악역영애를 호칭으로만 부른다. 그래도 진짜 이름으로 보인다
    app.state.narrator = RecordingNarrator()
    await declare(client, me, world['table'], POINT, name('비올레타', world['lady']['id']))
    await narrated()

    cast = await people(client, me, world['table'])

    assert cast['round'] == 2
    assert cast['people'] == [
        {'id': world['lady']['id'], 'name': '비올레타', 'status': 'alive', 'injuries': [], 'named': True, **NEUTRAL}
    ]


async def test_the_next_narration_gets_the_true_name(client: AsyncClient, app: FastAPI, me: dict[str, str], narrated):
    world = await start_table(client, me)
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    await declare(client, me, world['table'], POINT, name('비올레타', world['lady']['id']))
    await narrated()

    await declare(client, me, world['table'], LAUGH)
    await narrated()

    second = narrator.requests[1]
    assert [person.name for person in second.people] == ['비올레타']


async def test_the_lore_keeps_the_true_name_of_the_named(
    client: AsyncClient, app: FastAPI, me: dict[str, str], narrated
):
    world = await start_table(client, me)
    app.state.narrator = RecordingNarrator()
    table_id = uuid.UUID(world['table']['id'])
    before = await load_candidates(app.state.session_factory, table_id)
    await declare(client, me, world['table'], POINT, name('비올레타', world['lady']['id']))
    await narrated()

    after = await load_candidates(app.state.session_factory, table_id)

    assert before.named == frozenset()
    assert after.named == frozenset({uuid.UUID(world['lady']['id'])})


# --- 내보내는 것 ---


async def test_the_result_is_an_event(client: AsyncClient, me: dict[str, str]):
    world = await start_table(client, me)
    await declare(client, me, world['table'], POINT, name('로즈', world['lady']['id']))

    (event,) = await events_of(client, me, world['table'], 'naming_resolved')
    (action,) = await events_of(client, me, world['table'], 'player_action')

    assert event['payload'] == {
        'round': 1,
        'character_name': '엘프',
        'guess': '로즈',
        'correct': False,
        'entry_id': world['lady']['id'],
        'name': None,
        'label': '악역영애',
        'newly': False,
    }
    assert event['caused_by_sequence'] == action['sequence']
    assert event['actor_id'] is None


async def test_the_round_shows_the_result_to_everyone(client: AsyncClient, me: dict[str, str], friend):
    world = await start_table(client, me, friend)
    await declare(client, me, world['table'], POINT, name('비올레타', world['lady']['id']))
    await declare(client, friend, world['table'], LAUGH)

    response = await client.get(table_url(world['table'], '/rounds/1'), headers=friend)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()['declarations'][0]['outcome']['naming']['name'] == '비올레타'


# --- 서술 ---


async def test_the_narrator_gets_the_result_line(client: AsyncClient, app: FastAPI, me: dict[str, str], narrated):
    world = await start_table(client, me)
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    await declare(client, me, world['table'], POINT, name('비올레타', world['lady']['id']))
    await narrated()

    (request,) = narrator.requests
    assert request.moves[0].naming == NamingNote(guess='비올레타', correct=True, name='비올레타', label='악역영애')
    assert request.moves[0].verdict is None
    text_ = prompt.build_messages(request)[-1].content
    assert '→ 지목 맞음: 악역영애의 진짜 이름은 비올레타' in text_
    assert prompt.NAMING_NOTE in text_


def test_the_rule_line_is_only_for_rounds_with_naming():
    plain = Move('엘프', LAUGH)
    named = Move('엘프', POINT, naming=NamingNote(guess='로즈', correct=False, label='악역영애'))

    assert prompt.NAMING_NOTE not in prompt.round_text(request_of([plain]))
    assert prompt.NAMING_NOTE in prompt.round_text(request_of([plain, named]))


def request_of(moves: list[Move]) -> NarrationRequest:
    return NarrationRequest(round_number=1, scene='장면', moves=moves)


@pytest.mark.parametrize(
    ('note', 'expected'),
    [
        (
            NamingNote(guess='비올레타', correct=True, name='비올레타', label='악역영애'),
            '→ 지목 맞음: 악역영애의 진짜 이름은 비올레타',
        ),
        (NamingNote(guess='비올레타', correct=True, name='비올레타', label='비올레타'), '→ 지목 맞음: 비올레타'),
        (
            NamingNote(guess='드워프', correct=True, name='드워프'),
            '→ 지목 맞음: 드워프(이)라는 인물이 이 이야기에 있다. 이름 밖의 주장이 맞는지는 정해지지 않았다',
        ),
        (
            NamingNote(guess='로즈', correct=False, label='악역영애'),
            "→ 지목 틀림: 악역영애의 진짜 이름은 '로즈'(이)가 아니다",
        ),
        (NamingNote(guess='로즈', correct=False), "→ 지목 틀림: '로즈'(은)는 맞는 이름이 아니다"),
    ],
)
def test_the_result_is_told_in_one_line(note: NamingNote, expected: str):
    assert describe_naming(note) == expected


def test_a_naming_is_not_doing_nothing_before_dying():
    move = Move('엘프', POINT, dead=True, naming=NamingNote(guess='로즈', correct=False))

    # 지목의 결과가 있으면 하려던 일을 한 것이다
    assert '하려던 일을 하기 전에 죽었다' not in describe_move(move)


# --- 작은 함수들. DB 를 쓰지 않는다 ---


def person(name: str, true_names: list[str] | None = None, keywords: list[str] | None = None) -> EntrySnapshot:
    return EntrySnapshot(
        id=uuid.uuid4(),
        name=name,
        keywords=keywords or [],
        content='',
        kind=LoreKind.PERSON,
        true_names=true_names or [],
    )


@pytest.mark.parametrize(
    ('left', 'right'),
    [('Violetta', 'violetta'), ('비 올레타', '비올레타'), ('ＡＢＣ', 'abc'), (' 비올레타\t', '비올레타')],
)
def test_normalizing_ignores_case_spaces_and_width(left: str, right: str):
    assert normalize(left) == normalize(right)


def test_the_name_is_the_answer_when_none_are_written():
    assert answers_of(person('비올레타')) == ['비올레타']


def test_written_answers_replace_the_name():
    lady = person('비올레타 폰 로젠', true_names=['비올레타', 'Violetta'])

    assert matches(lady, 'violetta')
    assert matches(lady, '비올레타')
    # 제작자가 정답을 적었으면 항목의 이름은 정답이 아니다(제목처럼 쓴 이름일 수 있다)
    assert not matches(lady, '비올레타 폰 로젠')


def test_finding_by_name_takes_the_first_in_order():
    first = person('쌍둥이', true_names=['리엔'])
    second = person('리엔')

    assert find_named([first, second], '리엔') is first
    assert find_named([first, second], '로즈') is None


def test_the_named_keep_their_true_name_in_the_lore():
    lady = person('비올레타', keywords=['악역영애'])
    scene = '악역영애가 부채를 펼친다.'

    assert scene_labels([lady], scene) == {'비올레타': '악역영애'}
    assert scene_labels([lady], scene, named=frozenset({lady.id})) == {}


def test_a_naming_action_is_read_back():
    action = read_action({'kind': 'name', 'name': '비올레타', 'npc': None})

    assert action == NameAction(kind=ActionKind.NAME, name='비올레타')


def test_a_naming_action_takes_no_other_field():
    with pytest.raises(ValidationError):
        read_action({'kind': 'name', 'name': '비올레타', 'difficulty': 'hard'})


# --- 로어북의 정답 칸 ---


async def add_entry(client: AsyncClient, me: dict[str, str], **body):
    """새 로어북에 항목 하나를 더한다. 응답을 그대로 돌려준다."""
    lorebook = (await client.post(LOREBOOKS_URL, json={'title': '인명사전'}, headers=me)).json()
    return await client.post(f'{LOREBOOKS_URL}/{lorebook["id"]}/entries', json=body, headers=me)


async def test_an_entry_keeps_its_answers(client: AsyncClient, me: dict[str, str]):
    response = await add_entry(
        client, me, name='비올레타 폰 로젠', true_names=[' 비올레타 ', 'Violetta'], kind='person'
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()['true_names'] == ['비올레타', 'Violetta']


async def test_answers_can_be_changed(client: AsyncClient, me: dict[str, str]):
    lorebook = (await client.post(LOREBOOKS_URL, json={'title': '인명사전'}, headers=me)).json()
    entries_url = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'
    created = (await client.post(entries_url, json={'name': '비올레타', 'kind': 'person'}, headers=me)).json()

    response = await client.patch(f'{entries_url}/{created["id"]}', json={'true_names': ['로즈']}, headers=me)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()['true_names'] == ['로즈']


@pytest.mark.parametrize(
    'true_names',
    [
        [f'이름{number}' for number in range(LORE_ENTRY_MAX_TRUE_NAMES + 1)],
        ['가' * (LORE_TRUE_NAME_MAX_LENGTH + 1)],
        ['   '],
        ['Violetta', 'violetta'],
        '비올레타',
    ],
)
async def test_bad_answers_are_rejected(client: AsyncClient, me: dict[str, str], true_names):
    response = await add_entry(client, me, name='비올레타', true_names=true_names, kind='person')

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 판의 형식 ---


def make_format_15() -> dict:
    """정답 칸이 없던 때의 판. 치료가 생긴 형식이다."""
    return UPGRADES[14](make_format_14())


def test_an_old_version_reads_with_no_answers():
    document = make_format_15()
    document['lorebooks'] = [
        {
            'id': str(uuid.uuid4()),
            'title': '인명사전',
            'entries': [{'id': str(uuid.uuid4()), 'name': '스미스', 'keywords': [], 'content': ''}],
        }
    ]

    old = read_snapshot(document)

    assert [entry.true_names for lorebook in old.lorebooks for entry in lorebook.entries] == [[]]


def test_upgrading_keeps_answers_already_there():
    document = make_format_15()
    document['lorebooks'] = [
        {
            'id': str(uuid.uuid4()),
            'title': '인명사전',
            'entries': [{'id': str(uuid.uuid4()), 'name': '스미스', 'true_names': ['존']}],
        }
    ]

    current = upgrade_from_15(document)

    assert current['format'] == 16
    assert current['lorebooks'][0]['entries'][0]['true_names'] == ['존']
    # 받은 문서는 고치지 않는다
    assert document['format'] == 15
