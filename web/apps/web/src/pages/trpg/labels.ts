// web/apps/web/src/pages/trpg/labels.ts
// 게임 서버의 값(영문의 이름)을 화면의 글로 바꾼다. 장르, 캐릭터 방식, 서술 문체, 물건의 종류와 등급, 인물의 태도의 이름은 화면이 정한다(서버는 값만 준다).

import type {
  CharacterMode,
  FriendlyFire,
  Genre,
  ItemKind,
  ItemRarity,
  NarrationStyle,
  NpcAttitude,
  RecommendedPlayers,
} from '../../api/types';

// 차례가 곧 거르는 칩의 차례다. 앞의 열한 개는 이야기의 종류, 뒤의 둘은 누구를 위한 이야기인가(화면 명세 B1)
const GENRES: Record<Genre, string> = {
  fantasy: '판타지',
  wuxia: '무협',
  urban_fantasy: '현대 판타지',
  sf: 'SF',
  apocalypse: '아포칼립스',
  horror: '호러',
  mystery: '미스터리',
  romance: '로맨스',
  slice_of_life: '일상',
  alt_history: '대체역사',
  comedy: '코미디',
  for_men: '남성향',
  for_women: '여성향',
};

const CHARACTER_MODES: Record<CharacterMode, string> = {
  pregen: '준비된 캐릭터(프리젠)',
  custom: '이름과 설명만 쓰기',
  manual: '능력치를 직접 적기',
  point_buy: '점수로 능력치 사기',
  rolled: '주사위로 굴린 점수 놓기',
};

// 값의 이름은 쓰는 기법이고, 보이는 이름은 trpg-server README 의 "추천 문체"를 따른다
const NARRATION_STYLES: Record<NarrationStyle, string> = {
  none: '지시하지 않음',
  classic: '정통',
  web_novel: '웹소설',
  hardboiled: '하드보일드',
  emotional: '여성향',
  action: '남성향',
  dopamine: '도파민',
  literary: '문학',
};

const ITEM_KINDS: Record<ItemKind, string> = { gear: '장비', consumable: '소모품' };

// 물건의 등급. 차례가 곧 낮은 것에서 높은 것이다(높을수록 훔치기 어렵다)
const RARITIES: Record<ItemRarity, string> = {
  normal: '보통',
  rare: '희귀',
  unique: '고유',
  epic: '영웅',
  legendary: '전설',
};

// 인물이 일행을 대하는 태도(#474). 차례가 곧 고르는 칸의 차례다
const ATTITUDES: Record<NpcAttitude, string> = { friendly: '우호', neutral: '중립', wary: '경계', hostile: '적대' };

export const ATTITUDE_VALUES = Object.keys(ATTITUDES) as NpcAttitude[];

// 앉은 사람끼리 해칠 수 있는 정도(#803). 차례가 곧 낮은 것에서 높은 것이다(고르는 칸의 차례)
const FRIENDLY_FIRES: Record<FriendlyFire, string> = { off: '끔', prank: '장난만', full: '다 됨' };

export const FRIENDLY_FIRE_VALUES = Object.keys(FRIENDLY_FIRES) as FriendlyFire[];

/** 동료 피해의 정도의 이름. 모르는 값(서버가 새 정도를 더했다)이면 값 그대로 */
export function friendlyFireLabel(level: string): string {
  return FRIENDLY_FIRES[level as FriendlyFire] ?? level;
}

/** 둘 중 낮은 정도. 테이블의 것과 맞는 쪽이 받아들이는 것 중 낮은 쪽이 든다(서버의 app/tables/friendly_fire.py) */
export function lowerFriendlyFire(first: FriendlyFire, second: FriendlyFire): FriendlyFire {
  return FRIENDLY_FIRE_VALUES.indexOf(first) <= FRIENDLY_FIRE_VALUES.indexOf(second) ? first : second;
}

/** 태도의 이름. 모르는 값(서버가 새 태도를 더했다)이면 null */
export function attitudeLabel(attitude: string): string | null {
  return attitude in ATTITUDES ? ATTITUDES[attitude as NpcAttitude] : null;
}

export const ITEM_KIND_VALUES = Object.keys(ITEM_KINDS) as ItemKind[];
export const RARITY_VALUES = Object.keys(RARITIES) as ItemRarity[];

export function itemKindLabel(kind: ItemKind): string {
  return ITEM_KINDS[kind];
}

export function rarityLabel(rarity: ItemRarity): string {
  return RARITIES[rarity];
}

export const GENRE_VALUES = Object.keys(GENRES) as Genre[];

/** 함께 할 인원으로 거를 수 있는 수(서버는 1~4 밖이면 422) */
export const PLAYER_COUNTS = [1, 2, 3, 4] as const;

export function genreLabel(genre: Genre): string {
  return GENRES[genre];
}

export function isGenre(value: string): value is Genre {
  return value in GENRES;
}

export function characterModeLabel(mode: CharacterMode): string {
  return CHARACTER_MODES[mode];
}

/** "2~4명", 같으면 "1명" */
export function playersLabel(players: RecommendedPlayers): string {
  return players.min === players.max ? `${players.min}명` : `${players.min}~${players.max}명`;
}

export const NARRATION_STYLE_VALUES = Object.keys(NARRATION_STYLES) as NarrationStyle[];

export function narrationStyleLabel(style: NarrationStyle): string {
  return NARRATION_STYLES[style];
}

/** 초를 "5분", "1시간", "45초" 로. null 은 "제한 없음" */
export function durationLabel(seconds: number | null): string {
  if (seconds === null) return '제한 없음';
  if (seconds % 3600 === 0) return `${seconds / 3600}시간`;
  if (seconds % 60 === 0) return `${seconds / 60}분`;
  return seconds > 60 ? `${Math.floor(seconds / 60)}분 ${seconds % 60}초` : `${seconds}초`;
}
