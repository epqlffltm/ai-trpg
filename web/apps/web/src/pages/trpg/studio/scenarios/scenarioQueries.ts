// web/apps/web/src/pages/trpg/studio/scenarios/scenarioQueries.ts
// 시나리오 고치기(B9)가 읽는 것. 시나리오 하나, 게시 점검, 판의 목록, 소개 페이지는 시나리오의 낱개 열쇠 아래에 둔다.
// 저장하면 점검만 다시 읽고(시나리오는 받은 것으로 바꾼다), 게시하면 점검과 판의 목록을 다시 읽는다.
// 소개를 고치거나 공개하면 받은 소개 페이지로 바꾼다.
// 재료를 고르는 칸은 종류마다 내 재료를 한 번에 100 개까지 읽는다(목록 열쇠 아래라 재료를 만들면 함께 무른다).

import { queryOptions } from '@tanstack/react-query';
import { fetchOwnListing, fetchPublishCheck, fetchScenario, fetchVersions } from '../../../../api/scenarios';
import { fetchAssets, type StudioKind } from '../../../../api/studio';
import { assetDetailKey, assetListKey } from '../studioQueries';

/** 재료를 고르는 칸이 한 번에 읽는 수. 서버의 한 쪽의 최대다 */
export const CHOICES_LIMIT = 100;

export function scenarioQuery(scenarioId: string) {
  return queryOptions({
    queryKey: assetDetailKey('scenarios', scenarioId),
    queryFn: ({ signal }) => fetchScenario(scenarioId, signal),
  });
}

export function publishCheckKey(scenarioId: string) {
  return [...assetDetailKey('scenarios', scenarioId), 'publish-check'] as const;
}

export function publishCheckQuery(scenarioId: string) {
  return queryOptions({
    queryKey: publishCheckKey(scenarioId),
    queryFn: ({ signal }) => fetchPublishCheck(scenarioId, signal),
  });
}

export function versionsKey(scenarioId: string) {
  return [...assetDetailKey('scenarios', scenarioId), 'versions'] as const;
}

export function versionsQuery(scenarioId: string) {
  return queryOptions({
    queryKey: versionsKey(scenarioId),
    queryFn: ({ signal }) => fetchVersions(scenarioId, signal),
  });
}

export function listingKey(scenarioId: string) {
  return [...assetDetailKey('scenarios', scenarioId), 'listing'] as const;
}

export function listingQuery(scenarioId: string) {
  return queryOptions({
    queryKey: listingKey(scenarioId),
    queryFn: ({ signal }) => fetchOwnListing(scenarioId, signal),
  });
}

/** 고를 수 있는 내 재료(룰북, 세계관, 로어북, 몬스터 모음). 최근에 만든 것부터 */
export function choicesQuery(kind: StudioKind) {
  return queryOptions({
    queryKey: [...assetListKey(kind), 'choices'],
    queryFn: ({ signal }) => fetchAssets(kind, { limit: CHOICES_LIMIT, offset: 0 }, signal),
  });
}
