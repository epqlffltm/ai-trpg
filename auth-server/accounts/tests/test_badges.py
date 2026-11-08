# auth-server/accounts/tests/test_badges.py

"""
활동 배지(#193)를 검증한다. 규칙, 한 번만 주기, 출석·본인인증·초대 보상과 함께 주기, 주소, 있던 기록으로 채우기.
"""

import importlib
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from django.apps import apps
from django.db import transaction
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts import badge_rules as rules
from accounts.attendance import AttendanceVerificationRequiredError, claim_attendance
from accounts.badges import award, my_badges
from accounts.identity import person_key
from accounts.invite_rewards import request_invite_reward
from accounts.models import AttendanceClaim, IdentityVerification, Invitation, User, UserBadge
from accounts.tests.helpers import authorize, verify_identity

PASSWORD = 'correct-horse-battery'
BADGES_URL = '/api/v1/auth/me/badges'
# 2026-11-08 낮 12시(한국)
NOON = datetime(2026, 11, 8, 3, 0, tzinfo=UTC)


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


def badges_of(user: User) -> set[str]:
    return set(UserBadge.objects.filter(user=user).values_list('badge', flat=True))


def always(n: int):
    return lambda: n


class RuleTests(SimpleTestCase):
    def facts(self, total_days: int = 1, opened_chest: bool = False, chest_outcome: str | None = None):
        return rules.AttendanceFacts(total_days=total_days, opened_chest=opened_chest, chest_outcome=chest_outcome)

    def test_the_first_day_is_the_first_attendance(self):
        self.assertEqual(rules.attendance_badges(self.facts()), (rules.FIRST_ATTENDANCE,))

    def test_the_chest_day_completes_a_cycle(self):
        badges = rules.attendance_badges(self.facts(total_days=7, opened_chest=True, chest_outcome='goblin_pouch'))
        self.assertIn(rules.ATTENDANCE_CYCLE, badges)
        self.assertNotIn(rules.DRAGON_HOARD, badges)

    def test_the_dragon_hoard_has_its_own_badge(self):
        badges = rules.attendance_badges(self.facts(total_days=7, opened_chest=True, chest_outcome='dragon_hoard'))
        self.assertIn(rules.DRAGON_HOARD, badges)

    def test_thirty_days_in_all(self):
        self.assertNotIn(rules.ATTENDANCE_30_DAYS, rules.attendance_badges(self.facts(total_days=29)))
        self.assertIn(rules.ATTENDANCE_30_DAYS, rules.attendance_badges(self.facts(total_days=30)))

    def test_the_list_is_valid(self):
        rules.validate_badges(rules.BADGES)
        self.assertEqual(len(rules.BADGE_IDS), len(rules.BADGES))

    def test_refuses_a_list_with_repeated_names(self):
        twice = (rules.Badge('a', '가', ''), rules.Badge('a', '나', ''))
        with self.assertRaises(ValueError):
            rules.validate_badges(twice)

    def test_refuses_a_dragon_badge_the_chest_cannot_give(self):
        with patch.object(rules, 'DRAGON_HOARD_OUTCOME', 'unicorn'), self.assertRaises(ValueError):
            rules.validate_badges(rules.BADGES)


class AwardTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_gives_a_badge_once(self):
        self.assertTrue(award(self.user, rules.FIRST_INVITE, NOON))
        self.assertFalse(award(self.user, rules.FIRST_INVITE, NOON + timedelta(days=1)))

        row = UserBadge.objects.get(user=self.user)
        self.assertEqual((row.badge, row.earned_at), (rules.FIRST_INVITE, NOON))

    def test_refuses_an_unknown_badge(self):
        with self.assertRaises(ValueError):
            award(self.user, 'unknown', NOON)
        self.assertFalse(UserBadge.objects.exists())

    def test_a_badge_written_meanwhile_does_not_break_the_callers_transaction(self):
        # 다른 요청이 먼저 적은 경우다. 확인을 지나 유일 제약에 걸린다
        UserBadge.objects.create(user=self.user, badge=rules.FIRST_INVITE, earned_at=NOON)
        with transaction.atomic():
            with patch('accounts.badges.UserBadge.objects.filter') as filtered:
                filtered.return_value.exists.return_value = False
                self.assertFalse(award(self.user, rules.FIRST_INVITE, NOON))
            # 부르는 쪽의 트랜잭션은 그대로 쓸 수 있다
            self.assertEqual(UserBadge.objects.filter(user=self.user).count(), 1)

    def test_my_badges_lists_every_badge_in_order(self):
        award(self.user, rules.IDENTITY_VERIFIED, NOON)
        UserBadge.objects.create(user=self.user, badge='retired_badge', earned_at=NOON)

        states = my_badges(self.user)

        self.assertEqual([state.badge.id for state in states], [badge.id for badge in rules.BADGES])
        earned = {state.badge.id: state.earned_at for state in states if state.earned_at}
        self.assertEqual(earned, {rules.IDENTITY_VERIFIED: NOON})


class AttendanceBadgeTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def claim_on(self, day: int, roll: int = 0):
        return claim_attendance(self.user, now=NOON + timedelta(days=day), roll=always(roll))

    def test_the_first_claim_gives_the_first_attendance(self):
        self.claim_on(0)

        self.assertEqual(badges_of(self.user), {rules.FIRST_ATTENDANCE})
        self.assertEqual(UserBadge.objects.get(user=self.user).earned_at, NOON)

    def test_a_full_week_gives_the_cycle_and_a_dragon_its_badge(self):
        for day in range(7):
            self.claim_on(day, roll=9_800)

        self.assertEqual(badges_of(self.user), {rules.FIRST_ATTENDANCE, rules.ATTENDANCE_CYCLE, rules.DRAGON_HOARD})

    def test_an_ordinary_chest_gives_no_dragon(self):
        for day in range(7):
            self.claim_on(day, roll=0)

        self.assertNotIn(rules.DRAGON_HOARD, badges_of(self.user))

    def test_thirty_days_with_gaps_still_count(self):
        # 이틀에 한 번 출석한다. 주기는 늘 1일째라 상자는 열리지 않는다
        for n in range(30):
            self.claim_on(n * 2)

        self.assertEqual(badges_of(self.user), {rules.FIRST_ATTENDANCE, rules.ATTENDANCE_30_DAYS})
        badge = UserBadge.objects.get(user=self.user, badge=rules.ATTENDANCE_30_DAYS)
        self.assertEqual(badge.earned_at, NOON + timedelta(days=58))

    def test_a_refused_claim_gives_nothing(self):
        stranger = make_user(2, verified=False)

        with self.assertRaises(AttendanceVerificationRequiredError):
            claim_attendance(stranger, now=NOON)

        self.assertFalse(UserBadge.objects.filter(user=stranger).exists())


class IdentityBadgeTests(APITestCase):
    def test_verifying_gives_the_badge(self):
        user = make_user(1, verified=False)
        authorize(self.client, user)

        self.assertEqual(verify_identity(self.client).status_code, status.HTTP_201_CREATED)

        self.assertEqual(badges_of(user), {rules.IDENTITY_VERIFIED})

    def test_a_refused_verification_gives_nothing(self):
        make_user(1)  # person-1 은 이미 이 계정의 사람이다
        other = make_user(2, verified=False)
        authorize(self.client, other)

        response = verify_identity(self.client)

        self.assertNotEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(UserBadge.objects.filter(user=other).exists())


class InviteBadgeTests(TestCase):
    def test_the_inviter_gets_the_badge_when_rewarded(self):
        inviter = make_user(1)
        invitee = make_user(2, verified=False)
        Invitation.objects.create(invitee=invitee, inviter_public_id=inviter.public_id)

        reward = request_invite_reward(invitee=invitee, invitee_key=person_key('person-2'))

        self.assertIsNotNone(reward)
        self.assertEqual(badges_of(inviter), {rules.FIRST_INVITE})
        self.assertEqual(badges_of(invitee), set())

    def test_no_reward_no_badge(self):
        inviter = make_user(1, verified=False)
        invitee = make_user(2, verified=False)
        Invitation.objects.create(invitee=invitee, inviter_public_id=inviter.public_id)

        self.assertIsNone(request_invite_reward(invitee=invitee, invitee_key=person_key('person-2')))
        self.assertFalse(UserBadge.objects.exists())


class BadgesApiTests(APITestCase):
    def test_lists_every_badge_with_what_i_earned(self):
        user = make_user()
        award(user, rules.FIRST_ATTENDANCE, NOON)
        authorize(self.client, user)

        response = self.client.get(BADGES_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['earned'], 1)
        self.assertEqual([badge['id'] for badge in response.data['badges']], [badge.id for badge in rules.BADGES])
        first = response.data['badges'][0]
        self.assertEqual((first['id'], first['name']), (rules.FIRST_ATTENDANCE, '첫 출석'))
        self.assertIsNotNone(first['earned_at'])
        self.assertIsNone(response.data['badges'][1]['earned_at'])

    def test_shows_only_my_badges(self):
        other = make_user(2)
        award(other, rules.FIRST_ATTENDANCE, NOON)
        authorize(self.client, make_user(1))

        self.assertEqual(self.client.get(BADGES_URL).data['earned'], 0)

    def test_needs_a_login(self):
        self.assertEqual(self.client.get(BADGES_URL).status_code, status.HTTP_401_UNAUTHORIZED)


class FillFromRecordsTests(TestCase):
    """마이그레이션이 이미 있는 기록으로 받았어야 할 배지를 채운다."""

    def fill(self) -> None:
        migration = importlib.import_module('accounts.migrations.0038_user_badges')
        migration.fill_badges(apps, None)

    def claim(self, user: User, day: int, **fields) -> AttendanceClaim:
        values = {'cycle_day': 1, 'silver': 140, 'next_attempt_at': NOON, **fields}
        claim = AttendanceClaim.objects.create(user=user, day=NOON.date() + timedelta(days=day), **values)
        AttendanceClaim.objects.filter(pk=claim.pk).update(created_at=NOON + timedelta(days=day))
        return claim

    def test_fills_from_identity_invites_and_attendance(self):
        user = make_user(1)
        invitee = make_user(2)
        Invitation.objects.create(invitee=invitee, inviter_public_id=user.public_id)
        request_invite_reward(invitee=invitee, invitee_key=person_key('person-2'))
        for day in range(30):
            self.claim(user, day)
        self.claim(user, 30, cycle_day=7, chest_table='v1', chest_outcome='dragon_hoard', chest_silver=5000)
        UserBadge.objects.all().delete()

        self.fill()

        self.assertEqual(
            badges_of(user),
            {
                rules.IDENTITY_VERIFIED,
                rules.FIRST_INVITE,
                rules.FIRST_ATTENDANCE,
                rules.ATTENDANCE_CYCLE,
                rules.ATTENDANCE_30_DAYS,
                rules.DRAGON_HOARD,
            },
        )
        self.assertEqual(badges_of(invitee), {rules.IDENTITY_VERIFIED})
        earned = dict(UserBadge.objects.filter(user=user).values_list('badge', 'earned_at'))
        self.assertEqual(earned[rules.FIRST_ATTENDANCE], NOON)
        self.assertEqual(earned[rules.ATTENDANCE_30_DAYS], NOON + timedelta(days=29))
        self.assertEqual(earned[rules.DRAGON_HOARD], NOON + timedelta(days=30))

    def test_filling_twice_changes_nothing(self):
        user = make_user(1)
        self.fill()
        self.fill()

        self.assertEqual(UserBadge.objects.filter(user=user).count(), 1)
