// web/apps/web/src/pages/trpg/room/status/useActionShortcuts.ts
// 패널의 단추가 선언으로 갈 수 있는지. 진행 중인 테이블에서, 선언을 받는 라운드에, 내가 선언할 사람이고,
// 내 캐릭터가 행동할 수 있을 때다. 끝난 테이블이면 null(단추를 보이지 않는다).
// 지금 라운드는 라운드 화면과 같은 읽기(currentRoundQuery)를 함께 쓴다. 따로 부르지 않는다.

import { useQuery } from '@tanstack/react-query';
import type { TableDetail } from '../../../../api/types';
import { canAttachAction } from '../round/action/actionOptions';
import { useActionRequests } from '../round/action/actionRequest';
import { currentRoundQuery } from '../round/roundQueries';
import { myDeclaration } from '../round/roundView';
import type { ActionShortcuts } from './ActionButton';

export function useActionShortcuts(table: TableDetail, myId: string | undefined): ActionShortcuts {
  const round = useQuery({ ...currentRoundQuery(table.id), enabled: table.status === 'playing' });
  const { request } = useActionRequests();
  if (table.status !== 'playing') return null;
  const me = table.members.find((member) => member.user_id === myId);
  const current = round.data;
  const expected = Boolean(current && myId && (current.waiting_for.includes(myId) || myDeclaration(current, myId)));
  const enabled = Boolean(me && current?.status === 'open' && expected && canAttachAction(me));
  return { enabled, request };
}
