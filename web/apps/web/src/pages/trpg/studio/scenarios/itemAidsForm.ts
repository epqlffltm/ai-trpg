// web/apps/web/src/pages/trpg/studio/scenarios/itemAidsForm.ts
// 물건이 거드는 행동(#802, 거들기)의 입력. 순수한 함수다(서버의 ItemAid, app/engine/item_aids.py 를 따른다).
//
// - 거드는 행동은 치료, 따기, 고치기, 부수기, 넘기다. 한 물건에 같은 행동은 한 번(행동마다 한 줄, 5줄까지)
// - 보정은 0~10. 비우면 0 이다(보정 없이 도구로만 쓴다. 도구가 있어야 하는 문)
// - 굴린 뒤 물건이 어떻게 되나: 늘 하나 없어짐(붕대), 실패하면 부러짐(락픽), 안 없어짐(공구, 밧줄)
// - 장비와 소모품 모두 적는다

import type { ItemRule } from '../../../../api/types';
import { wholeNumber } from '../rulebooks/rulebookForm';

type Aid = ItemRule['aids'][number];
export type AidAct = Aid['act'];
export type AidWear = Aid['wear'];

export const AID_ACTS: AidAct[] = ['treat', 'pick', 'repair', 'force', 'cross'];
export const AID_ACT_LABELS: Record<AidAct, string> = { treat: '치료', pick: '따기', repair: '고치기', force: '부수기', cross: '넘기' };
export const AID_WEARS: AidWear[] = ['always', 'on_fail', 'never'];
export const AID_WEAR_LABELS: Record<AidWear, string> = { always: '쓰면 늘 없어짐', on_fail: '실패하면 부러짐', never: '없어지지 않음' };
export const AID_MAX_BONUS = 10;

export type AidDraft = { act: AidAct; bonus: string; wear: AidWear };

export function aidDraft(aid: Aid): AidDraft {
  return { act: aid.act, bonus: aid.bonus ? String(aid.bonus) : '', wear: aid.wear };
}

/** 새 줄. 아직 적지 않은 첫 행동이다. 다 적었으면 null */
export function newAidDraft(aids: AidDraft[]): AidDraft | null {
  const act = AID_ACTS.find((one) => !aids.some((aid) => aid.act === one));
  return act ? { act, bonus: '', wear: act === 'treat' ? 'always' : 'never' } : null;
}

/** 보낼 모양. 검사를 통과한 뒤에만 부른다 */
export function toAid(draft: AidDraft): Aid {
  return { act: draft.act, bonus: draft.bonus.trim() === '' ? 0 : Number(draft.bonus.trim()), wear: draft.wear };
}

/** 보내기 전에 알릴 것. "aid.<차례>", "aids" → 글 */
export function aidHints(aids: AidDraft[]): Record<string, string> {
  const hints: Record<string, string> = {};
  aids.forEach((one, index) => {
    if (one.bonus.trim() !== '' && wholeNumber(one.bonus, 0, AID_MAX_BONUS) === null) hints[`aid.${index}`] = `보정은 0~${AID_MAX_BONUS} 사이의 정수입니다.`;
  });
  const acts = aids.map((one) => one.act);
  if (new Set(acts).size !== acts.length) hints.aids = '한 물건에 같은 행동의 거들기를 두 번 적었습니다.';
  return hints;
}

/** 거들기 한 줄의 글. "따기 +2(실패하면 부러짐)", "넘기(없어지지 않음)" */
export function aidLine(aid: Aid): string {
  const bonus = aid.bonus ? ` +${aid.bonus}` : '';
  return `${AID_ACT_LABELS[aid.act]}${bonus}(${AID_WEAR_LABELS[aid.wear]})`;
}
