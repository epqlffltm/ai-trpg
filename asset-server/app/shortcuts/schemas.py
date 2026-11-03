# asset-server/app/shortcuts/schemas.py

"""
단축어의 모양과 상한(#981). 제작자 단축어(캐릭터, 세계관)와 내 단축어가 함께 쓴다.

  - 이름은 "/이름"으로 부르는 말이다. 빈칸과 / 가 없는 10자까지. 한 목록 안에서 겹치지 않는다
  - 설명은 고를 때 보이는 30자까지의 글, 본문은 그 턴에 붙는 400자까지의 글이다
  - 한 목록에 20개까지다(작품 하나, 사람 하나)
본문은 사용자의 입력처럼 다룬다. 붙이는 쪽(chat, story)이 시스템 지시나 상태로 쓰지 않는다.
"""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

SHORTCUT_NAME_MAX_LENGTH = 10
SHORTCUT_DESCRIPTION_MAX_LENGTH = 30
SHORTCUT_BODY_MAX_LENGTH = 400
SHORTCUTS_MAX = 20
# 이름: 빈칸과 / 가 없는 글자들
SHORTCUT_NAME_PATTERN = r'^[^\s/]+$'

ShortcutName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=SHORTCUT_NAME_MAX_LENGTH, pattern=SHORTCUT_NAME_PATTERN
    ),
]
ShortcutDescription = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=SHORTCUT_DESCRIPTION_MAX_LENGTH)
]
ShortcutBody = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=SHORTCUT_BODY_MAX_LENGTH)
]


class Shortcut(BaseModel):
    """단축어 하나. 받을 때도 판의 문서에 굳힐 때도 이 모양이다."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    name: ShortcutName
    description: ShortcutDescription = ''
    body: ShortcutBody


def unique_names(shortcuts: list[Shortcut]) -> list[Shortcut]:
    """한 목록에 같은 이름이 두 번 있으면 거부한다(422)."""
    names = [shortcut.name for shortcut in shortcuts]
    if len(set(names)) != len(names):
        raise ValueError('같은 이름의 단축어가 두 번 있습니다.')
    return shortcuts


Shortcuts = Annotated[list[Shortcut], Field(max_length=SHORTCUTS_MAX), AfterValidator(unique_names)]


def shortcut_rows(shortcuts: list[Shortcut]) -> list[dict]:
    """DB 에 적을 모양(dict 의 목록)."""
    return [shortcut.model_dump(mode='json') for shortcut in shortcuts]


class ShortcutList(BaseModel):
    """내 단축어 전체. 바꿀 때도 읽을 때도 목록을 통째로 주고받는다(적은 차례가 고르는 목록의 차례다)."""

    model_config = ConfigDict(extra='forbid')

    items: Shortcuts = []
