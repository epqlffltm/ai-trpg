// web/apps/web/src/pages/trpg/studio/scenarios/basicsForm.ts
// 시나리오의 기본 탭(제목, 소개, 등급, 추천 서술 모델, 서술 문체, 시계)의 입력. 순수한 함수다.
// 시계의 셋(시작 날, 시작 시각, 라운드 하나의 분)은 서버가 함께 받는다. 숫자 칸은 글로 들고 있다가 보낼 때 바꾼다.

import type { ModelStatus, NarrationStyle, Rating, ScenarioDetail, ScenarioUpdate } from '../../../../api/types';
import { dayLabel } from '../../models/modelChoice';
import { DESCRIPTION_MAX, TITLE_MAX, wholeNumber } from '../rulebooks/rulebookForm';

export const CLOCK_MAX_DAY = 999;
export const ROUND_MAX_MINUTES = 7 * 24 * 60;

export type BasicsDraft = {
  title: string;
  description: string;
  rating: Rating;
  narrationModel: string;
  narrationStyle: NarrationStyle;
  startDay: string;
  startHour: string;
  roundMinutes: string;
};

export function basicsDraft(scenario: ScenarioDetail): BasicsDraft {
  return {
    title: scenario.title,
    description: scenario.description,
    rating: scenario.rating,
    narrationModel: scenario.narration_model ?? '',
    narrationStyle: scenario.narration_style,
    startDay: String(scenario.clock.start_day),
    startHour: String(scenario.clock.start_hour),
    roundMinutes: String(scenario.clock.round_minutes),
  };
}

/** 보내기 전에 알릴 것. 칸 이름(서버의 칸 이름) → 글 */
export function basicsHints(draft: BasicsDraft): Record<string, string> {
  const hints: Record<string, string> = {};
  const title = draft.title.trim();
  if (title === '') hints.title = '제목을 적어 주세요.';
  else if (title.length > TITLE_MAX) hints.title = `제목은 ${TITLE_MAX}자까지입니다.`;
  if (draft.description.length > DESCRIPTION_MAX) hints.description = `소개는 ${DESCRIPTION_MAX}자까지입니다.`;
  if (draft.narrationModel === '') hints.narration_model = '추천 서술 모델을 골라 주세요.';
  if (wholeNumber(draft.startDay, 1, CLOCK_MAX_DAY) === null) hints.start_day = `1~${CLOCK_MAX_DAY} 사이의 정수입니다.`;
  if (wholeNumber(draft.startHour, 0, 23) === null) hints.start_hour = '0~23 사이의 정수입니다.';
  if (wholeNumber(draft.roundMinutes, 1, ROUND_MAX_MINUTES) === null) {
    hints.round_minutes = `1~${ROUND_MAX_MINUTES}(7일) 사이의 정수입니다.`;
  }
  return hints;
}

/** 기본 탭의 칸만 보낸다. 힌트가 없을 때만 부른다 */
export function toBasicsBody(draft: BasicsDraft): ScenarioUpdate {
  return {
    title: draft.title.trim(),
    description: draft.description,
    rating: draft.rating,
    narration_model: draft.narrationModel,
    narration_style: draft.narrationStyle,
    clock: {
      start_day: Number(draft.startDay.trim()),
      start_hour: Number(draft.startHour.trim()),
      round_minutes: Number(draft.roundMinutes.trim()),
    },
  };
}

/** 추천 서술 모델의 상태를 알리는 글. 문제가 없으면 null. nameOf 는 모델의 보이는 이름 */
export function modelStatusText(status: ModelStatus | null, nameOf: (slug: string) => string): string | null {
  if (!status || status.state === 'ok') return null;
  const instead = status.replacement ? ` 지금 테이블을 열면 대신 쓰는 모델: ${nameOf(status.replacement)}.` : '';
  if (status.state === 'retiring') {
    const when = status.retires_on ? `${dayLabel(status.retires_on)}에` : '곧';
    return `추천 서술 모델이 ${when} 서비스를 마칩니다. 다른 모델로 바꿔 두세요.`;
  }
  return `추천 서술 모델을 지금 쓸 수 없습니다. 다른 모델을 골라 주세요.${instead}`;
}
