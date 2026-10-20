# notification-server/app/mutes/schemas.py

"""
알림 끄기 API 의 응답의 모양.
"""

from pydantic import BaseModel


class KindMute(BaseModel):
    """끌 수 있는 종류 하나와 그것을 껐는지."""

    kind: str
    muted: bool


class MuteSettings(BaseModel):
    """
    이 사람의 알림 끄기 설정. 끌 수 있는 종류 전부다(이름 차례). 끌 수 없는 종류는 싣지 않는다.

    화면은 이것으로 켜고 끄는 단추를 그린다. 종류의 이름을 사람의 말로 바꾸는 것은 화면이 한다.
    """

    kinds: list[KindMute]
