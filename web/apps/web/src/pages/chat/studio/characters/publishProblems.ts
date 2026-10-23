// web/apps/web/src/pages/chat/studio/characters/publishProblems.ts
// 캐릭터의 게시 점검(GET /characters/{id}/publish-check)과 게시의 409 가 주는 문제의 이름을 화면의 글과 묶음으로 바꾼다. 순수한 함수다.
// 이름은 서버의 Problem(asset-server/app/characters/publishing.py)이다. 모르는 이름이 오면 이름을 그대로 보인다.

import type { CharacterSection } from './characterTabs';

type ProblemText = { text: string; section: CharacterSection };

const PROBLEMS: Record<string, ProblemText> = {
  start_missing: { text: '시작 상황이 하나도 없습니다.', section: 'starts' },
  place_missing: { text: '지도에 없는 장소를 가리키는 길, 배경, 시작 장소가 있습니다.', section: 'map' },
  start_place_missing: { text: '장소가 있는데 처음 있는 장소가 없습니다.', section: 'map' },
  item_missing: { text: '물건 목록에 없는 시작 소지품이 있습니다.', section: 'items' },
  affection_target_missing: { text: '호감도의 규칙이 없는 물건이나 장소를 가리킵니다.', section: 'affection' },
  scene_target_missing: { text: '이벤트 씬의 조건이 없는 장소, 물건, 호감도 단계를 가리킵니다.', section: 'images' },
  sprite_outfit_missing: { text: '물건 목록에 없는 옷을 입은 캐릭터 그림이 있습니다.', section: 'images' },
  image_not_owned: { text: '내가 올리지 않은 그림을 가리킵니다(소개 글의 그림 포함).', section: 'images' },
  lorebook_missing: { text: '붙인 로어북 가운데 지워진 것이 있습니다.', section: 'lorebooks' },
  lorebook_unpublished: { text: '붙인 로어북 가운데 아직 게시하지 않은 것이 있습니다.', section: 'lorebooks' },
};

/** 문제 하나의 글과 묶음. 모르는 이름이면 이름 그대로, 묶음은 없다 */
export function problemLine(name: string): { text: string; section: CharacterSection | null } {
  return PROBLEMS[name] ?? { text: name, section: null };
}
