# game-server/tests/test_injury_clock.py

"""
오래 가는 부상이 게임 안의 시간으로 낫는 규칙(달력 2단계)의 작은 함수들을 검증한다.

테이블을 띄우지 않는다. 부상의 기록(TableInjury)과 라운드가 닫히는 때(Moment)만 만든다.
  - 짧은 것은 라운드로 풀린다. 오래 가는 것은 장면이 끝나는 때가 나을 시각에 닿으면 낫는다.
  - 생긴 라운드에는 낫지 않는다. 다쳐서 그 장면 안에 나으면 생긴 것과 나은 것이 겹친다.
  - 시각을 바꾸면(치료) 라운드는 지운다. 둘을 함께 적지 않는다(DB 의 CHECK).
"""

from app.tables import injuries
from app.tables.injuries import Moment
from app.tables.models import TableInjury

# 2 라운드. 8시 10분에 열려 하룻밤(8시간) 뒤인 16시 10분에 장면이 끝난다
NIGHT = Moment(round_number=2, now=490, scene_end=490 + 8 * 60)


def lasting(heals_at: int, round_number: int = 1) -> TableInjury:
    """오래 가는 부상 하나. 나을 시각이 적혀 있다."""
    return TableInjury(injury='broken_arm', round_number=round_number, heals_at=heals_at)


def short(ends_after_round: int) -> TableInjury:
    """짧은 부상 하나. 풀릴 라운드가 적혀 있다."""
    return TableInjury(injury='stunned', round_number=1, ends_after_round=ends_after_round)


def test_a_lasting_injury_heals_when_the_scene_reaches_its_time():
    assert injuries.is_due(lasting(780), NIGHT)
    assert injuries.is_due(lasting(NIGHT.scene_end), NIGHT)
    assert not injuries.is_due(lasting(NIGHT.scene_end + 1), NIGHT)


def test_an_injury_taken_this_round_does_not_heal_this_round():
    assert not injuries.is_due(lasting(500, round_number=2), NIGHT)


def test_a_short_injury_still_counts_rounds():
    assert injuries.is_due(short(2), NIGHT)
    assert not injuries.is_due(short(3), NIGHT)


def test_an_ended_or_permanent_injury_is_never_due():
    ended = lasting(500)
    injuries.end(ended)
    permanent = TableInjury(injury='lost_eye', round_number=1)

    assert not injuries.is_due(ended, NIGHT)
    assert not injuries.is_due(permanent, NIGHT)


def test_expire_ends_only_what_is_due():
    rows = [lasting(780), lasting(2000), short(2)]

    ended = injuries.expire(rows, NIGHT)

    assert ended == [rows[0], rows[2]]
    assert rows[1].ended_at is None


def test_rescheduling_moves_an_old_round_based_injury_to_a_time():
    # 시간으로 낫기 전에 입어 라운드가 적혀 있던 오래 가는 부상
    old = TableInjury(injury='broken_arm', round_number=1, ends_after_round=31)

    injuries.reschedule(old, 700)

    assert (old.heals_at, old.ends_after_round) == (700, None)
