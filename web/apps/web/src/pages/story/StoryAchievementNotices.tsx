// web/apps/web/src/pages/story/StoryAchievementNotices.tsx
// 세션 화면의 "업적을 얻었습니다" 알림. 행동으로 처음 받은 업적(useStoryTurn 의 earned)을 답 아래에 보인다.
// 업적을 주는 것은 story 의 엔진이다(docs/architecture/achievements.md 의 "story"). 화면은 상태를 바꾸지 않는다.
// 닫기를 누르면 그 알림만 감춘다. 다시 들어와도 다시 뜨지 않는다(받은 업적은 세계관 소개의 업적에 남는다).
// 모양은 TRPG 테이블 방의 업적 알림과 같다(.achievement-item).

import { Button, Notice } from '@ai-trpg/ui';
import { useImageUrl } from '../../hooks/useImageUrl';
import { Avatar } from '../trpg/portraits/CharacterAvatar';
import type { EarnedAchievement } from './storyTurnState';

type Props = { earned: EarnedAchievement[]; onClose: (id: string) => void };

export function StoryAchievementNotices({ earned, onClose }: Props) {
  if (earned.length === 0) return null;
  return (
    <ul className="plain-list room-notices" aria-label="얻은 업적">
      {earned.map((achievement) => (
        <li key={achievement.id}>
          <EarnedNotice achievement={achievement} onClose={() => onClose(achievement.id)} />
        </li>
      ))}
    </ul>
  );
}

function EarnedNotice({ achievement, onClose }: { achievement: EarnedAchievement; onClose: () => void }) {
  const image = useImageUrl(achievement.image_id);
  return (
    <Notice>
      <span className="achievement-item">
        <Avatar name={achievement.name} url={image.url} />
        <span className="achievement-item__body">
          <strong>업적을 얻었습니다: {achievement.name}</strong>
          {achievement.description ? <span>{achievement.description}</span> : null}
        </span>
        <Button variant="quiet" aria-label={`${achievement.name} 알림 닫기`} onClick={onClose}>
          닫기
        </Button>
      </span>
    </Notice>
  );
}
