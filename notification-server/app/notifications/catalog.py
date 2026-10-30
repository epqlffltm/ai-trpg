# notification-server/app/notifications/catalog.py

"""
알림의 종류(kind)마다 그것을 넣을 수 있는 서버(source)와 payload 에 꼭 있어야 하는 칸을 정해 둔다.

서명은 "어느 서버가 보냈는가"만 확인한다. 그 서버가 그 알림을 보내도 되는지는 따로 본다.
이 표가 없으면 게시판 서버의 버그나 새어 나간 비밀로
결제 완료(`order.paid`)나 공개 금지(`publishing.banned`) 같은 알림을 넣을 수 있다.
화면은 kind 를 보고 글을 만들기 때문에 사용자에게는 진짜처럼 보인다.

  - 표에 없는 kind 는 받지 않는다(kind_unknown)
  - 표에 있어도 넣는 서버가 다르면 받지 않는다(kind_not_allowed)
  - 꼭 있어야 하는 칸이 빠졌으면 받지 않는다(payload_missing_fields). 화면이 글과 이동할 주소를 만드는 칸이다
  - 표에 없는 칸이 더 있는 것은 받는다. 넣는 서버가 칸을 먼저 더하고 화면이 나중에 쓰는 순서를 막지 않는다.
    칸의 값의 모양(글자인지 숫자인지)은 보지 않는다. 그건 넣는 서버의 테스트가 지킨다

사용자가 끌 수 있는 종류(mutable)도 이 표가 정한다(#525, app/mutes).
돈이 오간 일(결제, 청약철회)과 제재, 내 테이블의 모델이 이미 바뀐 일처럼 꼭 알아야 하는 것은 끌 수 없다.
한 번뿐인 일(환영 크레딧)도 끌 까닭이 없어 두지 않는다.

새 kind 를 더하는 PR 은 넣는 서버와 함께 이 표, README 의 "알림의 종류",
화면 명세(docs/product/screens.md 의 A10)를 고친다. 알림 서버를 먼저 배포한다. 거꾸로면 새 kind 가 422 로 버려진다.
DB 와 HTTP 를 모른다. 부르는 쪽(router.py)이 거절을 응답으로 바꾼다.
"""

import enum
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

# 넣는 서버의 이름. 주소의 {source} 이고 서명 비밀의 이름(GAME_SERVER_SECRET 등)과 짝이다
GAME = 'game'
BILLING = 'billing'
BOARD = 'board'
ASSET = 'asset'
CHAT = 'chat'
STORY = 'story'


@dataclass(frozen=True)
class KindRule:
    """kind 하나의 규칙. 넣을 수 있는 서버와 payload 에 꼭 있어야 하는 칸이다."""

    source: str
    required: frozenset[str]
    # 사용자가 이 종류를 끌 수 있는가. 끈 종류는 넣을 때 거른다(app/mutes)
    mutable: bool = False


def rule(source: str, *required: str, mutable: bool = False) -> KindRule:
    """규칙을 만든다. 표를 짧게 적으려는 것이다."""
    return KindRule(source=source, required=frozenset(required), mutable=mutable)


# 받는 알림의 표. 넣는 서버의 코드가 원본이다
# (trpg-server/README.md, board-server/README.md 의 "알림 보내기", billing-server/README.md 의 "정리 작업과 대사")
KINDS: Mapping[str, KindRule] = MappingProxyType(
    {
        # 게임: 서술 모델의 은퇴를 방장에게
        'narration_model.retiring': rule(
            GAME, 'table_id', 'title', 'narration_model', 'retires_on', 'days_left', mutable=True
        ),
        'narration_model.replaced': rule(
            GAME, 'table_id', 'title', 'from', 'narration_model', 'reason', 'round', 'price'
        ),
        'narration_model.unavailable': rule(GAME, 'table_id', 'title', 'narration_model', 'reason'),
        # 게임: 운영자의 제재를 당사자에게
        'scenario.sanctioned': rule(GAME, 'scenario_id', 'title', 'version_number', 'publishing_banned'),
        'publishing.banned': rule(GAME, 'automatic'),
        'publishing.unbanned': rule(GAME),
        # 결제: 결제와 크레딧
        'order.paid': rule(BILLING, 'order_id', 'product_id', 'price', 'credits'),
        'order.refunded': rule(BILLING, 'order_id', 'product_id', 'price', 'credits'),
        'credit.welcome': rule(BILLING, 'amount', 'expires_at'),
        'credit.expiring': rule(BILLING, 'amount', 'first_expires_at', mutable=True),
        'credit.short': rule(BILLING, 'price_code', 'amount', 'gold_required', mutable=True),
        # 게시판: 댓글과 답글
        'post.commented': rule(BOARD, 'board_slug', 'post_id', 'post_title', 'comment_id', mutable=True),
        'comment.replied': rule(BOARD, 'board_slug', 'post_id', 'post_title', 'comment_id', 'parent_id', mutable=True),
        # asset: 운영자가 캐릭터를 숨기고 푼 것을 주인에게(#678). 제재라 끌 수 없다
        'character.hidden': rule(ASSET, 'character_id', 'name'),
        'character.unhidden': rule(ASSET, 'character_id', 'name'),
        # asset, chat: 신고를 처리했다는 것을 신고한 사람에게(#678). 결과(숨김, 기각)는 싣지 않는다.
        # 자기가 신고한 것의 답이라 드물고, 끌 까닭이 적어 끌 수 없게 둔다
        'character_report.handled': rule(ASSET, 'name'),
        'message_report.handled': rule(CHAT, 'name'),
        # story: 세션 속 답의 신고를 처리했다는 것을 신고한 사람에게. chat 의 것과 같다(name 은 세계관의 이름)
        'story_report.handled': rule(STORY, 'name'),
    }
)


class RefusalCode(enum.StrEnum):
    """알림을 받지 않은 까닭. 422 의 detail.code 다."""

    KIND_UNKNOWN = 'kind_unknown'
    KIND_NOT_ALLOWED = 'kind_not_allowed'
    PAYLOAD_MISSING_FIELDS = 'payload_missing_fields'


@dataclass(frozen=True)
class Refusal:
    """받지 않은 까닭과, 칸이 빠졌으면 빠진 칸의 이름들(이름 차례)."""

    code: RefusalCode
    missing: tuple[str, ...] = ()


def mutable_kinds() -> tuple[str, ...]:
    """사용자가 끌 수 있는 종류들. 이름 차례다."""
    return tuple(sorted(kind for kind, kind_rule in KINDS.items() if kind_rule.mutable))


def is_mutable(kind: str) -> bool:
    """사용자가 끌 수 있는 종류인가. 표에 없는 종류는 끌 수 없다."""
    kind_rule = KINDS.get(kind)
    return kind_rule is not None and kind_rule.mutable


def missing_fields(kind_rule: KindRule, payload: Mapping[str, Any]) -> tuple[str, ...]:
    """payload 에 없는 꼭 있어야 하는 칸들. 이름 차례다. 값이 null 인 칸은 있는 것이다."""
    return tuple(sorted(kind_rule.required - payload.keys()))


def refusal_for(source: str, kind: str, payload: Mapping[str, Any]) -> Refusal | None:
    """그 서버가 그 알림을 넣어도 되는지 본다. 되면 None, 안 되면 까닭이다."""
    kind_rule = KINDS.get(kind)
    if kind_rule is None:
        return Refusal(RefusalCode.KIND_UNKNOWN)
    if kind_rule.source != source:
        return Refusal(RefusalCode.KIND_NOT_ALLOWED)
    missing = missing_fields(kind_rule, payload)
    if missing:
        return Refusal(RefusalCode.PAYLOAD_MISSING_FIELDS, missing)
    return None
