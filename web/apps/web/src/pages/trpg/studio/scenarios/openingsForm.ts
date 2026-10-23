// web/apps/web/src/pages/trpg/studio/scenarios/openingsForm.ts
// 시나리오의 스타팅(첫 장면의 글) 목록의 입력. 순수한 함수다.
// 5 개까지, 하나에 2,000 자. 공백뿐인 글은 서버가 받지 않는다. 목록의 차례가 테이블을 만들 때 고르는 차례다(맨 앞이 기본).

import type { ScenarioUpdate } from '../../../../api/types';

export const OPENINGS_MAX = 5;
export const OPENING_MAX_LENGTH = 2000;

/** 스타팅마다의 문제. 차례(0 부터) → 글 */
export function openingsHints(openings: string[]): Record<number, string> {
  const hints: Record<number, string> = {};
  openings.forEach((opening, index) => {
    if (opening.trim() === '') hints[index] = '비어 있습니다. 글을 쓰거나 이 스타팅을 지워 주세요.';
    else if (opening.length > OPENING_MAX_LENGTH) hints[index] = `스타팅 하나는 ${OPENING_MAX_LENGTH}자까지입니다.`;
  });
  return hints;
}

/** 빈 스타팅을 끝에 더한다. 가득 찼으면 그대로 */
export function addOpening(openings: string[]): string[] {
  return openings.length < OPENINGS_MAX ? [...openings, ''] : openings;
}

export function removeOpening(openings: string[], index: number): string[] {
  return openings.filter((_, at) => at !== index);
}

export function changeOpening(openings: string[], index: number, text: string): string[] {
  return openings.map((opening, at) => (at === index ? text : opening));
}

/** 한 칸 앞으로. 맨 앞이면 그대로 */
export function moveOpeningUp(openings: string[], index: number): string[] {
  if (index <= 0 || index >= openings.length) return openings;
  const moved = [...openings];
  [moved[index - 1], moved[index]] = [moved[index] as string, moved[index - 1] as string];
  return moved;
}

/** 스타팅 탭의 칸만 보낸다. 글은 다듬지 않는다(앞뒤의 줄바꿈도 제작자의 글이다) */
export function toOpeningsBody(openings: string[]): ScenarioUpdate {
  return { openings };
}
