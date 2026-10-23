// web/apps/web/src/pages/trpg/studio/rulebooks/rulebookForm.ts
// 룰북 만들기와 고치기(B9)의 입력. 처음 값, 보내기 전의 검사, 서버에 보낼 본문. 화면을 그리지 않는 순수한 함수다.
//
//   - 규칙은 템플릿에서 온다. 고칠 수 있는 규칙은 방어 규칙(armor) 하나다(#276)
//   - 만들 때는 고른 템플릿의 방어 규칙을 채워 보인다. 템플릿을 바꾸면 방어 규칙도 그 템플릿의 것으로 돌아간다
//   - 숫자 칸은 고치는 동안 글로 둔다(비워 두거나 지우는 중일 수 있다). 보낼 때 정수로 바꾼다
//   - 세이브의 목표값은 save 방식에만 있고 반드시 있다. 다른 방식에 보내면 서버가 422 다. 그래서 save 일 때만 싣는다

import type { Armor, ArmorMode, RulebookCreate, RulebookDetail, RulebookTemplate, RulebookTemplates, RulebookUpdate, TemplateKey } from '../../../../api/types';

/** 방어 규칙의 고를 거리. none 은 방어구가 막지 않는 규칙(armor: null) */
export type ArmorChoice = 'none' | ArmorMode;

export type ArmorDraft = { armor: ArmorChoice; saveTarget: string; pierceBase: string };

export type RulebookDraft = ArmorDraft & {
  title: string;
  description: string;
  gmGuide: string;
  /** 만들 때만 고른다. 고칠 때는 보이기만 한다(규칙이 어느 템플릿에서 왔는지) */
  template: TemplateKey | string;
};

// 서버의 한도(trpg-server/app/assets/models.py, app/engine/ruleset.py 의 RULESET_MAX_NUMBER)
export const TITLE_MAX = 100;
export const DESCRIPTION_MAX = 1000;
export const GM_GUIDE_MAX = 4000;
const NUMBER_MAX = 1000;
const DEFAULT_PIERCE_BASE = 10;

/** 서버의 방어 규칙을 고칠 거리로. 없으면(null) 막지 않음 */
export function armorDraft(armor: Armor | null): ArmorDraft {
  if (!armor) return { armor: 'none', saveTarget: '', pierceBase: String(DEFAULT_PIERCE_BASE) };
  return { armor: armor.mode, saveTarget: armor.save_target == null ? '' : String(armor.save_target), pierceBase: String(armor.pierce_base) };
}

function templateOf(templates: RulebookTemplates, key: string): RulebookTemplate | undefined {
  return templates.items.find((template) => template.key === key);
}

/** 만들 때의 처음 값. 서버의 기본 템플릿과 그 방어 규칙 */
export function newRulebookDraft(templates: RulebookTemplates): RulebookDraft {
  const template = templateOf(templates, templates.default) ?? templates.items[0];
  return {
    title: '',
    description: '',
    gmGuide: '',
    template: template?.key ?? templates.default,
    ...armorDraft(template?.rules.armor ?? null),
  };
}

/** 템플릿을 바꾼다. 방어 규칙도 그 템플릿의 것으로 돌아간다 */
export function withTemplate(draft: RulebookDraft, templates: RulebookTemplates, key: TemplateKey): RulebookDraft {
  const template = templateOf(templates, key);
  return { ...draft, template: key, ...armorDraft(template?.rules.armor ?? null) };
}

/** 고칠 때의 처음 값. 지금 룰북의 것 */
export function rulebookDraft(rulebook: RulebookDetail): RulebookDraft {
  return {
    title: rulebook.title,
    description: rulebook.description,
    gmGuide: rulebook.gm_guide,
    template: rulebook.rules.template,
    ...armorDraft(rulebook.rules.armor),
  };
}

/** 칸의 글을 정수로. 정수가 아니거나 범위 밖이면 null */
export function wholeNumber(value: string, min: number, max: number): number | null {
  if (!/^\d+$/.test(value.trim())) return null;
  const number = Number(value.trim());
  return number >= min && number <= max ? number : null;
}

/** 보내기 전에 알릴 것. 칸 이름(서버의 칸 이름) → 글. 비었으면 보낼 수 있다 */
export function rulebookHints(draft: RulebookDraft): Record<string, string> {
  const hints: Record<string, string> = {};
  const title = draft.title.trim();
  if (title === '') hints.title = '제목을 적어 주세요.';
  else if (title.length > TITLE_MAX) hints.title = `제목은 ${TITLE_MAX}자까지입니다.`;
  if (draft.description.length > DESCRIPTION_MAX) hints.description = `소개는 ${DESCRIPTION_MAX}자까지입니다.`;
  if (draft.gmGuide.length > GM_GUIDE_MAX) hints.gm_guide = `진행 지침은 ${GM_GUIDE_MAX}자까지입니다.`;
  if (draft.armor === 'save' && wholeNumber(draft.saveTarget, 1, NUMBER_MAX) === null) {
    hints.save_target = `세이브의 목표값을 1~${NUMBER_MAX} 사이의 정수로 적어 주세요.`;
  }
  if (draft.armor !== 'none' && wholeNumber(draft.pierceBase, 0, NUMBER_MAX) === null) {
    hints.pierce_base = `관통의 기준값을 0~${NUMBER_MAX} 사이의 정수로 적어 주세요.`;
  }
  return hints;
}

/** 보낼 방어 규칙. 막지 않음이면 null. 검사(rulebookHints)를 지난 뒤에 부른다 */
export function toArmor(draft: ArmorDraft): Armor | null {
  if (draft.armor === 'none') return null;
  const pierceBase = wholeNumber(draft.pierceBase, 0, NUMBER_MAX) ?? DEFAULT_PIERCE_BASE;
  if (draft.armor !== 'save') return { mode: draft.armor, pierce_base: pierceBase };
  return { mode: 'save', pierce_base: pierceBase, save_target: wholeNumber(draft.saveTarget, 1, NUMBER_MAX) };
}

/** 만들 때의 본문. 방어 규칙은 늘 보낸다(바꾸지 않았으면 템플릿의 것과 같다) */
export function toRulebookCreate(draft: RulebookDraft): RulebookCreate {
  return {
    title: draft.title.trim(),
    description: draft.description,
    gm_guide: draft.gmGuide,
    template: draft.template as TemplateKey,
    armor: toArmor(draft),
  };
}

/** 고칠 때의 본문. 고칠 수 있는 칸을 모두 보낸다. 글을 비우면 빈 글로 보낸다(서버는 null 을 "보내지 않음"으로 읽는다) */
export function toRulebookUpdate(draft: RulebookDraft): RulebookUpdate {
  return { title: draft.title.trim(), description: draft.description, gm_guide: draft.gmGuide, armor: toArmor(draft) };
}
