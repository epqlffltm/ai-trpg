// web/apps/web/src/pages/create/createTargets.ts
// 만들기의 입구에서 고르는 서비스, TRPG 의 만들 것, 그리고 고른 것을 새로 만드는 화면. 순수한 값과 함수다.

import type { StudioKind } from '../../api/studio';
import { studioNewPath } from '../trpg/studio/studioKinds';

export type CreateTarget = 'trpg' | 'chat' | 'story';

/** 고르는 차례와 이름. 설계서의 "TRPG / chat / story" */
export const CREATE_TARGETS: { value: CreateTarget; label: string }[] = [
  { value: 'trpg', label: 'TRPG' },
  { value: 'chat', label: 'chat' },
  { value: 'story', label: 'story' },
];

/** TRPG 를 고르면 나오는 "만들 것". 설계서의 "시나리오 / 캠페인 / 재료: 룰북, 세계관, 로어북, 몬스터 모음" */
export const TRPG_KINDS: { value: StudioKind; label: string }[] = [
  { value: 'scenarios', label: '시나리오' },
  { value: 'campaigns', label: '캠페인' },
  { value: 'rulebooks', label: '재료: 룰북' },
  { value: 'worlds', label: '재료: 세계관' },
  { value: 'lorebooks', label: '재료: 로어북' },
  { value: 'bestiaries', label: '재료: 몬스터 모음' },
];

/** story 의 "JSON 으로 세계관 넣기". 지금은 운영자만 연다 */
export const WORLD_IMPORT_PATH = '/story/worlds/import';

const NEW_PATHS: Record<Exclude<CreateTarget, 'trpg'>, string> = {
  // chat 의 캐릭터 만들기(C6)
  chat: '/chat/studio/characters/new',
  // story 의 세계관 만들기(D7)
  story: '/story/studio/worlds/new',
};

/** 고른 것을 새로 만드는 화면. TRPG 는 만들 것까지 골라야 한다(아니면 null) */
export function createPath(target: CreateTarget | '', kind: StudioKind | ''): string | null {
  if (target === '') return null;
  if (target !== 'trpg') return NEW_PATHS[target];
  return kind === '' ? null : studioNewPath(kind);
}
