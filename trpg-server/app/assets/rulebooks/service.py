# trpg-server/app/assets/rulebooks/service.py

"""
룰북을 만들고, 읽고, 고치고, 지운다.

규칙의 대부분은 모든 자산에 공통이라 app/assets/service.py 에 있다.
여기에는 룰북만의 것(입력에서 룰북을 만들고 템플릿의 규칙을 채우는 것)과,
공통 규칙에 "룰북"을 넘겨 부르는 함수가 있다.
"""

import uuid

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import service as assets
from app.assets.models import AssetType, Rulebook
from app.assets.rulebooks.schemas import RulebookCreate, RulebookUpdate
from app.engine.ruleset import Armor, Resource, Ruleset
from app.engine.templates import TemplateFile, all_templates, from_template


class RulesInvalidError(Exception):
    """
    고친 규칙이 규칙 한 벌로 맞지 않는다(#804). 수치의 최대에 쓰는 능력치가 규칙에 없거나, 같은 수치가 두 번 있다.

    칸 하나의 모양은 받을 때 봤다. 이것은 칸끼리 맞는지다. message 는 왜 맞지 않는지다.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def build_rulebook(owner_id: uuid.UUID, data: RulebookCreate) -> Rulebook:
    """
    입력에서 룰북 객체를 만든다. 아직 저장하지 않는다.

    고른 템플릿의 규칙을 복사해 넣는다. DB 에 문서로 들어가므로 JSON 으로 옮길 수 있는 값으로 바꾼다.
    방어 규칙을 보냈으면 템플릿의 것 대신 그것을 쓴다(#276).
    """
    asset = assets.build_asset(owner_id, AssetType.RULEBOOK, data)
    rules = from_template(data.template).model_dump(mode='json')
    if 'armor' in data.model_fields_set:
        rules = with_armor(rules, data.armor)
    if data.resources is not None:
        rules = with_resources(rules, data.resources)
    return Rulebook(asset=asset, gm_guide=data.gm_guide, rules=rules)


def with_armor(rules: dict, armor: Armor | None) -> dict:
    """규칙의 방어 규칙만 바꾼 문서. 받은 문서는 고치지 않는다. 방어 규칙은 받을 때 모양을 확인했다."""
    return {**rules, 'armor': armor.model_dump(mode='json') if armor is not None else None}


def with_resources(rules: dict, resources: list[Resource]) -> dict:
    """
    규칙의 수치만 바꾼 문서(#804). 받은 문서는 고치지 않는다.

    수치의 최대에 쓰는 능력치는 규칙의 능력치와 견주어야 알 수 있다. 규칙 한 벌로 다시 읽어 보고,
    맞지 않으면 RulesInvalidError 다.
    """
    changed = {**rules, 'resources': [resource.model_dump(mode='json') for resource in resources]}
    try:
        Ruleset.model_validate(changed)
    except ValidationError as error:
        raise RulesInvalidError(error.errors()[0]['msg']) from error
    return changed


def other_changes(data: RulebookUpdate) -> RulebookUpdate:
    """규칙(방어, 수치)을 뺀 고칠 것. 공통의 고치기(app/assets/service.py)는 내용의 칸만 안다. 규칙은 여기서 고친다."""
    return RulebookUpdate.model_validate(data.model_dump(exclude_unset=True, exclude={'armor', 'resources'}))


def list_templates() -> list[TemplateFile]:
    """고를 수 있는 템플릿들. 파일에서 읽어 둔 것이라 DB 를 보지 않는다."""
    return all_templates()


async def create_rulebook(session: AsyncSession, owner_id: uuid.UUID, data: RulebookCreate) -> Rulebook:
    """룰북을 만든다."""
    return await assets.create(session, build_rulebook(owner_id, data))


async def get_rulebook(session: AsyncSession, owner_id: uuid.UUID, rulebook_id: uuid.UUID) -> Rulebook:
    """자기 룰북 하나를 돌려준다. 없으면 AssetNotFoundError."""
    return await assets.get_owned(session, Rulebook, owner_id, rulebook_id)


async def list_rulebooks(
    session: AsyncSession, owner_id: uuid.UUID, limit: int, offset: int
) -> tuple[list[Rulebook], int]:
    """자기 룰북의 한 쪽과 전체 개수를 돌려준다."""
    return await assets.list_owned(session, Rulebook, owner_id, limit, offset)


async def update_rulebook(
    session: AsyncSession, owner_id: uuid.UUID, rulebook_id: uuid.UUID, data: RulebookUpdate
) -> Rulebook:
    """
    자기 룰북을 고친다. 없으면 AssetNotFoundError.

    방어 규칙이나 수치(#804)를 보냈으면 규칙에서 그것만 바꾼다(#276). 이미 게시한 판은 그때의 규칙으로 굳어 있다.
    수치가 규칙과 맞지 않으면 RulesInvalidError 다.
    """
    content = await assets.get_owned(session, Rulebook, owner_id, rulebook_id)
    if 'armor' in data.model_fields_set:
        content.rules = with_armor(content.rules, data.armor)
    if data.resources is not None:
        content.rules = with_resources(content.rules, data.resources)
    return await assets.save_changes(session, content, other_changes(data))


async def delete_rulebook(session: AsyncSession, owner_id: uuid.UUID, rulebook_id: uuid.UUID) -> None:
    """자기 룰북을 지운다. 없으면 AssetNotFoundError."""
    await assets.delete_owned(session, Rulebook, owner_id, rulebook_id)
