// web/apps/web/src/pages/story/storyAchievementView.ts
// 세계관 소개(D1)의 업적에 보일 것. 순수한 함수다(docs/architecture/achievements.md 의 "story").
// 업적의 차례와 공개된 이름은 세계관의 소개(asset 서버), 받은 사람의 수와 플레이한 사람의 수는 story 서버의 달성률,
// 내가 받은 때와 받은 숨긴 업적의 이름은 story 서버의 내 기록에서 온다. 셋을 업적마다 하나로 잇는다.
// 시나리오 업적(TRPG)의 줄과 같은 모양으로 만들어 그 글(achievementView.ts)을 그대로 쓴다.

import type { StoryAchievementRates, StoryAchievementRecords } from '../../api/story';
import type { PublicWorldAchievement } from '../../api/storyWorlds';

/** 업적 한 줄. 숨긴 업적을 받기 전에는 이름, 받는 법, 그림이 null 이다 */
export type StoryAchievementItem = {
  id: string;
  hidden: boolean;
  name: string | null;
  description: string | null;
  image_id: string | null;
  earned_at: string | null;
  earned_count: number;
};

/** 판의 차례로 업적마다 공개된 것, 받은 사람의 수, 내 기록을 잇는다. 받은 숨긴 업적은 받은 때의 이름과 그림이다 */
export function storyAchievementItems(
  achievements: PublicWorldAchievement[],
  rates: StoryAchievementRates | undefined,
  mine: StoryAchievementRecords | undefined,
): StoryAchievementItem[] {
  const counts = new Map((rates?.items ?? []).map((rate) => [rate.achievement_id, rate.earned_count]));
  const records = new Map((mine?.items ?? []).map((record) => [record.achievement_id, record]));
  return achievements.map((achievement) => {
    const record = records.get(achievement.id);
    const revealed = achievement.hidden && record !== undefined;
    return {
      id: achievement.id,
      hidden: achievement.hidden,
      name: revealed ? record.name : (achievement.name ?? null),
      description: revealed ? record.description : (achievement.description ?? null),
      image_id: revealed ? (record.image_id ?? null) : (achievement.image_id ?? null),
      earned_at: record?.earned_at ?? null,
      earned_count: counts.get(achievement.id) ?? 0,
    };
  });
}
