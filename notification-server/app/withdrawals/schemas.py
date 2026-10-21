# notification-server/app/withdrawals/schemas.py

"""
탈퇴를 받는 API 의 요청과 응답의 모양(#603). 인증 서버가 보내는 모양과 같다(auth-server/accounts/withdrawal_client.py).
"""

import enum
from dataclasses import dataclass

from pydantic import AwareDatetime, BaseModel, ConfigDict


class WithdrawalIn(BaseModel):
    """인증 서버가 보내는 탈퇴의 알림. 모르는 칸이 오면 422 다."""

    model_config = ConfigDict(extra='forbid')

    # 인증 서버가 계정을 비운 시각. 지우는 일은 이 값을 쓰지 않는다. 빠지면 틀린 알림이다
    withdrawn_at: AwareDatetime


class WithdrawalStatus(enum.StrEnum):
    """탈퇴를 받은 결과. 인증 서버는 processed 를 받아야 보내기를 멈춘다."""

    PROCESSED = 'processed'


class WithdrawalOut(BaseModel):
    """탈퇴를 받은 답. 지운 수는 싣지 않는다. 인증 서버는 결과만 본다."""

    status: WithdrawalStatus


@dataclass(frozen=True)
class Erased:
    """그 사람의 것을 지운 수. 로그에 남긴다. 이미 지웠거나 없던 사람이면 둘 다 0 이다."""

    notifications: int
    mutes: int
