// web/apps/web/src/pages/create/createTargets.ts
// 만들기의 입구에서 고르는 것과 그것을 새로 만드는 화면. 순수한 값과 함수다.
// 차례는 Stitch 12번의 카드 줄: TRPG(시나리오, 캠페인), 캐릭터(chat), 스토리 세계(story), 그다음 TRPG 의 재료(룰북, 세계관, 로어북, 몬스터 모음).

import type { StudioKind } from '../../api/studio';
import { studioNewPath } from '../trpg/studio/studioKinds';

export type CreateService = 'trpg' | 'chat' | 'story';

/** 카드 하나. tag 는 카드 오른쪽 위의 작은 표 */
export type CreateCard = { key: string; service: CreateService; title: string; line: string; tag: string; to: string };

/** story 의 "JSON 으로 세계관 넣기". 지금은 운영자만 연다 */
export const WORLD_IMPORT_PATH = '/story/worlds/import';

/** chat 의 캐릭터 만들기(C6) */
export const CHARACTER_NEW_PATH = '/chat/studio/characters/new';

/** story 의 세계관 만들기(D7) */
export const STORY_WORLD_NEW_PATH = '/story/studio/worlds/new';

function trpgCard(kind: StudioKind, title: string, line: string, tag: string): CreateCard {
  return { key: `trpg-${kind}`, service: 'trpg', title, line, tag, to: studioNewPath(kind) };
}

/** 첫 줄: 작품 */
export const WORK_CARDS: CreateCard[] = [
  trpgCard('scenarios', 'TRPG 시나리오', '여럿이 함께 하는 테이블의 이야기', 'TRPG'),
  trpgCard('campaigns', 'TRPG 캠페인', '시나리오를 이어 붙인 긴 모험', 'TRPG'),
  { key: 'chat', service: 'chat', title: '캐릭터', line: '1:1 로 깊이 나누는 대화', tag: '캐릭터', to: CHARACTER_NEW_PATH },
  { key: 'story', service: 'story', title: '스토리 세계', line: '선택과 사건이 이어지는 혼자의 이야기', tag: '스토리', to: STORY_WORLD_NEW_PATH },
];

/** 둘째 줄: TRPG 시나리오의 재료 */
export const MATERIAL_CARDS: CreateCard[] = [
  trpgCard('rulebooks', '룰북', '판정과 능력치의 규칙', '재료'),
  trpgCard('worlds', '세계관', '시나리오가 놓이는 곳', '재료'),
  trpgCard('lorebooks', '로어북', '작품에 잇는 지식과 설정 사전', '재료'),
  trpgCard('bestiaries', '몬스터 모음', '마주칠 적과 짐승', '재료'),
];
