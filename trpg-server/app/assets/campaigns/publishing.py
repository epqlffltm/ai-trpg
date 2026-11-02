# trpg-server/app/assets/campaigns/publishing.py

"""
캠페인을 게시한다(#481 B, docs/architecture/campaigns.md 의 "게시할 때 보는 것"). 지금의 편들이 새 판으로 굳는다.

막는 것(problems, 게시는 409):
  - episodes_too_few: 편이 둘보다 적다
  - episode_scenario_missing: 편의 시나리오가 없다(지웠다)
  - episode_unpublished: 편의 시나리오에 게시한 판이 없다
  - rulebook_mismatch: 편들의 시나리오의 마지막 판이 같은 룰북의 같은 규칙을 쓰지 않는다
  - campaign_quest_missing: 조건 campaign_quest_succeeded, campaign_quest_failed 가 그 편보다 앞의 편의 판에 없는
    퀘스트(사건 항목)를 가리킨다. 첫 편에서 쓰면 늘 걸린다
같은 시나리오가 두 번 있는 것과 남의 시나리오는 입력에서 막는다(422).

알리는 것(warnings, 막지 않는다):
  - progression_missing: 룰북에 성장이 없다. 경험치와 레벨이 옮겨지지 않는다
  - items_not_carried: 한 편의 판에 있는 물건 항목이 뒤의 편들의 판 어디에도 없다. 그 물건은 옮겨지지 않는다

판에는 편마다 그때의 시나리오의 마지막 판 번호를 굳힌다. 등급은 그 판들의 등급 가운데 가장 높은 것이다.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import repository as asset_repository
from app.assets import service as assets
from app.assets.campaigns import repository
from app.assets.campaigns.models import CAMPAIGN_MIN_EPISODES, Campaign, CampaignVersion
from app.assets.campaigns.schemas import CampaignSnapshot, CampaignVersionCreate, EpisodeSnapshot
from app.assets.models import CAMPAIGN_CONDITIONS, Rating, Scenario
from app.assets.ratings import ALL_AGES_ONLY, require_rating
from app.assets.scenarios.publishing import ScenarioNotReadyError
from app.assets.scenarios.snapshot import Snapshot, every_condition, item_entries, quest_entries, read_snapshot
from app.assets.service import AssetNotFoundError

EPISODES_TOO_FEW = 'episodes_too_few'
EPISODE_SCENARIO_MISSING = 'episode_scenario_missing'
EPISODE_UNPUBLISHED = 'episode_unpublished'
RULEBOOK_MISMATCH = 'rulebook_mismatch'
CAMPAIGN_QUEST_MISSING = 'campaign_quest_missing'

PROGRESSION_MISSING = 'progression_missing'
ITEMS_NOT_CARRIED = 'items_not_carried'


class CampaignNotReadyError(ScenarioNotReadyError):
    """캠페인이 게시할 조건을 갖추지 못했다. 시나리오의 것과 같은 409 로 답한다(app/main.py 의 처리기가 받는다)."""


@dataclass
class EpisodeVersion:
    """편 하나가 게시할 때 쓸 시나리오의 판. 번호와 지금의 모양으로 읽은 내용이다."""

    scenario_id: uuid.UUID
    title: str
    number: int
    snapshot: Snapshot


@dataclass
class Readiness:
    """게시할 수 있는지 본 결과. 막는 것과 알리는 것, 그리고 막는 것이 없을 때 굳힐 편들의 판."""

    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    episodes: list[EpisodeVersion] = field(default_factory=list)


def add_problem(problems: list[str], problem: str) -> None:
    """같은 이름을 두 번 적지 않는다."""
    if problem not in problems:
        problems.append(problem)


async def episode_versions(
    session: AsyncSession, owner_id: uuid.UUID, campaign: Campaign, problems: list[str]
) -> list[EpisodeVersion]:
    """편마다 시나리오의 마지막 판을 읽는다. 없는 시나리오, 판이 없는 시나리오는 problems 에 적고 건너뛴다."""
    numbers = await repository.last_scenario_numbers(session, [episode.scenario_id for episode in campaign.episodes])
    found: list[EpisodeVersion] = []
    for episode in campaign.episodes:
        scenario = await asset_repository.find_owned(session, Scenario, owner_id, episode.scenario_id)
        if scenario is None:
            add_problem(problems, EPISODE_SCENARIO_MISSING)
            continue
        number = numbers.get(episode.scenario_id)
        document = None if number is None else await repository.scenario_snapshot(session, episode.scenario_id, number)
        if number is None or document is None:
            add_problem(problems, EPISODE_UNPUBLISHED)
            continue
        found.append(EpisodeVersion(episode.scenario_id, episode.title, number, read_snapshot(document)))
    return found


def rulebook_key(snapshot: Snapshot) -> tuple[uuid.UUID, dict]:
    """판의 룰북을 견주는 열쇠. 같은 룰북이고 규칙이 같아야 같다(룰북을 고친 뒤 게시한 편은 다르다)."""
    return snapshot.rulebook.id, snapshot.rulebook.rules.model_dump(mode='json')


def same_rulebook(episodes: list[EpisodeVersion]) -> bool:
    """편들의 판이 모두 같은 룰북의 같은 규칙을 쓰는가."""
    keys = [rulebook_key(episode.snapshot) for episode in episodes]
    return all(key == keys[0] for key in keys[1:])


def campaign_targets(snapshot: Snapshot) -> set[uuid.UUID]:
    """그 판의 조건 가운데 캠페인의 앞 편의 퀘스트를 보는 것들이 가리키는 사건 항목."""
    return {
        condition.target
        for condition in every_condition(snapshot)
        if condition.kind in CAMPAIGN_CONDITIONS and condition.target is not None
    }


def campaign_quests_known(episodes: list[EpisodeVersion]) -> bool:
    """편마다 캠페인의 조건이 가리키는 퀘스트가 그 편보다 앞의 편들의 판에 있는가."""
    for index, episode in enumerate(episodes):
        earlier = {entry.id for before in episodes[:index] for entry in quest_entries(before.snapshot)}
        if not campaign_targets(episode.snapshot) <= earlier:
            return False
    return True


def items_not_carried(episodes: list[EpisodeVersion]) -> bool:
    """
    앞의 편의 물건 항목 가운데 뒤의 편들의 판 어디에도 없는 것이 있는가.

    마지막 편의 물건은 옮길 곳이 없어 보지 않는다.
    """
    for index, episode in enumerate(episodes[:-1]):
        later = {entry.id for after in episodes[index + 1 :] for entry in item_entries(after.snapshot)}
        if any(entry.id not in later for entry in item_entries(episode.snapshot)):
            return True
    return False


def find_warnings(episodes: list[EpisodeVersion]) -> list[str]:
    """막지 않고 알릴 것. 룰북이 같다고 본 뒤에 부른다."""
    warnings: list[str] = []
    if episodes and episodes[0].snapshot.rulebook.rules.progression is None:
        warnings.append(PROGRESSION_MISSING)
    if items_not_carried(episodes):
        warnings.append(ITEMS_NOT_CARRIED)
    return warnings


async def readiness(session: AsyncSession, owner_id: uuid.UUID, campaign: Campaign) -> Readiness:
    """게시할 수 있는지 본다. 막는 것이 하나라도 있으면 굳힐 편들을 비운다."""
    problems: list[str] = []
    if len(campaign.episodes) < CAMPAIGN_MIN_EPISODES:
        problems.append(EPISODES_TOO_FEW)
    episodes = await episode_versions(session, owner_id, campaign, problems)
    if episodes and not same_rulebook(episodes):
        problems.append(RULEBOOK_MISMATCH)
    if not campaign_quests_known(episodes):
        problems.append(CAMPAIGN_QUEST_MISSING)
    if problems:
        return Readiness(problems=problems)
    return Readiness(warnings=find_warnings(episodes), episodes=episodes)


def campaign_rating(episodes: list[EpisodeVersion]) -> Rating:
    """편의 판들의 등급 가운데 가장 높은 것. 성인용이 하나라도 있으면 성인용이다."""
    return Rating.ADULT if any(episode.snapshot.rating == Rating.ADULT for episode in episodes) else Rating.ALL


def build_snapshot(campaign: Campaign, episodes: list[EpisodeVersion]) -> CampaignSnapshot:
    """굳힐 내용. 편의 이름을 비웠으면 그 판의 시나리오의 제목이다."""
    return CampaignSnapshot(
        title=campaign.asset.title,
        description=campaign.asset.description,
        rating=campaign_rating(episodes),
        rulebook_id=episodes[0].snapshot.rulebook.id,
        episodes=[
            EpisodeSnapshot(
                scenario_id=episode.scenario_id, version=episode.number, title=episode.title or episode.snapshot.title
            )
            for episode in episodes
        ],
    )


async def check_publishable(
    session: AsyncSession, owner_id: uuid.UUID, campaign_id: uuid.UUID
) -> tuple[list[str], list[str]]:
    """지금 게시하면 막히는 이유와 알릴 것. 판을 만들지 않는다. 캠페인이 없으면 AssetNotFoundError."""
    campaign = await assets.get_owned(session, Campaign, owner_id, campaign_id)
    found = await readiness(session, owner_id, campaign)
    return found.problems, found.warnings


async def publish(
    session: AsyncSession,
    owner_id: uuid.UUID,
    campaign_id: uuid.UUID,
    data: CampaignVersionCreate,
    allowed: Sequence[Rating] = ALL_AGES_ONLY,
) -> CampaignVersion:
    """
    자기 캠페인을 게시한다. 없으면 AssetNotFoundError, 조건을 갖추지 못했으면 CampaignNotReadyError.
    성인용 편이 있는데 allowed 에 성인용이 없으면 AdultContentRequiredError.

    캠페인을 잠그고 한다. 번호는 "지금까지의 가장 큰 번호 + 1"이다. 잠그면 나중 요청은 앞의 판이 저장된 뒤에 센다.
    정한 등급은 캠페인의 공통 부분(assets.rating)에도 적는다. 목록이 그 등급을 보인다.
    """
    campaign = await assets.lock_owned(session, Campaign, owner_id, campaign_id)
    found = await readiness(session, owner_id, campaign)
    if found.problems:
        raise CampaignNotReadyError(found.problems)
    snapshot = build_snapshot(campaign, found.episodes)
    require_rating(snapshot.rating, allowed)

    number = await repository.last_number(session, campaign_id) + 1
    version = CampaignVersion(
        campaign_id=campaign_id, number=number, note=data.note, snapshot=snapshot.model_dump(mode='json')
    )
    repository.add_version(session, version)
    campaign.asset.rating = snapshot.rating
    await session.commit()
    await session.refresh(version)
    return version


async def list_versions(session: AsyncSession, owner_id: uuid.UUID, campaign_id: uuid.UUID) -> list[CampaignVersion]:
    """자기 캠페인의 판을 최근 것부터. 캠페인이 없으면 AssetNotFoundError."""
    await assets.get_owned(session, Campaign, owner_id, campaign_id)
    return await repository.list_versions(session, campaign_id)


async def get_version(
    session: AsyncSession, owner_id: uuid.UUID, campaign_id: uuid.UUID, number: int
) -> CampaignVersion:
    """자기 캠페인의 판 하나. 캠페인이나 판이 없으면 AssetNotFoundError."""
    await assets.get_owned(session, Campaign, owner_id, campaign_id)
    version = await repository.find_version(session, campaign_id, number)
    if version is None:
        raise AssetNotFoundError
    return version
