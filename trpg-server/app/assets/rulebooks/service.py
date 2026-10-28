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
from app.engine.ruleset import Armor, Ruleset
from app.engine.templates import TemplateFile, all_templates, from_template


class RulesInvalidError(Exception):
    """
    고친 규칙이 규칙 한 벌로 맞지 않는다. 수치(#804)의 최대에 쓰는 능력치가 규칙에 없거나, 같은 수치가 두 번 있거나,
    기술(#805)의 비용이나 효과가 규칙에 없는 것을 가리킨다.

    칸 하나의 모양은 받을 때 봤다. 이것은 칸끼리 맞는지다. message 는 왜 맞지 않는지, field 는 어느 칸인지다
    (PART_FIELDS 중 하나, #886).
    """

    def __init__(self, message: str, field: str) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


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
    rules = with_parts(rules, parts_of(data))
    return Rulebook(asset=asset, gm_guide=data.gm_guide, rules=rules)


def with_armor(rules: dict, armor: Armor | None) -> dict:
    """규칙의 방어 규칙만 바꾼 문서. 받은 문서는 고치지 않는다. 방어 규칙은 받을 때 모양을 확인했다."""
    return {**rules, 'armor': armor.model_dump(mode='json') if armor is not None else None}


def problem_of(rules: dict) -> str | None:
    """규칙 한 벌로 읽어 맞지 않으면 그 까닭. 맞으면 None."""
    try:
        Ruleset.model_validate(rules)
    except ValidationError as error:
        return error.errors()[0]['msg']
    return None


# 한꺼번에 바꿀 수 있는 규칙의 칸들. 앞의 것을 가리키는 것이 뒤에 온다
# (부상과 면역이 성질을, 부상 표가 부상을, 수치의 문턱과 기술이 부상과 수치를 가리킨다)
PART_FIELDS = ('natures', 'injuries', 'injury_table', 'injury_triggers', 'monster_immunities', 'resources', 'skills')
# null 로 비울 수 있는 칸. 보낸 것은 null 이어도 바꾼다. 다른 칸의 null 은 "보내지 않았다"다
NULLABLE_PARTS = ('injury_table',)


def parts_of(data: RulebookCreate | RulebookUpdate) -> dict[str, object]:
    """보낸 규칙의 칸들(PART_FIELDS 중 보낸 것). 이름 → 값. 차례는 PART_FIELDS 의 것이다."""
    return {field: getattr(data, field) for field in PART_FIELDS if was_sent(data, field)}


def was_sent(data: RulebookCreate | RulebookUpdate, field: str) -> bool:
    """그 칸을 보냈는가. 비울 수 있는 칸은 null 을 보낸 것도 보낸 것이다."""
    if field in NULLABLE_PARTS:
        return field in data.model_fields_set
    return getattr(data, field) is not None


def dump_part(value: object) -> object:
    """규칙의 칸 하나를 DB 에 넣을 문서로. 목록이면 하나씩, 조각이면 그대로, null 은 null 이다."""
    if value is None:
        return None
    if isinstance(value, list):
        return dump_all(value)
    return value.model_dump(mode='json')


def with_parts(rules: dict, parts: dict[str, object]) -> dict:
    """
    규칙의 성질과 면역과 부상과 부상 표와 굴리는 때(#886), 수치(#804), 기술(#805) 중 보낸 것만 바꾼 문서.
    받은 문서는 고치지 않는다. 아무것도 안 보냈으면 그대로다.

    칸끼리 가리키는 것(기술의 비용이 수치를, 부상과 면역이 성질을)은 규칙의 다른 칸과 견주어야 알 수 있다.
    보낸 것을 모두 바꾼 규칙 한 벌로 다시 읽어 보고(수치를 지우며 그 수치를 쓰던 기술도 함께 고칠 수 있게),
    맞지 않으면 RulesInvalidError 다. 어느 칸이 틀렸는지는 PART_FIELDS 의 차례로 하나씩 더해 가며
    처음 틀린 칸으로 가린다.
    """
    if not parts:
        return rules
    changed = {**rules, **{field: dump_part(value) for field, value in parts.items()}}
    problem = problem_of(changed)
    if problem is None:
        return changed
    raise RulesInvalidError(problem, first_wrong(rules, parts))


def first_wrong(rules: dict, parts: dict[str, object]) -> str:
    """보낸 칸을 차례로 하나씩 더해 갈 때 규칙이 처음 틀리는 칸. 끝까지 틀리지 않으면 마지막 칸이다."""
    step = rules
    for field, value in parts.items():
        step = {**step, field: dump_part(value)}
        if problem_of(step) is not None:
            return field
    return list(parts)[-1]


def dump_all(parts: list) -> list[dict]:
    """규칙의 조각들을 DB 에 넣을 문서로."""
    return [part.model_dump(mode='json') for part in parts]


def other_changes(data: RulebookUpdate) -> RulebookUpdate:
    """규칙(방어와 PART_FIELDS)을 뺀 고칠 것. 공통의 고치기(app/assets/service.py)는 내용의 칸만 안다."""
    changes = data.model_dump(exclude_unset=True, exclude={'armor', *PART_FIELDS})
    return RulebookUpdate.model_validate(changes)


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
    content.rules = with_parts(content.rules, parts_of(data))
    return await assets.save_changes(session, content, other_changes(data))


async def delete_rulebook(session: AsyncSession, owner_id: uuid.UUID, rulebook_id: uuid.UUID) -> None:
    """자기 룰북을 지운다. 없으면 AssetNotFoundError."""
    await assets.delete_owned(session, Rulebook, owner_id, rulebook_id)
