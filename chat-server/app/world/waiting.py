# chat-server/app/world/waiting.py

"""
시간 보내기의 규칙. DB 를 모르는 순수 함수다(#668, 2026-10-22 유저 결정).

다음 시간대가 시작하는 시각까지 흐른다. 밤이면 다음 날 새벽(4시)이다(story 의 "시간 보내기"와 같다).
지도가 없어도 된다. 막는 까닭이 없다. "하루 마치기"는 chat 에 두지 않는다(밤에서 보내면 다음 날이 된다).
"""

from dataclasses import replace

from app.world.clock import TIME_OF_DAY_WORDS, clock_minutes, read_time, until_next_time_of_day
from app.world.state import WorldState


def apply_wait(state: WorldState, start_hour: int) -> WorldState:
    """시간을 보낸 뒤의 상태. 다음 시간대의 시작까지 흐른다."""
    now = clock_minutes(start_hour, state.minutes)
    return replace(state, minutes=state.minutes + until_next_time_of_day(now))


def wait_text(state: WorldState, start_hour: int) -> str:
    """시간을 보낸 행동 말의 글(state 는 보낸 뒤의 상태). 사람에게도 보이고 모델에도 간다."""
    time = read_time(clock_minutes(start_hour, state.minutes))
    return f'시간을 보냈다. {TIME_OF_DAY_WORDS[time.time_of_day]}이 되었다.'
