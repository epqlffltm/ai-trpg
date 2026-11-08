// web/apps/web/src/pages/trpg/scenario/ScenarioAchievements.tsx
// 시나리오 소개(B2)의 "업적". 제작자가 이 작품에 단 업적을 판의 차례로 보인다(docs/architecture/achievements.md).
//   - 업적마다 그림, 이름, 받는 법, 달성률(플레이한 사람 중 받은 사람). 숨긴 업적은 받기 전에 이름과 받는 법을 가린다
//   - 로그인했으면 내가 받은 업적은 받은 날을, 아직인 것은 흐리게 보인다
//   - 업적이 없는 시나리오면 칸을 그리지 않는다. 읽지 못하면 다시 시도를 보인다
// 업적을 주는 것은 게임 엔진이다. 화면은 읽기만 한다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { fetchScenarioAchievements, type ScenarioAchievement } from '../../../api/achievements';
import { useSession } from '../../../auth/useSession';
import { ListingAvatar } from '../portraits/CharacterAvatar';
import { achievementDescription, achievementName, achievementRate, earnedLine, mineLine } from './achievementView';

export function scenarioAchievementsKey(scenarioId: string) {
  return ['game', 'listings', scenarioId, 'achievements'] as const;
}

export function ScenarioAchievements({ scenarioId }: { scenarioId: string }) {
  const signedIn = Boolean(useSession());
  const achievements = useQuery({
    // 로그인 여부에 따라 답(내가 받은 때, 받은 숨긴 업적)이 다르다
    queryKey: [...scenarioAchievementsKey(scenarioId), signedIn],
    queryFn: ({ signal }) => fetchScenarioAchievements(scenarioId, signal),
  });
  if (achievements.isError) {
    return (
      <section aria-labelledby="scenario-achievements">
        <h2 id="scenario-achievements">업적</h2>
        <Notice tone="error">
          업적을 불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void achievements.refetch()}>
            다시 시도
          </Button>
        </Notice>
      </section>
    );
  }
  const data = achievements.data;
  if (!data || data.items.length === 0) return null;
  return (
    <section aria-labelledby="scenario-achievements">
      <h2 id="scenario-achievements">업적</h2>
      {signedIn ? <p className="hint">{mineLine(data.items)}</p> : null}
      <ul className="plain-list achievement-list" aria-label="업적">
        {data.items.map((item) => (
          <AchievementItem key={item.id} scenarioId={scenarioId} item={item} players={data.players} signedIn={signedIn} />
        ))}
      </ul>
    </section>
  );
}

type ItemProps = { scenarioId: string; item: ScenarioAchievement; players: number; signedIn: boolean };

function AchievementItem({ scenarioId, item, players, signedIn }: ItemProps) {
  const name = achievementName(item);
  const description = achievementDescription(item);
  const earned = earnedLine(item);
  const locked = signedIn && !item.earned_at;
  return (
    <li className={locked ? 'achievement-item achievement-item--locked' : 'achievement-item'}>
      <ListingAvatar scenarioId={scenarioId} portraitId={item.image_id} name={name} />
      <div className="achievement-item__body">
        <strong>{name}</strong>
        {description ? <span>{description}</span> : null}
        <span className="hint">{achievementRate(item.earned_count, players)}</span>
        {earned ? <span className="hint">{earned}</span> : null}
      </div>
    </li>
  );
}
