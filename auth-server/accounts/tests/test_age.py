# auth-server/accounts/tests/test_age.py

"""
나이의 날짜 계산(accounts/age.py)을 검증한다. DB 를 쓰지 않는다.
"""

from datetime import UTC, date, datetime

from django.test import SimpleTestCase

from accounts.age import (
    adult_content_from,
    has_reached,
    is_under_min_age,
    korean_today,
    legal_adult_from,
    years_after,
)


class KoreanTodayTests(SimpleTestCase):
    def test_the_day_turns_at_korean_midnight(self):
        # UTC 15시가 한국 자정이다. 서버의 날짜(UTC)로 자르면 아침 9시까지 하루가 늦다
        self.assertEqual(korean_today(datetime(2026, 12, 31, 14, 59, 59, tzinfo=UTC)), date(2026, 12, 31))
        self.assertEqual(korean_today(datetime(2026, 12, 31, 15, 0, 0, tzinfo=UTC)), date(2027, 1, 1))


class YearsAfterTests(SimpleTestCase):
    def test_same_day_years_later(self):
        self.assertEqual(years_after(date(2007, 3, 15), 19), date(2026, 3, 15))

    def test_a_leap_day_birthday_counts_from_march_first(self):
        # 2월 29일이 없는 해에는 2월 28일로 기간이 끝나고 다음 날부터 그 나이다(민법 160조)
        self.assertEqual(years_after(date(2008, 2, 29), 19), date(2027, 3, 1))
        # 그해에 2월 29일이 있으면 그날이다
        self.assertEqual(years_after(date(2008, 2, 29), 20), date(2028, 2, 29))


class AdultDatesTests(SimpleTestCase):
    def test_legal_adulthood_is_the_nineteenth_birthday(self):
        self.assertEqual(legal_adult_from(date(2007, 10, 18)), date(2026, 10, 18))

    def test_adult_content_opens_on_january_first_of_that_year(self):
        # 청소년 보호법은 만 19세가 되는 해의 1월 1일부터 청소년으로 보지 않는다
        self.assertEqual(adult_content_from(date(2007, 10, 18)), date(2026, 1, 1))
        self.assertEqual(adult_content_from(date(2007, 1, 1)), date(2026, 1, 1))
        self.assertEqual(adult_content_from(date(2007, 12, 31)), date(2026, 1, 1))


class MinAgeTests(SimpleTestCase):
    def test_the_fourteenth_birthday_is_old_enough(self):
        birth_date = date(2012, 10, 17)

        self.assertTrue(is_under_min_age(birth_date, date(2026, 10, 16)))
        self.assertFalse(is_under_min_age(birth_date, date(2026, 10, 17)))


class HasReachedTests(SimpleTestCase):
    def test_a_day_is_reached_on_that_day(self):
        self.assertFalse(has_reached(date(2026, 10, 18), date(2026, 10, 17)))
        self.assertTrue(has_reached(date(2026, 10, 18), date(2026, 10, 18)))
        self.assertTrue(has_reached(date(2026, 10, 18), date(2026, 10, 19)))

    def test_an_empty_day_was_already_reached(self):
        self.assertTrue(has_reached(None, date(2026, 10, 17)))
