# trpg-server/app/campaigns/carrying.py

"""
편이 끝날 때 앉은 사람마다 넘길 것을 테이블의 상태에서 고른다(docs/architecture/campaigns.md 의 "옮기는 것").
순수한 함수다. DB 를 모른다.

넘기는 것: 이름과 설명, 능력치, 최대 HP(레벨로 늘어난 몫이 들어 있다), 경험치와 놓지 않은 점수, 기술과 타고난 저항,
돈, 소지품(물건 항목과 개수. 착용은 소지품의 일부라 따로 적지 않는다. 다음 편에서는 풀어서 옮긴다).
넘기지 않는 것: 지금 HP 와 수치의 지금 값(편 사이에 쉰다), 부상, 죽음의 굴림, 서 있던 장소,
레벨(경험치와 레벨표로 다시 정한다).

같은 룰북이라 숫자를 그대로 적는다(게시할 때 막는다). 다음 편의 판에 없는 물건을 거르는 것은 옮길 때 한다.
소지품에는 그 편의 판의 물건 이름도 적는다. 다음 편에서 옮기지 못한 물건을 알릴 때 쓴다(그 판에는 그 물건이 없다).
"""

import uuid

from pydantic import BaseModel, Field

from app.assets.scenarios.snapshot import item_entries
from app.campaigns.models import QuestResult
from app.tables.content import snapshot_of
from app.tables.models import GameTable, QuestStatus, TableMember
from app.tables.sheets import is_dead


class CarryItem(BaseModel):
    """넘기는 소지품 한 가지. 앞 편의 판의 물건 항목과 개수, 그 판의 물건 이름(이 칸이 생기기 전의 것은 비어 있다)."""

    entry_id: uuid.UUID
    count: int = Field(ge=1)
    name: str = ''


class Carry(BaseModel):
    """한 사람의 넘길 것. campaign_carries.carry 에 이 모양으로 적는다."""

    character_name: str
    character_description: str
    # 프리젠으로 한 캐릭터인가. 캠페인 안에서는 넘기지만 보관함에는 넣지 못한다
    pregen: bool
    abilities: dict[str, int]
    max_hp: int
    xp: int
    points: int
    skills: list[str]
    resistances: list[dict]
    money: int
    items: list[CarryItem]


def carry_of(member: TableMember, item_names: dict[uuid.UUID, str] | None = None) -> Carry | None:
    """
    앉은 사람 하나의 넘길 것. 캐릭터의 시트가 없거나(시작 전) 죽었으면 None 이다.

    item_names 는 그 편의 판의 물건 항목마다의 이름이다. 없는 물건은 이름을 비운다.
    """
    names = item_names or {}
    sheet = member.sheet
    if sheet is None or is_dead(member):
        return None
    return Carry(
        character_name=sheet.character_name,
        character_description=member.character_description,
        pregen=sheet.pregen_index is not None,
        abilities=dict(sheet.abilities),
        max_hp=sheet.max_hp,
        xp=sheet.xp,
        points=sheet.points,
        skills=list(sheet.skills),
        resistances=list(sheet.resistances),
        money=sheet.money,
        items=[
            CarryItem(entry_id=item.entry_id, count=item.count, name=names.get(item.entry_id, ''))
            for item in sheet.items
        ],
    )


def carries_of(table: GameTable) -> dict[uuid.UUID, Carry]:
    """앉은 사람마다의 넘길 것. 넘길 것이 없는 사람은 빠진다. 앉은 차례다."""
    names = {entry.id: entry.name for entry in item_entries(snapshot_of(table))}
    found = {member.user_id: carry_of(member, names) for member in table.members}
    return {user_id: carry for user_id, carry in found.items() if carry is not None}


# 테이블의 퀘스트의 상태 → 적을 결과. 숨김과 진행 중은 적지 않는다
RESULTS = {QuestStatus.SUCCEEDED: QuestResult.SUCCEEDED, QuestStatus.FAILED: QuestResult.FAILED}


def quest_results(table: GameTable) -> dict[uuid.UUID, QuestResult]:
    """그 편에서 이루었거나 실패한 퀘스트(사건 항목)와 그 결과."""
    return {quest.entry_id: RESULTS[quest.status] for quest in table.quests if quest.status in RESULTS}
