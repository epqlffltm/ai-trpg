// web/apps/web/src/pages/story/studio/worldPublishText.ts
// 세계관의 게시를 막는 것(problems)과 알리는 것(warnings)을 글로. 막는 것은 고칠 탭도 가리킨다. 순수한 함수다.
// 이름은 asset-server/app/worlds/publishing.py 의 Problem, Warning 이다. 모르는 이름은 이름을 그대로 보인다.
// JSON 으로 세계관 넣기(import)도 같은 글을 쓴다.

import type { WorldTab } from './worldTabs';

type Line = { text: string; tab?: WorldTab };

const PROBLEMS: Record<string, Line> = {
  start_place_missing: { text: '장소가 없거나 시작 장소를 고르지 않았습니다.', tab: 'progress' },
  start_slot_missing: { text: '시작 시간대가 없는 시간대입니다.', tab: 'progress' },
  cast_empty: { text: '인물이 하나도 없습니다.', tab: 'cast' },
  place_missing: { text: '없는 장소를 가리키는 길, 일정, 조건, 효과가 있습니다.', tab: 'map' },
  slot_missing: { text: '없는 시간대를 가리키는 배경, 일정, 조건이 있습니다.', tab: 'progress' },
  item_missing: { text: '없는 물건을 가리키는 소지품, 선물, 조건, 효과가 있습니다.', tab: 'items' },
  cast_target_missing: { text: '없는 인물을 가리키는 조건, 효과, 장면, 엔딩이 있습니다.' },
  event_missing: { text: '없는 이벤트를 가리키는 조건이나 엔딩이 있습니다.', tab: 'events' },
  stage_missing: { text: '인물에 없는 호감도의 단계를 가리킵니다(조건, 지도, 고백).', tab: 'cast' },
  character_missing: { text: '인물이 가리킨 캐릭터가 없습니다. 지웠거나 내 것이 아닙니다.', tab: 'cast' },
  character_unpublished: { text: '인물이 가리킨 캐릭터를 게시한 적이 없습니다. 캐릭터를 먼저 게시해 주세요.', tab: 'cast' },
  character_rating_too_high: { text: '전체이용가 세계관에 성인 등급 캐릭터가 있습니다.', tab: 'basics' },
  lorebook_missing: { text: '가리킨 로어북이 없습니다.', tab: 'lorebooks' },
  lorebook_unpublished: { text: '가리킨 로어북을 게시한 적이 없습니다.', tab: 'lorebooks' },
  ending_missing: { text: '고백 성공, 끝내는 고백 실패, 기한 같은 시작마다 조건이 빈 엔딩이 하나는 있어야 합니다.', tab: 'endings' },
  image_not_owned: { text: '내가 올리지 않은 그림이 있습니다.' },
};

const WARNINGS: Record<string, string> = {
  place_unreachable: '시작 장소에서 길로 닿지 않는 장소가 있습니다.',
  event_unreachable: '열릴 수 없는 이벤트가 있습니다.',
  cast_never_present: '어디에도 나오지 않는 인물이 있습니다.',
  ending_unreachable: '고를 일이 없는 엔딩이 있습니다.',
};

/** 게시를 막는 것 하나. 고칠 탭이 있으면 그 탭 */
export function worldProblemLine(name: string): Line {
  return PROBLEMS[name] ?? { text: name };
}

export function worldWarningText(name: string): string {
  return WARNINGS[name] ?? name;
}
