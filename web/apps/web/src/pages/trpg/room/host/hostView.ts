// web/apps/web/src/pages/trpg/room/host/hostView.ts
// 방장의 운영에서 무엇을 보일지. 순수한 함수다. 맞는지는 서버가 다시 본다.

import type { TableDetail, TableMember } from '../../../../api/types';
import { freshRoll } from '../character/characterForm';

/** 나를 뺀 앉은 사람들. 내보내기, 방장 넘기기의 대상이다 */
export function otherMembers(table: TableDetail, myId: string | undefined): TableMember[] {
  return table.members.filter((member) => member.user_id !== myId);
}

/**
 * "한 번 더 굴리기"를 줄 수 있어 보이는가. 제작자가 허락했고(reroll_allowed), 주사위 방식을 쓰고,
 * 그 사람이 지금 캐릭터를 위해 굴렸고, 아직 받지 않았을 때. 모집 중이거나, 진행 중에 캐릭터가 죽었을 때다
 */
export function canGrantReroll(table: TableDetail, member: TableMember): boolean {
  if (!table.reroll_allowed || !table.character_modes.includes('rolled')) return false;
  const roll = freshRoll(member);
  if (!roll || roll.reroll_granted) return false;
  if (table.status === 'recruiting') return true;
  return table.status === 'playing' && Boolean(member.sheet?.dead);
}
