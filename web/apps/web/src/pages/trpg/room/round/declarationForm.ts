// web/apps/web/src/pages/trpg/room/round/declarationForm.ts
// 선언 내기의 입력과 검사. 순수한 함수다. 맞는지는 서버가 다시 본다(trpg-server/app/rounds/schemas.py 의 DeclarationUpdate).
//   - 글: 빈칸만이 아니고 1000자까지
//   - 행동: 이번에는 판정(check) 하나만 붙인다. 능력과 난이도는 테이블의 규칙에 있는 것만 고른다
//     실패의 대가(risk), 대상(target, npc, monster), 타격(harm), 노려 치기(aim)는 다음이다(장면의 인물을 고르는 화면과 함께)
// 다시 내면 앞의 것을 통째로 바꾼다. 행동을 빼고 내면 행동도 없어진다.

import type { CheckAction, Declaration, DeclarationUpdate, Ruleset } from '../../../../api/types';

export const DECLARATION_MAX = 1000;

export type DeclarationDraft = {
  content: string;
  /** 판정을 붙이는가 */
  withCheck: boolean;
  ability: string;
  difficulty: string;
};

export type DeclarationField = 'content' | 'check';

/** 처음 보일 입력. 낸 선언이 있으면 그것으로 채운다(고치기). 판정이 아닌 행동은 이 입력으로 고치지 못한다 */
export function initialDeclarationDraft(rules: Ruleset, mine: Declaration | undefined): DeclarationDraft {
  const check = mine?.action?.kind === 'check' ? mine.action : null;
  return {
    content: mine?.content ?? '',
    withCheck: check !== null,
    ability: check?.ability ?? rules.abilities[0]?.key ?? '',
    difficulty: check?.difficulty ?? rules.default_difficulty,
  };
}

export function declarationHints(draft: DeclarationDraft, rules: Ruleset): Partial<Record<DeclarationField, string>> {
  const hints: Partial<Record<DeclarationField, string>> = {};
  if (!draft.content.trim()) hints.content = '무엇을 하는지 적어 주세요.';
  else if (draft.content.length > DECLARATION_MAX) hints.content = `선언은 ${DECLARATION_MAX}자까지입니다.`;
  if (draft.withCheck && !checkFits(draft, rules)) hints.check = '이 테이블의 규칙에 있는 능력과 난이도를 골라 주세요.';
  return hints;
}

function checkFits(draft: DeclarationDraft, rules: Ruleset): boolean {
  const ability = rules.abilities.some((entry) => entry.key === draft.ability);
  const difficulty = rules.difficulties.some((entry) => entry.key === draft.difficulty);
  return ability && difficulty;
}

/** 서버에 보낼 값. 판정을 붙이지 않으면 action 을 보내지 않는다(행동이 없는 선언) */
export function toDeclarationUpdate(draft: DeclarationDraft): DeclarationUpdate {
  if (!draft.withCheck) return { content: draft.content };
  const action: CheckAction = { kind: 'check', ability: draft.ability, difficulty: draft.difficulty, lethal: false };
  return { content: draft.content, action };
}

/** 낸 선언에 판정이 아닌 행동이 붙어 있는가. 이 입력으로 다시 내면 그 행동이 빠진다 */
export function hasOtherAction(mine: Declaration | undefined): boolean {
  return Boolean(mine?.action && mine.action.kind !== 'check');
}
