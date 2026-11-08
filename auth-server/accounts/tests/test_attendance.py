# auth-server/accounts/tests/test_attendance.py

"""
출석과 보물 상자를 검증한다. 규칙, 오늘의 출석, 받기(본인인증, 하루 한 번, 며칠째, 상자), 주소, 결제 서버에 맡기기.

결제 서버를 부르는 함수는 대부분 가짜로 바꿔 끼운다. 요청의 모양은 끝의 BillingRequestTests 가 가짜 결제 서버로 본다.
"""

import json
import threading
import uuid
from datetime import UTC, date, datetime, timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.db import connection
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts import attendance_rules as rules
from accounts.attendance import (
    AttendanceAlreadyClaimedError,
    AttendanceVerificationRequiredError,
    Claim,
    _record,
    attendance_status,
    claim_attendance,
    deliver_due_attendance,
)
from accounts.billing_client import (
    ALREADY_GRANTED,
    ATTENDANCE_PATH,
    GRANTED,
    BillingUnavailableError,
    grant_attendance_silver,
)
from accounts.identity import person_key
from accounts.models import AttendanceClaim, IdentityVerification, User, WelcomeCreditStatus
from accounts.tests.billing_stub import SECRET, BillingStub
from accounts.tests.helpers import authorize

PASSWORD = 'correct-horse-battery'
ATTENDANCE_URL = '/api/v1/auth/attendance'
REWARDS_URL = '/api/v1/auth/attendance/rewards'

# 2026-11-08 낮 12시(한국). 한국 날짜는 2026-11-08 이다
NOON = datetime(2026, 11, 8, 3, 0, tzinfo=UTC)
TODAY = date(2026, 11, 8)


def make_user(number: int = 1, verified: bool = True) -> User:
    """계정 하나를 만든다. verified 면 본인인증의 기록도 둔다(API 를 지나지 않는다)."""
    user = User.objects.create_user(
        username=f'player_{number:02d}',
        email=f'player{number}@example.com',
        nickname=f'플레이어{number}',
        password=PASSWORD,
        email_verified_at=timezone.now(),
    )
    if verified:
        IdentityVerification.objects.create(
            user=user, person_key=person_key(f'person-{number}'), provider='fake', verified_at=timezone.now()
        )
    return user


def days_later(days: int) -> datetime:
    """NOON 에서 days 날 뒤의 같은 시각."""
    return NOON + timedelta(days=days)


def always(n: int) -> rules.Roll:
    """늘 n 을 고르는 상자의 수."""
    return lambda: n


def claimed_row(user: User, day: date = TODAY, **overrides) -> AttendanceClaim:
    """맡기기 전인 출석의 줄 하나를 적는다."""
    fields = {'user': user, 'day': day, 'cycle_day': 1, 'silver': 140, 'next_attempt_at': timezone.now()}
    fields.update(overrides)
    return AttendanceClaim.objects.create(**fields)


class ScheduleRuleTests(SimpleTestCase):
    def test_an_empty_setting_is_the_default_week(self):
        self.assertEqual(rules.parse_schedule(''), rules.DEFAULT_SCHEDULE)
        self.assertEqual(rules.parse_schedule('  '), rules.DEFAULT_SCHEDULE)

    def test_reads_a_comma_separated_list(self):
        self.assertEqual(rules.parse_schedule('10,20,30'), (10, 20, 30))

    def test_refuses_wrong_lists(self):
        for text in ('a,b', '10,,20', '0,10', '10,100001', ','.join(['10'] * 15), '-1'):
            with self.subTest(text=text), self.assertRaises(rules.InvalidScheduleError):
                rules.parse_schedule(text)

    def test_the_longest_cycle_and_the_largest_day_are_allowed(self):
        self.assertEqual(len(rules.parse_schedule(','.join(['1'] * 14))), 14)
        self.assertEqual(rules.parse_schedule('100000'), (100_000,))

    def test_the_last_day_opens_the_chest(self):
        week = rules.DEFAULT_SCHEDULE
        self.assertEqual([day for day in range(1, 8) if rules.opens_chest(week, day)], [7])
        self.assertEqual(rules.silver_on(week, 1), 140)
        self.assertEqual(rules.silver_on(week, 7), 260)


class CycleRuleTests(SimpleTestCase):
    def test_the_first_day_ever_is_day_one(self):
        self.assertEqual(rules.cycle_day_on(None, TODAY, 7), 1)

    def test_coming_back_the_next_day_counts_on(self):
        last = rules.LastClaim(day=TODAY - timedelta(days=1), cycle_day=3)
        self.assertEqual(rules.cycle_day_on(last, TODAY, 7), 4)

    def test_missing_a_day_starts_over(self):
        last = rules.LastClaim(day=TODAY - timedelta(days=2), cycle_day=3)
        self.assertEqual(rules.cycle_day_on(last, TODAY, 7), 1)

    def test_after_the_last_day_a_new_cycle_starts(self):
        last = rules.LastClaim(day=TODAY - timedelta(days=1), cycle_day=7)
        self.assertEqual(rules.cycle_day_on(last, TODAY, 7), 1)

    def test_a_shortened_cycle_starts_over(self):
        last = rules.LastClaim(day=TODAY - timedelta(days=1), cycle_day=6)
        self.assertEqual(rules.cycle_day_on(last, TODAY, 5), 1)

    def test_the_day_changes_at_korean_midnight(self):
        self.assertEqual(rules.korean_date(datetime(2026, 11, 8, 14, 59, tzinfo=UTC)), date(2026, 11, 8))
        self.assertEqual(rules.korean_date(datetime(2026, 11, 8, 15, 0, tzinfo=UTC)), date(2026, 11, 9))


class ChestRuleTests(SimpleTestCase):
    def test_the_current_table_is_valid(self):
        rules.validate_chest(rules.CURRENT_CHEST)

    def test_the_first_table_averages_617_silver(self):
        self.assertEqual(rules.expected_silver(rules.CHEST_V1), 617)

    def test_each_number_falls_into_its_outcome(self):
        table = rules.CHEST_V1
        cases = {0: 'mimic_bite', 999: 'mimic_bite', 1000: 'mimic_teeth', 2999: 'mimic_teeth', 3000: 'goblin_pouch'}
        cases.update({9699: 'treasure_hoard', 9700: 'dragon_hoard', 9999: 'dragon_hoard'})
        for n, outcome in cases.items():
            with self.subTest(n=n):
                self.assertEqual(rules.pick(table, n).id, outcome)

    def test_a_number_out_of_range_gives_the_first_outcome(self):
        self.assertEqual(rules.pick(rules.CHEST_V1, rules.CHANCE_SCALE).id, 'mimic_bite')

    def test_every_outcome_is_counted_by_its_chance(self):
        counts: dict[str, int] = {}
        for n in range(rules.CHANCE_SCALE):
            outcome = rules.pick(rules.CHEST_V1, n)
            counts[outcome.id] = counts.get(outcome.id, 0) + 1
        self.assertEqual(counts, {outcome.id: outcome.chance for outcome in rules.CHEST_V1.outcomes})

    def test_refuses_wrong_tables(self):
        good = rules.Outcome('a', '가', 0, 5_000)
        tables = {
            '버전이 없다': rules.ChestTable('', (good, rules.Outcome('b', '나', 1, 5_000))),
            '결과가 없다': rules.ChestTable('v9', ()),
            '이름이 겹친다': rules.ChestTable('v9', (good, rules.Outcome('a', '나', 1, 5_000))),
            '이름이 비었다': rules.ChestTable('v9', (good, rules.Outcome('', '나', 1, 5_000))),
            '확률이 0': rules.ChestTable(
                'v9', (good, rules.Outcome('b', '나', 1, 0), rules.Outcome('c', '다', 1, 5_000))
            ),
            '실버가 음수': rules.ChestTable('v9', (good, rules.Outcome('b', '나', -1, 5_000))),
            '합이 모자란다': rules.ChestTable('v9', (good, rules.Outcome('b', '나', 1, 4_999))),
        }
        for name, table in tables.items():
            with self.subTest(name), self.assertRaises(rules.InvalidChestError):
                rules.validate_chest(table)

    def test_percent_drops_trailing_zeros(self):
        cases = {1000: '10%', 250: '2.5%', 1: '0.01%', 300: '3%', 2200: '22%', 10_000: '100%', 5: '0.05%'}
        for chance, text in cases.items():
            with self.subTest(chance=chance):
                self.assertEqual(rules.percent_of(chance), text)

    def test_the_crypto_roll_stays_in_range(self):
        self.assertTrue(all(0 <= rules.crypto_roll() < rules.CHANCE_SCALE for _ in range(200)))


class ClaimTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def claim_on(self, days: int, roll: int = 0) -> Claim:
        return claim_attendance(self.user, now=days_later(days), roll=always(roll))

    def test_the_first_claim_is_day_one_with_its_silver(self):
        claim = self.claim_on(0)

        self.assertEqual((claim.day, claim.cycle_day, claim.silver, claim.chest), (TODAY, 1, 140, None))
        row = AttendanceClaim.objects.get(user=self.user)
        self.assertEqual((row.day, row.cycle_day, row.silver, row.chest_silver), (TODAY, 1, 140, 0))
        self.assertEqual(row.status, WelcomeCreditStatus.PENDING)
        self.assertIsNone(row.chest_table)

    def test_the_same_day_twice_is_refused_and_writes_nothing(self):
        self.claim_on(0)

        with self.assertRaises(AttendanceAlreadyClaimedError):
            claim_attendance(self.user, now=NOON + timedelta(hours=11, minutes=59))

        self.assertEqual(AttendanceClaim.objects.filter(user=self.user).count(), 1)

    def test_a_week_in_a_row_ends_with_the_chest(self):
        claims = [self.claim_on(day, roll=9_800) for day in range(7)]

        self.assertEqual([claim.cycle_day for claim in claims], [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual([claim.silver for claim in claims], list(rules.DEFAULT_SCHEDULE))
        self.assertEqual([claim.chest is not None for claim in claims], [False] * 6 + [True])
        last = AttendanceClaim.objects.get(user=self.user, cycle_day=7)
        self.assertEqual((last.chest_table, last.chest_outcome, last.chest_silver), ('v1', 'dragon_hoard', 5_000))

    def test_the_day_after_the_chest_starts_a_new_cycle(self):
        for day in range(7):
            self.claim_on(day)

        self.assertEqual(self.claim_on(7).cycle_day, 1)

    def test_missing_a_day_starts_over(self):
        self.claim_on(0)
        self.claim_on(1)

        self.assertEqual(self.claim_on(3).cycle_day, 1)

    def test_an_empty_chest_is_written_too(self):
        for day in range(6):
            self.claim_on(day)

        claim = self.claim_on(6, roll=0)

        self.assertEqual(
            (claim.chest.table, claim.chest.outcome.id, claim.chest.outcome.silver), ('v1', 'mimic_bite', 0)
        )
        row = AttendanceClaim.objects.get(user=self.user, cycle_day=7)
        self.assertEqual((row.chest_outcome, row.chest_silver), ('mimic_bite', 0))

    def test_the_chest_is_rolled_only_on_its_day(self):
        rolls = []

        def counting() -> int:
            rolls.append(1)
            return 0

        for day in range(7):
            claim_attendance(self.user, now=days_later(day), roll=counting)

        self.assertEqual(len(rolls), 1)

    @override_settings(ATTENDANCE_SILVER=(50, 70))
    def test_the_setting_decides_the_cycle(self):
        claims = [self.claim_on(day) for day in range(3)]

        self.assertEqual([(claim.cycle_day, claim.silver) for claim in claims], [(1, 50), (2, 70), (1, 50)])
        self.assertEqual([claim.chest is not None for claim in claims], [False, True, False])

    def test_an_unverified_account_gets_nothing(self):
        stranger = make_user(2, verified=False)

        with self.assertRaises(AttendanceVerificationRequiredError):
            claim_attendance(stranger, now=NOON)

        self.assertFalse(AttendanceClaim.objects.filter(user=stranger).exists())

    def test_each_account_counts_on_its_own(self):
        other = make_user(2)
        self.claim_on(0)
        self.claim_on(1)

        self.assertEqual(claim_attendance(other, now=days_later(1)).cycle_day, 1)

    def test_a_row_written_past_the_lock_is_still_refused(self):
        # 잠금을 지나 같은 날의 줄이 이미 있는 경우다. 유일 제약이 막는다
        claimed_row(self.user)
        claim = Claim(day=TODAY, cycle_day=1, silver=140, chest=None)

        with self.assertRaises(AttendanceAlreadyClaimedError):
            _record(self.user, claim, NOON)

        self.assertEqual(AttendanceClaim.objects.filter(user=self.user).count(), 1)


class StatusTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_before_the_first_claim(self):
        current = attendance_status(self.user, now=NOON)

        self.assertEqual(
            (current.today, current.verified, current.claimed, current.cycle_day, current.silver, current.chest),
            (TODAY, True, False, 1, 140, False),
        )

    def test_after_claiming_it_shows_what_was_written(self):
        claim_attendance(self.user, now=NOON)

        with override_settings(ATTENDANCE_SILVER=(999, 999)):
            current = attendance_status(self.user, now=NOON)

        self.assertEqual((current.claimed, current.cycle_day, current.silver), (True, 1, 140))

    def test_the_next_day_shows_the_next_claim(self):
        for day in range(6):
            claim_attendance(self.user, now=days_later(day))

        current = attendance_status(self.user, now=days_later(6))

        self.assertEqual((current.claimed, current.cycle_day, current.silver, current.chest), (False, 7, 260, True))

    def test_an_unverified_account_is_not_an_error(self):
        current = attendance_status(make_user(2, verified=False), now=NOON)

        self.assertEqual((current.verified, current.claimed, current.cycle_day), (False, False, 1))


class AttendanceApiTests(APITestCase):
    def setUp(self):
        self.user = make_user()
        authorize(self.client, self.user)

    def test_status_of_today(self):
        response = self.client.get(ATTENDANCE_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['cycle_length'], 7)
        self.assertEqual(response.data['silver'], '140')
        self.assertIs(response.data['claimed'], False)
        self.assertIs(response.data['verified'], True)

    def test_claiming_answers_what_was_given(self):
        response = self.client.post(ATTENDANCE_URL)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['cycle_day'], 1)
        self.assertEqual(response.data['silver'], '140')
        self.assertIsNone(response.data['chest'])
        # 처음 받은 출석이라 활동 배지를 새로 받았다(#193)
        self.assertEqual(response.data['badges'], [{'id': 'first_attendance', 'name': '첫 출석'}])
        self.assertIs(self.client.get(ATTENDANCE_URL).data['claimed'], True)

    def test_the_chest_day_answers_the_chest(self):
        for day in range(6):
            claim_attendance(self.user, now=timezone.now() - timedelta(days=6 - day))

        # 뷰는 운영체제의 난수로 고른다. 그 출처를 정해진 수로 바꾼다
        with patch('accounts.attendance_rules.secrets.randbelow', return_value=3_000):
            response = self.client.post(ATTENDANCE_URL)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['cycle_day'], 7)
        self.assertEqual(
            response.data['chest'],
            {'table': 'v1', 'outcome': 'goblin_pouch', 'name': '고블린의 주머니', 'silver': '300'},
        )
        # 첫 출석은 앞에서 받았다. 이번에 새로 받은 것만 싣는다
        self.assertEqual(response.data['badges'], [{'id': 'attendance_cycle', 'name': '한 주기 완주'}])

    def test_claiming_twice_is_a_conflict_with_its_code(self):
        self.client.post(ATTENDANCE_URL)

        response = self.client.post(ATTENDANCE_URL)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['code'], 'attendance.already_claimed')

    def test_an_unverified_account_is_forbidden_with_its_code(self):
        authorize(self.client, make_user(2, verified=False))

        response = self.client.post(ATTENDANCE_URL)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'attendance.verification_required')
        self.assertIs(self.client.get(ATTENDANCE_URL).data['verified'], False)

    def test_needs_a_login(self):
        self.client.credentials()

        self.assertEqual(self.client.get(ATTENDANCE_URL).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.post(ATTENDANCE_URL).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(AttendanceClaim.objects.exists())

    def test_a_body_cannot_name_another_user(self):
        other = make_user(2)

        self.client.post(ATTENDANCE_URL, {'user': other.pk, 'user_id': str(other.public_id)}, format='json')

        self.assertEqual(list(AttendanceClaim.objects.values_list('user', flat=True)), [self.user.pk])


class RewardsApiTests(APITestCase):
    def test_anyone_sees_the_cycle_and_the_odds(self):
        response = self.client.get(REWARDS_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Cache-Control'], 'public, max-age=300')
        cycle = response.data['cycle']
        self.assertEqual([day['silver'] for day in cycle], ['140', '160', '180', '200', '220', '240', '260'])
        self.assertEqual([day['chest'] for day in cycle], [False] * 6 + [True])
        chest = response.data['chest']
        self.assertEqual((chest['table'], chest['scale'], chest['expected_silver']), ('v1', 10_000, '617'))
        self.assertEqual(sum(outcome['chance'] for outcome in chest['outcomes']), 10_000)
        self.assertEqual(
            chest['outcomes'][-1],
            {'outcome': 'dragon_hoard', 'name': '용의 보물', 'silver': '5000', 'chance': 300, 'percent': '3%'},
        )

    def test_a_broken_token_does_not_stop_it(self):
        self.client.credentials(HTTP_AUTHORIZATION='Bearer not-a-token')

        self.assertEqual(self.client.get(REWARDS_URL).status_code, status.HTTP_200_OK)


def billing_answers(*outcomes):
    """결제 서버가 차례로 이렇게 답하는 상황을 만든다. 예외를 넣으면 그 차례에 그 예외가 난다."""
    return patch('accounts.attendance.grant_attendance_silver', side_effect=list(outcomes))


class DeliveryTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_marks_the_row_with_what_the_billing_server_answered(self):
        granted = claimed_row(self.user, day=TODAY)
        again = claimed_row(self.user, day=TODAY + timedelta(days=1))

        with billing_answers(GRANTED, ALREADY_GRANTED):
            report = deliver_due_attendance()

        self.assertEqual((report.granted, report.skipped, report.retried), (1, 1, 0))
        granted.refresh_from_db()
        again.refresh_from_db()
        self.assertEqual(
            (granted.status, again.status), (WelcomeCreditStatus.GRANTED, WelcomeCreditStatus.ALREADY_GRANTED)
        )
        self.assertIsNotNone(granted.finished_at)

    def test_sends_the_day_the_silver_and_the_chest(self):
        claimed_row(
            self.user, cycle_day=7, silver=260, chest_table='v1', chest_outcome='goblin_pouch', chest_silver=300
        )

        with billing_answers(GRANTED) as client:
            deliver_due_attendance()

        client.assert_called_once_with(user_public_id=self.user.public_id, day=TODAY, silver=260, chest_silver=300)

    def test_finished_rows_are_not_delivered_again(self):
        claimed_row(self.user)
        with billing_answers(GRANTED):
            deliver_due_attendance()

        with billing_answers() as client:
            report = deliver_due_attendance()

        client.assert_not_called()
        self.assertEqual(report.handled, 0)

    def test_a_failure_waits_and_is_retried_later(self):
        row = claimed_row(self.user)
        down = BillingUnavailableError('결제 서버가 404 로 답했다')

        with billing_answers(down), self.assertLogs('accounts.attendance', level='WARNING') as logs:
            report = deliver_due_attendance()

        self.assertEqual(report.retried, 1)
        row.refresh_from_db()
        self.assertEqual((row.status, row.attempts, row.last_error), (WelcomeCreditStatus.PENDING, 1, str(down)))
        self.assertGreater(row.next_attempt_at, timezone.now())
        self.assertNotIn(str(self.user.public_id), logs.output[0])
        # 아직 때가 아니다
        with billing_answers() as client:
            deliver_due_attendance()
        client.assert_not_called()

    def test_rows_that_are_not_due_yet_wait(self):
        claimed_row(self.user, next_attempt_at=timezone.now() + timedelta(minutes=1))

        with billing_answers() as client:
            deliver_due_attendance()

        client.assert_not_called()


@override_settings(BILLING_SECRET=SECRET)
class WorkerCommandTests(TestCase):
    def test_the_worker_reports_attendance(self):
        claimed_row(make_user())

        with BillingStub() as stub, override_settings(BILLING_URL=stub.url):
            output = StringIO()
            call_command('send_welcome_credits', '--once', stdout=output)

        self.assertIn('출석 실버 지급 1건, 이미 받음 0건, 다시 시도 예정 0건', output.getvalue())
        self.assertEqual([request.path for request in stub.requests], [ATTENDANCE_PATH])


class BillingRequestTests(SimpleTestCase):
    USER_ID = uuid.UUID('11111111-2222-4333-8444-555555555555')

    def grant(self, stub: BillingStub) -> str:
        with override_settings(BILLING_URL=stub.url, BILLING_SECRET=SECRET):
            return grant_attendance_silver(user_public_id=self.USER_ID, day=TODAY, silver=260, chest_silver=300)

    def test_posts_the_day_and_the_amounts_as_text(self):
        with BillingStub() as stub:
            outcome = self.grant(stub)

        self.assertEqual(outcome, GRANTED)
        request = stub.requests[0]
        self.assertEqual((request.method, request.path), ('POST', ATTENDANCE_PATH))
        self.assertEqual(
            json.loads(request.body),
            {'user_id': str(self.USER_ID), 'day': '2026-11-08', 'silver': '260', 'chest_silver': '300'},
        )
        self.assertTrue(request.has_valid_signature())

    def test_already_granted_is_finished_too(self):
        answer = b'{"status":"already_granted","granted":"0","expires_at":null}'
        with BillingStub(status_code=200, body=answer) as stub:
            self.assertEqual(self.grant(stub), ALREADY_GRANTED)

    def test_an_old_billing_server_means_try_again_later(self):
        for code in (404, 400, 500):
            with (
                self.subTest(code=code),
                BillingStub(status_code=code, body=b'{}') as stub,
                self.assertRaises(BillingUnavailableError),
            ):
                self.grant(stub)

    def test_a_disabled_answer_is_not_trusted(self):
        answer = b'{"status":"disabled","granted":"0","expires_at":null}'
        with BillingStub(status_code=200, body=answer) as stub, self.assertRaises(BillingUnavailableError):
            self.grant(stub)


class ConcurrentClaimTests(TransactionTestCase):
    """두 요청이 함께 와도 하루에 한 줄이다. 계정의 줄을 잠가 차례로 지나간다."""

    def test_two_claims_at_once_write_one_row(self):
        user = make_user()
        results: list[str] = []
        barrier = threading.Barrier(2)

        def claim() -> None:
            barrier.wait()
            try:
                claim_attendance(user, now=NOON)
                results.append('claimed')
            except AttendanceAlreadyClaimedError:
                results.append('refused')
            finally:
                connection.close()

        threads = [threading.Thread(target=claim) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(sorted(results), ['claimed', 'refused'])
        self.assertEqual(AttendanceClaim.objects.filter(user=user).count(), 1)
