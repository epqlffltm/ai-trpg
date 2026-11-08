// web/apps/web/src/pages/me/MyBadgesSection.tsx
// 마이페이지 설정 탭의 "활동 배지"(#193). 모든 배지를 서버의 차례로 보인다. 받은 것은 받은 날과, 아직인 것은 흐리게 받는 법과 함께.
// 배지는 본인만 본다. 보상은 없다. 읽지 못하면 다시 시도를 보인다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { fetchMyBadges } from '../../api/badges';
import { badgeStatus, earnedLine } from './badgeView';

export function MyBadgesSection() {
  const badges = useQuery({ queryKey: ['auth', 'me', 'badges'], queryFn: ({ signal }) => fetchMyBadges(signal) });
  return (
    <section className="page-section" aria-labelledby="my-badges-heading">
      <h2 id="my-badges-heading">활동 배지</h2>
      <p className="hint">출석하고, 본인인증을 하고, 친구를 초대하면 배지를 받습니다. 배지는 나만 봅니다.</p>
      {badges.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {badges.isError ? (
        <Notice tone="error">
          활동 배지를 불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void badges.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {badges.data ? (
        <>
          <p>{earnedLine(badges.data.earned, badges.data.badges.length)}</p>
          <ul className="plain-list badge-list" aria-label="활동 배지">
            {badges.data.badges.map((badge) => (
              <li key={badge.id} className={badge.earned_at ? 'badge-item' : 'badge-item badge-item--locked'}>
                <strong>{badge.name}</strong>
                <span>{badge.description}</span>
                <span className="hint">{badgeStatus(badge)}</span>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}
