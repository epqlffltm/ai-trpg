# auth-server/support/tests/test_inquiries.py

"""
문의(고객센터)를 시험한다.

  - 보내기: 로그인하지 않았으면 적은 주소로, 로그인했으면 계정의 주소로 답한다. 로그인하지 않았는데 주소가 없으면 400
  - 보내기의 IP 시도 제한: 한 시간에 다섯 번까지
  - 내 문의: 내 것만, 최근 것부터 한 쪽씩, 답이 보인다
  - 운영자의 목록: 로그인하지 않았으면 401, 운영자가 아니면 404(운영자 주소를 드러내지 않는다),
    상태로 고르고 보낸 계정과 주소가 보인다
  - 답: 한 번만 쓰고 문의의 주소로 메일을 보내며 보낸 기록이 남는다. 없는 문의는 404, 이미 답했으면 409
  - 계정을 비우면(탈퇴) 그 사람의 문의를 지운다
  - 메일함처럼: 상자마다의 수, 하나를 열면 읽음(처음 한 번만 적는다)
  - 지우기: 하나, 고른 것, 상자 하나를 통째로. 운영자만. 보관 기간(1년)이 지난 것은 정리 명령이 지운다
"""

import io
import uuid
from datetime import timedelta

from django.contrib.auth.models import Group
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.erasure import blank_account
from accounts.models import MailKind, OutgoingMail, SecurityEvent, SecurityEventKind, User
from accounts.roles import OPERATORS_GROUP
from accounts.tests.helpers import authorize, delete_attempt_keys, reset_redis_breaker
from support.inquiries import PAGE_SIZE
from support.models import Inquiry, InquiryStatus

DELETE_URL = reverse('support:operator-inquiries-delete')
INQUIRIES_URL = reverse('support:inquiries')
MY_INQUIRIES_URL = reverse('support:my-inquiries')
OPERATOR_INQUIRIES_URL = reverse('support:operator-inquiries')
PASSWORD = 'correct-horse-battery'


def inquiry_url(inquiry_id) -> str:
    return reverse('support:operator-inquiry', args=[inquiry_id])


def reply_url(inquiry_id) -> str:
    return reverse('support:operator-inquiry-reply', args=[inquiry_id])


def make_user(number: int, *, operator: bool = False) -> User:
    user = User.objects.create_user(
        username=f'player_{number:02d}',
        email=f'player{number}@example.com',
        nickname=f'플레이어{number}',
        password=PASSWORD,
        email_verified_at=timezone.now(),
    )
    if operator:
        user.groups.add(Group.objects.get(name=OPERATORS_GROUP))
    return user


def inquiry_body(**extra) -> dict:
    return {'category': 'account', 'title': '로그인이 안 돼요', 'body': '코드 메일이 오지 않습니다.', **extra}


def make_inquiry(user: User | None = None, **fields) -> Inquiry:
    defaults = {
        'category': 'bug',
        'title': '화면이 멈춰요',
        'body': '테이블 방에서 멈춥니다.',
        'email': 'guest@example.com',
    }
    return Inquiry.objects.create(user=user, **{**defaults, **fields})


class SubmitTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_a_guest_sends_with_an_address_to_reply_to(self):
        response = self.client.post(INQUIRIES_URL, inquiry_body(email='guest@example.com'), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        inquiry = Inquiry.objects.get(pk=response.data['id'])
        self.assertIsNone(inquiry.user)
        self.assertEqual(inquiry.email, 'guest@example.com')
        self.assertEqual(inquiry.status, InquiryStatus.OPEN)

    def test_a_guest_without_an_address_is_refused(self):
        response = self.client.post(INQUIRIES_URL, inquiry_body(), format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data['errors'])
        self.assertFalse(Inquiry.objects.exists())

    def test_a_signed_in_person_is_answered_at_the_account_address(self):
        user = make_user(1)
        authorize(self.client, user)

        response = self.client.post(INQUIRIES_URL, inquiry_body(email='other@example.com'), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        inquiry = Inquiry.objects.get(pk=response.data['id'])
        self.assertEqual((inquiry.user, inquiry.email), (user, 'player1@example.com'))

    def test_wrong_fields_are_refused(self):
        for case, body in {
            'category': inquiry_body(category='love', email='guest@example.com'),
            'title': inquiry_body(title='가' * 101, email='guest@example.com'),
            'body': inquiry_body(body='', email='guest@example.com'),
            'email': inquiry_body(email='not-an-address'),
        }.items():
            with self.subTest(case):
                response = self.client.post(INQUIRIES_URL, body, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(case, response.data['errors'])


@override_settings(ATTEMPT_LIMITS_ENABLED=True, TRUSTED_PROXY_COUNT=0)
class SubmitLimitTests(TestCase):
    def setUp(self):
        delete_attempt_keys()
        reset_redis_breaker()
        self.addCleanup(delete_attempt_keys)
        self.addCleanup(reset_redis_breaker)

    def test_one_address_sends_five_an_hour(self):
        client = APIClient()
        for _ in range(5):
            self.assertEqual(
                client.post(INQUIRIES_URL, inquiry_body(email='guest@example.com'), format='json').status_code,
                status.HTTP_201_CREATED,
            )

        response = client.post(INQUIRIES_URL, inquiry_body(email='guest@example.com'), format='json')

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(Inquiry.objects.count(), 5)
        self.assertTrue(SecurityEvent.objects.filter(kind=SecurityEventKind.INQUIRY_IP_LIMITED).exists())


class MyInquiriesTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user(1)
        authorize(self.client, self.user)

    def test_only_mine_newest_first_with_the_reply(self):
        older = make_inquiry(self.user, title='처음')
        newer = make_inquiry(self.user, title='나중', status=InquiryStatus.ANSWERED, reply='고쳤습니다.')
        Inquiry.objects.filter(pk=newer.pk).update(
            answered_at=timezone.now(), created_at=older.created_at + timedelta(minutes=1)
        )
        make_inquiry(make_user(2), title='남의 것')
        make_inquiry(None, title='손님의 것')

        response = self.client.get(MY_INQUIRIES_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['title'] for item in response.data['items']], ['나중', '처음'])
        self.assertEqual(response.data['items'][0]['reply'], '고쳤습니다.')
        self.assertIsNone(response.data['items'][1]['answered_at'])
        self.assertIsNone(response.data['next_before'])
        self.assertNotIn('email', response.data['items'][0])

    def test_pages_go_back_with_before(self):
        start = timezone.now() - timedelta(days=1)
        for minute in range(PAGE_SIZE + 1):
            inquiry = make_inquiry(self.user, title=f'문의 {minute}')
            Inquiry.objects.filter(pk=inquiry.pk).update(created_at=start + timedelta(minutes=minute))

        first = self.client.get(MY_INQUIRIES_URL)
        second = self.client.get(MY_INQUIRIES_URL, {'before': first.data['next_before']})

        self.assertEqual(len(first.data['items']), PAGE_SIZE)
        self.assertEqual(first.data['items'][0]['title'], f'문의 {PAGE_SIZE}')
        self.assertEqual([item['title'] for item in second.data['items']], ['문의 0'])
        self.assertIsNone(second.data['next_before'])

    def test_signing_in_is_needed(self):
        self.assertEqual(APIClient().get(MY_INQUIRIES_URL).status_code, status.HTTP_401_UNAUTHORIZED)


class OperatorListTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_only_operators_see_the_list(self):
        self.assertEqual(self.client.get(OPERATOR_INQUIRIES_URL).status_code, status.HTTP_401_UNAUTHORIZED)
        authorize(self.client, make_user(1))
        self.assertEqual(self.client.get(OPERATOR_INQUIRIES_URL).status_code, status.HTTP_404_NOT_FOUND)

    def test_operators_choose_by_status_and_see_who_sent_it(self):
        sender = make_user(1)
        mine = make_inquiry(sender, email=sender.email)
        make_inquiry(None, status=InquiryStatus.ANSWERED, reply='답')
        authorize(self.client, make_user(9, operator=True))

        response = self.client.get(OPERATOR_INQUIRIES_URL, {'status': 'open'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        [item] = response.data['items']
        self.assertEqual(item['id'], str(mine.id))
        self.assertEqual(item['sender'], {'public_id': str(sender.public_id), 'nickname': '플레이어1'})
        self.assertEqual(item['email'], 'player1@example.com')
        self.assertIsNone(item['reply_sent_at'])
        self.assertEqual(len(self.client.get(OPERATOR_INQUIRIES_URL).data['items']), 2)
        self.assertEqual(response.data['counts'], {'all': 2, 'open': 1, 'answered': 1, 'unread': 2})
        self.assertIsNone(item['read_at'])

    def test_a_wrong_status_is_refused(self):
        authorize(self.client, make_user(9, operator=True))

        response = self.client.get(OPERATOR_INQUIRIES_URL, {'status': 'closed'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ReplyTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.operator = make_user(9, operator=True)
        authorize(self.client, self.operator)

    def test_the_reply_is_written_once_and_mailed_to_the_inquiry_address(self):
        inquiry = make_inquiry(None, title='결제가 두 번 됐어요', category='payment')

        response = self.client.post(reply_url(inquiry.id), {'reply': '한 번을 취소했습니다.'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['status'], 'answered')
        self.assertIsNotNone(response.data['reply_sent_at'])
        inquiry.refresh_from_db()
        self.assertEqual((inquiry.reply, inquiry.answered_by), ('한 번을 취소했습니다.', self.operator))
        [message] = mail.outbox
        self.assertEqual(message.to, ['guest@example.com'])
        self.assertEqual(message.subject, '[이매망량의 서재] 문의에 답했습니다: 결제가 두 번 됐어요')
        self.assertIn('한 번을 취소했습니다.', message.body)
        self.assertIn('테이블 방에서 멈춥니다.', message.body)

        again = self.client.post(reply_url(inquiry.id), {'reply': '한 번 더'}, format='json')

        self.assertEqual(again.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(again.data['code'], 'inquiry.already_answered')
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(MAIL_DELIVERY='outbox')
    def test_the_reply_mail_waits_in_the_outbox_for_a_day(self):
        inquiry = make_inquiry(None)

        response = self.client.post(reply_url(inquiry.id), {'reply': '확인했습니다.'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['reply_sent_at'])
        queued = OutgoingMail.objects.get()
        self.assertEqual((queued.to_email, queued.kind), ('guest@example.com', MailKind.INQUIRY_REPLY))
        self.assertGreater(queued.expires_at - queued.created_at, timedelta(hours=23))

    def test_the_sender_sees_the_reply(self):
        sender = make_user(1)
        inquiry = make_inquiry(sender, email=sender.email)
        self.client.post(reply_url(inquiry.id), {'reply': '고쳤습니다.'}, format='json')

        mine = APIClient()
        authorize(mine, sender)
        [item] = mine.get(MY_INQUIRIES_URL).data['items']

        self.assertEqual((item['status'], item['reply']), ('answered', '고쳤습니다.'))

    def test_a_missing_inquiry_and_an_empty_reply_are_refused(self):
        missing = self.client.post(reply_url(uuid.uuid4()), {'reply': '답'}, format='json')
        empty = self.client.post(reply_url(make_inquiry(None).id), {'reply': ''}, format='json')

        self.assertEqual((missing.status_code, missing.data['code']), (status.HTTP_404_NOT_FOUND, 'inquiry.not_found'))
        self.assertEqual(empty.status_code, status.HTTP_400_BAD_REQUEST)

    def test_only_operators_reply(self):
        inquiry = make_inquiry(None)
        authorize(self.client, make_user(1))

        response = self.client.post(reply_url(inquiry.id), {'reply': '답'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertNotIn('code', response.data)
        self.assertEqual(Inquiry.objects.get().status, InquiryStatus.OPEN)


class ErasureTests(TestCase):
    def test_blanking_an_account_erases_its_inquiries(self):
        user = make_user(1)
        make_inquiry(user, email=user.email)
        guest = make_inquiry(None)

        blank_account(user)

        self.assertEqual(list(Inquiry.objects.all()), [guest])


class ReadTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        authorize(self.client, make_user(9, operator=True))

    def test_opening_marks_it_read_once(self):
        inquiry = make_inquiry(None)

        first = self.client.get(inquiry_url(inquiry.id))
        second = self.client.get(inquiry_url(inquiry.id))

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(first.data['read_at'])
        self.assertEqual(second.data['read_at'], first.data['read_at'])
        self.assertEqual(self.client.get(OPERATOR_INQUIRIES_URL).data['counts']['unread'], 0)

    def test_a_missing_one_and_non_operators_get_404(self):
        missing = self.client.get(inquiry_url(uuid.uuid4()))
        inquiry = make_inquiry(None)
        player = APIClient()
        authorize(player, make_user(1))

        self.assertEqual(missing.data['code'], 'inquiry.not_found')
        self.assertEqual(player.get(inquiry_url(inquiry.id)).status_code, status.HTTP_404_NOT_FOUND)
        inquiry.refresh_from_db()
        self.assertIsNone(inquiry.read_at)


class DeleteTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        authorize(self.client, make_user(9, operator=True))

    def test_one_is_deleted(self):
        inquiry = make_inquiry(None)
        kept = make_inquiry(None)

        response = self.client.delete(inquiry_url(inquiry.id))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(list(Inquiry.objects.all()), [kept])
        self.assertEqual(self.client.delete(inquiry_url(inquiry.id)).data['code'], 'inquiry.not_found')

    def test_the_selected_are_deleted_and_missing_ones_skipped(self):
        first, second, kept = make_inquiry(None), make_inquiry(None), make_inquiry(None)

        response = self.client.post(
            DELETE_URL, {'ids': [str(first.id), str(second.id), str(uuid.uuid4())]}, format='json'
        )

        self.assertEqual((response.status_code, response.data), (status.HTTP_200_OK, {'deleted': 2}))
        self.assertEqual(list(Inquiry.objects.all()), [kept])

    def test_a_folder_is_emptied(self):
        answered = make_inquiry(None, status=InquiryStatus.ANSWERED, reply='답')
        waiting = make_inquiry(None)

        open_folder = self.client.post(DELETE_URL, {'folder': 'open'}, format='json')

        self.assertEqual(open_folder.data, {'deleted': 1})
        self.assertEqual(list(Inquiry.objects.all()), [answered])
        self.assertFalse(Inquiry.objects.filter(pk=waiting.pk).exists())

        make_inquiry(None)
        everything = self.client.post(DELETE_URL, {'folder': 'all'}, format='json')

        self.assertEqual(everything.data, {'deleted': 2})
        self.assertFalse(Inquiry.objects.exists())

    def test_ids_or_folder_but_not_both_nor_neither(self):
        inquiry = make_inquiry(None)
        for body in (
            {},
            {'ids': [str(inquiry.id)], 'folder': 'all'},
            {'ids': []},
            {'ids': [str(uuid.uuid4()) for _ in range(101)]},
            {'folder': 'trash'},
        ):
            with self.subTest(body=list(body)):
                self.assertEqual(
                    self.client.post(DELETE_URL, body, format='json').status_code, status.HTTP_400_BAD_REQUEST
                )
        self.assertTrue(Inquiry.objects.exists())

    def test_only_operators_delete(self):
        inquiry = make_inquiry(None)
        player = APIClient()
        authorize(player, make_user(1))

        self.assertEqual(player.delete(inquiry_url(inquiry.id)).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            player.post(DELETE_URL, {'folder': 'all'}, format='json').status_code, status.HTTP_404_NOT_FOUND
        )
        self.assertEqual(
            APIClient().post(DELETE_URL, {'folder': 'all'}, format='json').status_code, status.HTTP_401_UNAUTHORIZED
        )
        self.assertTrue(Inquiry.objects.exists())


class RetentionTests(TestCase):
    def test_the_command_deletes_what_is_older_than_a_year(self):
        old = make_inquiry(None, title='오래된 것')
        young = make_inquiry(None, title='남는 것')
        Inquiry.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=366))
        Inquiry.objects.filter(pk=young.pk).update(created_at=timezone.now() - timedelta(days=364))
        out = io.StringIO()

        call_command('delete_old_inquiries', stdout=out)

        self.assertEqual(list(Inquiry.objects.all()), [young])
        self.assertIn('1건', out.getvalue())
