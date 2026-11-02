// web/apps/web/src/pages/trpg/studio/campaigns/episodesDraft.ts
// 캠페인의 편(#481 B) 입력. 목록의 차례가 편의 차례다. 순수한 함수다.
// 서버의 규칙(trpg-server/app/assets/campaigns/schemas.py): 열 편까지, 같은 시나리오는 한 번, 편의 이름은 30자까지(비우면 시나리오의 제목).
// 둘 이상인지, 시나리오마다 게시한 판이 있는지는 게시할 때 본다(게시 점검). 초안은 편을 비워 두어도 된다.

import type { AssetSummary, CampaignDetail, CampaignEpisodeBody } from '../../../../api/types';

export const CAMPAIGN_MAX_EPISODES = 10;
export const EPISODE_TITLE_MAX = 30;

export type EpisodeDraft = {
  scenarioId: string;
  /** 편의 이름. 비우면 시나리오의 제목이다 */
  title: string;
  /** 시나리오의 지금 제목 */
  scenarioTitle: string;
  /** 시나리오를 게시한 마지막 판 번호. 게시한 판이 없으면 null, 막 더해 아직 저장하지 않아 모르면 undefined */
  lastVersion: number | null | undefined;
};

export function episodesDraft(campaign: CampaignDetail): EpisodeDraft[] {
  return campaign.episodes.map((episode) => ({
    scenarioId: episode.scenario_id,
    title: episode.title,
    scenarioTitle: episode.scenario_title,
    lastVersion: episode.last_version,
  }));
}

/** 그 편을 delta 만큼 옮긴 목록. 끝을 넘으면 그대로다 */
export function moveEpisode(episodes: EpisodeDraft[], index: number, delta: number): EpisodeDraft[] {
  const target = index + delta;
  if (index < 0 || index >= episodes.length || target < 0 || target >= episodes.length) return episodes;
  const moved = [...episodes];
  const [episode] = moved.splice(index, 1);
  moved.splice(target, 0, episode as EpisodeDraft);
  return moved;
}

export function removeEpisode(episodes: EpisodeDraft[], index: number): EpisodeDraft[] {
  return episodes.filter((_, at) => at !== index);
}

export function renameEpisode(episodes: EpisodeDraft[], index: number, title: string): EpisodeDraft[] {
  return episodes.map((episode, at) => (at === index ? { ...episode, title } : episode));
}

/**
 * 시나리오를 마지막 편으로 더한 목록. 가득 찼거나 이미 있으면 그대로다.
 * 게시한 판 번호는 저장하면 서버가 알려 준다. 그때까지 모른다(undefined)
 */
export function addEpisode(episodes: EpisodeDraft[], scenario: AssetSummary): EpisodeDraft[] {
  if (episodes.length >= CAMPAIGN_MAX_EPISODES || episodes.some((episode) => episode.scenarioId === scenario.id)) return episodes;
  return [...episodes, { scenarioId: scenario.id, title: '', scenarioTitle: scenario.title, lastVersion: undefined }];
}

/** 아직 편에 넣지 않은 내 시나리오 */
export function unusedScenarios(scenarios: AssetSummary[], episodes: EpisodeDraft[]): AssetSummary[] {
  const used = new Set(episodes.map((episode) => episode.scenarioId));
  return scenarios.filter((scenario) => !used.has(scenario.id));
}

/** 이름이 너무 긴 편의 차례(0 부터). 없으면 빈 목록 */
export function longTitles(episodes: EpisodeDraft[]): number[] {
  return episodes.flatMap((episode, index) => (episode.title.trim().length > EPISODE_TITLE_MAX ? [index] : []));
}

/** 편의 차례가 바뀌었거나 무엇이든 고쳤는가 */
export function episodesChanged(before: EpisodeDraft[], after: EpisodeDraft[]): boolean {
  return JSON.stringify(toEpisodesBody(before)) !== JSON.stringify(toEpisodesBody(after));
}

/** 보낼 편들. 차례가 편의 차례다. 이름은 앞뒤 공백을 뗀다 */
export function toEpisodesBody(episodes: EpisodeDraft[]): CampaignEpisodeBody[] {
  return episodes.map((episode) => ({ scenario_id: episode.scenarioId, title: episode.title.trim() }));
}
