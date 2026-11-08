# trpg-server/tests/test_under_wording.py

"""
눈 ≤ 기량 방식(under, #404)과 주사위 여럿을 서술자와 기록에 맞는 말로 적는지 검증한다.

서술자가 받는 판정의 줄(app/rounds/move_lines.py), 죽음의 굴림의 줄,
기록 내려받기의 죽음의 굴림(app/transcripts/story.py), 선언의 결과에서 판정을 읽는 곳
(app/rounds/narration_request.py)을 본다. DB 도 HTTP 도 쓰지 않는다.
"""

from types import SimpleNamespace

from app.rounds.move_lines import describe_death_save, describe_verdict
from app.rounds.narration_request import find_death_save
from app.rounds.narrator import DeathSaveNote, Verdict
from app.transcripts.labels import Labels
from app.transcripts.story import death_save_rolled

OVER = Verdict(ability='근력', difficulty='보통', roll=13, modifier=2, total=15, target=15, success=True)
SAVE = DeathSaveNote(roll=34, target=50, success=True, successes=1, failures=0, fate='dying')


def test_over_keeps_its_line():
    assert describe_verdict(OVER) == '(근력 판정 성공: 13 + 2 = 15, 목표 15)'


def test_several_dice_show_their_faces():
    rolled = Verdict(
        ability='근력', difficulty='보통', roll=7, modifier=2, total=9, target=8, success=True, faces=(3, 4)
    )

    assert describe_verdict(rolled) == '(근력 판정 성공: 3+4=7 + 2 = 9, 목표 8)'


def test_under_compares_the_roll_with_the_skill():
    made = Verdict(
        ability='근력',
        difficulty='보통',
        roll=34,
        modifier=0,
        total=34,
        target=45,
        success=True,
        style='under',
        faces=(34,),
    )

    assert describe_verdict(made) == '(근력 판정 성공: 눈 34, 기량 45 이하)'


def test_the_death_save_says_below_for_under():
    assert describe_death_save(SAVE) == '(죽음의 굴림 성공: 34, 목표 50. 성공 1, 실패 0, 죽어 가는 중)'
    under = DeathSaveNote(**{**SAVE.__dict__, 'style': 'under'})
    assert describe_death_save(under) == '(죽음의 굴림 성공: 34, 목표 50 이하. 성공 1, 실패 0, 죽어 가는 중)'


def test_the_death_save_takes_the_style_from_the_caller():
    user_id = '11111111-2222-4333-8444-555555555555'
    saved = {
        'user_id': user_id,
        'roll': 34,
        'target': 50,
        'success': True,
        'successes': 1,
        'failures': 0,
        'fate': 'dying',
    }
    round_ = SimpleNamespace(death_saves=[saved])

    assert find_death_save(round_, user_id).style == 'over'
    assert find_death_save(round_, user_id, 'under').style == 'under'


def test_the_transcript_compares_the_death_save_for_under():
    payload = {'character_name': '엘프', 'roll': 34, 'target': 50, 'success': True, 'successes': 1, 'failures': 0}

    (over,) = death_save_rolled(payload, Labels())
    (under,) = death_save_rolled(payload, Labels(roll_style='under'))

    assert over.text == '죽음의 굴림: 엘프 34 / 50 → 성공 (성공 1, 실패 0)'
    assert under.text == '죽음의 굴림: 엘프 34 ≤ 50 → 성공 (성공 1, 실패 0)'
