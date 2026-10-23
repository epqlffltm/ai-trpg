# trpg-server/app/assets/rulebooks/schemas.py

"""
룰북 API 가 받는 입력과 내보내는 응답의 모양. 공통 모양(app/assets/schemas.py)에 룰북의 칸을 더한다.
"""

from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.assets.models import RULEBOOK_GM_GUIDE_MAX_LENGTH
from app.assets.schemas import AssetCreate, AssetSummary, AssetUpdate
from app.engine.ruleset import Ruleset
from app.engine.templates import DEFAULT_TEMPLATE, Template

GmGuide = Annotated[str, StringConstraints(max_length=RULEBOOK_GM_GUIDE_MAX_LENGTH)]


class RulebookCreate(AssetCreate):
    """
    룰북을 만들 때 받는 값. 제목만 필수다.

    규칙을 직접 받지 않는다. 템플릿의 이름만 받고, 그 템플릿의 규칙을 서버가 채운다.
    """

    gm_guide: GmGuide = ''
    template: Template = DEFAULT_TEMPLATE


class RulebookUpdate(AssetUpdate):
    """
    룰북을 고칠 때 받는 값. 보낸 칸만 바꾼다.

    규칙은 아직 고칠 수 없다. template 이나 rules 를 보내면 모르는 칸이라 거절한다.
    """

    gm_guide: GmGuide | None = None


class RulebookDetail(AssetSummary):
    """
    만든 사람이 자기 룰북을 볼 때의 값. 진행 지침과 규칙까지 싣는다.

    진행 지침은 AI 만 보는 글이다. 만든 사람이 아닌 사람에게 보여 주는 기능을 만들 때는
    진행 지침이 없는 응답을 따로 만든다.
    """

    gm_guide: str
    rules: Ruleset


class TemplateSummary(BaseModel):
    """
    고를 수 있는 템플릿 하나(#615). 룰북을 만들 때 template 에 key 를 보내면 rules 가 룰북에 복사된다.

    attribution 은 본뜬 공개 문서의 출처 표시다. 화면에 템플릿을 보여 줄 때 함께 싣는다.
    """

    key: Template
    name: str
    summary: str
    attribution: list[str]
    notes: list[str]
    rules: Ruleset


class TemplateList(BaseModel):
    """
    고를 수 있는 템플릿들. app/engine/templates/ 의 Template 에 적은 차례다.

    default 는 룰북을 만들 때 template 을 보내지 않으면 쓰는 것이다.
    """

    default: Template
    items: list[TemplateSummary]
