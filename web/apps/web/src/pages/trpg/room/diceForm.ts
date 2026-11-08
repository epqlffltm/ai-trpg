// web/apps/web/src/pages/trpg/room/diceForm.ts
// 대화창의 주사위 탭(#404)이 쓰는 순수한 함수. 빠른 단추의 주사위, 보내기 전의 검사, 최근 굴림을 고르기.
//
//   - 검사는 서버(trpg-server/app/engine/dice_notation.py)와 같은 모양과 상한으로 본다. 최종 판단은 서버가 한다(422)
//   - 최근 굴림은 이벤트(dice_rolled)에서 고른다. 응답을 따로 쌓지 않는다. 스트림이 같은 이벤트를 붙인다

import type { TableEvent } from '../../../api/types';
import { diceRollText } from './events/eventLines';

/** 빠른 단추. 서버가 받는 면 수 모두다 */
export const DICE_SHORTCUTS = ['d4', 'd6', 'd8', 'd10', 'd12', 'd20', 'd100'] as const;

const ALLOWED_SIDES = new Set([4, 6, 8, 10, 12, 20, 100]);
const MAX_COUNT = 10;
const MAX_BONUS = 100;
export const DICE_MAX_LENGTH = 16;
const NOTATION = /^(\d{1,2})?d(\d{1,3})([+-]\d{1,3})?$/;

/** 굴릴 수 있는 설명인가. 서버의 모양과 상한으로 본다 */
export function readableDice(text: string): boolean {
  const cleaned = text.trim().toLowerCase();
  if (cleaned.length > DICE_MAX_LENGTH) return false;
  const matched = NOTATION.exec(cleaned);
  if (!matched) return false;
  const count = Number(matched[1] ?? '1');
  const sides = Number(matched[2]);
  const bonus = Number(matched[3] ?? '0');
  return count >= 1 && count <= MAX_COUNT && ALLOWED_SIDES.has(sides) && Math.abs(bonus) <= MAX_BONUS;
}

export type RecentRoll = { sequence: number; who: string; text: string; mine: boolean };

/** 이벤트에서 최근 자유 굴림 몇 개. 새것이 위다. 이름은 캐릭터의 이름, 없으면 nameOf 가 준다 */
export function recentRolls(events: TableEvent[], myId: string | undefined, nameOf: (userId: string) => string, limit = 5): RecentRoll[] {
  return events
    .filter((event) => event.type === 'dice_rolled')
    .slice(-limit)
    .reverse()
    .map((event) => {
      const payload = event.payload ?? {};
      const userId = typeof payload.user_id === 'string' ? payload.user_id : (event.actor_id ?? '');
      const named = typeof payload.character_name === 'string' ? payload.character_name : null;
      return { sequence: event.sequence, who: named ?? nameOf(userId), text: diceRollText(payload), mine: userId === myId };
    });
}
