# asset-server/app/characters/service.py

"""
캐릭터를 만들고, 고치고, 지우고, 게시하고, 공개 목록으로 내준다(#567).

지키는 것.
  - 초안은 만든 사람만 보고 고친다. 남의 것은 없는 것과 같다(CharacterNotFoundError, 404).
  - 1~2단계에는 운영자만 만든다(설정 CHARACTERS_FOR_EVERYONE 이 거짓). 공개로 두는 것은 늘 운영자만이다.
    일반 사용자의 공개는 신고와 관리자 화면(E4)이 생긴 뒤에 연다.
  - 성인 등급은 성인용 내용을 볼 수 있는 사람(또는 운영자)만 쓴다(app/ratings.py).
  - 판은 바뀌지 않는다. 게시할 때마다 번호가 하나씩 오른다.
    같은 캐릭터를 동시에 게시해도 번호가 겹치지 않게 행을 잠근다.
  - 공개 목록은 공개이고 게시한 판이 있고, 보는 사람이 볼 수 있는 등급(판의 등급)인 것만 낸다. 나머지는 404 다.
  - 다른 서버(chat, story)에 내주는 판은 마지막 판이다. 쓸 수 있는 사람은 주인이거나, 공개 캐릭터를 볼 수 있는 사람이다.
    등급은 주인에게도 본다(성인 확인을 잃은 주인에게 성인 판을 내주지 않는다). 주인에게는 403, 남에게는 404 다.
  - 대표 그림과 소개 글의 그림은 자기가 올린 그림이어야 한다(#566). 초안의 대표 그림은 붙일 때 보고(422),
    게시할 때는 소개 글의 그림까지 다시 본다(막는 것). 게시하면 판에 쓰인 그림을 적는다. 공개 캐릭터의 판에 쓰인 그림은
    그 판을 볼 수 있는 사람이 본다(app/images/service.py).
  - 나이와 성별로 거르거나 막지 않는다.
  - 가리키는 로어북은 자기 로어북이어야 한다(#672). 붙일 때 보고(422 lorebook_not_owned), 게시할 때 그 마지막 판을
    판에 복사한다. 지웠거나 게시한 적이 없는 로어북이면 게시를 막는다.
"""

import uuid

from server_core.auth.tokens import AccessClaims
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.characters import repository
from app.characters.documents import LorebookCopyDocument, build_document
from app.characters.models import Character, CharacterVersion, Visibility
from app.characters.publishing import (
    CharacterNotReadyError,
    Problem,
    cleaned_intro,
    find_problems,
    lorebook_copies,
    used_image_ids,
)
from app.characters.schemas import CharacterCreate, CharacterUpdate
from app.content.html import Removed
from app.images import service as images
from app.lorebooks import repository as lorebooks
from app.ratings import AdultContentRequiredError, allowed_ratings, require_rating


class CharacterNotFoundError(Exception):
    """그런 캐릭터(또는 판)가 없다. 남의 초안과 볼 수 없는 공개 캐릭터도 이것이다."""


class OperatorOnlyError(Exception):
    """운영자만 할 수 있는 일이다(1~2단계의 캐릭터 만들기, 공개로 두기). 403 이다."""


class LorebookNotOwnedError(Exception):
    """가리키려는 로어북 가운데 자기 로어북이 아닌(또는 없는) 것이 있다. 422 다."""


def require_maker(viewer: AccessClaims, for_everyone: bool) -> None:
    """캐릭터를 만들 수 있는 사람인지 본다. 모두에게 열지 않았으면 운영자만이다."""
    if not for_everyone and not viewer.is_operator:
        raise OperatorOnlyError


def require_visibility(viewer: AccessClaims, visibility: Visibility | None) -> None:
    """공개로 두려면 운영자여야 한다. 비공개로 두거나 바꾸지 않으면 누구나 된다."""
    if visibility == Visibility.PUBLIC and not viewer.is_operator:
        raise OperatorOnlyError


def build_character(owner_id: uuid.UUID, data: CharacterCreate) -> Character:
    """입력에서 캐릭터 객체를 만든다. 아직 저장하지 않는다. 처음에는 비공개다."""
    return Character(owner_id=owner_id, visibility=Visibility.PRIVATE, **data.values())


def apply_changes(character: Character, changes: dict) -> None:
    """보낸 칸을 초안에 반영한다."""
    for name, value in changes.items():
        setattr(character, name, value)


async def require_own_images(session: AsyncSession, owner_id: uuid.UUID, image_ids: list[uuid.UUID]) -> None:
    """
    붙이려는 그림(대표 그림, 장소의 배경, 물건의 그림)이 모두 자기 그림이어야 한다. 아니면 ImageNotOwnedError.
    떼거나 바꾸지 않은 칸은 보지 않는다(빈 목록이면 보지 않는다).
    """
    if image_ids:
        await images.require_own_images(session, owner_id, image_ids)


async def require_own_lorebooks(session: AsyncSession, owner_id: uuid.UUID, lorebook_ids: list[uuid.UUID]) -> None:
    """가리키려는 로어북이 모두 자기 로어북이어야 한다. 아니면 LorebookNotOwnedError. 빈 목록이면 보지 않는다."""
    if lorebook_ids and await lorebooks.owned_ids(session, owner_id, lorebook_ids) != set(lorebook_ids):
        raise LorebookNotOwnedError


async def get_mine(session: AsyncSession, owner_id: uuid.UUID, character_id: uuid.UUID) -> Character:
    """자기 캐릭터 하나. 없으면 CharacterNotFoundError."""
    character = await repository.find_owned(session, owner_id, character_id)
    if character is None:
        raise CharacterNotFoundError
    return character


async def list_mine(session: AsyncSession, owner_id: uuid.UUID, limit: int, offset: int) -> tuple[list[Character], int]:
    """자기 캐릭터의 한 쪽과 전체 개수."""
    return await repository.list_owned(session, owner_id, limit, offset)


async def create_character(
    session: AsyncSession, viewer: AccessClaims, data: CharacterCreate, for_everyone: bool
) -> Character:
    """캐릭터를 만든다. 만들 수 없는 사람이면 OperatorOnlyError, 쓸 수 없는 등급이면 AdultContentRequiredError."""
    require_maker(viewer, for_everyone)
    require_rating(data.rating, allowed_ratings(viewer))
    await require_own_images(session, viewer.user_id, data.image_ids())
    await require_own_lorebooks(session, viewer.user_id, data.lorebooks)
    character = build_character(viewer.user_id, data)
    repository.add(session, character)
    await session.commit()
    await session.refresh(character)
    return character


async def update_character(
    session: AsyncSession, viewer: AccessClaims, character_id: uuid.UUID, data: CharacterUpdate
) -> Character:
    """자기 캐릭터의 초안을 고친다. 게시한 판은 그대로다."""
    character = await get_mine(session, viewer.user_id, character_id)
    require_visibility(viewer, data.visibility)
    if data.rating is not None:
        require_rating(data.rating, allowed_ratings(viewer))
    await require_own_images(session, viewer.user_id, data.image_ids())
    await require_own_lorebooks(session, viewer.user_id, data.lorebooks or [])
    apply_changes(character, data.changes())
    await session.commit()
    await session.refresh(character)
    return character


async def delete_character(session: AsyncSession, owner_id: uuid.UUID, character_id: uuid.UUID) -> None:
    """자기 캐릭터를 지운다(판도 함께). 이미 가져간 대화는 사본으로 돈다."""
    character = await get_mine(session, owner_id, character_id)
    await repository.delete(session, character)
    await session.commit()


async def check_publish(
    session: AsyncSession, owner_id: uuid.UUID, character_id: uuid.UUID
) -> tuple[list[str], list[Removed]]:
    """지금 게시하면 막히는 이유와 소개에서 걸러질 것. 판을 만들지 않는다."""
    character = await get_mine(session, owner_id, character_id)
    cleaned = cleaned_intro(character)
    _, lorebook_problems = await lorebook_parts(session, character)
    problems = await publishing_problems(session, character, cleaned.html) + lorebook_problems
    return [str(problem) for problem in problems], cleaned.removed


async def publishing_problems(session: AsyncSession, character: Character, intro_html: str) -> list[Problem]:
    """게시를 막는 것들. 초안의 규칙(find_problems)과, 판에 쓰일 그림이 모두 자기 그림인지."""
    problems = find_problems(character)
    if await images.foreign_ids(session, character.owner_id, used_image_ids(character, intro_html)):
        problems.append(Problem.IMAGE_NOT_OWNED)
    return problems


async def lorebook_parts(
    session: AsyncSession, character: Character
) -> tuple[list[LorebookCopyDocument], list[Problem]]:
    """가리킨 로어북들의 마지막 판을 판에 넣을 모양으로, 그리고 막는 것들(지웠다, 게시한 적이 없다). 한 번의 쿼리다."""
    if not character.lorebooks:
        return [], []
    found = await lorebooks.latest_owned(session, character.owner_id, character.lorebooks)
    numbers = {lorebook_id: version.number if version else None for lorebook_id, (_, version) in found.items()}
    documents = {lorebook_id: version.document for lorebook_id, (_, version) in found.items() if version}
    return lorebook_copies(character.lorebooks, numbers, documents)


def next_number(character: Character) -> int:
    """다음 판의 번호. 처음이면 1 이다."""
    return (character.latest_version or 0) + 1


def build_version(
    character: Character, number: int, note: str, intro: str, copies: list[LorebookCopyDocument]
) -> CharacterVersion:
    """초안과 거른 소개, 복사할 로어북들로 판을 만든다. 아직 저장하지 않는다."""
    document = build_document(character, intro, copies)
    return CharacterVersion(
        id=uuid.uuid4(),
        character_id=character.id,
        number=number,
        note=note,
        rating=document.rating,
        document=document.model_dump(mode='json'),
    )


async def publish(
    session: AsyncSession, owner_id: uuid.UUID, character_id: uuid.UUID, note: str
) -> tuple[CharacterVersion, list[Removed]]:
    """
    자기 캐릭터를 게시한다. 새 판과 소개에서 걸러 낸 것들을 돌려준다.

    막는 것이 있으면 CharacterNotReadyError(판을 만들지 않는다). 행을 잠그고 번호를 정한다.
    가리킨 로어북들의 마지막 판을 판에 복사한다.
    판에 쓰인 그림을 판과 같은 트랜잭션에 적는다.
    """
    character = await repository.find_owned(session, owner_id, character_id, for_update=True)
    if character is None:
        raise CharacterNotFoundError
    cleaned = cleaned_intro(character)
    copies, lorebook_problems = await lorebook_parts(session, character)
    problems = await publishing_problems(session, character, cleaned.html) + lorebook_problems
    if problems:
        raise CharacterNotReadyError(problems)
    version = build_version(character, next_number(character), note, cleaned.html, copies)
    repository.add(session, version)
    await session.flush()
    images.record_uses(session, version.id, used_image_ids(character, cleaned.html))
    character.latest_version = version.number
    character.published_at = func.now()
    await session.commit()
    await session.refresh(version)
    return version, cleaned.removed


async def list_versions(session: AsyncSession, owner_id: uuid.UUID, character_id: uuid.UUID) -> list[CharacterVersion]:
    """자기 캐릭터의 판들. 최근 것부터다."""
    await get_mine(session, owner_id, character_id)
    return await repository.list_versions(session, character_id)


async def get_version(
    session: AsyncSession, owner_id: uuid.UUID, character_id: uuid.UUID, number: int
) -> CharacterVersion:
    """자기 캐릭터의 판 하나. 없으면 CharacterNotFoundError."""
    await get_mine(session, owner_id, character_id)
    version = await repository.find_version(session, character_id, number)
    if version is None:
        raise CharacterNotFoundError
    return version


async def list_public(
    session: AsyncSession, viewer: AccessClaims | None, limit: int, offset: int
) -> tuple[list[tuple[Character, CharacterVersion]], int]:
    """공개 목록의 한 쪽과 전체 개수. 보는 사람이 볼 수 있는 등급만이다."""
    return await repository.list_public(session, allowed_ratings(viewer), limit, offset)


async def get_public(
    session: AsyncSession, viewer: AccessClaims | None, character_id: uuid.UUID
) -> tuple[Character, CharacterVersion]:
    """공개 캐릭터 하나와 그 마지막 판. 볼 수 없으면 CharacterNotFoundError(있는지도 드러내지 않는다)."""
    found = await repository.find_public(session, character_id, allowed_ratings(viewer))
    if found is None:
        raise CharacterNotFoundError
    return found


def is_owner(character: Character, viewer: AccessClaims) -> bool:
    """그 사람이 만든 캐릭터인가."""
    return character.owner_id == viewer.user_id


def require_reachable(character: Character, viewer: AccessClaims) -> None:
    """주인이 아니면 공개여야 한다. 아니면 CharacterNotFoundError(있는지도 드러내지 않는다)."""
    if not is_owner(character, viewer) and character.visibility != Visibility.PUBLIC:
        raise CharacterNotFoundError


def require_usable_rating(character: Character, version: CharacterVersion, viewer: AccessClaims) -> None:
    """
    판의 등급을 그 사람이 쓸 수 있어야 한다.

    주인이면 AdultContentRequiredError(자기 캐릭터라 있는 것을 안다. 화면이 본인인증으로 안내한다),
    남이면 CharacterNotFoundError(공개 목록과 같다).
    """
    if version.rating in allowed_ratings(viewer):
        return
    if is_owner(character, viewer):
        raise AdultContentRequiredError
    raise CharacterNotFoundError


async def get_usable_latest(
    session: AsyncSession, viewer: AccessClaims, character_id: uuid.UUID
) -> tuple[Character, CharacterVersion]:
    """
    그 사람이 쓸 수 있는 캐릭터와 그 마지막 판. 다른 서버가 대화를 시작하거나 새 판을 물을 때 쓴다.

    없거나 게시한 적이 없거나 쓸 수 없으면 CharacterNotFoundError,
    주인인데 등급을 쓸 수 없으면 AdultContentRequiredError.
    """
    found = await repository.find_latest(session, character_id)
    if found is None:
        raise CharacterNotFoundError
    character, version = found
    require_reachable(character, viewer)
    require_usable_rating(character, version, viewer)
    return character, version
