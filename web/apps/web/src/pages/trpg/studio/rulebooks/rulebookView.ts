// web/apps/web/src/pages/trpg/studio/rulebooks/rulebookView.ts
// 룰북 화면(B9)이 보일 글. 순수한 함수다. 방어 규칙의 이름과 하는 일은 서버의 app/engine/armor.py 와 같은 말로 적는다.

import type { Ability, Armor, RulebookTemplate, RulebookTemplates } from '../../../../api/types';
import type { ArmorChoice } from './rulebookForm';

type ArmorText = { label: string; description: string };

export const ARMOR_CHOICES: ArmorChoice[] = ['none', 'ac', 'reduce', 'save'];

const ARMOR_TEXTS: Record<ArmorChoice, ArmorText> = {
  none: { label: '방어구가 막지 않음', description: '방어구와 맞은 부위를 쓰지 않습니다. 무기의 공격 보정은 듭니다.' },
  ac: { label: '맞히기 어렵게', description: '맞은 부위의 방어만큼 맞히는 목표값이 오릅니다(D&D 5판의 AC).' },
  reduce: { label: '피해를 깎음', description: '맞은 부위의 방어만큼 피해에서 뺍니다. 0 아래로는 가지 않습니다(WFRP).' },
  save: { label: '세이브로 막음', description: '맞은 뒤 맞는 쪽이 주사위를 굴려, 눈 + 방어가 세이브의 목표값 이상이면 막습니다(워해머 40K).' },
};

export function armorText(choice: ArmorChoice): ArmorText {
  return ARMOR_TEXTS[choice];
}

/** 한 줄 요약. "세이브로 막음 · 목표 7 · 관통 기준 10", 막지 않으면 "방어구가 막지 않음" */
export function armorSummary(armor: Armor | null): string {
  if (!armor) return ARMOR_TEXTS.none.label;
  const target = armor.mode === 'save' && armor.save_target != null ? ` · 목표 ${armor.save_target}` : '';
  return `${ARMOR_TEXTS[armor.mode].label}${target} · 관통 기준 ${armor.pierce_base}`;
}

/** 템플릿의 보일 이름. 목록에 없으면 이름표 그대로 */
export function templateName(templates: RulebookTemplates | undefined, key: string): string {
  return templates?.items.find((template) => template.key === key)?.name ?? key;
}

/** 템플릿의 서술 분위기(#616). 없으면 null */
export function templateTone(template: RulebookTemplate): string | null {
  return template.rules.narration?.tone || null;
}

/** 그 템플릿의 판정의 주사위의 면 수. 없으면 null */
/** 그 템플릿의 능력치들(#804, 수치의 최대에 쓴다). 모르는 템플릿이면 빈 목록 */
export function templateAbilities(templates: RulebookTemplates, key: string): Ability[] {
  return templates.items.find((template) => template.key === key)?.rules.abilities ?? [];
}

export function templateDie(templates: RulebookTemplates, key: string): number | null {
  return templates.items.find((template) => template.key === key)?.rules.die ?? null;
}
