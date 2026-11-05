# auth-server/accounts/creator_profiles.py

"""
제작자의 프로필(#992). 표시 이름(닉네임)과 소개다. 그림은 아직 두지 않는다.

  - 표시 이름은 닉네임 그대로다. 목록 서버는 이름을 적어 두지 않고, 화면이 공개 ID 로 묻는다(public_names.py 와 같다)
  - 소개는 200자까지의 글이다. 누구나 제작자 페이지에서 본다. 비워 둘 수 있다
  - 없는 공개 ID 와 비운 계정(만 14세 미만, 탈퇴)은 프로필이 없다. 둘을 나누지 않는다
  - 정지된 계정은 그대로 보인다(public_names.py 와 같다)
  - 이름으로 찾기(#984): 소개를 쓴 사람만 나온다(2026-11-05). 작품이 없는 사람의 닉네임이 검색으로 드러나지 않게 한다.
    인증 서버는 누가 작품을 공개했는지 모른다(목록 서버를 부르지 않는다). 소개를 쓰는 것을 "제작자로 나선다"로 본다
"""

import uuid
from dataclasses import dataclass

from django.db.models import Case, IntegerField, Value, When

from accounts.models import User
from accounts.public_names import shown_name

# 소개의 길이 상한. 모델의 칸(User.bio)과 같다
BIO_MAX_LENGTH = 200
# 이름으로 찾을 때 한 번에 주는 수의 상한과 기본
SEARCH_MAX_LIMIT = 20
SEARCH_DEFAULT_LIMIT = 10


@dataclass(frozen=True)
class CreatorProfile:
    """남에게 보이는 제작자 한 사람."""

    public_id: uuid.UUID
    nickname: str
    bio: str


def find_creator(public_id: uuid.UUID) -> CreatorProfile | None:
    """공개 ID 의 프로필. 없거나 비운 계정이면 None 이다."""
    user = User.objects.filter(public_id=public_id).only('pk', 'public_id', 'nickname', 'bio').first()
    nickname = shown_name(user)
    if user is None or nickname is None:
        return None
    return CreatorProfile(public_id=user.public_id, nickname=nickname, bio=user.bio)


def update_bio(user: User, bio: str) -> User:
    """내 소개를 바꾼다. 앞뒤 공백은 지운다. 길이는 부르는 쪽(직렬화)이 이미 봤다."""
    user.bio = bio.strip()
    user.save(update_fields=['bio'])
    return user


def search_creators(text: str, limit: int) -> list[CreatorProfile]:
    """
    닉네임에 text 가 든 제작자(소개를 쓴 사람). 닉네임이 같은 것, text 로 시작하는 것, 나머지 차례다.
    같은 차례 안에서는 닉네임 차례다.

    대소문자를 가리지 않는다. text 는 부르는 쪽이 앞뒤 공백을 떼고 길이를 봤다.
    비운 계정(탈퇴, 만 14세 미만)은 소개가 비어 있어 나오지 않는다.
    """
    rank = Case(
        When(nickname__iexact=text, then=Value(0)),
        When(nickname__istartswith=text, then=Value(1)),
        default=Value(2),
        output_field=IntegerField(),
    )
    users = (
        User.objects.exclude(bio='')
        .filter(nickname__icontains=text)
        .annotate(rank=rank)
        .order_by('rank', 'nickname')
        .only('public_id', 'nickname', 'bio')[:limit]
    )
    return [CreatorProfile(public_id=user.public_id, nickname=user.nickname, bio=user.bio) for user in users]
