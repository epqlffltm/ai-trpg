// web/apps/web/src/pages/trpg/models/modelChoice.ts
// 서술 모델과 단계 고르기(B8)의 글과 계산. 순수한 함수다. 값은 모두 서버(GET /tables/narration-models)가 준 것이다.
//
// - 모델은 회사(vendor)별로 묶는다. 서버가 회사, 보이는 이름 차례로 준다
// - 단계(#387): 입력 단계는 서술에 넣는 기억(지난 기록, 로어북)의 양, 출력 단계는 장면의 길이다.
//   지금 파는 단계만 options 에 있다. 기본 단계(0, 0)가 맨 앞이다. 모델을 바꿔 그 단계가 없으면 기본으로 돌린다
// - 값(credits)은 글자로 온다. 계산하지 않고 그대로 보인다. free 면 값이 없다(결제 서버 없는 서버)

import type { NarrationModel } from '../../../api/types';

type StepPrice = NarrationModel['options'][number];
type NextPrice = NonNullable<NarrationModel['next']>;

/** 고른 모델과 단계. model 이 빈 글이면 시나리오의 추천 모델(테이블 만들기에서만) */
export type ModelValue = { model: string; inputStep: number; outputStep: number };

const GRADE_LABELS: Record<NarrationModel['grade'], string> = { basic: '기본', standard: '표준', premium: '프리미엄' };

export function gradeLabel(grade: NarrationModel['grade']): string {
  return GRADE_LABELS[grade];
}

/** 회사별 묶음. 서버가 준 차례를 지킨다 */
export function groupByVendor(models: NarrationModel[]): { vendor: string; models: NarrationModel[] }[] {
  const groups: { vendor: string; models: NarrationModel[] }[] = [];
  for (const model of models) {
    const group = groups.find((entry) => entry.vendor === model.vendor);
    if (group) group.models.push(model);
    else groups.push({ vendor: model.vendor, models: [model] });
  }
  return groups;
}

/** 고른 값이 가리키는 모델. 빈 글이면 추천 모델. 목록에 없으면 undefined */
export function chosenModel(models: NarrationModel[], value: ModelValue, recommended: string | null): NarrationModel | undefined {
  const slug = value.model || recommended;
  return models.find((model) => model.slug === slug);
}

/** 그 모델의 그 단계. 팔지 않는 단계면 undefined */
export function findOption(model: NarrationModel | undefined, inputStep: number, outputStep: number): StepPrice | undefined {
  return (model?.options ?? []).find((option) => option.input_step === inputStep && option.output_step === outputStep);
}

/** 모델을 바꿀 때의 값. 새 모델에 지금 단계가 없으면 기본 단계(0, 0)로 */
export function withModel(models: NarrationModel[], value: ModelValue, model: string, recommended: string | null): ModelValue {
  const next = { ...value, model };
  return findOption(chosenModel(models, next, recommended), next.inputStep, next.outputStep)
    ? next
    : { model, inputStep: 0, outputStep: 0 };
}

/** 입력 단계마다 하나. [단계, 토큰] 단계 차례 */
export function inputSteps(model: NarrationModel | undefined): { step: number; tokens: number }[] {
  return uniqueSteps((model?.options ?? []).map((option) => ({ step: option.input_step, tokens: option.input_tokens })));
}

/** 그 입력 단계와 함께 파는 출력 단계들 */
export function outputSteps(model: NarrationModel | undefined, inputStep: number): { step: number; tokens: number }[] {
  const options = (model?.options ?? []).filter((option) => option.input_step === inputStep);
  return uniqueSteps(options.map((option) => ({ step: option.output_step, tokens: option.output_tokens })));
}

function uniqueSteps(steps: { step: number; tokens: number }[]): { step: number; tokens: number }[] {
  const seen = new Map<number, number>();
  for (const entry of steps) if (!seen.has(entry.step)) seen.set(entry.step, entry.tokens);
  return [...seen.entries()].sort((a, b) => a[0] - b[0]).map(([step, tokens]) => ({ step, tokens }));
}

/** 입력 단계를 바꿀 때의 값. 그 입력 단계에 지금 출력 단계가 없으면 그 입력 단계의 가장 낮은 출력 단계로 */
export function withInputStep(model: NarrationModel | undefined, value: ModelValue, inputStep: number): ModelValue {
  const outputs = outputSteps(model, inputStep);
  const outputStep = outputs.some((entry) => entry.step === value.outputStep) ? value.outputStep : (outputs[0]?.step ?? 0);
  return { ...value, inputStep, outputStep };
}

/** 단계의 짧은 이름. "기본", "2단계" */
export function stepName(step: number): string {
  return step === 0 ? '기본' : `${step}단계`;
}

/** "기본 · 12,000 토큰", "2단계 · 20,000 토큰" */
export function stepLabel(step: number, tokens: number): string {
  return `${stepName(step)} · ${tokens.toLocaleString('ko-KR')} 토큰`;
}

/** 1인 1라운드의 값. "120 크레딧 · 골드만 · 행사가". 값이 없으면(free) null */
export function priceText(price: Pick<StepPrice, 'credits' | 'tier' | 'promo'> | undefined): string | null {
  if (!price?.credits) return null;
  const parts = [`1인 1라운드 ${price.credits} 크레딧`];
  if (price.tier === 'premium') parts.push('골드로만');
  if (price.promo) parts.push('행사가');
  return parts.join(' · ');
}

/** 예약된 바뀜. "12월 1일부터 240 크레딧", 값이 null 이면 "12월 1일부터 팔지 않음". 없으면 null */
export function nextText(next: NextPrice | null | undefined): string | null {
  if (!next) return null;
  const date = dayLabel(next.effective_at);
  if (next.credits === null) return `${date}부터 팔지 않음`;
  return `${date}부터 ${next.credits} 크레딧${next.promo ? '(행사가)' : ''}`;
}

/** 은퇴일. "12월 1일 종료" */
export function retireText(retiresOn: string | null): string | null {
  return retiresOn ? `${dayLabel(retiresOn)} 종료` : null;
}

/** "2026-12-01" 이나 시각 → "12월 1일". 날짜만 오면 그 날 그대로(시간대를 타지 않는다) */
export function dayLabel(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!match) return value;
  return `${Number(match[2])}월 ${Number(match[3])}일`;
}

/** 그 모델과 단계를 지금 고를 수 있는가(목록에 있고 그 단계를 판다). 시작한 뒤에는 쓸 수 없을 때만 바꿀 수 있다 */
export function modelUsable(models: NarrationModel[], slug: string | null, inputStep: number, outputStep: number): boolean {
  return Boolean(findOption(models.find((model) => model.slug === slug), inputStep, outputStep));
}

/** 모델 고르기의 한 줄. "GLM 4.7 Flash · 표준 · 12월 1일 종료" */
export function modelOptionLabel(model: NarrationModel): string {
  return [model.display_name, gradeLabel(model.grade), retireText(model.retires_on)].filter(Boolean).join(' · ');
}
