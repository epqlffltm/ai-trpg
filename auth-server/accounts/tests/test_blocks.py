# auth-server/accounts/tests/test_blocks.py

"""
막은 제작자와 태그(#988, accounts/blocks.py)를 검증한다. /me 에 실리고, /me/blocks/... 로 막고 푼다.

  - 처음에는 비어 있다. 막으면 최근에 막은 것부터 /me 에 실린다. 다시 막아도, 막지 않은 것을 풀어도 같다
  - 자기 자신은 막지 않는다(400 block_self). 태그는 앞뒤 공백을 떼고 1~20자다(400 invalid_tag). 쉼표와 / 도 든다
  - 제작자 100명, 태그 30개까지다(409 block_limit). 이미 막은 것은 상한에 걸리지 않는다
  - 로그인해야 한다. 남의 것은 보이지 않는다. 계정을 비우면 그 사람이 막은 것과 그 사람을 막은 것을 지운다
"""

import uuid
from urllib.parse import quote

from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.blocks import MAX_CREATORS, MAX_TAGS
from accounts.erasure import blank_account
from accounts.models import CreatorBlock, TagBlock, User
from accounts.tests.helpers import authorize

ME_URL = reverse('accounts:me')


def make_user(number: int = 1) -> User:
    return User.objects.create_user(
        username=f'player_{number:02d}',
        email=f'player{number}@example.com',
        nickname=f'플레이어{number}',
        password='correct-horse-battery',
        email_verified_at=timezone.now(),
    )


def creator_url(public_id: uuid.UUID | str) -> str:
    return reverse('accounts:my-creator-block', kwargs={'public_id': public_id})


def tag_url(tag: str) -> str:
    return f'/api/v1/auth/me/blocks/tags/{quote(tag, safe="")}'


class BlockTests(APITestCase):
    def setUp(self):
        self.user = make_user()
        authorize(self.client, self.user)

    def test_starts_empty(self):
        self.assertEqual(self.client.get(ME_URL).data['blocks'], {'creators': [], 'tags': []})

    def test_blocks_and_unblocks_creators_and_tags(self):
        first, second = uuid.uuid4(), uuid.uuid4()

        self.client.put(creator_url(first))
        again = self.client.put(creator_url(second))
        self.client.put(creator_url(second))
        tagged = self.client.put(tag_url('  공포  '))
        self.client.put(tag_url('가,나/다'))

        self.assertEqual(again.status_code, status.HTTP_200_OK)
        self.assertEqual(again.data['creators'], [str(second), str(first)])
        self.assertEqual(tagged.data['tags'], ['공포'])
        self.assertEqual(
            self.client.get(ME_URL).data['blocks'],
            {'creators': [str(second), str(first)], 'tags': ['가,나/다', '공포']},
        )

        removed = self.client.delete(creator_url(first))
        untagged = self.client.delete(tag_url('공포'))
        missing = self.client.delete(tag_url('없음'))

        self.assertEqual(removed.data['creators'], [str(second)])
        self.assertEqual(untagged.data['tags'], ['가,나/다'])
        self.assertEqual(missing.status_code, status.HTTP_200_OK)

    def test_cannot_block_oneself(self):
        response = self.client.put(creator_url(self.user.public_id))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'block_self')

    def test_rejects_a_bad_tag(self):
        for tag in (' ', 'ㄱ' * 21):
            response = self.client.put(tag_url(tag))
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, tag)
            self.assertEqual(response.data['code'], 'invalid_tag')
        self.assertEqual(self.client.put(tag_url('ㄱ' * 20)).status_code, status.HTTP_200_OK)

    def test_limits_creators_and_tags(self):
        CreatorBlock.objects.bulk_create(
            CreatorBlock(user=self.user, creator_public_id=uuid.uuid4()) for _ in range(MAX_CREATORS)
        )
        TagBlock.objects.bulk_create(TagBlock(user=self.user, tag=f'태그{index}') for index in range(MAX_TAGS))
        kept = CreatorBlock.objects.filter(user=self.user).first().creator_public_id

        over_creator = self.client.put(creator_url(uuid.uuid4()))
        over_tag = self.client.put(tag_url('하나 더'))
        already = self.client.put(creator_url(kept))

        self.assertEqual(over_creator.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(over_creator.data['code'], 'block_limit')
        self.assertEqual(over_tag.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(already.status_code, status.HTTP_200_OK)
        self.assertEqual(CreatorBlock.objects.filter(user=self.user).count(), MAX_CREATORS)

    def test_needs_a_login_and_keeps_to_oneself(self):
        self.client.put(tag_url('공포'))
        other = make_user(2)
        authorize(self.client, other)

        self.assertEqual(self.client.get(ME_URL).data['blocks'], {'creators': [], 'tags': []})
        self.client.credentials()
        self.assertEqual(self.client.put(tag_url('공포')).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.delete(creator_url(uuid.uuid4())).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_emptying_an_account_erases_its_blocks_both_ways(self):
        other = make_user(2)
        self.client.put(creator_url(other.public_id))
        self.client.put(tag_url('공포'))
        CreatorBlock.objects.create(user=other, creator_public_id=self.user.public_id)

        with transaction.atomic():
            blank_account(User.objects.select_for_update().get(pk=self.user.pk))

        self.assertFalse(CreatorBlock.objects.exists())
        self.assertFalse(TagBlock.objects.exists())
