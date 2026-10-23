// web/apps/web/src/pages/trpg/studio/bestiaries/monsterForm.ts
// 몬스터 하나의 입력. 순수한 함수다. 한도는 서버의 것이다(trpg-server/app/assets/bestiaries/models.py).
// 숫자(HP, 공격, 지닌 물건)는 여기가 아니라 시나리오의 몬스터 시트가 정한다.

import type { Monster, MonsterCreate, MonsterKind } from '../../../../api/types';

export const MONSTER_NAME_MAX = 50;
export const MONSTER_CONTENT_MAX = 500;
export const BESTIARY_MAX_MONSTERS = 100;

export const MONSTER_KINDS: Record<MonsterKind, string> = {
  humanoid: '인간형',
  beast: '짐승',
  undead: '언데드',
  construct: '만들어진 것',
  other: '기타',
};

export type MonsterDraft = { name: string; kind: MonsterKind; content: string; unique: boolean };

export function newMonsterDraft(): MonsterDraft {
  return { name: '', kind: 'other', content: '', unique: false };
}

export function monsterDraft(monster: Monster): MonsterDraft {
  return { name: monster.name, kind: monster.kind, content: monster.content, unique: monster.unique };
}

/** 보내기 전에 알릴 것. 칸 이름 → 글 */
export function monsterHints(draft: MonsterDraft): Record<string, string> {
  const hints: Record<string, string> = {};
  const name = draft.name.trim();
  if (name === '') hints.name = '이름을 적어 주세요.';
  else if (name.length > MONSTER_NAME_MAX) hints.name = `이름은 ${MONSTER_NAME_MAX}자까지입니다.`;
  if (draft.content.length > MONSTER_CONTENT_MAX) hints.content = `설명은 ${MONSTER_CONTENT_MAX}자까지입니다.`;
  return hints;
}

/** 더할 때와 고칠 때 같은 본문이다 */
export function toMonsterBody(draft: MonsterDraft): MonsterCreate {
  return { name: draft.name.trim(), kind: draft.kind, content: draft.content, unique: draft.unique };
}
