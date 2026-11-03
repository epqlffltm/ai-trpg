# auth-server/accounts/invites.py

"""
초대 코드(#990). 계정마다 코드 하나를 주고, 가입할 때 적은 코드로 초대한 사람을 적는다.

보상은 여기서 정하지 않는다. 초대받은 사람이 본인인증을 마칠 때 정한다(invite_rewards.py).
메일은 얼마든지 만들 수 있어 가입만으로는 사람을 알 수 없다.

코드는 추측하기 어렵게 난수로 만든다. 헷갈리는 글자(0, O, 1, I, L)를 빼서 손으로 옮겨 적어도 틀리지 않게 한다.
받을 때는 대소문자, 공백, 하이픈을 가리지 않는다.
"""

import secrets
from uuid import UUID

from django.db import IntegrityError, transaction

from accounts.models import Invitation, InviteCode, User

# 코드에 쓰는 글자. 31자다. 8자면 경우의 수가 31^8(약 8,500억)이다
INVITE_CODE_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
INVITE_CODE_LENGTH = 8
# 받을 때의 길이 상한. 공백과 하이픈을 섞어 적은 것까지 받는다
INVITE_CODE_INPUT_MAX_LENGTH = 20
# 만든 코드가 이미 있을 때 다시 만드는 횟수. 겹칠 일은 거의 없다
MAX_CODE_ATTEMPTS = 5


class InvalidInviteCodeError(Exception):
    """그런 초대 코드가 없거나, 그 주인이 막힌 계정이다."""


def normalize_invite_code(raw: str) -> str:
    """받은 코드에서 공백과 하이픈을 빼고 대문자로 바꾼다."""
    return ''.join(raw.split()).replace('-', '').upper()


def new_invite_code() -> str:
    """새 코드 하나. 겹치는지는 보지 않는다(my_invite_code 가 본다)."""
    return ''.join(secrets.choice(INVITE_CODE_ALPHABET) for _ in range(INVITE_CODE_LENGTH))


def my_invite_code(user: User) -> InviteCode:
    """
    이 계정의 초대 코드. 없으면 만든다.

    같은 계정의 요청 둘이 함께 만들어도 하나만 남는다(기본 키가 계정이다). 다른 계정의 코드와 겹치면 새로 만든다.
    """
    existing = InviteCode.objects.filter(user=user).first()
    if existing is not None:
        return existing
    for _ in range(MAX_CODE_ATTEMPTS):
        try:
            with transaction.atomic():
                return InviteCode.objects.create(user=user, code=new_invite_code())
        except IntegrityError:
            # 같은 계정이 방금 만들었거나, 다른 계정의 코드와 겹쳤다
            existing = InviteCode.objects.filter(user=user).first()
            if existing is not None:
                return existing
    raise RuntimeError('초대 코드를 만들지 못했다')


def find_inviter(raw_code: str) -> UUID:
    """
    코드의 주인(초대한 계정)의 공개 ID. 가입을 마치기 전에 부른다.

    그런 코드가 없거나 주인이 막힌 계정이면 InvalidInviteCodeError 다.
    """
    code = normalize_invite_code(raw_code)
    found = InviteCode.objects.select_related('user').filter(code=code, user__is_active=True).first()
    if found is None:
        raise InvalidInviteCodeError
    return found.user.public_id


def record_invitation(invitee: User, inviter_public_id: UUID) -> Invitation:
    """가입한 계정을 초대한 사람을 적는다. 가입과 같은 트랜잭션에서 부른다(services.complete_signup)."""
    return Invitation.objects.create(invitee=invitee, inviter_public_id=inviter_public_id)
