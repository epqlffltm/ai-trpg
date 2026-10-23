# chat-server/tests/test_note_proposals_api.py

"""
요약이 제안한 기억 메모(#677)를 API 로 검증한다. 실제 DB(chat_test)에서 돈다. asset 서버와 모델은 가짜다.

보는 것.
  - 요약을 쓸 때 같은 호출에서 받은 제안을 메모의 제안(source summary, pending)으로 적는다
  - 제안은 받아들이기 전에는 모델에 가지 않고 메모의 수에도 들지 않는다. 받아들이면(accept) 다음 말부터 간다
  - 받아들일 때 메모가 가득 찼으면 409 notes_full. 이미 모델에 가는 메모를 받아들이면 그대로다. 버리기는 지우기다
  - 이미 있는 메모와 같은 제안은 적지 않는다. 기다리는 제안은 대화마다 상한까지만 쌓인다
  - 길이 상한에서 잘린 요약이면 제안은 버린다(줄거리는 적는다)
한 번에 적힌 제안은 같은 시각이라 그 안의 순서는 정하지 않는다. 그래서 글로 찾는다.
"""

import asyncio
import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.models import NOTES_PER_CONVERSATION, PROPOSALS_PER_CONVERSATION, MemoryNote, NoteSource, Summary
from tests.assets import FakeAsset
from tests.models import FakeRouter, ScriptedProvider
from tests.turns import CONVERSATIONS_URL, bearer, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables', 'router', 'summarizing')

LONG = '가' * 400
STORY = '비가 왔다. 사용자는 고양이 이야기를 했다.\n<notes>\n- 고양이를 좋아한다\n- 3월생이다\n'


class Answers(ScriptedProvider):
    """대화에는 짧은 답을, 요약을 시키면 정해 둔 줄거리와 제안을 준다."""

    story: str = STORY
    cut: bool = False

    async def complete(self, messages, params, on_text=None):
        if '요약하는 도우미' in messages[0].content:
            return await ScriptedProvider(pieces=[self.story], truncated=self.cut).complete(messages, params)
        self.calls.append((list(messages), params))
        return await ScriptedProvider(pieces=['응.']).complete(messages, params, on_text or (lambda text: None))


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def provider() -> Answers:
    return Answers()


@pytest.fixture
def router(app: FastAPI, provider: Answers) -> FakeRouter:
    fake = FakeRouter(provider)
    app.state.model_router = fake
    return fake


@pytest.fixture
def summarizing(app: FastAPI) -> None:
    """요약을 켠다. 창은 1,000자, 밀려난 말이 둘이면 요약한다."""
    app.state.settings = app.state.settings.model_copy(
        update={'summary_model': 'luna', 'chat_context_chars': 1000, 'summary_after_messages': 2}
    )


@pytest.fixture
async def conversation(clean_tables: None, session: AsyncSession, client: AsyncClient, asset: FakeAsset, mine: dict):
    await turn_on_luna(session)
    return await start_with_luna(client, asset, mine)


def notes_url(conversation: dict, *rest: str) -> str:
    return '/'.join([f'{CONVERSATIONS_URL}/{conversation["id"]}/notes', *rest])


async def say(client: AsyncClient, app: FastAPI, headers: dict, conversation: dict, content: str = LONG) -> None:
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    response = await client.post(url, json={'content': content}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    await asyncio.gather(*list(app.state.turns))
    await asyncio.gather(*list(app.state.summarizer.tasks))


async def summarize(client: AsyncClient, app: FastAPI, headers: dict, conversation: dict) -> None:
    """요약이 한 번 쓰일 만큼 말한다."""
    for _ in range(3):
        await say(client, app, headers, conversation)


async def notes(client: AsyncClient, headers: dict, conversation: dict) -> list[dict]:
    return (await client.get(notes_url(conversation), headers=headers)).json()


async def proposal(client: AsyncClient, headers: dict, conversation: dict, text: str = '고양이를 좋아한다') -> dict:
    (found,) = [note for note in await notes(client, headers, conversation) if note['text'] == text]
    return found


async def test_a_summary_proposes_notes_that_wait_for_acceptance(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, provider: Answers, mine: dict
):
    await summarize(client, app, mine, conversation)

    listed = await notes(client, mine, conversation)
    assert sorted((note['text'], note['source'], note['pending']) for note in listed) == [
        ('3월생이다', 'summary', True),
        ('고양이를 좋아한다', 'summary', True),
    ]
    # 줄거리에는 제안이 섞이지 않는다
    (story,) = (await session.scalars(select(Summary.text))).all()
    assert story == '비가 왔다. 사용자는 고양이 이야기를 했다.'
    await say(client, app, mine, conversation, '안녕')
    assert '[기억]' not in provider.calls[-1][0][0].content


async def test_an_accepted_proposal_goes_to_the_model(
    client: AsyncClient, app: FastAPI, conversation: dict, provider: Answers, mine: dict
):
    await summarize(client, app, mine, conversation)
    found = await proposal(client, mine, conversation)

    accepted = await client.post(notes_url(conversation, found['id'], 'accept'), headers=mine)
    await say(client, app, mine, conversation, '안녕')

    assert accepted.status_code == status.HTTP_200_OK
    body = accepted.json()
    assert (body['pending'], body['source'], body['accepted_at'] is not None) == (False, 'summary', True)
    card = provider.calls[-1][0][0].content
    assert '[기억]\n- 고양이를 좋아한다' in card
    assert '3월생이다' not in card


async def test_accepting_when_full_is_409_and_a_users_note_stays(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, mine: dict
):
    await summarize(client, app, mine, conversation)
    found = await proposal(client, mine, conversation)
    for number in range(NOTES_PER_CONVERSATION):
        added = await client.post(notes_url(conversation), json={'text': f'메모 {number}'}, headers=mine)
        # 제안은 수에 들지 않아 스무 개를 다 쓸 수 있다
        assert added.status_code == status.HTTP_201_CREATED, added.text
    users = (await notes(client, mine, conversation))[-1]

    full = await client.post(notes_url(conversation, found['id'], 'accept'), headers=mine)
    again = await client.post(notes_url(conversation, users['id'], 'accept'), headers=mine)

    assert (full.status_code, full.json()['code']) == (status.HTTP_409_CONFLICT, 'notes_full')
    assert (again.status_code, again.json()['pending'], again.json()['accepted_at']) == (
        status.HTTP_200_OK,
        False,
        None,
    )


async def test_dismissing_is_deleting(client: AsyncClient, app: FastAPI, conversation: dict, mine: dict):
    await summarize(client, app, mine, conversation)
    found = await proposal(client, mine, conversation)

    dismissed = await client.delete(notes_url(conversation, found['id']), headers=mine)

    assert dismissed.status_code == status.HTTP_204_NO_CONTENT
    assert [note['text'] for note in await notes(client, mine, conversation)] == ['3월생이다']


async def test_a_proposal_matching_an_existing_note_is_skipped(
    client: AsyncClient, app: FastAPI, conversation: dict, mine: dict
):
    await client.post(notes_url(conversation), json={'text': '고양이를  좋아한다'}, headers=mine)

    await summarize(client, app, mine, conversation)

    listed = await notes(client, mine, conversation)
    assert sorted((note['text'], note['pending']) for note in listed) == [
        ('3월생이다', True),
        ('고양이를  좋아한다', False),
    ]


async def test_waiting_proposals_stop_at_the_limit(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, mine: dict
):
    for number in range(PROPOSALS_PER_CONVERSATION - 1):
        session.add(
            MemoryNote(conversation_id=uuid.UUID(conversation['id']), text=f'제안 {number}', source=NoteSource.SUMMARY)
        )
    await session.commit()

    await summarize(client, app, mine, conversation)

    pending = [note for note in await notes(client, mine, conversation) if note['pending']]
    assert len(pending) == PROPOSALS_PER_CONVERSATION
    assert sum(note['text'] in ('고양이를 좋아한다', '3월생이다') for note in pending) == 1


async def test_a_cut_summary_keeps_the_story_but_drops_the_proposals(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, provider: Answers, mine: dict
):
    provider.cut = True

    await summarize(client, app, mine, conversation)

    assert len((await session.scalars(select(Summary))).all()) == 1
    assert await notes(client, mine, conversation) == []


async def test_a_note_outside_the_conversation_or_someone_elses_conversation_is_404(
    client: AsyncClient, app: FastAPI, signing_key: SigningKey, conversation: dict, mine: dict
):
    await summarize(client, app, mine, conversation)
    found = await proposal(client, mine, conversation)

    missing = await client.post(notes_url(conversation, str(uuid.uuid4()), 'accept'), headers=mine)
    theirs = await client.post(
        notes_url(conversation, found['id'], 'accept'), headers=bearer(signing_key, uuid.uuid4())
    )

    assert (missing.status_code, missing.json()['code']) == (status.HTTP_404_NOT_FOUND, 'note_not_found')
    assert theirs.status_code == status.HTTP_404_NOT_FOUND
    assert (await proposal(client, mine, conversation))['pending']
