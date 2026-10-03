# game-server/app/assets/rulebooks/schemas.py

"""
룰북 API 가 받는 입력과 내보내는 응답의 모양. 공통 모양(app/assets/schemas.py)에 룰북의 칸을 더한다.
"""

from typing import Annotated

from pydantic import StringConstraints

from app.assets.models import RULEBOOK_GM_GUIDE_MAX_LENGTH
from app.assets.schemas import AssetCreate, AssetSummary, AssetUpdate

GmGuide = Annotated[str, StringConstraints(max_length=RULEBOOK_GM_GUIDE_MAX_LENGTH)]


class RulebookCreate(AssetCreate):
    """룰북을 만들 때 받는 값. 제목만 필수다."""

    gm_guide: GmGuide = ''


class RulebookUpdate(AssetUpdate):
    """룰북을 고칠 때 받는 값. 보낸 칸만 바꾼다."""

    gm_guide: GmGuide | None = None


class RulebookDetail(AssetSummary):
    """
    만든 사람이 자기 룰북을 볼 때의 값. 진행 지침까지 싣는다.

    진행 지침은 AI 만 보는 글이다. 만든 사람이 아닌 사람에게 보여 주는 기능을 만들 때는
    진행 지침이 없는 응답을 따로 만든다.
    """

    gm_guide: str
