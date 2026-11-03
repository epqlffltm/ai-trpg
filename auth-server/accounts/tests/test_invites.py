# auth-server/accounts/tests/test_invites.py

"""
초대 코드와 초대 보상을 검증한다(#990).

  - 코드: 계정마다 하나, 처음 물을 때 만든다. 헷갈리는 글자가 없다
  - 가입: 적은 코드의 주인을 초대한 사람으로 적는다. 없는 코드와 막힌 계정의 코드는 그 칸의 오류다
  - 보상: 초대받은 사람이 본인인증을 마칠 때 정한다. 사람마다 한 번 받고, 초대한 사람은 상한까지 받는다
  - 맡기기: 결제 서버에 두 사람의 지급을 맡기고, 실패하면 다시 맡긴다
"""

import json
import uuid
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.billing_client import ALREADY_GRANTED, GRANTED, INVITE_PATH, BillingUnavailableError
from accounts.identity import person_key
from accounts.invite_grants import deliver_due_invite_grants
from accounts.invite_rewards import request_invite_reward, rewarded_count
from accounts.invites import (
    INVITE_CODE_ALPHABET,
    INVITE_CODE_LENGTH,
    find_inviter,
    my_invite_code,
    normalize_invite_code,
)
from accounts.models import (
    IdentityVerification,
    Invitation,
    InviteCode,
    InviteGrant,
    InviteGrantRole,
    InviteReward,
    User,
    WelcomeCreditStatus,
)
from accounts.tests.billing_stub import SECRET, BillingStub
from accounts.tests.helpers import (
    authorize,
    complete_signup,
    identity_token,
    request_signup_ticket,
    verify_identity,
)
from accounts.welcome_credit import FIRST_RETRY_DELAY

MY_INVITE_URL = reverse('accounts:my-invite')
PASSWORD = 'correct-horse-battery'


def make_user(number: int, *, active: bool = True) -> User:
    """계정 하나. number 로 아이디와 닉네임이 겹치지 않게 한다."""
    return User.objects.create_user(
        username=f'player_{number:02d}',
        email=f'player{number}@example.com',
        nickname=f'플레이어{number}',
        password=PASSWORD,
        email_verified_at=timezone.now(),
        is_active=active,
    )


def sign_up_with(client, number: int, invite_code: str):
    """가입의 세 단계를 지나며 3단계에 초대 코드를 적는다."""
    ticket = request_signup_ticket(client, f'player{number}@example.com')
    return complete_signup(
        client,
        ticket,
        username=f'player_{number:02d}',
        nickname=f'플레이어{number}',
        password=PASSWORD,
        invite_code=invite_code,
    )


def verified(client, user: User, di: str) -> None:
    """그 계정으로 본인인증을 마친다."""
    authorize(client, user)
    response = verify_identity(client, identity_token(di))
    assert response.status_code == status.HTTP_201_CREATED, response.data
    client.credentials()


def invited(invitee: User, inviter: User) -> Invitation:
    """invitee 를 inviter 가 초대한 것으로 적는다."""
    return Invitation.objects.create(invitee=invitee, inviter_public_id=inviter.public_id)


class InviteCodeTests(TestCase):
    def test_a_code_is_made_once_and_kept(self):
        user = make_user(1)

        first = my_invite_code(user)
        second = my_invite_code(user)

        self.assertEqual(first.code, second.code)
        self.assertEqual(InviteCode.objects.count(), 1)
        self.assertEqual(len(first.code), INVITE_CODE_LENGTH)
        self.assertTrue(set(first.code) <= set(INVITE_CODE_ALPHABET))

    def test_the_alphabet_has_no_confusing_letters(self):
        self.assertFalse(set('0O1IL') & set(INVITE_CODE_ALPHABET))

    def test_a_colliding_code_is_made_again(self):
        other = make_user(1)
        InviteCode.objects.create(user=other, code='AAAAAAAA')
        user = make_user(2)

        with patch('accounts.invites.new_invite_code', side_effect=['AAAAAAAA', 'BBBBBBBB']):
            code = my_invite_code(user)

        self.assertEqual(code.code, 'BBBBBBBB')

    def test_codes_are_read_without_case_spaces_or_hyphens(self):
        self.assertEqual(normalize_invite_code(' abcd-efgh '), 'ABCDEFGH')

    def test_finds_the_owner(self):
        user = make_user(1)
        code = my_invite_code(user).code

        self.assertEqual(find_inviter(code.lower()), user.public_id)


class MyInviteApiTests(APITestCase):
    def test_needs_login(self):
        self.assertEqual(self.client.get(MY_INVITE_URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_shows_my_code_and_what_i_received(self):
        user = make_user(1)
        authorize(self.client, user)

        response = self.client.get(MY_INVITE_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {'code': user.invite_code.code, 'rewarded': 0, 'limit': 5})

    @override_settings(INVITE_REWARD_LIMIT=2)
    def test_counts_rewards_by_person(self):
        inviter = make_user(1)
        verified(self.client, inviter, 'person-1')
        InviteReward.objects.create(
            invitee_key=person_key('person-2'),
            inviter_key=person_key('person-1'),
            invitee_public_id=uuid.uuid4(),
            inviter_public_id=inviter.public_id,
        )
        authorize(self.client, inviter)

        response = self.client.get(MY_INVITE_URL)

        self.assertEqual((response.data['rewarded'], response.data['limit']), (1, 2))


class SignupWithInviteTests(APITestCase):
    def test_records_who_invited(self):
        inviter = make_user(1)
        code = my_invite_code(inviter).code

        response = sign_up_with(self.client, 2, code.lower())

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        invitee = User.objects.get(username='player_02')
        self.assertEqual(invitee.invitation.inviter_public_id, inviter.public_id)

    def test_an_empty_code_invites_nobody(self):
        response = sign_up_with(self.client, 2, '  ')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertFalse(Invitation.objects.exists())

    def test_an_unknown_code_is_a_field_error_and_makes_no_account(self):
        response = sign_up_with(self.client, 2, 'ZZZZZZZZ')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('invite_code', response.data['errors'])
        self.assertFalse(User.objects.filter(username='player_02').exists())

    def test_the_code_of_a_closed_account_is_refused(self):
        inviter = make_user(1)
        code = my_invite_code(inviter).code
        User.objects.filter(pk=inviter.pk).update(is_active=False)

        response = sign_up_with(self.client, 2, code)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('invite_code', response.data['errors'])

    def test_a_too_long_code_is_refused(self):
        response = sign_up_with(self.client, 2, 'A' * 21)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('invite_code', response.data['errors'])


class RewardOnIdentityTests(APITestCase):
    """본인인증의 API 를 지나며 보상이 정해지는지 본다."""

    def test_both_get_a_grant_when_the_invitee_verifies(self):
        inviter, invitee = make_user(1), make_user(2)
        verified(self.client, inviter, 'person-1')
        invited(invitee, inviter)

        verified(self.client, invitee, 'person-2')

        reward = InviteReward.objects.get()
        self.assertEqual((reward.inviter_key, reward.invitee_key), (person_key('person-1'), person_key('person-2')))
        grants = {grant.role: grant.user_public_id for grant in InviteGrant.objects.all()}
        self.assertEqual(
            grants, {InviteGrantRole.INVITER: inviter.public_id, InviteGrantRole.INVITEE: invitee.public_id}
        )

    def test_no_reward_without_an_invitation(self):
        verified(self.client, make_user(1), 'person-1')

        self.assertFalse(InviteReward.objects.exists())

    def test_no_reward_while_the_inviter_has_not_verified(self):
        inviter, invitee = make_user(1), make_user(2)
        invited(invitee, inviter)

        verified(self.client, invitee, 'person-2')

        self.assertFalse(InviteReward.objects.exists())


class RewardRuleTests(TestCase):
    """규칙을 하나씩 본다. 사람 열쇠를 직접 넣는다."""

    def setUp(self):
        self.inviter = make_user(1)
        # 초대한 계정의 본인인증. API 를 지나지 않고 기록만 둔다
        IdentityVerification.objects.create(
            user=self.inviter, person_key=person_key('person-1'), provider='fake', verified_at=timezone.now()
        )

    def reward_for(self, number: int, di: str | None = None):
        invitee = make_user(number)
        invited(invitee, self.inviter)
        return request_invite_reward(invitee=invitee, invitee_key=person_key(di or f'person-{number}'))

    def test_the_same_person_is_rewarded_as_an_invitee_once(self):
        # 계정을 지우고 새 계정으로 다시 가입해 인증한 경우다. 사람 열쇠가 같다
        self.assertIsNotNone(self.reward_for(2, 'person-2'))

        self.assertIsNone(self.reward_for(3, 'person-2'))
        self.assertEqual(InviteReward.objects.count(), 1)

    def test_inviting_yourself_is_not_rewarded(self):
        self.assertIsNone(self.reward_for(2, 'person-1'))

    @override_settings(INVITE_REWARD_LIMIT=2)
    def test_the_inviter_is_rewarded_up_to_the_limit(self):
        self.assertIsNotNone(self.reward_for(2))
        self.assertIsNotNone(self.reward_for(3))

        self.assertIsNone(self.reward_for(4))
        self.assertEqual(rewarded_count(self.inviter), 2)

    @override_settings(INVITE_REWARD_LIMIT=0)
    def test_a_limit_of_zero_turns_rewards_off(self):
        self.assertIsNone(self.reward_for(2))

    def test_no_reward_when_the_inviter_is_closed(self):
        User.objects.filter(pk=self.inviter.pk).update(is_active=False)

        self.assertIsNone(self.reward_for(2))

    def test_no_reward_when_the_inviter_is_gone(self):
        invitee = make_user(2)
        Invitation.objects.create(invitee=invitee, inviter_public_id=uuid.uuid4())

        self.assertIsNone(request_invite_reward(invitee=invitee, invitee_key=person_key('person-2')))


def pending_grant(role: str = InviteGrantRole.INVITEE) -> InviteGrant:
    """맡기기 전인 지급 한 줄."""
    reward = InviteReward.objects.create(
        invitee_key=person_key(f'person-{uuid.uuid4()}'),
        inviter_key=person_key('person-1'),
        invitee_public_id=uuid.uuid4(),
        inviter_public_id=uuid.uuid4(),
    )
    return InviteGrant.objects.create(
        reward=reward, role=role, user_public_id=reward.invitee_public_id, next_attempt_at=timezone.now()
    )


def billing_answers(*outcomes):
    """결제 서버가 차례로 이렇게 답하는 상황. 예외를 넣으면 그 차례에 그 예외가 난다."""
    return patch('accounts.invite_grants.grant_invite_credit', side_effect=list(outcomes))


class DeliveryTests(TestCase):
    def test_records_what_the_billing_server_answered(self):
        granted, already = pending_grant(), pending_grant(InviteGrantRole.INVITER)

        with billing_answers(GRANTED, ALREADY_GRANTED):
            report = deliver_due_invite_grants()

        granted.refresh_from_db()
        already.refresh_from_db()
        self.assertEqual((report.granted, report.skipped), (1, 1))
        self.assertEqual((granted.status, already.status), (GRANTED, ALREADY_GRANTED))

    def test_a_failure_is_tried_again_later(self):
        claim = pending_grant()

        with (
            billing_answers(BillingUnavailableError('결제 서버가 503 로 답했다')),
            self.assertLogs('accounts.invite_grants', level='WARNING'),
        ):
            report = deliver_due_invite_grants()

        claim.refresh_from_db()
        self.assertEqual(report.retried, 1)
        self.assertEqual((claim.status, claim.attempts), (WelcomeCreditStatus.PENDING, 1))
        self.assertGreater(claim.next_attempt_at, timezone.now())

    def test_the_worker_reports_invite_grants(self):
        pending_grant()

        with billing_answers(GRANTED), patch('accounts.welcome_credit.grant_welcome_credit'):
            output = StringIO()
            with override_settings(BILLING_SECRET=SECRET):
                call_command('send_welcome_credits', '--once', stdout=output)

        self.assertIn('초대 보상 지급 1건, 주지 않음 0건, 다시 시도 예정 0건', output.getvalue())


class EndToEndTests(APITestCase):
    """가짜를 끼우지 않는다. 본인인증부터 결제 서버가 받는 요청까지 지난다."""

    def test_the_billing_server_receives_two_signed_grants(self):
        inviter, invitee = make_user(1), make_user(2)
        verified(self.client, inviter, 'person-1')
        invited(invitee, inviter)
        verified(self.client, invitee, 'person-2')

        with BillingStub() as stub, override_settings(BILLING_URL=stub.url, BILLING_SECRET=SECRET):
            deliver_due_invite_grants()
            # 다시 돌려도 또 부르지 않는다
            deliver_due_invite_grants()

        requests = [request for request in stub.requests if request.path == INVITE_PATH]
        self.assertEqual(len(requests), 2)
        self.assertTrue(all(request.has_valid_signature() for request in requests))
        bodies = sorted((json.loads(request.body) for request in requests), key=lambda body: body['role'])
        reward = InviteReward.objects.get()
        self.assertEqual(
            bodies,
            [
                {'user_id': str(invitee.public_id), 'reward_id': str(reward.id), 'role': 'invitee'},
                {'user_id': str(inviter.public_id), 'reward_id': str(reward.id), 'role': 'inviter'},
            ],
        )
        # 사람 열쇠는 결제 서버에 보내지 않는다
        self.assertFalse(any(person_key('person-1').encode() in request.body for request in requests))
        self.assertTrue(all(grant.status == GRANTED for grant in InviteGrant.objects.all()))

    def test_a_dead_billing_server_only_delays_the_grant(self):
        claim = pending_grant()

        with (
            BillingStub(status_code=503, body=b'') as stub,
            override_settings(BILLING_URL=stub.url, BILLING_SECRET=SECRET),
        ):
            with self.assertLogs('accounts.invite_grants', level='WARNING'):
                deliver_due_invite_grants()
            stub.status_code = 201
            stub.body = b'{"status":"granted","granted":"500","expires_at":"2026-03-09T09:00:00Z"}'
            with patch('accounts.invite_grants.timezone.now', return_value=timezone.now() + FIRST_RETRY_DELAY):
                deliver_due_invite_grants()

        claim.refresh_from_db()
        self.assertEqual(claim.status, GRANTED)
