# game-server/tests/test_world_service.py

"""
세계관을 만들고, 읽고, 고치고, 지우는 규칙을 검증한다. 실제 DB 에 저장한다.
"""

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import WORLD_SETTING_MAX_LENGTH, Asset, AssetType, Rating, Visibility, World
from app.assets.service import AssetNotFoundError
from app.assets.worlds import service
from app.assets.worlds.schemas import WorldCreate, WorldUpdate

# 이 파일의 모든 테스트는 빈 테이블에서 시작한다
pytestmark = pytest.mark.usefixtures('clean_tables')

OWNER = uuid.UUID('11111111-2222-4333-8444-555555555555')
SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')

# 테스트에 쓰는 예시 세계관. 내용은 아무 뜻이 없다
TITLE = '악역영애와 엘프 폭주족'
SETTING = (
    '실연당한 악역영애가, 17개 행성에서 사형선고를 받은 모히칸 엘프 폭주족의 바이크 뒷자리에 탔다. '
    '둘은 행성마다 TS 약물을 뿌리는 테러를 벌인다.'
)
GM_NOTES = '둘을 쫓는 추격자는 마법소년 매지컬 스미스. 드워프다.'


async def make_world(session: AsyncSession, owner_id: uuid.UUID = OWNER, **fields) -> World:
    """세계관 하나를 만들어 저장한다."""
    values = {'title': TITLE}
    values.update(fields)
    return await service.create_world(session, owner_id, WorldCreate(**values))


# --- 만들기 ---


async def test_creates_a_world(session: AsyncSession):
    world = await make_world(
        session,
        setting=SETTING,
        gm_notes=GM_NOTES,
    )

    assert world.asset.owner_id == OWNER
    assert world.asset.type == AssetType.WORLD
    assert world.asset.title == TITLE
    assert world.setting == SETTING
    assert world.gm_notes == GM_NOTES


async def test_a_new_world_is_private_and_for_all_ages_by_default(session: AsyncSession):
    world = await make_world(session)

    # 공개하는 것도, 성인 등급으로 올리는 것도 만든 사람이 직접 골라야 한다
    assert world.asset.visibility == Visibility.PRIVATE
    assert world.asset.rating == Rating.ALL
    assert world.asset.deleted_at is None


async def test_a_created_world_is_really_saved(session: AsyncSession, app):
    world = await make_world(session)

    # 다른 세션으로 읽는다. 커밋되지 않았다면 여기서 보이지 않는다
    async with app.state.session_factory() as other_session:
        found = await service.get_world(other_session, OWNER, world.asset_id)

    assert found.asset.title == TITLE
    assert found.asset.created_at is not None


# --- 읽기 ---


async def test_cannot_read_a_world_that_does_not_exist(session: AsyncSession):
    with pytest.raises(AssetNotFoundError):
        await service.get_world(session, OWNER, uuid.uuid4())


async def test_cannot_read_someone_elses_world(session: AsyncSession):
    world = await make_world(session, owner_id=SOMEONE_ELSE, gm_notes='비밀')

    # "네 것이 아니다"가 아니라 "없다"로 답한다. 그 ID 의 자산이 있다는 것을 알려 주지 않는다
    with pytest.raises(AssetNotFoundError):
        await service.get_world(session, OWNER, world.asset_id)


async def test_lists_only_my_worlds_newest_first(session: AsyncSession):
    first = await make_world(session, title='첫째')
    second = await make_world(session, title='둘째')
    await make_world(session, owner_id=SOMEONE_ELSE, title='남의 것')

    worlds, total = await service.list_worlds(session, OWNER, limit=10, offset=0)

    assert [world.asset_id for world in worlds] == [second.asset_id, first.asset_id]
    assert total == 2


async def test_list_is_split_into_pages(session: AsyncSession):
    for number in range(5):
        await make_world(session, title=f'세계 {number}')

    first_page, total = await service.list_worlds(session, OWNER, limit=2, offset=0)
    second_page, _ = await service.list_worlds(session, OWNER, limit=2, offset=2)

    assert total == 5
    assert len(first_page) == 2
    assert len(second_page) == 2
    # 쪽이 겹치지 않는다
    assert {world.asset_id for world in first_page}.isdisjoint({world.asset_id for world in second_page})


# --- 고치기 ---


async def test_updates_only_the_fields_that_were_sent(session: AsyncSession):
    world = await make_world(session, description='소개', setting='옛 설정', gm_notes='비밀')

    updated = await service.update_world(session, OWNER, world.asset_id, WorldUpdate(setting='새 설정'))

    assert updated.setting == '새 설정'
    # 보내지 않은 칸은 그대로다
    assert updated.asset.title == TITLE
    assert updated.asset.description == '소개'
    assert updated.gm_notes == '비밀'


async def test_text_can_be_emptied(session: AsyncSession):
    world = await make_world(session, gm_notes='비밀')

    updated = await service.update_world(session, OWNER, world.asset_id, WorldUpdate(gm_notes=''))

    # 빈 문자열은 "비운다"는 뜻이다. "보내지 않았다"와 다르다
    assert updated.gm_notes == ''


async def test_update_moves_the_updated_time_even_when_only_the_content_changed(session: AsyncSession):
    world = await make_world(session)
    created_at = world.asset.created_at

    updated = await service.update_world(session, OWNER, world.asset_id, WorldUpdate(setting='새 설정'))

    # setting 은 worlds 테이블에 있고 고친 시각은 assets 테이블에 있다
    assert updated.asset.updated_at > created_at
    assert updated.asset.created_at == created_at


async def test_cannot_update_someone_elses_world(session: AsyncSession):
    world = await make_world(session, owner_id=SOMEONE_ELSE)

    with pytest.raises(AssetNotFoundError):
        await service.update_world(session, OWNER, world.asset_id, WorldUpdate(title='빼앗음'))

    untouched = await service.get_world(session, SOMEONE_ELSE, world.asset_id)
    assert untouched.asset.title == TITLE


# --- 지우기 ---


async def test_a_deleted_world_cannot_be_read_or_listed(session: AsyncSession):
    world = await make_world(session)

    await service.delete_world(session, OWNER, world.asset_id)

    with pytest.raises(AssetNotFoundError):
        await service.get_world(session, OWNER, world.asset_id)
    worlds, total = await service.list_worlds(session, OWNER, limit=10, offset=0)
    assert worlds == []
    assert total == 0


async def test_delete_keeps_the_row(session: AsyncSession):
    world = await make_world(session)

    await service.delete_world(session, OWNER, world.asset_id)

    # 행은 남고 지운 시각만 적힌다. 진행 중인 방이 이 자산을 가리키고 있을 수 있다
    deleted_at = await session.scalar(text('SELECT deleted_at FROM assets WHERE id = :id'), {'id': world.asset_id})
    assert deleted_at is not None


async def test_cannot_delete_twice(session: AsyncSession):
    world = await make_world(session)
    await service.delete_world(session, OWNER, world.asset_id)

    with pytest.raises(AssetNotFoundError):
        await service.delete_world(session, OWNER, world.asset_id)


async def test_cannot_delete_someone_elses_world(session: AsyncSession):
    world = await make_world(session, owner_id=SOMEONE_ELSE)

    with pytest.raises(AssetNotFoundError):
        await service.delete_world(session, OWNER, world.asset_id)

    assert await service.get_world(session, SOMEONE_ELSE, world.asset_id)


# --- 입력 검증 ---


@pytest.mark.parametrize('title', ['', '   ', 'x' * 101])
def test_rejects_a_bad_title(title: str):
    with pytest.raises(ValidationError):
        WorldCreate(title=title)


def test_title_is_trimmed():
    assert WorldCreate(title=f'  {TITLE}  ').title == TITLE


def test_rejects_a_setting_that_is_too_long():
    with pytest.raises(ValidationError):
        WorldCreate(title='세계', setting='가' * (WORLD_SETTING_MAX_LENGTH + 1))


def test_accepts_a_setting_at_the_limit():
    data = WorldCreate(title='세계', setting='가' * WORLD_SETTING_MAX_LENGTH)

    assert len(data.setting) == WORLD_SETTING_MAX_LENGTH


def test_rejects_an_unknown_rating():
    with pytest.raises(ValidationError):
        WorldCreate(title='세계', rating='teen')


@pytest.mark.parametrize('field', ['owner_id', 'visibility', 'id', 'deleted_at'])
def test_rejects_fields_the_client_must_not_set(field: str):
    # 누구 것인지, 누구에게 보이는지는 서버가 정한다. 끼워 보내면 무시하지 않고 거부한다
    with pytest.raises(ValidationError):
        WorldCreate(title='세계', **{field: 'x'})


# --- DB 의 마지막 방어선 ---


async def test_the_database_rejects_an_unknown_type(session: AsyncSession):
    session.add(Asset(owner_id=OWNER, type='spaceship', title='검증을 건너뛴 자산'))

    # 입력 검증을 거치지 않고 들어온 값도 DB 가 막는다
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_the_database_rejects_a_setting_that_is_too_long(session: AsyncSession):
    asset = Asset(owner_id=OWNER, type=AssetType.WORLD, title='세계')
    session.add(World(asset=asset, setting='가' * (WORLD_SETTING_MAX_LENGTH + 1)))

    with pytest.raises(IntegrityError):
        await session.commit()
