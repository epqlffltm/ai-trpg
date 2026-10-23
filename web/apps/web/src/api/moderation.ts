// web/apps/web/src/api/moderation.ts
// 운영자의 신고 처리(E4, #678). 운영자가 아니면 모두 404 다.
//
//   - asset 서버: 캐릭터의 신고. 열린 신고를 캐릭터마다 묶어 읽고, 한 캐릭터의 신고를 한꺼번에 처리한다.
//     받아들이면(actioned) 숨긴다. 숨기기와 풀기는 따로도 한다
//   - chat 서버: 대화 속 답의 신고. 신고 하나를 보려면 사유가 있어야 하고, 볼 때마다 감사 기록이 남는다.
//     그래서 저절로 다시 읽지 않는다(화면이 사유를 받고 한 번 부른다)

import { apiRequest } from './http';
import type {
  CharacterReport,
  CharacterReportPage,
  HiddenInput,
  HiddenResult,
  MessageReportDetail,
  MessageReportPage,
  OutcomeInput,
  OutcomeResult,
} from './types';

const ASSET_ADMIN = '/api/v1/asset/admin';
const CHAT_ADMIN = '/api/v1/chat/admin';

type Paging = { limit: number; offset: number };

/** 열린 신고를 캐릭터마다 묶은 한 쪽. minor 가 있는 것이 먼저다 */
export function fetchCharacterReportGroups(paging: Paging, signal?: AbortSignal): Promise<CharacterReportPage> {
  return apiRequest<CharacterReportPage>(`${ASSET_ADMIN}/character-reports`, { query: paging, ...(signal ? { signal } : {}) });
}

/** 한 캐릭터의 신고 전부. 처리한 것까지. 신고한 사람은 싣지 않는다 */
export function fetchCharacterReports(characterId: string, signal?: AbortSignal): Promise<CharacterReport[]> {
  return apiRequest<CharacterReport[]>(`${ASSET_ADMIN}/characters/${characterId}/reports`, signal ? { signal } : {});
}

/** 한 캐릭터의 열린 신고를 모두 처리한다. actioned 면 숨긴다 */
export function decideCharacterReports(characterId: string, body: OutcomeInput): Promise<OutcomeResult> {
  return apiRequest<OutcomeResult>(`${ASSET_ADMIN}/characters/${characterId}/reports/outcome`, { method: 'PUT', body });
}

/** 캐릭터를 숨기거나 푼다 */
export function setCharacterHidden(characterId: string, body: HiddenInput): Promise<HiddenResult> {
  return apiRequest<HiddenResult>(`${ASSET_ADMIN}/characters/${characterId}/hidden`, { method: 'PUT', body });
}

/** 열린 대화 속 답의 신고 한 쪽. minor 가 먼저, 그다음 오래된 것부터. 대화의 글은 싣지 않는다 */
export function fetchMessageReports(paging: Paging, signal?: AbortSignal): Promise<MessageReportPage> {
  return apiRequest<MessageReportPage>(`${CHAT_ADMIN}/message-reports`, { query: paging, ...(signal ? { signal } : {}) });
}

/** 신고 하나와 굳힌 글. reason 은 보는 까닭이고 감사 기록에 남는다 */
export function readMessageReport(reportId: string, reason: string): Promise<MessageReportDetail> {
  return apiRequest<MessageReportDetail>(`${CHAT_ADMIN}/message-reports/${reportId}`, { query: { reason } });
}

/** 대화 속 답의 신고 하나를 처리한다. 캐릭터를 숨기는 것은 asset 의 일이다 */
export function decideMessageReport(reportId: string, body: OutcomeInput): Promise<void> {
  return apiRequest<void>(`${CHAT_ADMIN}/message-reports/${reportId}/outcome`, { method: 'PUT', body });
}
