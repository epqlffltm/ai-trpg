# trpg-server/tests/test_secret_names.py

"""
아직 드러나지 않은 진짜 이름이 서술로 새지 않게 하는 것(app/rounds/secret_names.py)을 검증한다.

보는 것.
  - 숨길 이름: 제작자가 정답으로 적은 이름(true_names)만이다. 키워드, 짧은 이름, 이번 장면에 이미 나온 이름은 빼고,
    맞힌 인물은 숨기지 않는다. 대신 부를 호칭은 항목의 이름이거나(그것이 숨길 이름이 아니면) 키워드다.
  - 가리기: 긴 이름부터 바꾼다. 미리 보기는 조각의 끝에 걸린 이름의 앞부분을 잡아 두었다가 가려서 넘긴다.
  - 서술자: 숨길 이름을 쓴 글은 장면으로 받지 않는다(secret_leaked). 미리 보기에는 가린 글만 간다.
  - 다시 부르기: 다시 불러 깨끗한 장면을 받으면 그것을, 끝내 새면 가린 장면을 쓴다. 가린 장면이 없으면 실패다.
  - 테이블: 서술을 맡길 때 숨길 이름이 실리고, 맞힌 뒤에는 빠진다. 끝내 새면 다음 장면과 기록에 진짜 이름이 없다.
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient

from app.ai.fake import FakeCallLog, FakeProvider
from app.ai.provider import ProviderError
from app.assets.models import LoreKind
from app.assets.scenarios.snapshot import EntrySnapshot
from app.rounds.llm_narrator import SECRET_LEAKED, LLMNarrator, SecretLeaked, keep_secrets
from app.rounds.narrator import Move, NarrationRequest, StoryContext
from app.rounds.retrying_narrator import NarrationFailed
from app.rounds.secret_names import GuardedPreview, held_length, leaked, redact, secret_names
from tests import test_npc_actions as npc_tests
from tests.previews import RecordingPreview
from tests.sheets import SHEET
from tests.test_npc_actions import (
    LADY_SHEET,
    LAUGH,
    LOREBOOKS_URL,
    NPC_DEFAULT,
    OPENING,
    RULEBOOKS_URL,
    SCENARIOS_URL,
    TABLES_URL,
    RecordingNarrator,
    declare,
    events_of,
    post,
    table_url,
)
from tests.test_retrying_narrator import Setup

me = npc_tests.me

LADY = {'비올레타': '악역영애', 'Violetta': '악역영애'}
STORY = StoryContext(title='추격전', rating='all', guide='추격은 바이크로 한다.')
LEAKY = '악역영애가 부채를 접는다. 비올레타는 웃었다.'
CLEAN = '악역영애가 부채를 접는다. 그녀는 웃었다.'


def person(name: str, keywords: list[str], true_names: list[str]) -> EntrySnapshot:
    return EntrySnapshot(
        id=uuid.uuid4(), name=name, keywords=keywords, content='', kind=LoreKind.PERSON, true_names=true_names
    )


def request(secrets: dict[str, str]) -> NarrationRequest:
    return NarrationRequest(
        round_number=1, scene=OPENING, moves=[Move('엘프', '달린다.')], story=STORY, secrets=secrets
    )


# --- 숨길 이름 ---


def test_only_the_written_answers_are_hidden_behind_the_label():
    lady = person('악역영애', ['영애'], ['비올레타', 'Violetta'])
    dwarf = person('드워프', ['망치'], [])

    # 정답을 적지 않은 인물은 키워드가 있어도 아무것도 숨기지 않는다
    assert secret_names([lady, dwarf], set(), '') == {'비올레타': '악역영애', 'Violetta': '악역영애'}


def test_an_entry_named_by_its_true_name_is_called_by_its_keyword():
    lady = person('비올레타', ['영애', '악역영애'], ['비올레타'])

    # 장면에 나온 키워드가 있으면 그것, 없으면 가장 긴 키워드다
    assert secret_names([lady], set(), '') == {'비올레타': '악역영애'}
    assert secret_names([lady], set(), '영애가 웃는다.') == {'비올레타': '영애'}


def test_what_cannot_be_hidden_is_not():
    no_keyword = person('비올레타', [], ['비올레타', '비비'])
    short = person('악역영애', [], ['비'])
    keyword = person('악역영애', ['로젠'], ['로젠', '비올레타'])

    # 키워드가 없으면 항목의 이름이 부를 이름이다. 한 글자, 키워드는 숨기지 않는다
    assert secret_names([no_keyword, short, keyword], set(), '') == {'비비': '비올레타', '비올레타': '악역영애'}


def test_a_name_already_in_the_scene_and_the_named_are_not_hidden():
    lady = person('악역영애', [], ['비올레타'])
    dwarf = person('드워프', [], ['토르빈'])

    assert secret_names([lady, dwarf], {dwarf.id}, '비올레타가 웃는다.') == {}


def test_leaks_are_found_and_hidden_longest_first():
    secrets = {'비올레타': '악역영애', '비올레타 폰 로젠': '악역영애'}

    assert leaked('비올레타 폰 로젠이 웃는다.', secrets) == ['비올레타 폰 로젠', '비올레타']
    assert redact('비올레타 폰 로젠이 웃는다. 비올레타!', secrets) == '악역영애이 웃는다. 악역영애!'
    assert leaked(CLEAN, secrets) == []


@pytest.mark.parametrize(
    ('text', 'held'), [('그녀는 비올', 2), ('그녀는 비', 1), ('그녀는 비올레타', 0), ('그녀는', 0), ('레타', 0)]
)
def test_the_start_of_a_name_at_the_end_is_held(text: str, held: int):
    assert held_length(text, {'비올레타': '악역영애'}) == held


def test_the_preview_never_shows_a_name_cut_across_pieces():
    shown = RecordingPreview()
    preview = GuardedPreview(shown, LADY)

    preview.begin()
    for piece in ['악역영애가 부채를 접는다. 비올', '레타는 웃었', '다.']:
        preview.text(piece)

    assert shown.shown() == ['악역영애가 부채를 접는다. 악역영애는 웃었다.']
    assert all('비올' not in piece for piece in shown.attempts[0])


def test_a_new_attempt_drops_what_was_held():
    shown = RecordingPreview()
    preview = GuardedPreview(shown, LADY)
    preview.begin()
    preview.text('그녀는 비올')

    preview.begin()
    preview.text('레타가 아니다.')

    assert shown.shown() == ['그녀는 ', '레타가 아니다.']


# --- 서술자 ---


def test_a_scene_with_a_secret_is_refused_with_the_hidden_version():
    with pytest.raises(SecretLeaked) as caught:
        keep_secrets(LEAKY, LADY)

    assert str(caught.value) == SECRET_LEAKED
    assert caught.value.redacted == '악역영애가 부채를 접는다. 악역영애는 웃었다.'
    assert keep_secrets(CLEAN, LADY) == CLEAN


async def test_the_narrator_refuses_a_leak_and_shows_only_the_hidden_text():
    shown = RecordingPreview()
    log = FakeCallLog()

    with pytest.raises(SecretLeaked):
        await LLMNarrator(FakeProvider(reply=LEAKY, piece_size=3), log).narrate(request(LADY), shown)

    assert '비올레타' not in ''.join(shown.shown())
    (record,) = log.records
    assert record.error == SECRET_LEAKED


async def test_without_secrets_the_narrator_is_as_before():
    shown = RecordingPreview()

    scene = await LLMNarrator(FakeProvider(reply=LEAKY, piece_size=3), FakeCallLog()).narrate(request({}), shown)

    assert scene == LEAKY
    assert shown.shown() == [LEAKY]


# --- 다시 부르기 ---


async def test_a_leak_is_tried_again_and_a_clean_scene_is_used():
    setup = Setup()
    narrator = setup.narrator(setup.model('a', SecretLeaked('가린 장면'), CLEAN))

    assert await narrator.narrate(request(LADY)) == CLEAN
    assert setup.calls == ['a', 'a']


async def test_when_every_try_leaks_the_hidden_scene_is_used():
    setup = Setup()
    narrator = setup.narrator(
        setup.model('a', SecretLeaked('가린 장면 1'), SecretLeaked('가린 장면 2')),
        setup.model('b', SecretLeaked('가린 장면 3'), ProviderError('timeout')),
    )

    # 마지막으로 가린 장면이다. 뒤의 실패가 다른 까닭이어도 이야기를 잇는다
    assert await narrator.narrate(request(LADY)) == '가린 장면 3'
    assert setup.calls == ['a', 'a', 'b', 'b']


async def test_without_a_leak_a_failure_is_still_a_failure():
    setup = Setup()
    narrator = setup.narrator(setup.model('a', ProviderError('timeout'), ProviderError('timeout')))

    with pytest.raises(NarrationFailed):
        await narrator.narrate(request(LADY))


# --- 테이블 ---


async def start_with_a_true_name(client: AsyncClient, me: dict) -> dict:
    """진짜 이름(비올레타)을 정답으로 적은 인물 하나가 든 판으로 혼자 테이블을 시작한다. 테이블과 그 인물이다."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='추격전의 인물들')
    entries_url = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'
    lady = await post(
        client,
        entries_url,
        me,
        name='악역영애',
        keywords=['영애'],
        true_names=['비올레타'],
        content='경찰의 끄나풀',
        kind='person',
    )
    rulebook = await post(client, RULEBOOKS_URL, me, title='룰북')
    scenario = await post(
        client,
        SCENARIOS_URL,
        me,
        title='열일곱 행성 추격전',
        rulebook_id=rulebook['id'],
        lorebook_ids=[lorebook['id']],
        openings=[OPENING],
        default_sheet=SHEET,
        npc_sheets=[{'entry_id': lady['id'], 'sheet': LADY_SHEET}],
        default_npc_sheet=NPC_DEFAULT,
    )
    await post(client, f'{SCENARIOS_URL}/{scenario["id"]}/versions', me)
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1)
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return {'table': table, 'lady': lady}


@pytest.mark.usefixtures('clean_tables')
async def test_the_narrator_is_told_what_to_hide_until_it_is_named(
    client: AsyncClient, app: FastAPI, me: dict, narrated
):
    world = await start_with_a_true_name(client, me)
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    guess = {'kind': 'name', 'name': '비올레타', 'npc': world['lady']['id']}

    await declare(client, me, world['table'], LAUGH)
    await narrated()
    await declare(client, me, world['table'], '악역영애를 가리키며 이름을 부른다.', guess)
    await narrated()

    before, named = narrator.requests
    assert before.secrets == {'비올레타': '악역영애'}
    # 맞힌 라운드의 서술부터는 숨기지 않는다. 서술이 드러난 이름을 부를 수 있어야 한다
    assert named.secrets == {}


@pytest.mark.usefixtures('clean_tables')
async def test_a_leak_that_never_stops_is_hidden_in_the_story(client: AsyncClient, app: FastAPI, me: dict, narrated):
    world = await start_with_a_true_name(client, me)
    app.state.narrator = Setup().narrator(LLMNarrator(FakeProvider(reply=LEAKY), FakeCallLog()))

    await declare(client, me, world['table'], LAUGH)
    await narrated()

    current = (await client.get(table_url(world['table'], '/rounds/current'), headers=me)).json()
    (told,) = [event for event in await events_of(client, me, world['table'], 'gm_narration')][-1:]
    assert current['scene'] == '악역영애가 부채를 접는다. 악역영애는 웃었다.'
    assert '비올레타' not in told['payload']['text']
