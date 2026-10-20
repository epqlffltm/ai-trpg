# auth-server/accounts/public_names.py

"""
다른 사람의 공개 이름(닉네임)을 공개 ID 로 한꺼번에 찾는다(#532).

목록과 소개 화면(시나리오의 만든 사람 등)은 다른 서버에서 공개 ID(creator_id)만 받는다. 이름은 이 서버만 안다.
화면이 한 쪽에 보이는 공개 ID 를 모아 한 번에 묻는다. 다른 서버는 이름을 적어 두지 않으므로 이름을 바꾸면 바로 보인다.

  - 닉네임만 내준다. 이메일, 아이디, 나이, 본인인증 여부는 내주지 않는다. 닉네임은 원래 남에게 보이는 이름이다
  - 없는 공개 ID 와 만 14세 미만으로 막은 계정은 이름이 없다(null). 둘을 나누지 않는다. 화면은 "탈퇴한 사용자"로 보인다
  - 정지된 계정은 이름을 그대로 내준다. 그 사람이 만든 것은 그대로 보이고, 정지는 이름을 지우는 일이 아니다
  - 공개 ID 는 난수(UUID 4)라 차례로 넣어 보며 계정을 찾을 수 없다
"""

import uuid
from dataclasses import dataclass

from accounts.identity import is_removed_account
from accounts.models import User

# 한 번에 찾는 공개 ID 의 상한. 화면의 한 쪽(목록은 많아야 100개)이면 넉넉하다
MAX_IDS = 100


@dataclass(frozen=True)
class PublicName:
    """공개 ID 하나와 그 이름. 없거나 막은 계정이면 nickname 이 None 이다."""

    public_id: uuid.UUID
    nickname: str | None


class InvalidPublicIdsError(ValueError):
    """공개 ID 의 목록이 비었거나, UUID 가 아닌 것이 있거나, 너무 많다."""


def parse_ids(raw: str) -> list[uuid.UUID]:
    """
    쉼표로 나눈 공개 ID 들을 읽는다. 같은 것은 한 번만, 처음 나온 차례대로 둔다.

    비었거나, UUID 가 아닌 것이 있거나, 서로 다른 것이 MAX_IDS 를 넘으면 InvalidPublicIdsError.
    """
    parts = [part.strip() for part in raw.split(',') if part.strip()]
    if not parts:
        raise InvalidPublicIdsError('ids 에 공개 ID 를 하나 이상 쉼표로 나눠 적습니다.')
    try:
        ids = list(dict.fromkeys(uuid.UUID(part) for part in parts))
    except ValueError as exc:
        raise InvalidPublicIdsError('ids 에 UUID 가 아닌 것이 있습니다.') from exc
    if len(ids) > MAX_IDS:
        raise InvalidPublicIdsError(f'공개 ID 는 한 번에 {MAX_IDS}개까지 찾습니다.')
    return ids


def shown_name(user: User | None) -> str | None:
    """남에게 보일 이름. 없거나 막은 계정이면 None 이다."""
    if user is None or is_removed_account(user):
        return None
    return user.nickname


def find_names(ids: list[uuid.UUID]) -> list[PublicName]:
    """공개 ID 들의 이름을 받은 차례대로 돌려준다. 한 번의 쿼리다."""
    users = {
        user.public_id: user for user in User.objects.filter(public_id__in=ids).only('pk', 'public_id', 'nickname')
    }
    return [PublicName(public_id=public_id, nickname=shown_name(users.get(public_id))) for public_id in ids]
