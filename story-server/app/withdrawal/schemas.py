# story-server/app/withdrawal/schemas.py

"""
탈퇴 알림의 본문과 답의 모양(docs/architecture/withdrawal.md 의 "알리는 길"). 모든 받는 서버가 같은 모양이다.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class WithdrawalNotice(BaseModel):
    """
    인증 서버가 보내는 본문. 계정을 비운 시각이다.

    모르는 칸은 버린다. 인증 서버가 칸을 더해도 이 서버가 422 로 답해 알림이 끝없이 다시 오는 일이 없다.
    """

    model_config = ConfigDict(extra='ignore')

    withdrawn_at: datetime


class WithdrawalResult(BaseModel):
    """답. 지운 것이 없어도(이미 지웠다, 이 서버에 그 사람의 것이 없다) 같다. 인증 서버는 이것을 보고 그만 보낸다."""

    status: Literal['processed'] = 'processed'
