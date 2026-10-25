# board-server/app/core/dependencies.py

"""
라우터들이 함께 쓰는 의존성. 요청 하나의 DB 세션과 앱의 설정이다.
"""

from typing import Annotated

from fastapi import Depends, Request
from server_core.database import get_session
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings

# 요청 하나가 쓰는 DB 세션
Session = Annotated[AsyncSession, Depends(get_session)]


def get_app_settings(request: Request) -> Settings:
    """앱의 설정. 앱을 만들 때 붙여 둔 것이다(테스트가 바꾼 설정도 이것이다)."""
    return request.app.state.settings


AppSettings = Annotated[Settings, Depends(get_app_settings)]
