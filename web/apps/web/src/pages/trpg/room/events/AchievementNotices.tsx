// web/apps/web/src/pages/trpg/room/events/AchievementNotices.tsx
// 지금 라운드 위의 "업적을 얻었다" 알림. 방금 닫힌 라운드에 이 테이블이 받은 판의 업적을 고른다(achievementNoticeView.ts).
// 일어난 일의 끝부분(스트림으로 온 것까지)을 읽는다. 상태를 바꾸지 않는다. 업적은 엔진이 줬다.
// 닫기를 누르면 이 화면에서만 감춘다(다시 들어오면 그 라운드 동안 다시 보인다). 지난 업적은 일어난 일의 기록에 남는다.
// 그림은 앉은 테이블의 그림 주소로 받는다(TableAvatar). 업적의 그림은 판에 붙은 그림이라 앉은 사람이 받는다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import type { TableDetail } from '../../../../api/types';
import { TableAvatar } from '../../portraits/CharacterAvatar';
import { eventsQuery } from '../roomQueries';
import { receiversLine, recentAchievements, type EarnedAchievement } from './achievementNoticeView';
import { withoutReverted } from './revertedEvents';

type Props = { table: TableDetail; currentRound: number | null; nameOfMember: (userId: string) => string };

export function AchievementNotices({ table, currentRound, nameOfMember }: Props) {
  const events = useQuery(eventsQuery(table.id));
  const [closed, setClosed] = useState<ReadonlySet<string>>(() => new Set());
  if (!events.data) return null;
  const shown = recentAchievements(withoutReverted(events.data.items), currentRound, nameOfMember).filter((one) => !closed.has(one.key));
  if (shown.length === 0) return null;
  return (
    <ul className="plain-list room-notices" aria-label="얻은 업적">
      {shown.map((achievement) => (
        <li key={achievement.key}>
          <AchievementNotice tableId={table.id} achievement={achievement} onClose={() => setClosed((current) => new Set([...current, achievement.key]))} />
        </li>
      ))}
    </ul>
  );
}

type NoticeProps = { tableId: string; achievement: EarnedAchievement; onClose: () => void };

function AchievementNotice({ tableId, achievement, onClose }: NoticeProps) {
  return (
    <Notice>
      <span className="achievement-item">
        <TableAvatar tableId={tableId} portraitId={achievement.imageId} name={achievement.name} />
        <span className="achievement-item__body">
          <strong>업적을 얻었습니다: {achievement.name}</strong>
          {achievement.description ? <span>{achievement.description}</span> : null}
          <span className="hint">{receiversLine(achievement.receivers)}</span>
        </span>
        <Button variant="quiet" aria-label={`${achievement.name} 알림 닫기`} onClick={onClose}>
          닫기
        </Button>
      </span>
    </Notice>
  );
}
