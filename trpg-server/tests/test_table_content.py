# trpg-server/tests/test_table_content.py

"""
테이블의 판의 복사본을 한 번만 검증하는 것(#1264, app/tables/content.py 의 snapshot_of)을 검증한다.

보는 것.
  - 같은 테이블에서 같은 문서는 한 번만 검증한다. 테이블마다 따로 붙여 둔다
  - 라운드를 닫는 요청 하나(마지막 선언)에서 판의 검증은 한 번이다. 고치기 전에는 다섯 번이었다
    (수로 입구의 쥐 한 마리, tests/test_monster_turns.py 의 판)
  - 문서를 바꿔 넣으면(새 dict) 다시 읽는다. 값이 같은 새 dict 여도 다시 읽는다
  - 캠페인의 앞 편의 퀘스트를 넘긴 뒤(hand_down_quests) 새 campaign_quests 가 읽힌다
  - 지키기: 앱에서 테이블의 문서를 바꿔 넣는 곳은 정해진 곳뿐이고, 제자리에서 고치는 곳은 없다.
    그래야 문서 객체가 같으면 판도 같다는 가정이 맞는다
"""

import ast
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios import snapshot as snapshot_module
from app.campaigns import service as campaigns
from app.campaigns.models import CampaignRun
from app.tables import content as table_content
from app.tables.content import snapshot_of
from app.tables.models import GameTable
from tests import test_monster_turns as turns
from tests.test_scenario_items import snapshot_document

me = turns.me

APP = Path(__file__).resolve().parents[1] / 'app'

# 테이블의 문서를 통째로 바꿔 넣는 곳. 새 곳을 더하면 여기에 까닭과 함께 적는다
CONTENT_WRITERS = {
    # 캠페인의 다음 편을 열 때 앞 편의 퀘스트 결과를 적는다
    ('campaigns/service.py', 'hand_down_quests'),
}


@pytest.fixture
def counted(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """snapshot_of 가 문서를 검증한(read_snapshot 을 부른) 때마다 그 문서를 적는다."""
    seen: list[dict] = []
    real = table_content.read_snapshot

    def reading(document: dict):
        seen.append(document)
        return real(document)

    monkeypatch.setattr(table_content, 'read_snapshot', reading)
    return seen


def test_the_same_content_is_validated_once_per_table(counted: list[dict]):
    document = snapshot_document()
    table = SimpleNamespace(content=document)
    other = SimpleNamespace(content=document)

    first = snapshot_of(table)
    again = [snapshot_of(table) for _ in range(5)]
    snapshot_of(other)

    assert all(one is first for one in again)
    assert len(counted) == 2


def test_new_content_is_read_again(counted: list[dict]):
    table = cast(GameTable, SimpleNamespace(content=snapshot_document()))
    before = snapshot_of(table)

    # 값이 같아도 새 dict 면 다시 읽는다
    table.content = {**table.content}
    same = snapshot_of(table)
    table.content = {**table.content, 'title': '바뀐 판'}
    changed = snapshot_of(table)

    assert len(counted) == 3
    assert same is not before and same == before
    assert changed.title == '바뀐 판'


@pytest.fixture
def validations(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """판(Snapshot)을 검증한 때마다 하나씩 적는다. read_snapshot 을 거치든 아니든 센다."""
    seen: list[int] = []
    real = snapshot_module.Snapshot.model_validate.__func__

    def counted(cls, *args, **kwargs):
        seen.append(1)
        return real(cls, *args, **kwargs)

    monkeypatch.setattr(snapshot_module.Snapshot, 'model_validate', classmethod(counted))
    return seen


@pytest.mark.usefixtures('clean_tables')
async def test_closing_a_round_validates_the_snapshot_once(
    client: AsyncClient, app: FastAPI, me: dict, validations: list[int]
):
    table = await turns.start_table(client, me)
    turns.load_dice(app, [1] * 20)
    validations.clear()

    # 혼자 앉은 테이블이라 이 선언으로 라운드가 닫히기 시작한다(판정, 쥐의 차례, 닫힘의 기록)
    await turns.declare(client, me, table, '숨을 고른다.')

    assert len(validations) == 1


async def test_handed_down_quests_are_read_after_handing(monkeypatch: pytest.MonkeyPatch):
    entry_id = uuid.uuid4()
    rows = [SimpleNamespace(entry_id=entry_id, result='succeeded')]

    async def quest_results(session, run_id):
        return rows

    monkeypatch.setattr(campaigns.repository, 'quest_results', quest_results)
    table = cast(GameTable, SimpleNamespace(content=snapshot_document()))
    assert snapshot_of(table).campaign_quests == []

    # 앞 편의 결과를 읽는 함수를 바꿔 끼워 세션을 쓰지 않는다
    await campaigns.hand_down_quests(
        cast(AsyncSession, None), cast(CampaignRun, SimpleNamespace(id=uuid.uuid4())), table
    )

    handed = snapshot_of(table).campaign_quests
    assert [(str(one.entry_id), one.result) for one in handed] == [(str(entry_id), 'succeeded')]


# --- 지키기 ---


def content_writes(tree: ast.AST) -> list[tuple[str, ast.AST]]:
    """함수마다 테이블의 문서(*.content)를 바꿔 넣거나 제자리에서 고치는 곳. (함수 이름, 마디)."""
    found = []
    for function in [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)]:
        for node in ast.walk(function):
            if is_table_content_write(node):
                found.append((function.name, node))
    return found


def is_table_content(node: ast.AST) -> bool:
    """테이블의 문서인가. 이름에 table 이 든 것의 content 칸이다(선언의 content 같은 다른 칸과 가른다)."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr == 'content'
        and isinstance(node.value, ast.Name)
        and 'table' in node.value.id
    )


def is_table_content_write(node: ast.AST) -> bool:
    """문서를 바꿔 넣거나(=), 그 안을 고치거나([..] =, del), 고치는 메서드를 부르는가."""
    if isinstance(node, ast.Assign | ast.AugAssign | ast.AnnAssign | ast.Delete):
        targets = node.targets if isinstance(node, ast.Assign | ast.Delete) else [node.target]
        return any(
            is_table_content(target) or (isinstance(target, ast.Subscript) and is_table_content(target.value))
            for target in targets
        )
    mutators = {'update', 'pop', 'popitem', 'setdefault', 'clear', '__setitem__', '__delitem__'}
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in mutators
        and is_table_content(node.func.value)
    )


def test_only_the_known_places_replace_the_content():
    found = set()
    inplace = []
    for path in APP.rglob('*.py'):
        for name, node in content_writes(ast.parse(path.read_text(encoding='utf-8'))):
            where = (path.relative_to(APP).as_posix(), name)
            if isinstance(node, ast.Assign) and all(is_table_content(target) for target in node.targets):
                found.add(where)
            else:
                inplace.append(where)

    assert inplace == [], '테이블의 문서를 제자리에서 고치는 곳이 있다. 새 dict 로 바꿔 넣는다'
    assert found == CONTENT_WRITERS


def test_the_guard_sees_writes():
    code = (
        'def put(table):\n    table.content = {}\n'
        'def poke(table):\n    table.content["a"] = 1\n'
        'def merge(table):\n    table.content.update(a=1)\n'
        'def other(declaration):\n    declaration.content = "글"\n'
    )

    assert [name for name, _ in content_writes(ast.parse(code))] == ['put', 'poke', 'merge']
