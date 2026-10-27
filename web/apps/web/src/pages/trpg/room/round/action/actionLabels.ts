// web/apps/web/src/pages/trpg/room/round/action/actionLabels.ts
// 행동의 종류마다 보이는 이름. 선언 입력과 라운드의 기록이 함께 쓴다.

import type { ActionKind } from './actionOptions';

export const ACTION_LABELS: Record<ActionKind, string> = {
  check: '판정',
  treat: '치료',
  name: '지목',
  use: '물건 쓰기',
  throw: '던지기',
  give: '건네기',
  move: '가기',
  search: '찾기',
  rest: '쉬기',
  take: '줍기',
  put_down: '내려놓기',
  steal: '훔치기',
  loot: '빼앗기',
  wait: '기다리기',
  buy: '사기',
  sell: '팔기',
  pay: '돈 건네기',
  cover: '엄폐하기',
  lock: '잠그기',
  unlock: '열기',
  pick: '따기',
  force: '부수기',
  repair: '고치기',
  replace: '자물쇠 바꾸기',
  skill: '기술 쓰기',
};
