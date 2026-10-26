# asset-server/app/worlds/service.py

"""
story 의 세계관을 만들고, 고치고, 지우고, 게시한다(#591, 화면 명세 D7 의 서버).

지키는 것(캐릭터와 같은 규칙이다, app/characters/service.py).
  - 초안은 만든 사람만 보고 고친다. 남의 것은 없는 것과 같다(WorldNotFoundError, 404).
  - 1~2단계에는 운영자만 만든다(설정 CHARACTERS_FOR_EVERYONE 이 거짓). 공개로 두는 것은 운영자만이다
    (PUBLIC_FOR_EVERYONE 이면 누구나). 제작자의 범위를 캐릭터와 따로 열 까닭이 아직 없어 같은 설정을 쓴다.
  - 성인 등급은 성인용 내용을 볼 수 있는 사람(또는 운영자)만 쓴다(app/ratings.py).
  - 판은 바뀌지 않는다. 게시할 때마다 번호가 하나씩 오른다.
    같은 세계관을 동시에 게시해도 번호가 겹치지 않게 행을 잠근다.
  - 붙이는 그림은 자기 그림이어야 한다(422). 게시할 때는 소개 글과 인물의 그림까지 다시 본다(막는 것).
  - 인물은 자기 캐릭터만 가리킨다(422 character_not_owned). 게시할 때 그 마지막 판을 복사한다.
    지웠거나 게시한 적이 없는 캐릭터면 게시를 막는다. 로어북도 같다(422 lorebook_not_owned).
  - story 서버에 내주는 판은 마지막 판이다. 쓸 수 있는 사람은 주인이거나, 공개 세계관의 판의 등급을 볼 수 있는 사람이다.
    등급은 주인에게도 본다. 주인에게는 403 adult_content_required, 남에게는 404 다(캐릭터와 같다).
"""

import uuid
from dataclasses import dataclass

from server_core.auth.tokens import AccessClaims
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.characters import repository as characters
from app.characters.documents import LorebookCopyDocument
from app.characters.models import Visibility
from app.characters.service import LorebookNotOwnedError, OperatorOnlyError, require_own_images
from app.content.html import Removed
from app.images import service as images
from app.lorebooks import repository as lorebooks
from app.ratings import AdultContentRequiredError, allowed_ratings, require_rating
from app.worlds import repository
from app.worlds.documents import CastCharacterDocument, build_document
from app.worlds.models import World, WorldVersion
from app.worlds.publishing import (
    Problem,
    WorldNotReadyError,
    character_copies,
    cleaned_intro,
    find_problems,
    find_warnings,
    lorebook_copies,
    used_image_ids,
)
from app.worlds.schemas import WorldCreate, WorldUpdate


class WorldNotFoundError(Exception):
    """그런 세계관(또는 판)이 없다. 남의 초안도 이것이다."""


class CharacterNotOwnedError(Exception):
    """인물이 가리키려는 캐릭터 가운데 자기 캐릭터가 아닌(또는 없는) 것이 있다. 422 다."""


def require_maker(viewer: AccessClaims, for_everyone: bool) -> None:
    """세계관을 만들 수 있는 사람인지 본다. 모두에게 열지 않았으면 운영자만이다."""
    if not for_everyone and not viewer.is_operator:
        raise OperatorOnlyError


def require_visibility(viewer: AccessClaims, visibility: Visibility | None, public_for_everyone: bool) -> None:
    """공개로 두려면 운영자여야 한다(PUBLIC_FOR_EVERYONE 이면 누구나). 비공개로 두거나 바꾸지 않으면 누구나 된다."""
    if visibility == Visibility.PUBLIC and not (viewer.is_operator or public_for_everyone):
        raise OperatorOnlyError


async def require_own_characters(session: AsyncSession, owner_id: uuid.UUID, character_ids: list[uuid.UUID]) -> None:
    """인물이 가리키려는 캐릭터가 모두 자기 캐릭터여야 한다. 아니면 CharacterNotOwnedError. 빈 목록이면 보지 않는다."""
    if character_ids and await characters.owned_ids(session, owner_id, character_ids) != set(character_ids):
        raise CharacterNotOwnedError


async def require_own_lorebooks(session: AsyncSession, owner_id: uuid.UUID, lorebook_ids: list[uuid.UUID]) -> None:
    """가리키려는 로어북이 모두 자기 로어북이어야 한다. 아니면 LorebookNotOwnedError. 빈 목록이면 보지 않는다."""
    if lorebook_ids and await lorebooks.owned_ids(session, owner_id, lorebook_ids) != set(lorebook_ids):
        raise LorebookNotOwnedError


def build_world(owner_id: uuid.UUID, data: WorldCreate) -> World:
    """입력에서 세계관 객체를 만든다. 아직 저장하지 않는다. 처음에는 비공개다."""
    return World(owner_id=owner_id, visibility=Visibility.PRIVATE, **data.values())


def apply_changes(world: World, changes: dict) -> None:
    """보낸 칸을 초안에 반영한다."""
    for name, value in changes.items():
        setattr(world, name, value)


async def get_mine(session: AsyncSession, owner_id: uuid.UUID, world_id: uuid.UUID) -> World:
    """자기 세계관 하나. 없으면 WorldNotFoundError."""
    world = await repository.find_owned(session, owner_id, world_id)
    if world is None:
        raise WorldNotFoundError
    return world


async def list_mine(session: AsyncSession, owner_id: uuid.UUID, limit: int, offset: int) -> tuple[list[World], int]:
    """자기 세계관의 한 쪽과 전체 개수."""
    return await repository.list_owned(session, owner_id, limit, offset)


async def create_world(session: AsyncSession, viewer: AccessClaims, data: WorldCreate, for_everyone: bool) -> World:
    """세계관을 만든다. 만들 수 없는 사람이면 OperatorOnlyError, 쓸 수 없는 등급이면 AdultContentRequiredError."""
    require_maker(viewer, for_everyone)
    require_rating(data.rating, allowed_ratings(viewer))
    await require_own_images(session, viewer.user_id, data.image_ids())
    await require_own_characters(session, viewer.user_id, data.character_ids())
    await require_own_lorebooks(session, viewer.user_id, data.lorebooks)
    world = build_world(viewer.user_id, data)
    repository.add(session, world)
    await session.commit()
    await session.refresh(world)
    return world


async def update_world(
    session: AsyncSession, viewer: AccessClaims, world_id: uuid.UUID, data: WorldUpdate, public_for_everyone: bool
) -> World:
    """자기 세계관의 초안을 고친다. 게시한 판은 그대로다."""
    world = await get_mine(session, viewer.user_id, world_id)
    require_visibility(viewer, data.visibility, public_for_everyone)
    if data.rating is not None:
        require_rating(data.rating, allowed_ratings(viewer))
    await require_own_images(session, viewer.user_id, data.image_ids())
    await require_own_characters(session, viewer.user_id, data.character_ids())
    await require_own_lorebooks(session, viewer.user_id, data.lorebooks or [])
    apply_changes(world, data.changes())
    await session.commit()
    await session.refresh(world)
    return world


async def delete_world(session: AsyncSession, owner_id: uuid.UUID, world_id: uuid.UUID) -> None:
    """자기 세계관을 지운다(판도 함께). 이미 가져간 세션은 사본으로 돈다."""
    world = await get_mine(session, owner_id, world_id)
    await repository.delete(session, world)
    await session.commit()


async def character_parts(
    session: AsyncSession, world: World
) -> tuple[dict[uuid.UUID, CastCharacterDocument], list[Problem]]:
    """인물들이 가리킨 캐릭터의 마지막 판을 복사한 것과 막는 것들. 한 번의 쿼리다."""
    if not world.cast:
        return {}, []
    ids = [uuid.UUID(member['character_id']) for member in world.cast]
    found = await characters.latest_owned(session, world.owner_id, ids)
    versions = {key: (version.number, version.document) if version else None for key, (_, version) in found.items()}
    return character_copies(world, versions)


async def lorebook_parts(session: AsyncSession, world: World) -> tuple[list[LorebookCopyDocument], list[Problem]]:
    """가리킨 로어북들의 마지막 판을 복사한 것과 막는 것들. 한 번의 쿼리다."""
    if not world.lorebooks:
        return [], []
    found = await lorebooks.latest_owned(session, world.owner_id, world.lorebooks)
    versions = {key: (version.number, version.document) if version else None for key, (_, version) in found.items()}
    return lorebook_copies(world, versions)


async def image_problems(session: AsyncSession, world: World, image_ids: list[uuid.UUID]) -> list[Problem]:
    """판에 쓰일 그림 가운데 자기 그림이 아닌 것이 있으면 막는다."""
    return [Problem.IMAGE_NOT_OWNED] if await images.foreign_ids(session, world.owner_id, image_ids) else []


@dataclass(frozen=True)
class Prepared:
    """
    게시에 드는 것. 복사한 캐릭터(캐릭터의 id 로 찾는다)와 로어북, 막는 것들, 거른 소개와 걸러 낸 것들,
    판에 쓰일 그림들이다.
    """

    characters: dict[uuid.UUID, CastCharacterDocument]
    lorebooks: list[LorebookCopyDocument]
    problems: list[Problem]
    intro: str
    removed: list[Removed]
    images: list[uuid.UUID]


async def prepare(session: AsyncSession, world: World) -> Prepared:
    """게시에 드는 것을 모은다. 게시해 보기와 게시가 같은 길을 지난다."""
    cleaned = cleaned_intro(world)
    copies, character_problems = await character_parts(session, world)
    lorebook_list, lorebook_problems = await lorebook_parts(session, world)
    used = used_image_ids(world, cleaned.html, list(copies.values()))
    problems = find_problems(world) + character_problems + lorebook_problems
    problems += await image_problems(session, world, used)
    return Prepared(copies, lorebook_list, problems, cleaned.html, cleaned.removed, used)


async def check_publish(
    session: AsyncSession, owner_id: uuid.UUID, world_id: uuid.UUID
) -> tuple[list[str], list[str], list[Removed]]:
    """지금 게시하면 막히는 이유, 알리는 것, 소개에서 걸러질 것. 판을 만들지 않는다."""
    world = await get_mine(session, owner_id, world_id)
    prepared = await prepare(session, world)
    warnings = [str(warning) for warning in find_warnings(world)]
    return [str(problem) for problem in prepared.problems], warnings, prepared.removed


def next_number(world: World) -> int:
    """다음 판의 번호. 처음이면 1 이다."""
    return (world.latest_version or 0) + 1


def build_version(world: World, number: int, note: str, prepared: Prepared) -> WorldVersion:
    """초안과 거른 소개, 복사한 캐릭터와 로어북으로 판을 만든다. 아직 저장하지 않는다."""
    document = build_document(world, prepared.intro, prepared.characters, prepared.lorebooks)
    return WorldVersion(
        id=uuid.uuid4(),
        world_id=world.id,
        number=number,
        note=note,
        rating=document.rating,
        document=document.model_dump(mode='json'),
    )


async def publish(
    session: AsyncSession, owner_id: uuid.UUID, world_id: uuid.UUID, note: str
) -> tuple[WorldVersion, list[Removed], list[str]]:
    """
    자기 세계관을 게시한다. 새 판과 소개에서 걸러 낸 것들, 알리는 것들을 돌려준다.

    막는 것이 있으면 WorldNotReadyError(판을 만들지 않는다). 행을 잠그고 번호를 정한다.
    인물의 캐릭터와 로어북의 마지막 판을 판에 복사하고, 판에 쓰인 그림을 판과 같은 트랜잭션에 적는다.
    """
    world = await repository.find_owned(session, owner_id, world_id, for_update=True)
    if world is None:
        raise WorldNotFoundError
    prepared = await prepare(session, world)
    if prepared.problems:
        raise WorldNotReadyError(prepared.problems)
    version = build_version(world, next_number(world), note, prepared)
    repository.add(session, version)
    await session.flush()
    images.record_world_uses(session, version.id, prepared.images)
    world.latest_version = version.number
    world.published_at = func.now()
    warnings = [str(warning) for warning in find_warnings(world)]
    await session.commit()
    await session.refresh(version)
    return version, prepared.removed, warnings


async def list_versions(session: AsyncSession, owner_id: uuid.UUID, world_id: uuid.UUID) -> list[WorldVersion]:
    """자기 세계관의 판들. 최근 것부터다."""
    await get_mine(session, owner_id, world_id)
    return await repository.list_versions(session, world_id)


async def get_version(session: AsyncSession, owner_id: uuid.UUID, world_id: uuid.UUID, number: int) -> WorldVersion:
    """자기 세계관의 판 하나. 없으면 WorldNotFoundError."""
    await get_mine(session, owner_id, world_id)
    version = await repository.find_version(session, world_id, number)
    if version is None:
        raise WorldNotFoundError
    return version


def is_owner(world: World, viewer: AccessClaims) -> bool:
    """그 사람이 만든 세계관인가."""
    return world.owner_id == viewer.user_id


def require_reachable(world: World, viewer: AccessClaims) -> None:
    """주인이 아니면 공개여야 한다. 아니면 WorldNotFoundError(있는지도 드러내지 않는다)."""
    if not is_owner(world, viewer) and world.visibility != Visibility.PUBLIC:
        raise WorldNotFoundError


def require_usable_rating(world: World, version: WorldVersion, viewer: AccessClaims) -> None:
    """판의 등급을 그 사람이 쓸 수 있어야 한다. 주인이면 AdultContentRequiredError, 남이면 WorldNotFoundError."""
    if version.rating in allowed_ratings(viewer):
        return
    if is_owner(world, viewer):
        raise AdultContentRequiredError
    raise WorldNotFoundError


async def get_usable_latest(
    session: AsyncSession, viewer: AccessClaims, world_id: uuid.UUID
) -> tuple[World, WorldVersion]:
    """
    그 사람이 쓸 수 있는 세계관과 그 마지막 판. story 서버가 세션을 시작하거나 새 판을 물을 때 쓴다.
    없거나 게시한 적이 없거나 쓸 수 없으면 WorldNotFoundError, 주인인데 등급을 쓸 수 없으면 AdultContentRequiredError.
    """
    found = await repository.find_latest(session, world_id)
    if found is None:
        raise WorldNotFoundError
    world, version = found
    require_reachable(world, viewer)
    require_usable_rating(world, version, viewer)
    return world, version


async def list_public(
    session: AsyncSession, viewer: AccessClaims | None, limit: int, offset: int
) -> tuple[list[tuple[World, WorldVersion]], int]:
    """공개 목록의 한 쪽과 전체 개수. 보는 사람(로그인하지 않았으면 None)이 볼 수 있는 등급만이다."""
    return await repository.list_public(session, allowed_ratings(viewer), limit, offset)


async def get_public(
    session: AsyncSession, viewer: AccessClaims | None, world_id: uuid.UUID
) -> tuple[World, WorldVersion]:
    """공개 세계관 하나와 그 마지막 판. 볼 수 없으면 WorldNotFoundError(있는지도 드러내지 않는다)."""
    found = await repository.find_public(session, world_id, allowed_ratings(viewer))
    if found is None:
        raise WorldNotFoundError
    return found
