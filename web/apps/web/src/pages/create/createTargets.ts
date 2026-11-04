// web/apps/web/src/pages/create/createTargets.ts
// 만들기의 입구에서 고르는 서비스와 그 제작 화면. 순수한 값과 함수다.

export type CreateTarget = 'trpg' | 'chat' | 'story';

/** 고르는 차례와 이름. 설계서의 "TRPG / chat / story" */
export const CREATE_TARGETS: { value: CreateTarget; label: string }[] = [
  { value: 'trpg', label: 'TRPG' },
  { value: 'chat', label: 'chat' },
  { value: 'story', label: 'story' },
];

const PATHS: Record<CreateTarget, string> = {
  // TRPG 의 제작 도구(B9): 시나리오, 캠페인, 재료(룰북, 세계관, 로어북, 몬스터 모음)
  trpg: '/trpg/studio',
  // chat 의 내 캐릭터(C6)
  chat: '/chat/studio/characters',
  // story 의 내 세계관
  story: '/story/studio/worlds',
};

/** 고른 서비스의 제작 화면 */
export function createTargetPath(target: CreateTarget): string {
  return PATHS[target];
}
