// web/apps/web/src/api/maintenance.ts
// 점검 중인지. 프록시(nginx)는 점검 파일이 있으면 /api/ 의 모든 요청에 503 과 그 파일을 답한다(docker/nginx/maintenance).
// 본문은 {"detail", "code": "maintenance", "starts_at"?, "ends_at"?} 다. 어느 서버를 부르든 같은 답이라 한 번 받으면 점검 중으로 본다.
// 실패한 응답은 모두 toApiError(errors.ts)를 거치므로 거기서 알린다. 화면은 useMaintenance 로 읽는다(점검 화면, layout/ServiceScreens.tsx).
// 점검이 끝났는지는 사용자가 다시 시도(새로 고침)해서 안다. 새로 고치면 이 값은 처음(null)부터다.

import type { ApiError } from './errors';

export const MAINTENANCE_CODE = 'maintenance';

export type Maintenance = {
  detail: string;
  startsAt: string | null;
  endsAt: string | null;
};

let current: Maintenance | null = null;
const listeners = new Set<() => void>();

export function getMaintenance(): Maintenance | null {
  return current;
}

export function subscribeMaintenance(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** 실패한 응답 하나를 본다. 점검의 503 이면 점검 중으로 둔다 */
export function noteMaintenance(error: ApiError): void {
  if (error.status !== 503 || error.code !== MAINTENANCE_CODE || current !== null) return;
  current = { detail: error.message, startsAt: textOf(error.body.starts_at), endsAt: textOf(error.body.ends_at) };
  for (const listener of listeners) listener();
}

/** 시험에서 처음으로 되돌린다 */
export function resetMaintenance(): void {
  current = null;
  for (const listener of listeners) listener();
}

function textOf(value: unknown): string | null {
  return typeof value === 'string' && value ? value : null;
}
