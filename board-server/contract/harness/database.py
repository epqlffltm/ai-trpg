# board-server/contract/harness/database.py

"""
시험이 DB 를 맞출 때 쓰는 도구. 테스트용 스키마(기본 board_test)에서만 돈다.

API 로 할 수 없는 것만 여기서 한다: 시험 사이에 비우기, 시간이 흐른 것처럼 시각을 옮기기, 행을 그대로 읽기.
표와 칸의 이름은 계약의 일부다. 서버를 다시 써도 board 스키마를 그대로 넘겨받는다(#785).
"""

from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

# 비우는 표. 게시판(boards)은 마이그레이션이 넣은 것을 그대로 쓴다
DATA_TABLES = ('reports', 'comments', 'posts', 'authors', 'outgoing_notifications')
# 시각을 옮길 때 사람마다 고를 칸
WRITE_OWNERS = (('posts', 'author_id'), ('comments', 'author_id'), ('reports', 'reporter_id'))


class Database:
    """테스트용 스키마에 붙은 연결 하나. 문장마다 바로 커밋한다."""

    def __init__(self, url: str, schema: str) -> None:
        if not schema.endswith('_test'):
            raise RuntimeError('계약 시험은 테스트용 스키마에서만 돈다')
        self.schema = schema
        self._connection = psycopg.connect(url, autocommit=True, row_factory=dict_row)
        self._connection.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))

    def close(self) -> None:
        self._connection.close()

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        """쿼리 하나. 돌려주는 행이 있으면 돌려준다."""
        cursor = self._connection.execute(query, params)  # type: ignore[arg-type]
        return cursor.fetchall() if cursor.description else []

    def clear(self) -> None:
        """글, 댓글, 신고, 닉네임, 알림의 발송함을 비우고 번호를 1 부터 다시 센다."""
        tables = sql.SQL(', ').join(sql.Identifier(table) for table in DATA_TABLES)
        self._connection.execute(sql.SQL('TRUNCATE {} RESTART IDENTITY').format(tables))

    def expire_pin(self, post_id: str) -> None:
        """고정이 끝난 것처럼 만든다. 고정한 시각도 그만큼 앞으로 옮긴다."""
        self.execute(
            """UPDATE posts
                  SET pinned_at = now() - interval '8 days', pinned_until = now() - interval '1 second'
                WHERE id = %s""",
            (post_id,),
        )

    def age_writes(self, user_id: str, seconds: int) -> None:
        """이 사람이 쓴 글과 댓글, 한 신고의 시각을 seconds 초만큼 과거로 옮긴다."""
        for table, owner in WRITE_OWNERS:
            self.execute(
                sql.SQL('UPDATE {} SET created_at = created_at - make_interval(secs => %s) WHERE {} = %s')
                .format(sql.Identifier(table), sql.Identifier(owner))
                .as_string(self._connection),
                (seconds, user_id),
            )

    def insert_many_posts(self, count: int, author_id: str, board: str = 'free') -> None:
        """글을 한꺼번에 많이 넣는다. API 를 거치지 않는다(쓰기 한도를 넘는 양을 볼 때)."""
        self.execute(
            """INSERT INTO posts (board_id, author_id, title, content)
               SELECT (SELECT id FROM boards WHERE slug = %s), %s, '글 ' || n, repeat('본문 글자 ', 400) || n
                 FROM generate_series(1, %s) AS n""",
            (board, author_id, count),
        )

    def row(self, table: str, key: str, value: Any) -> dict[str, Any] | None:
        """한 행을 그대로 읽는다. 지운 것도 읽는다. 없으면 None."""
        rows = self.execute(
            sql.SQL('SELECT * FROM {} WHERE {} = %s')
            .format(sql.Identifier(table), sql.Identifier(key))
            .as_string(self._connection),
            (value,),
        )
        return rows[0] if rows else None
