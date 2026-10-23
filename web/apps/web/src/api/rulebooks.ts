// web/apps/web/src/api/rulebooks.ts
// 게임 서버의 룰북(제작 도구 B9 의 재료 하나). 모두 만든 사람 자신의 것만 읽고 쓴다. 남의 것은 있어도 404 다.
// 규칙(rules)은 직접 보내지 않는다. 만들 때 템플릿을 고르고, 방어 규칙(armor)만 만들 때와 고칠 때 고른다(#276).
// 목록과 지우기는 재료가 함께 쓴다(studio.ts).

import { apiRequest } from './http';
import { assetPath, assetsPath } from './studio';
import type { RulebookCreate, RulebookDetail, RulebookTemplates, RulebookUpdate } from './types';

const RULEBOOKS = assetsPath('rulebooks');

function rulebookPath(rulebookId: string): string {
  return assetPath('rulebooks', rulebookId);
}

/** 룰북 하나. 진행 지침과 규칙까지 */
export function fetchRulebook(rulebookId: string, signal?: AbortSignal): Promise<RulebookDetail> {
  return apiRequest<RulebookDetail>(rulebookPath(rulebookId), signal ? { signal } : {});
}

/** 만들 때 고를 수 있는 템플릿들과 그 규칙, 출처 표시(#615) */
export function fetchRulebookTemplates(signal?: AbortSignal): Promise<RulebookTemplates> {
  return apiRequest<RulebookTemplates>(`${RULEBOOKS}/templates`, signal ? { signal } : {});
}

export function createRulebook(body: RulebookCreate): Promise<RulebookDetail> {
  return apiRequest<RulebookDetail>(RULEBOOKS, { method: 'POST', body });
}

/** 보낸 칸만 바뀐다. 이미 게시한 판은 게시할 때의 규칙으로 굳어 있어 바뀌지 않는다 */
export function updateRulebook(rulebookId: string, body: RulebookUpdate): Promise<RulebookDetail> {
  return apiRequest<RulebookDetail>(rulebookPath(rulebookId), { method: 'PATCH', body });
}
