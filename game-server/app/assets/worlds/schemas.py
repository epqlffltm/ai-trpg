# game-server/app/assets/worlds/schemas.py

"""
세계관 API 가 받는 입력과 내보내는 응답의 모양. 공통 모양(app/assets/schemas.py)에 세계관의 칸을 더한다.
"""

from typing import Annotated

from pydantic import StringConstraints

from app.assets.models import WORLD_GM_NOTES_MAX_LENGTH, WORLD_SETTING_MAX_LENGTH
from app.assets.schemas import AssetCreate, AssetSummary, AssetUpdate

Setting = Annotated[str, StringConstraints(max_length=WORLD_SETTING_MAX_LENGTH)]
GmNotes = Annotated[str, StringConstraints(max_length=WORLD_GM_NOTES_MAX_LENGTH)]


class WorldCreate(AssetCreate):
    """세계관을 만들 때 받는 값. 제목만 필수다."""

    setting: Setting = ''
    gm_notes: GmNotes = ''


class WorldUpdate(AssetUpdate):
    """세계관을 고칠 때 받는 값. 보낸 칸만 바꾼다."""

    setting: Setting | None = None
    gm_notes: GmNotes | None = None


class WorldDetail(AssetSummary):
    """
    만든 사람이 자기 세계관을 볼 때의 값. gm_notes 까지 싣는다.

    만든 사람이 아닌 사람에게 보여 주는 기능을 만들 때는 gm_notes 가 없는 응답을 따로 만든다.
    이 모양을 그대로 쓰면 비밀이 새어 나간다.
    """

    setting: str
    gm_notes: str
