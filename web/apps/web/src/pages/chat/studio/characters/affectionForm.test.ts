// web/apps/web/src/pages/chat/studio/characters/affectionForm.test.ts
// 호감도 탭(C6)의 입력: 서버와 같은 단계의 규칙, 규칙의 변화, 종류를 바꾸면 대상을 비우기, 켜고 끄기, 보낼 때의 모양.

import { describe, expect, it } from 'vitest';
import type { AssetCharacterDetail } from '../../../../api/types';
import {
  addRule,
  addStage,
  affectionDraft,
  affectionHints,
  changeRule,
  changeStage,
  hasAffectionHints,
  integerIn,
  newAffectionDraft,
  removeStage,
  STAGES_MAX,
  toAffectionBody,
  type AffectionDraft,
} from './affectionForm';

const base: AffectionDraft = newAffectionDraft();

describe('호감도', () => {
  it('정수 칸은 범위 안의 정수만', () => {
    expect([integerIn('0', 0, 100), integerIn('-20', -20, 20), integerIn('21', -20, 20), integerIn('1.5', 0, 9), integerIn('', 0, 9)]).toEqual([
      0,
      -20,
      null,
      null,
      null,
    ]);
  });

  it('단계는 0 에서 시작하고 경계가 커지며 이름이 겹치지 않는다', () => {
    const stages = [
      { name: '처음', at: '5' },
      { name: '', at: '10' },
      { name: '처음', at: '20' },
      { name: '친구', at: '30' },
      { name: '연인', at: '101' },
      { name: '가'.repeat(21), at: '90' },
    ];
    const hints = affectionHints({ ...base, stages }).stages;
    expect(hints[0]).toMatch(/0 에서 시작/);
    expect(hints[1]).toMatch(/이름을 적어/);
    expect(hints[2]).toMatch(/같은 이름/);
    expect(hints[3]).toBeUndefined();
    expect(hints[4]).toMatch(/0~100/);
    expect(hints[5]).toMatch(/20자/);
    expect(affectionHints({ ...base, stages: [{ name: 'a', at: '0' }, { name: 'b', at: '0' }] }).stages[1]).toMatch(/커야/);
  });

  it('단계를 더하면 경계를 10 크게, 하나는 남긴다', () => {
    expect(addStage(base).stages.at(-1)).toEqual({ name: '', at: '10' });
    expect(addStage({ ...base, stages: [{ name: 'a', at: '95' }] }).stages.at(-1)?.at).toBe('100');
    const full = { ...base, stages: Array.from({ length: STAGES_MAX }, (_, i) => ({ name: `s${i}`, at: String(i * 10) })) };
    expect(addStage(full)).toBe(full);
    expect(removeStage(base, 0)).toBe(base);
  });

  it('규칙은 대상을 골라야 하고 변화는 0 이 아닌 -20~20', () => {
    const draft = addRule(base, 'rule-a');
    expect(affectionHints(draft).rules['rule-a']).toMatch(/물건을 골라/);
    const placed = changeRule(draft, 'rule-a', { kind: 'reach_place' });
    expect(affectionHints(placed).rules['rule-a']).toMatch(/장소를 골라/);
    const zero = changeRule(draft, 'rule-a', { target: 'i1', change: '0' });
    expect(affectionHints(zero).rules['rule-a']).toMatch(/0 은/);
    expect(affectionHints(changeRule(zero, 'rule-a', { change: '21' })).rules['rule-a']).toMatch(/-20~20/);
    expect(hasAffectionHints(affectionHints(changeRule(zero, 'rule-a', { change: '-3' })))).toBe(false);
  });

  it('물건과 장소 사이로 종류를 바꾸면 대상을 비운다. 물건끼리는 남긴다', () => {
    const draft = changeRule(addRule(base, 'r'), 'r', { target: 'i1' });
    expect(changeRule(draft, 'r', { kind: 'use_item' }).rules[0]?.target).toBe('i1');
    expect(changeRule(draft, 'r', { kind: 'reach_place' }).rules[0]?.target).toBe('');
  });

  it('처음 값과 모델의 크기', () => {
    expect(affectionHints({ ...base, start: '101' }).start).toMatch(/0~100/);
    expect(affectionHints({ ...base, modelStep: '21' }).modelStep).toMatch(/0~20/);
    expect(affectionHints({ ...base, enabled: false, start: 'x' })).toEqual({ stages: {}, rules: {} });
  });

  it('보낼 때의 모양. 끄면 null', () => {
    const draft = changeStage(changeRule(addRule(base, 'r'), 'r', { target: 'i1', change: '-4', once: true }), 0, { name: ' 처음 ' });
    expect(toAffectionBody(draft)).toEqual({
      affection: {
        display: 'number',
        start: 0,
        model_step: 3,
        stages: [{ name: '처음', at: 0 }],
        rules: [{ id: 'r', on: { kind: 'give_item', target: 'i1' }, change: -4, once: true }],
      },
    });
    expect(toAffectionBody({ ...draft, enabled: false })).toEqual({ affection: null });
  });

  it('받은 호감도를 칸으로. 없으면 꺼 둔 처음 모양', () => {
    expect(affectionDraft({ affection: null } as AssetCharacterDetail)).toEqual({ ...base, enabled: false });
    const affection = { display: 'stage', start: 7, model_step: 0, stages: [{ name: 'a', at: 0 }], rules: [{ id: 'r', on: { kind: 'reach_place', target: 'p' }, change: 2, once: false }] };
    expect(affectionDraft({ affection } as AssetCharacterDetail)).toEqual({
      enabled: true,
      display: 'stage',
      start: '7',
      modelStep: '0',
      stages: [{ name: 'a', at: '0' }],
      rules: [{ id: 'r', kind: 'reach_place', target: 'p', change: '2', once: false }],
    });
  });
});
