# story-server/app/shortcuts/schemas.py

"""
단축어 목록 API 의 응답의 모양(#981). 입력칸에서 "/"를 치면 고를 수 있는 것들이다. 본문은 싣지 않는다.
"""

from enum import StrEnum

from pydantic import BaseModel


class ShortcutSource(StrEnum):
    """단축어가 어디의 것인가. work 는 세계관의 판(제작자), mine 은 내 단축어다."""

    WORK = 'work'
    MINE = 'mine'


class ShortcutOut(BaseModel):
    """고를 수 있는 단축어 하나."""

    name: str
    description: str
    source: ShortcutSource
