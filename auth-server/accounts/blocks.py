# auth-server/accounts/blocks.py

"""
막은 제작자와 태그(#988, docs/architecture/blocks.md). 보기 싫은 제작자와 태그의 작품을 공개 목록에서 뺀다.

인증 서버가 가지는 까닭: 여러 서비스(TRPG, chat, story)의 화면이 함께 읽고, 기기를 바꿔도 같아야 한다.
목록을 거르는 설정(content_settings.py)과 같다.
목록을 내는 서버(trpg-server, asset-server)는 이 값을 모른다. 실행 중에 인증 서버를 부르지 않는다.
화면이 /me 에서 읽어 공개 목록을 부를 때 싣는다(exclude_creators, exclude_tag).

  - 상한은 제작자 MAX_CREATORS 명, 태그 MAX_TAGS 개다(2026-11-04 유저 결정). 목록의 주소에 싣기 때문이다.
    목록 서버의 상한(trpg-server 의 app/listings/exclusions.py, asset-server 의 app/exclusions.py)과 같다
  - 같은 사람의 막기는 계정의 줄을 잠그고 한다. 동시에 눌러도 상한을 넘지 않는다
  - 막기와 풀기는 몇 번 해도 같다. 이미 막은 것은 상한에 걸리지 않는다. 자기 자신은 막지 않는다
  - 태그는 앞뒤 공백을 떼고 1~20자다. 글자 그대로 견준다(작품의 태그와 똑같은 것을 뺀다)
"""

import uuid

from django.db import transaction

from accounts.models import CreatorBlock, TagBlock, User

MAX_CREATORS = 100
MAX_TAGS = 30
TAG_MAX_LENGTH = 20


class BlockSelfError(Exception):
    """자기 자신을 막으려 했다."""


class BlockLimitError(Exception):
    """상한을 넘는다."""


class InvalidTagError(Exception):
    """태그의 모양이 틀렸다(비었거나 20자를 넘는다)."""


def blocks_of(user: User) -> dict:
    """응답에 싣는 막은 것들. 최근에 막은 것부터다."""
    creators = CreatorBlock.objects.filter(user=user).order_by('-created_at', '-pk')
    tags = TagBlock.objects.filter(user=user).order_by('-created_at', '-pk')
    return {
        'creators': [str(public_id) for public_id in creators.values_list('creator_public_id', flat=True)],
        'tags': list(tags.values_list('tag', flat=True)),
    }


def clean_tag(tag: str) -> str:
    """앞뒤 공백을 뗀 태그. 비었거나 길면 InvalidTagError."""
    cleaned = tag.strip()
    if not cleaned or len(cleaned) > TAG_MAX_LENGTH:
        raise InvalidTagError
    return cleaned


def lock_user(user: User) -> User:
    """같은 사람의 막기를 하나씩 하도록 계정의 줄을 잠근다. 트랜잭션 안에서 부른다."""
    return User.objects.select_for_update().get(pk=user.pk)


@transaction.atomic
def block_creator(user: User, creator_public_id: uuid.UUID) -> dict:
    """제작자를 막는다. 자기 자신이면 BlockSelfError, 상한을 넘으면 BlockLimitError."""
    if creator_public_id == user.public_id:
        raise BlockSelfError
    locked = lock_user(user)
    blocks = CreatorBlock.objects.filter(user=locked)
    if not blocks.filter(creator_public_id=creator_public_id).exists():
        if blocks.count() >= MAX_CREATORS:
            raise BlockLimitError
        CreatorBlock.objects.create(user=locked, creator_public_id=creator_public_id)
    return blocks_of(locked)


def unblock_creator(user: User, creator_public_id: uuid.UUID) -> dict:
    """제작자의 막기를 푼다. 막지 않았어도 된다."""
    CreatorBlock.objects.filter(user=user, creator_public_id=creator_public_id).delete()
    return blocks_of(user)


@transaction.atomic
def block_tag(user: User, tag: str) -> dict:
    """태그를 막는다. 모양이 틀리면 InvalidTagError, 상한을 넘으면 BlockLimitError."""
    cleaned = clean_tag(tag)
    locked = lock_user(user)
    blocks = TagBlock.objects.filter(user=locked)
    if not blocks.filter(tag=cleaned).exists():
        if blocks.count() >= MAX_TAGS:
            raise BlockLimitError
        TagBlock.objects.create(user=locked, tag=cleaned)
    return blocks_of(locked)


def unblock_tag(user: User, tag: str) -> dict:
    """태그의 막기를 푼다. 막지 않았어도 된다."""
    TagBlock.objects.filter(user=user, tag=tag.strip()).delete()
    return blocks_of(user)


def erase_blocks(user: User) -> None:
    """그 사람이 막은 것과, 남이 그 사람(제작자)을 막은 것을 지운다. 계정을 비울 때 부른다."""
    CreatorBlock.objects.filter(user=user).delete()
    TagBlock.objects.filter(user=user).delete()
    CreatorBlock.objects.filter(creator_public_id=user.public_id).delete()
