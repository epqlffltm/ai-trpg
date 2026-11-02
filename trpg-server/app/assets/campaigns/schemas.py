# trpg-server/app/assets/campaigns/schemas.py

"""
캠페인 API 의 입력과 응답의 모양, 판에 굳히는 내용의 모양(#481 B, docs/architecture/campaigns.md).

편(episodes)은 목록의 차례가 편의 차례다. 고칠 때는 목록을 통째로 보낸다.
같은 시나리오를 두 번 넣지 못한다(422). 시나리오가 자기 것인지는 서비스가 본다(422).
초안은 편을 비워 둘 수 있다. 둘 이상인지, 시나리오마다 게시한 판이 있는지는 게시할 때 본다.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.assets.campaigns.models import CAMPAIGN_MAX_EPISODES, EPISODE_TITLE_MAX_LENGTH
from app.assets.models import Rating
from app.assets.scenarios.schemas import VersionNote
from app.assets.schemas import AssetCreate, AssetSummary, AssetUpdate

# 판의 모양의 번호. 모양을 바꾸면 올리고, 옛 판을 읽는 법을 더한다
CAMPAIGN_SNAPSHOT_FORMAT = 1

EpisodeTitle = Annotated[str, StringConstraints(strip_whitespace=True, max_length=EPISODE_TITLE_MAX_LENGTH)]


class EpisodeIn(BaseModel):
    """편 하나. 시나리오와 이름(비우면 시나리오의 제목)."""

    model_config = ConfigDict(extra='forbid')

    scenario_id: uuid.UUID
    title: EpisodeTitle = ''


def reject_repeated_scenarios(episodes: list[EpisodeIn]) -> list[EpisodeIn]:
    """같은 시나리오가 두 번 있으면 거부한다. 같은 사람들이 같은 편을 두 번 하게 된다."""
    scenario_ids = [episode.scenario_id for episode in episodes]
    if len(set(scenario_ids)) != len(scenario_ids):
        raise ValueError('같은 시나리오를 두 편에 넣을 수 없습니다.')
    return episodes


Episodes = Annotated[list[EpisodeIn], Field(max_length=CAMPAIGN_MAX_EPISODES)]


class CampaignCreate(AssetCreate):
    """캠페인을 만들 때 받는 값. 편은 비워도 된다."""

    episodes: Episodes = []

    @field_validator('episodes')
    @classmethod
    def unique_scenarios(cls, episodes: list[EpisodeIn]) -> list[EpisodeIn]:
        """같은 시나리오가 두 번 있으면 거부한다."""
        return reject_repeated_scenarios(episodes)


class CampaignUpdate(AssetUpdate):
    """캠페인을 고칠 때 받는 값. 보낸 칸만 바뀐다. 편은 목록을 통째로 바꾼다."""

    episodes: Episodes | None = None

    @field_validator('episodes')
    @classmethod
    def unique_scenarios(cls, episodes: list[EpisodeIn] | None) -> list[EpisodeIn] | None:
        """같은 시나리오가 두 번 있으면 거부한다."""
        return None if episodes is None else reject_repeated_scenarios(episodes)


class EpisodeOut(BaseModel):
    """초안의 편 하나. 시나리오의 제목(지금의 것)과 게시한 마지막 판 번호(없으면 None)를 함께 싣는다."""

    scenario_id: uuid.UUID
    title: str
    scenario_title: str
    last_version: int | None


class CampaignSummary(AssetSummary):
    """캠페인의 목록에 싣는 값. 공통 값에 등급(마지막으로 게시할 때 정한 것)과 편의 수를 더한다."""

    rating: Rating
    episode_count: int


class CampaignPage(BaseModel):
    """캠페인 목록의 한 쪽."""

    items: list[CampaignSummary]
    total: int = Field(ge=0)


class CampaignDetail(CampaignSummary):
    """캠페인 하나. 편들을 차례대로 싣는다."""

    episodes: list[EpisodeOut]


class CampaignVersionCreate(BaseModel):
    """게시할 때 받는 값. 변경 내용만 적는다. 판의 내용은 서버가 초안에서 굳힌다."""

    model_config = ConfigDict(extra='forbid')

    note: VersionNote = ''


class EpisodeSnapshot(BaseModel):
    """판에 굳힌 편 하나. 시나리오와 그때의 마지막 판 번호, 편의 이름(비웠으면 그때의 시나리오의 제목)."""

    scenario_id: uuid.UUID
    version: int = Field(ge=1)
    title: str


class CampaignSnapshot(BaseModel):
    """
    캠페인의 판 하나의 내용. 편들과 등급이다.

    등급은 편의 판들의 등급 가운데 가장 높은 것이다(성인용이 하나라도 있으면 성인용).
    룰북은 편들이 모두 같다(게시할 때 막는다).
    rulebook_id 는 그 룰북이 어디서 왔는지 알려 줄 뿐이다. 규칙은 편마다의 시나리오 판에 굳어 있다.
    """

    format: int = CAMPAIGN_SNAPSHOT_FORMAT
    title: str
    description: str
    rating: Rating
    rulebook_id: uuid.UUID
    episodes: list[EpisodeSnapshot] = Field(min_length=2, max_length=CAMPAIGN_MAX_EPISODES)


class CampaignVersionSummary(BaseModel):
    """캠페인의 판의 목록에 싣는 값. 굳힌 내용은 싣지 않는다."""

    id: uuid.UUID
    number: int
    note: str
    created_at: datetime


class CampaignVersionDetail(CampaignVersionSummary):
    """캠페인의 판 하나. 굳힌 내용을 싣는다."""

    snapshot: CampaignSnapshot


class CampaignPublishCheck(BaseModel):
    """
    지금 게시하면 막히는 이유와 알릴 것. 판을 만들지 않는다.

    problems 는 게시가 409 로 돌려주는 것과 같은 이름들이다. 비어 있으면 지금 게시할 수 있다(ready).
    warnings 는 게시를 막지 않는 알림이다(옮겨지지 않는 물건, 성장이 없는 룰북).
    """

    ready: bool
    problems: list[str]
    warnings: list[str]
