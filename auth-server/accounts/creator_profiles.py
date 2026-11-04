# auth-server/accounts/creator_profiles.py

"""
제작자의 프로필(#992). 표시 이름(닉네임)과 소개다. 그림은 아직 두지 않는다.

  - 표시 이름은 닉네임 그대로다. 목록 서버는 이름을 적어 두지 않고, 화면이 공개 ID 로 묻는다(public_names.py 와 같다)
  - 소개는 200자까지의 글이다. 누구나 제작자 페이지에서 본다. 비워 둘 수 있다
  - 없는 공개 ID 와 비운 계정(만 14세 미만, 탈퇴)은 프로필이 없다. 둘을 나누지 않는다
  - 정지된 계정은 그대로 보인다(public_names.py 와 같다)
"""

import uuid
from dataclasses import dataclass

from accounts.models import User
from accounts.public_names import shown_name

# 소개의 길이 상한. 모델의 칸(User.bio)과 같다
BIO_MAX_LENGTH = 200


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
