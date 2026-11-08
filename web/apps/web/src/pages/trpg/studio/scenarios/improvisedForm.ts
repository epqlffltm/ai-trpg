// web/apps/web/src/pages/trpg/studio/scenarios/improvisedForm.ts
// 즉흥 조우(B9 몬스터 탭, #254)의 입력. 서술(AI)이 무작위 조우 표에서 몬스터의 등장을 고를 수 있는 테이블 하나의 횟수다.
// 순수한 함수다. 서버의 한도(trpg-server/app/assets/models.py 의 IMPROVISED_ENCOUNTERS_MAX)와 같다.

import { wholeNumber } from '../rulebooks/rulebookForm';

export const IMPROVISED_MAX = 20;

/** 칸의 글을 보낼 횟수로. 0~20 의 정수가 아니면 null */
export function toImprovised(value: string): number | null {
  return wholeNumber(value, 0, IMPROVISED_MAX);
}

/** 보내기 전에 알릴 것. 없으면 null */
export function improvisedHint(value: string): string | null {
  return toImprovised(value) === null ? `0~${IMPROVISED_MAX} 사이의 정수로 적어 주세요. 0 이면 꺼집니다.` : null;
}

/** 지금의 설정을 한 줄로. 꺼져 있으면 "꺼짐" */
export function improvisedLine(count: number): string {
  return count === 0 ? '꺼짐' : `테이블 하나에 ${count}번까지`;
}
