# trpg-server/tests/test_improvised_encounters.py

"""
즉흥 조우(#254)를 검증한다. 서술(AI)이 판의 조우 표에서 몬스터의 등장을 고르고, 엔진이 검증해 받아들인다.

판은 tests/test_wander_rolls.py 의 지하 수로다(혼자 앉고 수로 입구에서 시작한다). 판의 기본 조우 표에 쥐 둘과 해골
하나의 줄이 있다. 길을 가거나 길게 쉬지 않으므로 무작위 조우는 굴리지 않는다(주사위가 필요 없다).
서술자는 받은 요청을 적어 두고, 정해 둔 장면(표식이 붙을 수 있다)을 돌려준다.

보는 것.
  - 시나리오: 횟수(0~20)를 저장하고 보인다. 21 은 422 다
  - 서술 요청: 켰고 고를 것이 있을 때만 고를 거리가 실린다. [즉흥 조우] 와 표식을 적는 법이 프롬프트에 들어간다
  - 받아들이기: 고른 번호의 몬스터를 그 장소에 놓고 monsters_appeared(cause improvised)를 닫힘에 잇는다.
    장면에서 표식을 뗀다. 횟수를 다 쓰면 고를 거리가 없고 표식은 떼기만 한다. 없는 번호도 떼기만 한다.
    살아 있는 몬스터가 있는 장소와 안전한 곳(그 장소의 표의 확률이 0)은 고를 거리가 아니다
  - 미리 보기: 표식을 가린다
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import API_PREFIX
from app.rounds import prompt
from app.rounds.improvised import TaglessPreview, split_tag
from app.rounds.narrator import NO_PREVIEW, EncounterNote, NarrationRequest, Preview
from app.tables.models import GameTable
from tests import test_wander_rolls as wanders

pytestmark = pytest.mark.usefixtures('clean_tables')

me = wanders.me
world = wanders.world
table = wanders.table
line = wanders.line
start = wanders.start
monsters_at = wanders.monsters_at
appeared = wanders.appeared

SCENE = '물방울이 떨어진다. 어둠 속에서 무언가 찍찍거린다.'


class TaggingNarrator:
    """받은 요청을 적어 두고 정해 둔 장면을 돌려주는 서술자. tag 가 있으면 장면의 끝에 표식을 붙인다."""

    def __init__(self, tag: str | None = '[[조우 1]]') -> None:
        self.requests: list[NarrationRequest] = []
        self.tag = tag

    async def narrate(self, request: NarrationRequest, preview: Preview = NO_PREVIEW) -> str:
        self.requests.append(request)
        return SCENE if self.tag is None else f'{SCENE}\n\n{self.tag}'


async def wait(client: AsyncClient, me: dict, the_table: dict, narrated) -> None:
    """혼자라 선언하면 라운드가 닫힌다. 서술까지 기다린다."""
    await wanders.turns.declare(client, me, the_table, '숨을 고른다.')
    await narrated()


def rats_and_skeleton(world: dict) -> list[dict]:
    """판의 기본 표. 쥐 둘과 해골 하나의 줄이다."""
    return [table(None, 10, line(world['rat'], 2), line(world['skeleton'], 1))]


async def latest_scene(client: AsyncClient, me: dict, the_table: dict) -> str:
    events = await wanders.turns.events_of(client, me, the_table)
    return [item for item in events if item['type'] == 'gm_narration'][-1]['payload']['text']


async def count_of(session: AsyncSession, the_table: dict) -> int:
    query = select(GameTable.improvised_encounters).where(GameTable.id == uuid.UUID(the_table['id']))
    return await session.scalar(query.execution_options(populate_existing=True))


# --- 시나리오 ---


async def test_the_scenario_keeps_its_improvised_encounters(client: AsyncClient, me: dict, world: dict):
    url = f'{API_PREFIX}/scenarios'
    made = await wanders.post(client, url, me, title='수로', improvised_encounters=3)
    refused = await client.patch(f'{url}/{made["id"]}', json={'improvised_encounters': 21}, headers=me)

    assert made['improvised_encounters'] == 3
    assert refused.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 받아들이기 ---


async def test_a_chosen_encounter_places_the_monsters_and_leaves_the_scene_clean(
    client: AsyncClient, app: FastAPI, me: dict, world: dict, session: AsyncSession, narrated
):
    the_table = await start(client, me, world, rats_and_skeleton(world), improvised_encounters=1)
    narrator = TaggingNarrator()
    app.state.narrator = narrator

    await wait(client, me, the_table, narrated)

    (request,) = narrator.requests
    assert request.encounters == [
        EncounterNote(number=1, place='수로 입구', monster='수로 쥐', count=2),
        EncounterNote(number=2, place='수로 입구', monster='해골 병사', count=1),
    ]
    written = '\n'.join(message.content for message in prompt.build_messages(request))
    assert '[즉흥 조우]' in written
    assert '- 1: 수로 입구에 수로 쥐 2마리' in written
    # 쥐 두 마리가 수로 입구에 놓였다. 표식은 장면에 남지 않았다
    gate, rat = world['gate']['id'], world['rat']['id']
    assert await monsters_at(session, the_table) == [(gate, 1, rat, 'none'), (gate, 2, rat, 'none')]
    (met,) = await appeared(client, me, the_table)
    assert (met['cause'], met['count'], met['place']['name'], met['monster']['name']) == (
        'improvised',
        2,
        '수로 입구',
        '수로 쥐',
    )
    assert await latest_scene(client, me, the_table) == SCENE
    assert await count_of(session, the_table) == 1


async def test_no_choices_once_the_table_has_used_them_all(
    client: AsyncClient, app: FastAPI, me: dict, world: dict, session: AsyncSession, narrated
):
    the_table = await start(client, me, world, rats_and_skeleton(world), improvised_encounters=1)
    app.state.narrator = TaggingNarrator()
    await wait(client, me, the_table, narrated)
    # 쥐가 살아 있으면 그 장소라서도 빠진다. 횟수만 보려고 쥐를 죽은 것으로 둔다
    await session.execute(
        text("UPDATE table_monsters SET status = 'dead', hp = 0 WHERE table_id = :id"), {'id': the_table['id']}
    )
    await session.commit()
    narrator = TaggingNarrator()
    app.state.narrator = narrator

    await wait(client, me, the_table, narrated)

    assert narrator.requests[0].encounters == []
    assert len(await appeared(client, me, the_table)) == 1
    assert await latest_scene(client, me, the_table) == SCENE


async def test_a_switched_off_scenario_offers_nothing_and_drops_the_tag(
    client: AsyncClient, app: FastAPI, me: dict, world: dict, session: AsyncSession, narrated
):
    the_table = await start(client, me, world, rats_and_skeleton(world))
    narrator = TaggingNarrator()
    app.state.narrator = narrator

    await wait(client, me, the_table, narrated)

    assert narrator.requests[0].encounters == []
    assert await monsters_at(session, the_table) == []
    assert await latest_scene(client, me, the_table) == SCENE


async def test_an_unknown_number_only_drops_the_tag(
    client: AsyncClient, app: FastAPI, me: dict, world: dict, session: AsyncSession, narrated
):
    the_table = await start(client, me, world, rats_and_skeleton(world), improvised_encounters=2)
    app.state.narrator = TaggingNarrator('[[조우 9]]')

    await wait(client, me, the_table, narrated)

    assert await monsters_at(session, the_table) == []
    assert await count_of(session, the_table) == 0
    assert await latest_scene(client, me, the_table) == SCENE


async def test_a_safe_place_offers_nothing(client: AsyncClient, app: FastAPI, me: dict, world: dict, narrated):
    # 수로 입구에는 그 장소의 안전한 표(확률 0, 몬스터 없음)가 있다. 판의 기본 표보다 그 장소의 표가 먼저다
    safe = [table(world['gate'], 0), *rats_and_skeleton(world)]
    the_table = await start(client, me, world, safe, improvised_encounters=1)
    narrator = TaggingNarrator(None)
    app.state.narrator = narrator

    await wait(client, me, the_table, narrated)

    assert narrator.requests[0].encounters == []


# --- 작은 함수들 ---


def test_the_tag_is_cut_out_of_the_scene():
    assert split_tag(f'{SCENE}\n\n[[조우 2]]') == (SCENE, 2)
    assert split_tag(f'{SCENE} [[ 조우 1 ]]\n[[조우 3]]\n') == (SCENE, 3)
    assert split_tag(SCENE) == (SCENE, None)


class Collected:
    def __init__(self) -> None:
        self.pieces: list[str] = []

    def begin(self) -> None:
        self.pieces = []

    def text(self, piece: str) -> None:
        self.pieces.append(piece)


def test_the_preview_hides_the_tag_even_in_pieces():
    shown = Collected()
    preview = TaglessPreview(shown)
    preview.begin()

    for piece in ['물방울이 떨어진다.', '\n\n[', '[조우', ' 1]', ']']:
        preview.text(piece)

    assert ''.join(shown.pieces) == '물방울이 떨어진다.\n\n'
