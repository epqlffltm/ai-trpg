# chat-server/app/world/refusals.py

"""
행동(이동, 쓰기, 건네기)을 할 수 없는 까닭. 응답은 422 이고 code 가 까닭이다. 아무것도 저장하지 않는다.
"""

import enum


class Refusal(enum.StrEnum):
    """할 수 없는 까닭."""

    # 지도가 없는 캐릭터다(지금 있는 장소가 없다)
    NO_MAP = 'no_map'
    # 판에 없는 장소다
    PLACE_NOT_FOUND = 'place_not_found'
    # 이미 그곳에 있다
    ALREADY_THERE = 'already_there'
    # 지금 있는 곳과 길로 이어지지 않았다
    NOT_CONNECTED = 'not_connected'
    # 판에 없는 물건이다
    ITEM_NOT_FOUND = 'item_not_found'
    # 그 물건을 가지고 있지 않다
    NOT_HELD = 'not_held'


class ActionRefusedError(Exception):
    """할 수 없는 행동이다(422). reason 이 까닭이다."""

    def __init__(self, reason: Refusal) -> None:
        super().__init__(reason)
        self.reason = reason
