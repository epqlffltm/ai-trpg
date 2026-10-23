// web/apps/web/src/pages/trpg/studio/scenarios/questForm.ts
// 퀘스트 규칙 하나의 입력과 퀘스트 규칙 목록을 바꾸는 것(B9 퀘스트·사건 탭). 순수한 함수다.
// 퀘스트 규칙은 붙인 로어북의 사건 항목 하나가 퀘스트로서 어떤지 정한다: 처음 상태(숨김, 진행 중), 이루는 조건,
// 드러나는 조건(숨김으로 시작할 때만), 실패하는 조건, 보상(물건, 돈), 기한(분). 규칙이 없으면 숨김으로 시작하고 조건이 없다.
// 퀘스트의 성공·실패·드러남은 엔진만 정한다. 사람(방장, 서술)은 바꾸지 못한다.

import type { ItemRule, QuestMatch, QuestRule, QuestRuleBody, QuestStart } from '../../../../api/types';
import { wholeNumber } from '../rulebooks/rulebookForm';
import { conditionDrafts, conditionsHints, conditionLine, toConditions, type ConditionDraft, type Targets } from './conditionsForm';
import { MONEY_MAX } from './itemRuleForm';
import { stackDrafts, stacksHints, toStacks, type StackDraft } from './stacksForm';

export const MAX_QUESTS = 50;
export const QUEST_MAX_MINUTES = 365 * 24 * 60;

export type QuestDraft = {
  start: QuestStart;
  conditions: ConditionDraft[];
  match: QuestMatch;
  reveal: ConditionDraft[];
  revealMatch: QuestMatch;
  fail: ConditionDraft[];
  failMatch: QuestMatch;
  reward: StackDraft[];
  money: string;
  minutes: string;
};

export function questDraft(rule: QuestRule | undefined): QuestDraft {
  return {
    start: rule?.start ?? 'hidden',
    conditions: conditionDrafts(rule?.conditions ?? []),
    match: rule?.match ?? 'all',
    reveal: conditionDrafts(rule?.reveal ?? []),
    revealMatch: rule?.reveal_match ?? 'all',
    fail: conditionDrafts(rule?.fail ?? []),
    failMatch: rule?.fail_match ?? 'all',
    reward: stackDrafts(rule?.reward ?? []),
    money: String(rule?.reward_money ?? 0),
    minutes: rule?.time_limit_minutes ? String(rule.time_limit_minutes) : '',
  };
}

export type QuestHints = {
  conditions: Record<number, string>;
  reveal: Record<number, string>;
  fail: Record<number, string>;
  reward: Record<number, string>;
  /** money, minutes */
  fields: Record<string, string>;
};

export function questHints(draft: QuestDraft, entryId: string, itemRules: ItemRule[]): QuestHints {
  const fields: Record<string, string> = {};
  if (wholeNumber(draft.money, 0, MONEY_MAX) === null) fields.money = `0~${MONEY_MAX.toLocaleString('ko-KR')} 사이의 정수입니다.`;
  if (draft.minutes.trim() !== '' && wholeNumber(draft.minutes, 1, QUEST_MAX_MINUTES) === null) fields.minutes = `1~${QUEST_MAX_MINUTES} 사이의 정수입니다(1년까지).`;
  return {
    conditions: conditionsHints(draft.conditions, entryId),
    reveal: draft.start === 'hidden' ? conditionsHints(draft.reveal, entryId) : {},
    fail: conditionsHints(draft.fail, entryId),
    reward: stacksHints(
      draft.reward.map((line) => ({ ...line, wear: [] })),
      itemRules,
    ),
    fields,
  };
}

export function hasQuestHints(hints: QuestHints): boolean {
  return [hints.conditions, hints.reveal, hints.fail, hints.reward, hints.fields].some((part) => Object.keys(part).length > 0);
}

/** 보낼 규칙. 진행 중으로 시작하면 드러나는 조건을 보내지 않는다. 보상에는 착용이 없다 */
export function toQuestRule(entryId: string, draft: QuestDraft): QuestRuleBody {
  const hidden = draft.start === 'hidden';
  return {
    entry_id: entryId,
    start: draft.start,
    conditions: toConditions(draft.conditions, true),
    match: draft.match,
    reveal: hidden ? toConditions(draft.reveal, false) : [],
    reveal_match: hidden ? draft.revealMatch : 'all',
    fail: toConditions(draft.fail, false),
    fail_match: draft.failMatch,
    reward: toStacks(draft.reward.map((line) => ({ ...line, wear: [] }))),
    reward_money: Number(draft.money.trim()),
    time_limit_minutes: draft.minutes.trim() === '' ? null : Number(draft.minutes.trim()),
  };
}

export function withQuestRule(rules: QuestRule[], rule: QuestRuleBody): QuestRuleBody[] {
  return rules.some((one) => one.entry_id === rule.entry_id) ? rules.map((one) => (one.entry_id === rule.entry_id ? rule : one)) : [...rules, rule];
}

export function withoutQuestRule(rules: QuestRule[], entryId: string): QuestRuleBody[] {
  return rules.filter((one) => one.entry_id !== entryId);
}

function matchText(match: QuestMatch, count: number): string {
  return count > 1 ? (match === 'all' ? '(모두)' : '(하나라도)') : '';
}

/** 목록의 한 줄. "진행 중으로 시작 · 이룸: 구울 3마리를 쓰러뜨린다 · 보상 1줄 · 돈 30 · 기한 1440분" */
export function questLine(rule: QuestRule, targets: Targets): string {
  const parts = [rule.start === 'active' ? '진행 중으로 시작' : '숨김으로 시작'];
  if (rule.conditions.length > 0) parts.push(`이룸${matchText(rule.match, rule.conditions.length)}: ${rule.conditions.map((one) => conditionLine(one, targets)).join(', ')}`);
  else parts.push('이루는 조건 없음');
  if (rule.reveal.length > 0) parts.push(`드러남: ${rule.reveal.map((one) => conditionLine(one, targets)).join(', ')}`);
  if (rule.fail.length > 0) parts.push(`실패: ${rule.fail.map((one) => conditionLine(one, targets)).join(', ')}`);
  if (rule.reward.length > 0) parts.push(`보상 ${rule.reward.length}줄`);
  if (rule.reward_money > 0) parts.push(`돈 ${rule.reward_money}`);
  if (rule.time_limit_minutes) parts.push(`기한 ${rule.time_limit_minutes}분`);
  return parts.join(' · ');
}
