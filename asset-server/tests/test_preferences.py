# asset-server/tests/test_preferences.py

"""보는 사람이 공개 목록을 거르는 설정(app/preferences.py, #986, #987)의 순수한 함수를 검증한다."""

from app.preferences import Orientation, Preferences, shown_ratings
from app.ratings import Rating


def test_hiding_adult_drops_only_the_adult_rating():
    both = [Rating.ALL, Rating.ADULT]

    assert shown_ratings(both, Preferences()) == both
    assert shown_ratings(both, Preferences(hide_adult=True)) == [Rating.ALL]
    assert shown_ratings([Rating.ALL], Preferences(hide_adult=True)) == [Rating.ALL]


def test_the_orientation_is_its_tag():
    assert Preferences().orientation_tag is None
    assert Preferences(orientation=Orientation.MALE).orientation_tag == '남성향'
    assert Preferences(orientation=Orientation.FEMALE).orientation_tag == '여성향'
