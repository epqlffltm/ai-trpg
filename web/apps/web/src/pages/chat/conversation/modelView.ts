// web/apps/web/src/pages/chat/conversation/modelView.ts
// 대화의 모델 고르기에 보이는 글. 순수한 함수다. 값(credits)은 글자로 오고 계산하지 않는다. free 면 값이 없다.

import type { ChatModel } from '../../../api/types';
import { dayLabel, retireText } from '../../trpg/models/modelChoice';

const GRADE: Record<ChatModel['grade'], string> = { basic: '기본', standard: '표준', premium: '프리미엄' };

/** 회사별 묶음. 서버가 준 차례(회사, 이름표)를 지킨다 */
export function groupModels(models: ChatModel[]): { vendor: string; models: ChatModel[] }[] {
  const groups: { vendor: string; models: ChatModel[] }[] = [];
  for (const model of models) {
    const group = groups.find((entry) => entry.vendor === model.vendor);
    if (group) group.models.push(model);
    else groups.push({ vendor: model.vendor, models: [model] });
  }
  return groups;
}

/** 이 대화에 고를 수 있는 모델. 성인 등급의 대화면 성인 대화에 쓸 수 있는 것만 */
export function modelsFor(models: ChatModel[], rating: string): ChatModel[] {
  return rating === 'adult' ? models.filter((model) => model.allows_adult) : models;
}

/** "표준 · 말 한 번 80 크레딧 · 골드로만 · 12월 1일부터 120 크레딧 · 12월 21일 종료" */
export function modelLine(model: ChatModel): string {
  return [GRADE[model.grade], priceLine(model), nextLine(model.next), retireText(model.retires_on)].filter(Boolean).join(' · ');
}

function priceLine(model: Pick<ChatModel, 'credits' | 'tier' | 'promo'>): string | null {
  if (!model.credits) return null;
  return [`말 한 번 ${model.credits} 크레딧`, model.tier === 'premium' ? '골드로만' : null, model.promo ? '행사가' : null].filter(Boolean).join(' · ');
}

function nextLine(next: ChatModel['next']): string | null {
  if (!next) return null;
  const date = dayLabel(next.effective_at);
  return next.credits === null ? `${date}부터 팔지 않음` : `${date}부터 ${next.credits} 크레딧${next.promo ? '(행사가)' : ''}`;
}
