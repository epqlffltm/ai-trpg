# trpg-server/app/rounds/snapshots.py

"""
라운드를 닫기 직전의 게임 상태를 찍는 법(#288). 무엇을 찍고 무엇을 빼는지, 값을 JSON 으로 바꾸고 되돌리는 법이다.

DB 를 모른다. 행을 읽고 쓰는 것은 app/rounds/repository.py 의 read_state, replace_state 다.
찍는 때와 되돌리는 때는 app/rounds/reverting.py 가 정한다.

찍는 것은 닫기 시작(app/rounds/service.py 의 begin_closing)이 바꿀 수 있는 테이블의 상태 전부다.
  - 표마다 그 테이블의 행 전부(STATE_TABLES). 시트, 소지품, 착용, 부상, 인물, 몬스터, 퀘스트, 사건, 맵, 덫, 시각
  - 테이블의 행에서는 장(STATE_COLUMNS)만. 나머지는 방장의 설정이나 번호다
되돌릴 때는 이 표들의 그 테이블의 행을 모두 지우고 찍은 행을 다시 넣는다. 행의 id 도 찍은 그대로다.

빼는 것과 그 까닭은 EXCLUDED 에 적는다. 테이블에 딸린 표가 새로 생기면 둘 중 한 곳에 넣어야 한다.
tests/test_round_revert.py 가 모델의 모든 표를 보고 어느 쪽에도 없는 표를 찾는다. 빠뜨리면 되돌려도 그 표만
닫은 뒤의 상태로 남는다(반쯤 되돌아간 상태가 영구히 남는다).

표의 모양이 바뀌면(마이그레이션으로 칸이 늘거나 줄면) 옛 사진은 쓰지 않는다(fits). 칸의 이름을 함께 적어 두고 견준다.
"""

import uuid
from collections.abc import Iterable, Mapping
from datetime import datetime

from sqlalchemy import Column, DateTime, Table, Uuid

from app.core.database import Base

# 찍는 표들. 가리켜지는 표가 앞이다(다시 넣는 차례). 지울 때는 뒤에서부터 지운다
STATE_TABLES: tuple[str, ...] = (
    'table_clocks',
    'table_quests',
    'table_happenings',
    'table_visits',
    'table_found_routes',
    'table_route_locks',
    'table_place_items',
    'table_traps',
    'table_npcs',
    'table_npc_items',
    'table_monsters',
    'table_monster_items',
    'table_sheets',
    'table_items',
    'table_worn',
    'table_injuries',
)

# 테이블의 행에서 찍는 칸. 닫기가 장을 넘긴다(app/rounds/chapters.py)
STATE_COLUMNS: tuple[str, ...] = ('chapter_id', 'chapter_round')

# 테이블에 딸렸지만 찍지 않는 표와 그 까닭
EXCLUDED: dict[str, str] = {
    'game_tables': '테이블의 행. 장(STATE_COLUMNS)만 찍는다. 나머지는 방장의 설정과 이벤트의 번호다',
    'table_members': '자리. 닫기가 바꾸지 않는다. 들어오고 나가거나 캐릭터를 바꾸면 되돌릴 수 없다(reverting.blocker)',
    'table_rolls': '능력치를 굴린 것. 시작하기 전의 일이다. 닫기가 바꾸지 않는다',
    'table_departures': '떠난 사람. 떠난 일이 있으면 되돌릴 수 없다(reverting.blocker)',
    'table_events': '이벤트는 덧붙이기만 한다. 되돌린 묶음은 지우지 않고 round_reverted 로 알린다',
    'table_messages': '채팅. 게임의 상태가 아니다',
    'table_whispers': '쪽지. 게임의 상태가 아니다',
    'table_rounds': '라운드. 되돌린 라운드는 기록으로 남기고, 다음 라운드를 다시 연다(reverting)',
    'round_declarations': '선언. 되돌린 라운드의 것은 남기고, 다시 여는 라운드에 글과 행동을 옮겨 적는다',
    'round_snapshots': '이 사진 자체다',
    'narration_charges': '서술 값의 청구. 되돌려도 돌려주지 않는다(2026-11-03 결정). 다시 닫으면 다시 받는다',
    'round_memories': '지난 라운드의 벡터. 되돌린 번호부터 지운다(다시 만든다)',
    'campaign_tables': '캠페인의 편. 시작할 때 정한다',
    'campaign_seats': '캠페인의 자리. 시작할 때 정한다',
}

# 몬스터의 물건은 테이블의 id 가 없다. 그 테이블의 몬스터로 고른다
PARENT_SCOPES: dict[str, tuple[str, str]] = {'table_monster_items': ('monster_id', 'table_monsters')}


def state_tables() -> list[Table]:
    """찍는 표들. 다시 넣는 차례다."""
    return [Base.metadata.tables[name] for name in STATE_TABLES]


def column_names(table: Table) -> list[str]:
    """표의 칸 이름들. 모델의 차례다."""
    return [column.name for column in table.columns]


def encode_value(column: Column, value: object) -> object:
    """칸의 값 하나를 JSON 에 넣을 값으로. UUID 와 시각은 글자로, 나머지(글, 수, 참거짓, JSON, 목록)는 그대로."""
    if value is None:
        return None
    if isinstance(column.type, Uuid):
        return str(value)
    if isinstance(column.type, DateTime):
        return value.isoformat()
    return value


def decode_value(column: Column, value: object) -> object:
    """encode_value 를 거꾸로. DB 에 넣을 값이다."""
    if value is None:
        return None
    if isinstance(column.type, Uuid):
        return uuid.UUID(value)
    if isinstance(column.type, DateTime):
        return datetime.fromisoformat(value)
    return value


def encode_row(table: Table, row: Mapping[str, object]) -> dict:
    """행 하나를 칸 이름에서 JSON 값으로."""
    return {column.name: encode_value(column, row[column.name]) for column in table.columns}


def decode_row(table: Table, row: Mapping[str, object]) -> dict:
    """찍은 행 하나를 DB 에 넣을 값으로."""
    return {column.name: decode_value(column, row[column.name]) for column in table.columns}


def make_state(rows: Mapping[str, Iterable[Mapping[str, object]]], table_values: Mapping[str, object]) -> dict:
    """
    찍은 상태 하나. rows 는 표 이름에서 그 테이블의 행들로, table_values 는 테이블의 행의 STATE_COLUMNS 의 값이다.

    표마다 칸의 이름을 함께 적는다(fits 가 견준다).
    """
    game_tables = Base.metadata.tables['game_tables']
    return {
        'table': {name: encode_value(game_tables.columns[name], table_values[name]) for name in STATE_COLUMNS},
        'tables': {
            table.name: {
                'columns': column_names(table),
                'rows': [encode_row(table, row) for row in rows.get(table.name, ())],
            }
            for table in state_tables()
        },
    }


def fits(state: Mapping) -> bool:
    """찍은 상태가 지금의 표 모양과 맞는가. 표가 빠졌거나 칸이 다르면 False 다(그때 찍은 것으로 덮을 수 없다)."""
    tables = state.get('tables', {})
    return all(
        table.name in tables and tables[table.name].get('columns') == column_names(table) for table in state_tables()
    )


def rows_of(state: Mapping, table: Table) -> list[dict]:
    """찍은 상태에서 그 표의 행들을 DB 에 넣을 값으로."""
    return [decode_row(table, row) for row in state['tables'][table.name]['rows']]


def table_values_of(state: Mapping) -> dict:
    """찍은 상태에서 테이블의 행의 STATE_COLUMNS 의 값들."""
    game_tables = Base.metadata.tables['game_tables']
    return {name: decode_value(game_tables.columns[name], state['table'][name]) for name in STATE_COLUMNS}
