# board-server/app/core/times.py

"""
응답에 싣는 시각의 모양. UTC 의 밀리초까지와 Z 다(2026-10-25T08:00:00.123Z).

NestJS 로 쓰던 때(자바스크립트의 Date 를 JSON 으로)와 같은 모양이다. 화면이 시각을 글자 그대로 견주는 곳이 있다.
응답의 시각 칸은 이 타입(Timestamp)으로 적는다.
"""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import PlainSerializer


def format_timestamp(value: datetime) -> str:
    """시각을 UTC 의 밀리초까지의 글자로. 시간대가 없는 시각은 UTC 로 본다."""
    moment = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return moment.strftime('%Y-%m-%dT%H:%M:%S.') + f'{moment.microsecond // 1000:03d}Z'


# 응답의 시각 칸
Timestamp = Annotated[datetime, PlainSerializer(format_timestamp, return_type=str, when_used='json')]
