# game-server/app/rounds/time_words.py

"""
게임 안의 시각과 기간을 서술자에게 보일 말로 적는다. 프롬프트의 [시각](app/rounds/prompt.py)과
한 일의 줄(app/rounds/move_lines.py)이 같은 말을 쓴다.

파일을 따로 둔 이유: 프롬프트는 한 일의 줄을 불러온다. 한 일의 줄이 프롬프트를 불러오면 서로를 불러오게 된다.
"""

from app.calendar.clock import MINUTES_PER_DAY, MINUTES_PER_HOUR, ClockTime, TimeOfDay

# 시간이 흐르지 않는 라운드에 적는 말
NO_TIME_PASSES = '흐르지 않는다(같은 때가 이어진다)'
# 하루의 어느 때를 서술자에게 보일 말
TIME_OF_DAY_WORDS = {
    TimeOfDay.DAWN: '새벽',
    TimeOfDay.MORNING: '아침',
    TimeOfDay.DAY: '낮',
    TimeOfDay.EVENING: '저녁',
    TimeOfDay.NIGHT: '밤',
}


def time_text(time: ClockTime) -> str:
    """시각 하나. 예: 3일째 22시 00분(밤)"""
    return f'{time.day}일째 {time.hour}시 {time.minute:02d}분({TIME_OF_DAY_WORDS[time.time_of_day]})'


def duration_text(minutes: int) -> str:
    """기간. 예: 20분, 8시간, 1일 2시간 30분. 0 이면 흐르지 않는다는 말."""
    if minutes == 0:
        return NO_TIME_PASSES
    days, rest = divmod(minutes, MINUTES_PER_DAY)
    hours, mins = divmod(rest, MINUTES_PER_HOUR)
    parts = [f'{days}일' if days else '', f'{hours}시간' if hours else '', f'{mins}분' if mins else '']
    return ' '.join(part for part in parts if part)
