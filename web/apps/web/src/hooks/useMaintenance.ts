// web/apps/web/src/hooks/useMaintenance.ts
// 점검 중인지 읽는다(api/maintenance.ts). 어느 요청이 점검의 503 을 받으면 다시 그린다.

import { useSyncExternalStore } from 'react';
import { getMaintenance, subscribeMaintenance, type Maintenance } from '../api/maintenance';

export function useMaintenance(): Maintenance | null {
  return useSyncExternalStore(subscribeMaintenance, getMaintenance, getMaintenance);
}
