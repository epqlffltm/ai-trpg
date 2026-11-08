# trpg-server/tests/test_check_style_records.py

"""
판정 방식(#404)을 내보내는 쪽을 검증한다. 판정의 결과의 응답 모양, 지난 결과(방식이 없는 것), 이야기로 옮긴 판정의 글.

DB 도 HTTP 도 쓰지 않는다. 판정의 굴림과 엔진은 tests/test_check_styles.py 가 본다.
"""

from app.rounds.schemas import CheckOutcome, CrossOut, RolledOut
from app.transcripts.story import check_numbers

OLD = {'roll': 12, 'modifier': 3, 'total': 15, 'target': 15, 'success': True}


def test_an_outcome_from_before_the_styles_reads_as_one_die_over():
    assert (CheckOutcome.model_validate(OLD).style, CheckOutcome.model_validate(OLD).faces) == ('over', [])
    assert RolledOut.model_validate(OLD).style == 'over'
    assert CrossOut.model_validate({**OLD, 'ability': 'str', 'difficulty': 'medium'}).faces == []


def test_an_under_outcome_keeps_its_style_and_faces():
    under = CheckOutcome.model_validate({**OLD, 'total': 34, 'target': 45, 'style': 'under', 'faces': [34]})

    assert (under.style, under.faces) == ('under', [34])


def test_the_transcript_writes_over_with_the_modifier():
    assert check_numbers(OLD) == '12 + 3 = 15, 목표 15'
    assert check_numbers({**OLD, 'roll': 7, 'total': 10, 'faces': [3, 4], 'style': 'over'}) == '3+4=7 + 3 = 10, 목표 15'


def test_the_transcript_writes_under_against_the_skill():
    made = {'roll': 34, 'modifier': 0, 'total': 34, 'target': 45, 'success': True, 'style': 'under', 'faces': [34]}

    assert check_numbers(made) == '눈 34 ≤ 기량 45'
    assert check_numbers({**made, 'roll': 46, 'total': 46, 'success': False, 'faces': [46]}) == '눈 46 > 기량 45'
