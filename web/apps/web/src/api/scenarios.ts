// web/apps/web/src/api/scenarios.ts
// 게임 서버의 시나리오(제작 도구 B9 의 조립). 재료를 가리키고 규칙을 적어 두었다가, 게시하면 그때의 내용이 판으로 굳는다.
// 목록과 지우기는 재료가 함께 쓴다(studio.ts). 만들 때는 제목과 추천 서술 모델만 있으면 되고 나머지는 임시 저장이다.
//
// 실패(trpg-server/app/assets/scenarios/router.py):
//   - 403 code adult_content_required: 성인 확인 없이 성인용으로 만들거나 고쳤다
//   - 409 {problems}: 게시할 조건을 갖추지 못했다. 게시해 보기(publish-check)와 같은 이름들이다
//   - 422 {field: narration_model, reason: missing | not_offered}: 추천 서술 모델이 없거나 서비스 중이 아니다
//
// 소개 페이지와 공개(trpg-server/app/listings/router.py):
//   - 409 {problems: tagline_empty | genre_missing}: 공개할 조건(한줄소개, 장르)을 갖추지 못했다. 공개 중에 비워도 같다
//   - 403 code version_sanctioned | publishing_banned: 운영자가 제재한 판이거나 공개 금지 중이다(#392)
//   - 403 code adult_content_required: 성인 확인 없이 성인용을 고치거나 공개했다

import { apiRequest } from './http';
import { assetPath, assetsPath } from './studio';
import type { ListingDetail, ListingUpdate, PublishCheck, ScenarioCreate, ScenarioDetail, ScenarioUpdate, VersionDetail, VersionSummary } from './types';

function scenarioPath(scenarioId: string, rest = ''): string {
  return `${assetPath('scenarios', scenarioId)}${rest}`;
}

export function fetchScenario(scenarioId: string, signal?: AbortSignal): Promise<ScenarioDetail> {
  return apiRequest<ScenarioDetail>(scenarioPath(scenarioId), signal ? { signal } : {});
}

/** 만들 때 보내는 것. 나머지 칸은 서버가 기본으로 채운다(등급은 전체 이용가, 문체는 정통, 1일째 8시) */
export type ScenarioStart = Pick<ScenarioCreate, 'title' | 'description' | 'narration_model'>;

export function createScenario(body: ScenarioStart): Promise<ScenarioDetail> {
  return apiRequest<ScenarioDetail>(assetsPath('scenarios'), { method: 'POST', body });
}

/** 보낸 칸만 바뀐다. 목록 칸(로어북, 스타팅 …)은 보낸 목록으로 통째로 바뀐다 */
export function updateScenario(scenarioId: string, body: ScenarioUpdate): Promise<ScenarioDetail> {
  return apiRequest<ScenarioDetail>(scenarioPath(scenarioId), { method: 'PATCH', body });
}

/** 지금 게시하면 막히는 까닭 전부. 판을 만들지 않는다 */
export function fetchPublishCheck(scenarioId: string, signal?: AbortSignal): Promise<PublishCheck> {
  return apiRequest<PublishCheck>(scenarioPath(scenarioId, '/publish-check'), signal ? { signal } : {});
}

/** 판의 목록. 최근 것부터 */
export function fetchVersions(scenarioId: string, signal?: AbortSignal): Promise<VersionSummary[]> {
  return apiRequest<VersionSummary[]>(scenarioPath(scenarioId, '/versions'), signal ? { signal } : {});
}

/** 지금의 내용이 새 판으로 굳는다. 조건을 갖추지 못했으면 409 problems */
export function publishScenario(scenarioId: string, note: string): Promise<VersionDetail> {
  return apiRequest<VersionDetail>(scenarioPath(scenarioId, '/versions'), { method: 'POST', body: { note } });
}

/** 자기 시나리오의 소개 페이지와 공개 중인 판. 아직 쓰지 않았으면 빈 것이 온다 */
export function fetchOwnListing(scenarioId: string, signal?: AbortSignal): Promise<ListingDetail> {
  return apiRequest<ListingDetail>(scenarioPath(scenarioId, '/listing'), signal ? { signal } : {});
}

/** 소개 페이지를 고친다. 보낸 칸만 바뀐다. 판을 새로 내지 않아도 공개된 소개에 바로 보인다 */
export function updateListing(scenarioId: string, body: ListingUpdate): Promise<ListingDetail> {
  return apiRequest<ListingDetail>(scenarioPath(scenarioId, '/listing'), { method: 'PATCH', body });
}

/** 공개할 판을 정한다. 시나리오 하나에 공개 판은 하나다. null 이면 공개를 내린다 */
export function setPublication(scenarioId: string, version: number | null): Promise<ListingDetail> {
  return apiRequest<ListingDetail>(scenarioPath(scenarioId, '/listing/publication'), { method: 'PUT', body: { version } });
}
