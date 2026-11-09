// web/apps/web/src/pages/chat/character/CharacterAchievements.tsx
// 캐릭터 소개(C2)의 "업적". 제작자가 이 캐릭터에 단 업적을 판의 차례로 보인다(docs/architecture/achievements.md 의 "chat").
//   - 업적마다 그림, 이름, 받는 법, 달성률(대화한 사람 중 받은 사람). 숨긴 업적은 받기 전에 이름과 받는 법을 가린다
//   - 로그인했으면 내가 받은 업적은 받은 날을, 아직인 것은 흐리게 보인다. 받은 숨긴 업적은 이름이 보인다
//   - 업적이 없는 캐릭터면 칸을 그리지 않는다. 달성률이나 내 기록을 읽지 못하면 그것만 빼고 보인다(다시 시도를 둔다)
// 업적을 주는 것은 chat 의 엔진이다. 화면은 읽기만 한다. 줄을 잇는 것과 글은 세계관 소개의 업적과 같다(storyAchievementView.ts).

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import type { PublicCharacterAchievement } from '../../../api/types';
import { useImageUrl } from '../../../hooks/useImageUrl';
import { storyAchievementItems, type StoryAchievementItem } from '../../story/storyAchievementView';
import { Avatar } from '../../trpg/portraits/CharacterAvatar';
import { achievementDescription, achievementName, achievementRate, earnedLine, mineLine } from '../../trpg/scenario/achievementView';
import { chatAchievementRatesQuery, chatAchievementsQuery } from '../chatQueries';

type Props = { characterId: string; achievements: PublicCharacterAchievement[]; signedIn: boolean };

export function CharacterAchievements({ characterId, achievements, signedIn }: Props) {
  const rates = useQuery({ ...chatAchievementRatesQuery(characterId), enabled: achievements.length > 0 });
  const mine = useQuery({ ...chatAchievementsQuery(characterId, signedIn), enabled: signedIn && achievements.length > 0 });
  if (achievements.length === 0) return null;
  const items = storyAchievementItems(achievements, rates.data, mine.data);
  const failed = rates.isError || mine.isError;
  return (
    <section aria-labelledby="character-achievements">
      <h2 id="character-achievements">업적</h2>
      {signedIn && mine.data ? <p className="hint">{mineLine(items)}</p> : null}
      {failed ? (
        <Notice tone="error">
          {rates.isError ? '달성률' : '내가 받은 업적'}을 불러오지 못했습니다.{' '}
          <Button
            variant="quiet"
            onClick={() => {
              if (rates.isError) void rates.refetch();
              if (mine.isError) void mine.refetch();
            }}
          >
            다시 시도
          </Button>
        </Notice>
      ) : null}
      <ul className="plain-list achievement-list" aria-label="업적">
        {items.map((item) => (
          <AchievementItem key={item.id} item={item} players={rates.data?.players ?? null} signedIn={signedIn && mine.isSuccess} />
        ))}
      </ul>
    </section>
  );
}

type ItemProps = { item: StoryAchievementItem; players: number | null; signedIn: boolean };

function AchievementItem({ item, players, signedIn }: ItemProps) {
  const image = useImageUrl(item.image_id);
  const name = achievementName(item);
  const description = achievementDescription(item);
  const earned = earnedLine(item);
  const locked = signedIn && !item.earned_at;
  return (
    <li className={locked ? 'achievement-item achievement-item--locked' : 'achievement-item'}>
      <Avatar name={name} url={image.url} />
      <div className="achievement-item__body">
        <strong>{name}</strong>
        {description ? <span>{description}</span> : null}
        {players !== null ? <span className="hint">{achievementRate(item.earned_count, players, '대화한')}</span> : null}
        {earned ? <span className="hint">{earned}</span> : null}
      </div>
    </li>
  );
}
