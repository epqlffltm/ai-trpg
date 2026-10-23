// web/apps/web/src/pages/trpg/room/round/declarationForm.ts
// 선언 내기의 입력과 검사. 순수한 함수다. 맞는지는 서버가 다시 본다(trpg-server/app/rounds/schemas.py 의 DeclarationUpdate).
//   - 글: 빈칸만이 아니고 1000자까지
//   - 행동: 하나를 붙이거나 붙이지 않는다. 종류마다의 칸은 action/actionDraft.ts 다
// 다시 내면 앞의 것을 통째로 바꾼다. 행동을 빼고 내면 행동도 없어진다.

import type { Declaration, DeclarationUpdate, Ruleset } from '../../../../api/types';
import { actionHint, draftFromAction, toAction, type ActionDraft } from './action/actionDraft';
import type { ActionContext } from './action/actionOptions';

export const DECLARATION_MAX = 1000;

export type DeclarationDraft = { content: string; action: ActionDraft };

export type DeclarationField = 'content' | 'action';

/** 처음 보일 입력. 낸 선언이 있으면 그것으로 채운다(고치기) */
export function initialDeclarationDraft(rules: Ruleset, mine: Declaration | undefined): DeclarationDraft {
  return { content: mine?.content ?? '', action: draftFromAction(rules, mine?.action ?? null) };
}

export function declarationHints(draft: DeclarationDraft, ctx: ActionContext): Partial<Record<DeclarationField, string>> {
  const hints: Partial<Record<DeclarationField, string>> = {};
  if (!draft.content.trim()) hints.content = '무엇을 하는지 적어 주세요.';
  else if (draft.content.length > DECLARATION_MAX) hints.content = `선언은 ${DECLARATION_MAX}자까지입니다.`;
  const action = actionHint(draft.action, ctx);
  if (action) hints.action = action;
  return hints;
}

/** 서버에 보낼 값. 행동이 없으면 action 을 보내지 않는다 */
export function toDeclarationUpdate(draft: DeclarationDraft, ctx: ActionContext): DeclarationUpdate {
  const action = toAction(draft.action, ctx);
  return action ? { content: draft.content, action } : { content: draft.content };
}
