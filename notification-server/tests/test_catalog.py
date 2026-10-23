# notification-server/tests/test_catalog.py

"""
알림의 종류 표(app/notifications/catalog.py)를 검증한다. DB 도 HTTP 도 쓰지 않는다.

  - 그 서버가 넣는 kind 이고 꼭 있어야 하는 칸이 있으면 받는다
  - 표에 없는 kind, 남의 kind, 칸이 빠진 payload 는 받지 않는다
  - 표의 kind 는 DB 의 모양 규칙에 맞고, 넣는 서버의 이름은 서명 비밀이 있는 서버다
  - 사용자가 끌 수 있는 kind 는 정해 둔 것뿐이다. 돈과 제재처럼 꼭 알아야 하는 것은 끌 수 없다
"""

import re

import pytest

from app.core.config import Settings
from app.notifications.catalog import (
    ASSET,
    BILLING,
    BOARD,
    CHAT,
    GAME,
    KINDS,
    Refusal,
    RefusalCode,
    is_mutable,
    mutable_kinds,
    refusal_for,
)
from app.notifications.schemas import KIND_PATTERN

# 넣는 서버마다 지금 넣는 kind. 넣는 서버의 코드에서 옮겨 적었다. 표가 이것과 다르면 그 서버의 알림이 422 로 버려진다
SENT_BY = {
    GAME: {
        'narration_model.retiring',
        'narration_model.replaced',
        'narration_model.unavailable',
        'scenario.sanctioned',
        'publishing.banned',
        'publishing.unbanned',
    },
    BILLING: {'order.paid', 'order.refunded', 'credit.welcome', 'credit.expiring', 'credit.short'},
    BOARD: {'post.commented', 'comment.replied'},
    ASSET: {'character.hidden', 'character.unhidden', 'character_report.handled'},
    CHAT: {'message_report.handled'},
}


def full_payload(kind: str) -> dict:
    """그 kind 의 꼭 있어야 하는 칸을 모두 채운 값."""
    return dict.fromkeys(KINDS[kind].required, 'x')


def test_every_server_owns_exactly_the_kinds_it_sends():
    owned = {source: {kind for kind, rule in KINDS.items() if rule.source == source} for source in SENT_BY}

    assert owned == SENT_BY
    assert {rule.source for rule in KINDS.values()} == set(SENT_BY)


def test_every_kind_has_the_shape_the_database_takes():
    assert all(re.fullmatch(KIND_PATTERN, kind) for kind in KINDS)


def test_every_source_has_a_signing_secret_in_the_settings():
    # 표에 있는 서버는 비밀의 설정이 있어야 넣을 수 있다. 이름이 어긋나면 그 서버의 kind 는 아무도 넣지 못한다
    names = {name.removesuffix('_server_secret') for name in Settings.model_fields if name.endswith('_server_secret')}

    assert {rule.source for rule in KINDS.values()} <= names


@pytest.mark.parametrize('kind', sorted(KINDS))
def test_takes_a_listed_kind_from_its_server(kind: str):
    assert refusal_for(KINDS[kind].source, kind, full_payload(kind)) is None


def test_takes_fields_that_are_not_listed():
    # 넣는 서버가 칸을 먼저 더하고 화면이 나중에 쓴다
    payload = {**full_payload('publishing.banned'), 'new_field': 1}

    assert refusal_for(GAME, 'publishing.banned', payload) is None


def test_takes_a_kind_that_needs_no_fields():
    assert refusal_for(GAME, 'publishing.unbanned', {}) is None


def test_refuses_a_kind_that_is_not_listed():
    assert refusal_for(GAME, 'stack.smoke', {}) == Refusal(RefusalCode.KIND_UNKNOWN)


@pytest.mark.parametrize(
    ('source', 'kind'),
    [(BOARD, 'order.paid'), (BILLING, 'publishing.banned'), (GAME, 'comment.replied'), ('chat', 'order.paid')],
)
def test_refuses_a_kind_from_another_server(source: str, kind: str):
    assert refusal_for(source, kind, full_payload(kind)) == Refusal(RefusalCode.KIND_NOT_ALLOWED)


def test_the_server_is_checked_before_the_fields():
    # 남의 kind 면 칸이 빠졌어도 kind_not_allowed 다. 무엇이 빠졌는지 남의 서버에 알려 주지 않는다
    assert refusal_for(BOARD, 'order.paid', {}) == Refusal(RefusalCode.KIND_NOT_ALLOWED)


def test_names_the_missing_fields_in_order():
    payload = {'board_slug': 'free', 'post_id': '1'}

    refusal = refusal_for(BOARD, 'comment.replied', payload)

    assert refusal == Refusal(RefusalCode.PAYLOAD_MISSING_FIELDS, ('comment_id', 'parent_id', 'post_title'))


def test_a_null_value_counts_as_there():
    payload = {**full_payload('narration_model.replaced'), 'round': None, 'price': None}

    assert refusal_for(GAME, 'narration_model.replaced', payload) is None


def test_the_table_cannot_be_changed_at_run_time():
    with pytest.raises(TypeError):
        KINDS['order.paid'] = KINDS['post.commented']  # type: ignore[index]


def test_only_the_chosen_kinds_can_be_muted():
    # 이 목록을 바꾸는 PR 은 화면 명세(A10)와 README 의 "알림 끄기"도 고친다
    assert mutable_kinds() == (
        'comment.replied',
        'credit.expiring',
        'credit.short',
        'narration_model.retiring',
        'post.commented',
    )


@pytest.mark.parametrize('kind', ['order.paid', 'order.refunded', 'scenario.sanctioned', 'publishing.banned'])
def test_money_and_sanctions_cannot_be_muted(kind: str):
    assert not is_mutable(kind)


def test_a_kind_that_is_not_listed_cannot_be_muted():
    assert not is_mutable('stack.smoke')
