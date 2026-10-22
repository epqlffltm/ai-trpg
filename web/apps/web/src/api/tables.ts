// web/apps/web/src/api/tables.ts
// 게임 서버의 테이블: 만들기(B4), 로비(B3), 들어가기(로비에서, 초대 코드로). 모두 로그인한 사람만 부른다.
// 들어가거나 만들면 서버가 테이블 하나(TableDetail)를 돌려준다. 화면은 그 id 로 테이블 방(B6)에 간다.

import { apiRequest } from './http';
import type { TableCreate, TableDetail, TablePage } from './types';

const TABLES = '/api/v1/game/tables';

/** 테이블을 만든다. 만든 사람이 방장으로 앉는다 */
export function createTable(body: TableCreate): Promise<TableDetail> {
  return apiRequest<TableDetail>(TABLES, { method: 'POST', body });
}

/** 로비의 한 쪽. 모집 중이고 자리가 남은 공개 테이블, 최근에 만든 것부터. 시나리오로 거를 수 있다 */
export function fetchLobby(
  scenarioId: string | undefined,
  page: { limit: number; offset: number },
  signal?: AbortSignal,
): Promise<TablePage> {
  return apiRequest<TablePage>(`${TABLES}/lobby`, {
    query: { ...page, scenario_id: scenarioId },
    ...(signal ? { signal } : {}),
  });
}

/** 로비에 보이는 테이블에 들어간다. 비밀번호가 걸려 있으면 보낸다 */
export function joinPublicTable(tableId: string, password: string | null): Promise<TableDetail> {
  return apiRequest<TableDetail>(`${TABLES}/${encodeURIComponent(tableId)}/join`, {
    method: 'POST',
    body: { password },
  });
}

/** 초대 코드로 들어간다. 로비에 없는 테이블에도 들어간다 */
export function joinByInvite(inviteCode: string): Promise<TableDetail> {
  return apiRequest<TableDetail>(`${TABLES}/join`, { method: 'POST', body: { invite_code: inviteCode } });
}
