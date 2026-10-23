// web/apps/web/src/pages/trpg/room/status/useEquipment.ts
// 내 캐릭터의 착용과 벗기(#276). 한 번에 하나만 보낸다. 답(바뀐 테이블)으로 테이블을 바로 바꾼다.
// 다른 사람에게는 equipment_changed 이벤트가 가고, 그 창은 이벤트로 테이블을 다시 읽는다.
// 바꿀 수 있는지(라운드가 선언을 받는 중, 서 있음)는 지금 라운드를 함께 읽어 본다(currentRoundQuery 를 함께 쓴다).

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { takeOffSlot, wearItem } from '../../../../api/tableRoom';
import type { TableDetail } from '../../../../api/types';
import { currentRoundQuery } from '../round/roundQueries';
import { tableQuery } from '../roomQueries';
import { describeEquipmentProblem, type EquipmentProblem } from './equipmentProblem';
import { canChangeEquipment } from './equipmentView';

export type Equipment = {
  /** 지금 바꿀 수 있는가. 끝난 테이블이면 단추를 두지 않는다 */
  enabled: boolean;
  busy: boolean;
  problem: EquipmentProblem | undefined;
  wear: (entryId: string, slots: string[]) => Promise<boolean>;
  takeOff: (slot: string) => Promise<boolean>;
};

export function useEquipment(table: TableDetail, myId: string | undefined): Equipment {
  const queryClient = useQueryClient();
  const round = useQuery({ ...currentRoundQuery(table.id), enabled: table.status === 'playing' });
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<EquipmentProblem | undefined>();
  const me = table.members.find((member) => member.user_id === myId);

  async function send(change: () => Promise<TableDetail>): Promise<boolean> {
    if (busy) return false;
    setBusy(true);
    setProblem(undefined);
    try {
      queryClient.setQueryData(tableQuery(table.id).queryKey, await change());
      return true;
    } catch (error) {
      const next = describeEquipmentProblem(error);
      setProblem(next);
      if (next.refresh) void queryClient.invalidateQueries({ queryKey: tableQuery(table.id).queryKey });
      return false;
    } finally {
      setBusy(false);
    }
  }

  return {
    enabled: canChangeEquipment(table, me, round.data),
    busy,
    problem,
    wear: (entryId, slots) => send(() => wearItem(table.id, entryId, slots)),
    takeOff: (slot) => send(() => takeOffSlot(table.id, slot)),
  };
}
