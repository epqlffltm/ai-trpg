// web/apps/web/src/format/usage.ts
// 카드에 붙이는 쓰인 수(#985)와 관심의 수(#989). "테이블 1.2K", "대화 12.3K", "♥ 12" 같은 것이다. 0 이면 싣지 않는다.
// 수는 서버가 준 모든 기간의 것이다(캐릭터와 세계관은 한 시간까지 늦다). DOM 을 모르는 순수한 함수다.

import { compactCount } from './count';

/** 시작한 것을 부르는 말. TRPG 는 테이블, chat 은 대화, story 는 이야기다 */
export type UsageNoun = '테이블' | '대화' | '이야기';

/** 서버가 아직 칸을 주지 않으면(먼저 올라간 화면) 0 으로 본다 */
export function usageTags(noun: UsageNoun, starts: number | undefined, hearts: number | undefined): string[] {
  const tags: string[] = [];
  if (starts) tags.push(`${noun} ${compactCount(starts)}`);
  if (hearts) tags.push(`♥ ${compactCount(hearts)}`);
  return tags;
}
