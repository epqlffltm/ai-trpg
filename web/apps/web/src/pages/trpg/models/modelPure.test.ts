// web/apps/web/src/pages/trpg/models/modelPure.test.ts
// 서술 모델과 단계 고르기(B8)의 순수한 함수. 회사별 묶음, 단계 고르기와 맞추기, 값과 바뀜과 종료의 글을 본다.

import { describe, expect, it } from 'vitest';
import type { NarrationModel } from '../../../api/types';
import {
  chosenModel,
  dayLabel,
  groupByVendor,
  inputSteps,
  modelOptionLabel,
  modelUsable,
  nextText,
  outputSteps,
  priceText,
  stepLabel,
  withInputStep,
  withModel,
} from './modelChoice';

function option(inputStep: number, outputStep: number, credits: string | null = '10', extra: Record<string, unknown> = {}) {
  return {
    input_step: inputStep,
    output_step: outputStep,
    input_tokens: [12000, 20000, 28000][inputStep] ?? 0,
    output_tokens: [1200, 2200, 3200][outputStep] ?? 0,
    credits,
    tier: 'basic',
    promo: false,
    next: null,
    ...extra,
  };
}

function model(slug: string, vendor: string, options = [option(0, 0)], extra: Record<string, unknown> = {}): NarrationModel {
  return {
    slug,
    display_name: slug.toUpperCase(),
    vendor,
    grade: 'standard',
    credits: '10',
    tier: 'basic',
    promo: false,
    next: null,
    retires_on: null,
    options,
    ...extra,
  } as unknown as NarrationModel;
}

const MODELS = [
  model('a', 'Google', [option(0, 0), option(1, 0, '15'), option(1, 1, '20')]),
  model('b', 'Google'),
  model('c', 'Z.ai', [option(0, 0), option(0, 1, '12')], { retires_on: '2026-12-01' }),
];

describe('modelChoice', () => {
  it('회사별로 묶는다. 서버의 차례를 지킨다', () => {
    expect(groupByVendor(MODELS).map((group) => [group.vendor, group.models.map((entry) => entry.slug)])).toEqual([
      ['Google', ['a', 'b']],
      ['Z.ai', ['c']],
    ]);
  });

  it('빈 값은 추천 모델이다', () => {
    expect(chosenModel(MODELS, { model: '', inputStep: 0, outputStep: 0 }, 'b')?.slug).toBe('b');
    expect(chosenModel(MODELS, { model: 'x', inputStep: 0, outputStep: 0 }, 'b')).toBeUndefined();
  });

  it('파는 단계만 고를 거리다. 입력 단계마다 함께 파는 출력 단계가 다르다', () => {
    expect(inputSteps(MODELS[0])).toEqual([
      { step: 0, tokens: 12000 },
      { step: 1, tokens: 20000 },
    ]);
    expect(outputSteps(MODELS[0], 0).map((entry) => entry.step)).toEqual([0]);
    expect(outputSteps(MODELS[0], 1).map((entry) => entry.step)).toEqual([0, 1]);
  });

  it('모델을 바꿔 그 단계가 없으면 기본 단계로, 입력 단계를 바꿔 출력 단계가 없으면 가장 낮은 것으로', () => {
    const value = { model: 'a', inputStep: 1, outputStep: 1 };
    expect(withModel(MODELS, value, 'b', null)).toEqual({ model: 'b', inputStep: 0, outputStep: 0 });
    expect(withModel(MODELS, { ...value, inputStep: 0, outputStep: 0 }, 'c', null)).toEqual({ model: 'c', inputStep: 0, outputStep: 0 });
    expect(withInputStep(MODELS[0], value, 0)).toEqual({ model: 'a', inputStep: 0, outputStep: 0 });
  });

  it('값과 바뀜과 종료를 글로. 값이 없으면(free) 보이지 않는다', () => {
    expect(stepLabel(1, 20000)).toBe('1단계 · 20,000 토큰');
    expect(priceText({ credits: '120', tier: 'premium', promo: true })).toBe('1인 1라운드 120 크레딧 · 골드로만 · 행사가');
    expect(priceText({ credits: null, tier: null, promo: false })).toBeNull();
    expect(nextText({ credits: '240', tier: 'basic', promo: false, effective_at: '2026-12-01T00:00:00+09:00' })).toBe('12월 1일부터 240 크레딧');
    expect(nextText({ credits: null, tier: null, promo: false, effective_at: '2026-12-01T00:00:00+09:00' })).toBe('12월 1일부터 팔지 않음');
    expect(dayLabel('2026-01-05')).toBe('1월 5일');
    expect(modelOptionLabel(MODELS[2] as NarrationModel)).toBe('C · 표준 · 12월 1일 종료');
  });

  it('목록에 있고 그 단계를 팔면 쓸 수 있다', () => {
    expect(modelUsable(MODELS, 'a', 1, 1)).toBe(true);
    expect(modelUsable(MODELS, 'b', 1, 0)).toBe(false);
    expect(modelUsable(MODELS, 'gone', 0, 0)).toBe(false);
    expect(modelUsable(MODELS, null, 0, 0)).toBe(false);
  });
});
