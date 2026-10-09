# game-server/tests/test_llm_narrator.py

"""
언어 모델로 서술하는 서술자(app/rounds/llm_narrator.py)를 검증한다. 모델은 가짜 provider 다(app/ai/fake.py).

보는 것은 셋이다.
  - 서술자는 메시지를 조립해 provider 에 넘기고, 받은 글을 검사해 장면으로 돌려준다.
  - 장면으로 쓸 수 없는 글(끊긴 글, 빈 글, 너무 긴 글)은 받지 않는다. 그러면 라운드는 닫는 중에 머문다.
  - 테이블에서 라운드를 닫으면, 서술자는 이야기의 바탕(진행 지침, 세계관, GM 메모)과 지난 라운드를 받는다.
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient

from app.ai.fake import FAKE_MODEL, FakeProvider
from app.ai.provider import ChatMessage, Completion, GenerationParams, ProviderError, Reasoning, Role
from app.main import API_PREFIX
from app.rounds import llm_narrator, prompt
from app.rounds.llm_narrator import NARRATION_PARAMS, LLMNarrator, NarrationError, accept_completion, accept_scene
from app.rounds.narrator import Move, NarrationRequest, StoryContext
from tests.sheets import SHEET
from tests.signing import SigningKey, make_access_claims, make_token

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')

STORY = StoryContext(title='추격전', rating='all', guide='추격은 언제나 바이크로 한다.')
GUIDE = '추격은 언제나 바이크로 한다.'
SETTING = '열일곱 개의 행성이 고속도로로 이어져 있다.'
GM_NOTES = '악역영애는 사실 경찰의 끄나풀이다.'
OPENING = '사이렌이 울린다.'
REPLY = '엔진 소리가 골목을 메운다.'


def make_request(story: StoryContext | None = STORY) -> NarrationRequest:
    return NarrationRequest(round_number=1, scene=OPENING, moves=[Move('엘프', '달린다.')], story=story)


class BrokenProvider:
    """늘 실패하는 provider. 모델에 연결할 수 없는 경우다."""

    async def complete(self, messages: list[ChatMessage], params: GenerationParams) -> Completion:
        raise ProviderError('연결할 수 없다')


# --- 서술자 하나 ---


async def test_the_narrator_hands_the_assembled_messages_to_the_provider():
    provider = FakeProvider(reply=REPLY)

    scene = await LLMNarrator(provider).narrate(make_request())

    assert scene == REPLY
    (call,) = provider.calls
    assert call.messages == prompt.build_messages(make_request())
    assert call.params == NARRATION_PARAMS


async def test_the_scene_is_trimmed():
    scene = await LLMNarrator(FakeProvider(reply=f'\n  {REPLY}  \n')).narrate(make_request())

    assert scene == REPLY


@pytest.mark.parametrize('text', ['', '   \n  '])
async def test_an_empty_reply_is_not_a_scene(text: str):
    with pytest.raises(NarrationError):
        await LLMNarrator(FakeProvider(reply=text)).narrate(make_request())


async def test_a_reply_cut_by_the_length_limit_is_not_a_scene():
    # 문장 중간에서 끊긴 글이 기록으로 굳는다. 너무 긴 글을 잘라 받지 않는 것과 같은 이유다
    with pytest.raises(NarrationError) as caught:
        await LLMNarrator(FakeProvider(reply=REPLY, truncated=True)).narrate(make_request())

    assert str(caught.value) == 'cut_off'


def test_a_complete_reply_is_accepted():
    assert accept_completion(Completion(text=f' {REPLY} ', model=FAKE_MODEL)) == REPLY


def test_reasoning_is_off_for_narration():
    # 서술은 추론이 필요 없다. 켜면 토큰과 시간만 먹는다. 켜는 것은 테이블 옵션이 생길 때 정한다
    assert NARRATION_PARAMS.reasoning == Reasoning.NONE


def test_a_reply_too_long_is_not_cut_but_refused():
    # 잘라서 받으면 문장 중간에서 끊긴 장면이 기록으로 굳는다
    with pytest.raises(NarrationError):
        accept_scene('가' * (llm_narrator.SCENE_MAX_LENGTH + 1))
    assert accept_scene('가' * llm_narrator.SCENE_MAX_LENGTH) == '가' * llm_narrator.SCENE_MAX_LENGTH


async def test_a_request_without_the_story_is_not_sent():
    provider = FakeProvider()

    with pytest.raises(NarrationError):
        await LLMNarrator(provider).narrate(make_request(story=None))
    assert provider.calls == []


async def test_a_failing_provider_fails_the_narration():
    with pytest.raises(ProviderError):
        await LLMNarrator(BrokenProvider()).narrate(make_request())


async def test_the_fake_provider_says_it_is_fake():
    completion = await FakeProvider(reply=REPLY).complete([ChatMessage(Role.USER, '안녕')], NARRATION_PARAMS)

    # 기록에 남을 때 진짜 모델과 섞이지 않는다
    assert (completion.text, completion.model) == (REPLY, FAKE_MODEL)


# --- 테이블에서 라운드를 닫으면 ---


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(ME)))
    return {'Authorization': f'Bearer {token}'}


async def start_solo(client: AsyncClient, me: dict[str, str], with_world: bool = True) -> str:
    """혼자 앉아 시작한 테이블의 주소. 룰북에 진행 지침이, 세계관에 설정과 GM 메모가 있다."""
    url = API_PREFIX
    rulebook = (await client.post(f'{url}/rulebooks', json={'title': '룰북', 'gm_guide': GUIDE}, headers=me)).json()
    body = {
        'title': '추격전',
        'rulebook_id': rulebook['id'],
        'openings': [OPENING],
        'default_sheet': SHEET,
    }
    if with_world:
        world_body = {'title': '세계', 'setting': SETTING, 'gm_notes': GM_NOTES}
        body['world_id'] = (await client.post(f'{url}/worlds', json=world_body, headers=me)).json()['id']
    scenario = (await client.post(f'{url}/scenarios', json=body, headers=me)).json()
    await client.post(f'{url}/scenarios/{scenario["id"]}/versions', json={}, headers=me)
    table = await client.post(
        f'{url}/tables', json={'scenario_id': scenario['id'], 'version': 1, 'capacity': 1}, headers=me
    )
    table_url = f'{url}/tables/{table.json()["id"]}'
    await client.put(f'{table_url}/character', json={'name': '엘프'}, headers=me)
    started = await client.post(f'{table_url}/start', headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return table_url


async def play_round(client: AsyncClient, me: dict[str, str], table_url: str, content: str, narrated) -> None:
    """선언을 하나 낸다. 혼자라서 라운드가 닫히고, 서술이 끝날 때까지 기다린다."""
    response = await client.put(f'{table_url}/rounds/current/declaration', json={'content': content}, headers=me)
    assert response.status_code == status.HTTP_200_OK, response.text
    await narrated()


@pytest.mark.usefixtures('clean_tables')
async def test_the_reply_of_the_model_becomes_the_next_scene(
    client: AsyncClient, app: FastAPI, me: dict[str, str], narrated
):
    app.state.narrator = LLMNarrator(FakeProvider(reply=REPLY))
    table_url = await start_solo(client, me)

    await play_round(client, me, table_url, '달린다.', narrated)

    current = (await client.get(f'{table_url}/rounds/current', headers=me)).json()
    assert (current['number'], current['scene']) == (2, REPLY)


@pytest.mark.usefixtures('clean_tables')
async def test_the_model_gets_the_story_and_the_rounds_before(
    client: AsyncClient, app: FastAPI, me: dict[str, str], narrated
):
    provider = FakeProvider(reply=REPLY)
    app.state.narrator = LLMNarrator(provider)
    table_url = await start_solo(client, me)

    await play_round(client, me, table_url, '달린다.', narrated)
    await play_round(client, me, table_url, '골목으로 꺾는다.', narrated)

    messages = provider.calls[-1].messages
    system = messages[0].content
    # AI 가 읽으라고 쓴 글이 들어간다. 플레이어에게는 내보내지 않는 글이다
    assert GUIDE in system
    assert SETTING in system
    assert GM_NOTES in system
    # 1 라운드가 지난 기록으로, 2 라운드가 이번 라운드로 들어간다
    contents = [message.content for message in messages]
    assert contents[2:4] == [OPENING, '엘프: 달린다.']
    assert contents[4] == REPLY
    assert '엘프: 골목으로 꺾는다.' in contents[5]


@pytest.mark.usefixtures('clean_tables')
async def test_a_scenario_without_a_world_still_has_a_story(
    client: AsyncClient, app: FastAPI, me: dict[str, str], narrated
):
    provider = FakeProvider(reply=REPLY)
    app.state.narrator = LLMNarrator(provider)
    table_url = await start_solo(client, me, with_world=False)

    await play_round(client, me, table_url, '달린다.', narrated)

    system = provider.calls[0].messages[0].content
    assert GUIDE in system
    assert '## 세계관' not in system


@pytest.mark.usefixtures('clean_tables')
async def test_only_the_latest_rounds_go_to_the_model(client: AsyncClient, app: FastAPI, me: dict[str, str], narrated):
    provider = FakeProvider(reply=REPLY)
    app.state.narrator = LLMNarrator(provider)
    table_url = await start_solo(client, me)

    for number in range(1, 6):
        await play_round(client, me, table_url, f'{number} 번째로 달린다.', narrated)

    contents = [message.content for message in provider.calls[-1].messages]
    # 5 라운드를 닫을 때 지난 기록은 2, 3, 4 라운드다. 1 라운드의 말은 들어가지 않는다
    assert '엘프: 1 번째로 달린다.' not in contents
    assert [content for content in contents if content.startswith('엘프:')] == [
        '엘프: 2 번째로 달린다.',
        '엘프: 3 번째로 달린다.',
        '엘프: 4 번째로 달린다.',
    ]


@pytest.mark.usefixtures('clean_tables')
async def test_a_refused_reply_leaves_the_round_closing(
    client: AsyncClient, app: FastAPI, me: dict[str, str], narrated
):
    app.state.narrator = LLMNarrator(FakeProvider(reply='   '))
    table_url = await start_solo(client, me)

    await play_round(client, me, table_url, '달린다.', narrated)

    # 빈 장면이 기록으로 굳지 않는다. 방장이 닫기를 다시 눌러 맡길 수 있다
    current = (await client.get(f'{table_url}/rounds/current', headers=me)).json()
    assert (current['number'], current['status']) == (1, 'closing')
