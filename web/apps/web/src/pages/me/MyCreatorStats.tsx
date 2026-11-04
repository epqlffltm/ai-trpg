// web/apps/web/src/pages/me/MyCreatorStats.tsx
// 마이페이지 "만들기"의 내 작품 숫자(#991). TRPG 시나리오, chat 캐릭터, story 세계관마다 최근 7일과 모든 기간에 시작한 수,
// 가장 많이 쓰인 작품, 작품마다의 수를 보인다. "내 작품 숫자 보기"를 눌렀을 때 부른다(마이페이지는 그동안 부르지 않는다).
// 서버마다 따로 부르고 따로 실패한다(#593). 서비스를 넘어 더하지 않는다(세는 것이 테이블, 대화, 세션으로 다르다).
// 캐릭터와 세계관의 수는 한 시간마다 받아 온 것이라 받은 시각을 함께 보인다. 맨 위에 내 팔로워 수(알림 서버, #989)를 보인다.

import { Button } from '@ai-trpg/ui';
import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { useState } from 'react';
import { fetchCharacterStats, fetchScenarioStats, fetchWorldStats, type CreatorStats } from '../../api/creatorStats';
import { fetchFollowerCount } from '../../api/follows';
import { useSession } from '../../auth/useSession';
import { sessionPublicId } from '../../components/FollowButton';
import { formatDateTime } from '../../format/dateTime';

const STATS_KEY = ['creator-stats'] as const;

export function MyCreatorStats() {
  const [open, setOpen] = useState(false);
  if (!open) {
    return (
      <p>
        <Button variant="quiet" onClick={() => setOpen(true)}>
          내 작품 숫자 보기
        </Button>
      </p>
    );
  }
  return (
    <div>
      <FollowerCountLine />
      <ScenarioStatsBlock />
      <CharacterStatsBlock />
      <WorldStatsBlock />
    </div>
  );
}

/** 내 팔로워 수. 읽지 못하면 알린다. 토큰에서 내 공개 ID 를 읽지 못하면 그리지 않는다 */
function FollowerCountLine() {
  const session = useSession();
  const me = session ? sessionPublicId(session) : undefined;
  const query = useQuery({
    queryKey: ['follows', 'count', me],
    queryFn: ({ signal }) => fetchFollowerCount(me as string, signal),
    enabled: me !== undefined,
  });
  if (me === undefined || query.isPending) return null;
  if (query.isError) return <p role="alert">팔로워 수를 읽지 못했습니다.</p>;
  return <p>팔로워 {query.data.follower_count.toLocaleString('ko-KR')}명</p>;
}

function ScenarioStatsBlock() {
  const query = useQuery({ queryKey: [...STATS_KEY, 'scenarios'], queryFn: ({ signal }) => fetchScenarioStats(signal) });
  return <StatsBlock title="TRPG 시나리오" noun="테이블" query={query} />;
}

function CharacterStatsBlock() {
  const query = useQuery({ queryKey: [...STATS_KEY, 'characters'], queryFn: ({ signal }) => fetchCharacterStats(signal) });
  return <StatsBlock title="chat 캐릭터" noun="대화" query={query} />;
}

function WorldStatsBlock() {
  const query = useQuery({ queryKey: [...STATS_KEY, 'worlds'], queryFn: ({ signal }) => fetchWorldStats(signal) });
  return <StatsBlock title="story 세계관" noun="세션" query={query} />;
}

type BlockProps = { title: string; noun: string; query: UseQueryResult<CreatorStats> };

function StatsBlock({ title, noun, query }: BlockProps) {
  return (
    <section aria-label={title}>
      <h3>{title}</h3>
      <StatsBody noun={noun} query={query} />
    </section>
  );
}

function StatsBody({ noun, query }: Omit<BlockProps, 'title'>) {
  if (query.isPending) return <p className="hint">읽는 중입니다.</p>;
  if (query.isError) {
    return (
      <p role="alert">
        숫자를 읽지 못했습니다.{' '}
        <Button variant="quiet" onClick={() => void query.refetch()}>
          다시 읽기
        </Button>
      </p>
    );
  }
  const stats = query.data;
  if (stats.items.length === 0) return <p className="hint">공개한 작품이 없습니다.</p>;
  return (
    <>
      <p>
        최근 {stats.recent_days}일 {noun} {count(stats.recent)} · 모든 기간 {count(stats.total)}
      </p>
      <TopWork stats={stats} />
      <ul>
        {stats.items.map((item) => (
          <li key={item.id}>
            {item.title} — 최근 {stats.recent_days}일 {count(item.recent)} · 모든 기간 {count(item.total)}
          </li>
        ))}
      </ul>
      <RefreshedAt stats={stats} />
    </>
  );
}

/** 가장 많이 쓰인 작품. 줄은 최근의 수, 같으면 모든 수가 많은 것부터 온다. 아무도 시작하지 않았으면 보이지 않는다 */
function TopWork({ stats }: { stats: CreatorStats }) {
  const top = stats.items[0];
  if (!top || top.total === 0) return null;
  return <p>가장 많이 쓰인 작품: {top.title}</p>;
}

/** asset 서버의 수는 받아 온 시각을 함께 보인다. 시나리오는 바로 센 것이라 없다 */
function RefreshedAt({ stats }: { stats: CreatorStats }) {
  if (!('refreshed_at' in stats)) return null;
  const text = stats.refreshed_at ? `수는 한 시간마다 받아 옵니다. 마지막: ${formatDateTime(stats.refreshed_at)}` : '아직 받아 온 수가 없습니다.';
  return <p className="hint">{text}</p>;
}

function count(value: number): string {
  return `${value.toLocaleString('ko-KR')}회`;
}
