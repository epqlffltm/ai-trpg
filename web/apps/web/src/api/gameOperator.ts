// web/apps/web/src/api/gameOperator.ts
// 게임 서버의 운영자 제재(E4, #392). 운영자(토큰의 roles 의 operator)만 부른다. 아니면 모든 주소가 404 다.
//   - 시나리오 제재: 공개 중인 판의 공개를 내리고, 그 판은 다시 공개하지 못한다. 공개 중이 아니면 409 not_published
//     제작자의 제재가 정해진 수(기본 3)에 닿으면 저절로 공개 금지가 된다(publishing_banned)
//   - 공개 금지와 풀기: 한 사람이 어떤 판도 공개하지 못한다. 플레이는 막지 않는다. 409 already_banned, not_banned
// 모두 본문의 사유(1~200자, 공백만은 안 됨)를 감사 기록에 남긴다. 당사자의 알림에는 사유와 운영자를 싣지 않는다.
// 409 의 까닭은 본문의 reason 이고 ApiError.code 로 읽힌다. 타입은 생성 타입에서 바로 가져온다.

import type { components } from './generated/trpg';
import { apiRequest } from './http';

type Schemas = components['schemas'];
export type SanctionResult = Schemas['SanctionOut'];
export type PublishingBan = Schemas['PublishingBanOut'];

const ADMIN = '/api/v1/game/admin';

export function sanctionScenario(scenarioId: string, reason: string): Promise<SanctionResult> {
  return apiRequest<SanctionResult>(`${ADMIN}/scenarios/${encodeURIComponent(scenarioId)}/sanction`, { method: 'POST', body: { reason } });
}

export function banPublisher(userId: string, reason: string): Promise<PublishingBan> {
  return apiRequest<PublishingBan>(`${ADMIN}/users/${encodeURIComponent(userId)}/publishing-ban`, { method: 'POST', body: { reason } });
}

export function liftPublishingBan(userId: string, reason: string): Promise<PublishingBan> {
  return apiRequest<PublishingBan>(`${ADMIN}/users/${encodeURIComponent(userId)}/publishing-ban/lift`, { method: 'POST', body: { reason } });
}
