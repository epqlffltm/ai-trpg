// web/apps/web/src/pages/me/achievements/myAchievementsView.ts
// 마이페이지의 "작품 업적"에 보일 줄. 세 서버의 응답을 한 모양으로 바꾼다. 순수한 함수다.
//   - 받았으므로 숨긴 업적도 이름이 있다. TRPG 는 판에서 뺀 업적이면 이름이 없다("지금은 볼 수 없는 업적")
//   - 작품의 이름이 없으면(가져온 판을 지웠다) "이름을 알 수 없는 작품"이다
//   - TRPG 는 지금 공개 중이고 볼 수 있을 때만 소개로 가는 길과 그림이 있다(그림은 공개된 시나리오의 주소로 받는다)
//   - story 와 chat 의 그림은 그림 저장소(asset)의 것이다. 소개로 가는 길은 늘 둔다(볼 수 없으면 그 화면이 알린다)

import type { MyChatAchievement, MyScenarioAchievement, MyStoryAchievement } from '../../../api/myAchievements';
import { formatDate } from '../../../format/dateTime';

export type AchievementService = 'trpg' | 'story' | 'chat';

export const SERVICE_TABS: { value: AchievementService; label: string }[] = [
  { value: 'trpg', label: 'TRPG' },
  { value: 'story', label: '스토리' },
  { value: 'chat', label: '채팅' },
];

/** 업적 그림을 받는 곳. TRPG 는 공개된 시나리오의 주소, 나머지는 그림 저장소다 */
export type AchievementImage = { kind: 'listing'; scenarioId: string; imageId: string } | { kind: 'asset'; imageId: string } | null;

export type MyAchievementLine = {
  key: string;
  name: string;
  description: string;
  workName: string;
  /** 작품의 소개. 없으면 null */
  workLink: string | null;
  image: AchievementImage;
  earnedAt: string;
};

export const MISSING_ACHIEVEMENT = '지금은 볼 수 없는 업적';
export const MISSING_WORK = '이름을 알 수 없는 작품';

export function scenarioLine(item: MyScenarioAchievement): MyAchievementLine {
  return {
    key: `${item.scenario_id}/${item.achievement_id}`,
    name: item.name ?? MISSING_ACHIEVEMENT,
    description: item.description ?? '',
    workName: item.scenario_title,
    workLink: item.listed ? `/trpg/scenarios/${item.scenario_id}` : null,
    image: item.listed && item.image_id ? { kind: 'listing', scenarioId: item.scenario_id, imageId: item.image_id } : null,
    earnedAt: item.earned_at,
  };
}

export function storyLine(item: MyStoryAchievement): MyAchievementLine {
  return {
    key: `${item.world_id}/${item.achievement_id}`,
    name: item.name,
    description: item.description,
    workName: item.world_name ?? MISSING_WORK,
    workLink: `/story/worlds/${item.world_id}`,
    image: item.image_id ? { kind: 'asset', imageId: item.image_id } : null,
    earnedAt: item.earned_at,
  };
}

export function chatLine(item: MyChatAchievement): MyAchievementLine {
  return {
    key: `${item.character_id}/${item.achievement_id}`,
    name: item.name,
    description: item.description,
    workName: item.character_name ?? MISSING_WORK,
    workLink: `/chat/characters/${item.character_id}`,
    image: item.image_id ? { kind: 'asset', imageId: item.image_id } : null,
    earnedAt: item.earned_at,
  };
}

/** 받은 날의 한 줄 */
export function earnedOn(line: MyAchievementLine): string {
  return `${formatDate(line.earnedAt)}에 받음`;
}

/** 받은 수의 한 줄. 서비스마다다 */
export function totalLine(service: AchievementService, total: number): string {
  const label = SERVICE_TABS.find((tab) => tab.value === service)?.label ?? '';
  return `${label}에서 받은 업적 ${total}개`;
}

/** 다음 쪽의 offset. 다 읽었으면 undefined */
export function nextAchievementOffset(read: number, total: number): number | undefined {
  return read < total ? read : undefined;
}
