// web/apps/web/src/pages/me/works/MyWorks.tsx
// 마이페이지 제작자 탭의 "내 작품"(Stitch 10번). 아래 탭 넷(캐릭터, 세계관, 시나리오·캠페인, 재료)과 탭마다의 목록.
// 캐릭터와 세계관은 공개 상태 칩(초안, 공개 중, 링크 공개, 숨겨짐)으로 거르고, 줄마다 상태와 마지막으로 고친 때, "고치기"를 단다.
// 시나리오·캠페인은 공개 상태를 서버가 주지 않아 칩 없이 목록만, 재료는 저마다의 목록으로 가는 길이다.
// 목록은 저마다의 제작 화면이 쓰는 읽기를 그대로 쓴다(앞의 한 쪽). 정렬과 쓰인 수는 아직 서버에 없다.

import { Button, ChipGroup, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { Link } from 'react-router';
import { formatDate } from '../../../format/dateTime';
import { CHARACTERS_PATH, characterPath } from '../../chat/studio/characters/characterPaths';
import { myCharactersQuery } from '../../chat/studio/characters/characterQueries';
import { WORLDS_PATH, worldPath } from '../../story/studio/worldPaths';
import { myWorldsQuery } from '../../story/studio/worldQueries';
import { kindText, studioPath } from '../../trpg/studio/studioKinds';
import { assetsQuery } from '../../trpg/studio/studioQueries';
import { filterByStatus, STATUS_CHIPS, statusLabel, workStatus, type StatusSource, type WorkStatus } from './myWorksView';

type WorksTab = 'characters' | 'worlds' | 'scenarios' | 'materials';

const TABS: { value: WorksTab; label: string }[] = [
  { value: 'characters', label: '캐릭터' },
  { value: 'worlds', label: '세계관' },
  { value: 'scenarios', label: '시나리오·캠페인' },
  { value: 'materials', label: '재료' },
];

export function MyWorks() {
  const [tab, setTab] = useState<WorksTab>('characters');
  return (
    <section className="page-section my-works" aria-labelledby="my-works-heading">
      <h2 id="my-works-heading">내 작품</h2>
      <div className="my-works__tabs" role="group" aria-label="작품의 종류">
        {TABS.map((entry) => (
          <button key={entry.value} type="button" className="ui-chip" aria-pressed={entry.value === tab} onClick={() => setTab(entry.value)}>
            {entry.label}
          </button>
        ))}
      </div>
      {tab === 'characters' ? <MyCharacters /> : null}
      {tab === 'worlds' ? <MyStoryWorlds /> : null}
      {tab === 'scenarios' ? <MyScenarios /> : null}
      {tab === 'materials' ? <MyMaterials /> : null}
    </section>
  );
}

type Work = StatusSource & { id: string; name: string; updated_at: string };

function MyCharacters() {
  const query = useInfiniteQuery(myCharactersQuery());
  const works: Work[] = query.data?.pages[0]?.items ?? [];
  return (
    <StatusWorks label="캐릭터" works={works} pathOf={(id) => characterPath(id)} allPath={CHARACTERS_PATH} pending={query.isPending} failed={query.isError} retry={() => void query.refetch()} />
  );
}

function MyStoryWorlds() {
  const query = useQuery(myWorldsQuery());
  const works: Work[] = query.data?.items ?? [];
  return <StatusWorks label="세계관" works={works} pathOf={(id) => worldPath(id)} allPath={WORLDS_PATH} pending={query.isPending} failed={query.isError} retry={() => void query.refetch()} />;
}

type StatusWorksProps = { label: string; works: Work[]; pathOf: (id: string) => string; allPath: string; pending: boolean; failed: boolean; retry: () => void };

/** 공개 상태 칩과 그것으로 거른 목록 */
function StatusWorks({ label, works, pathOf, allPath, pending, failed, retry }: StatusWorksProps) {
  const [status, setStatus] = useState<WorkStatus | undefined>(undefined);
  const shown = filterByStatus(works, status);
  return (
    <>
      <ChipGroup label="공개 상태" chips={STATUS_CHIPS} selected={status} onChange={setStatus} />
      <LoadState pending={pending} failed={failed} retry={retry} />
      {!pending && !failed && works.length === 0 ? <EmptyWorks /> : null}
      {works.length > 0 && shown.length === 0 ? <p className="empty-state">이 상태의 {label}가 없습니다.</p> : null}
      <ul className="plain-list my-works__list" aria-label={`내 ${label}`}>
        {shown.map((work) => (
          <WorkCard key={work.id} name={work.name} updatedAt={work.updated_at} to={pathOf(work.id)} badge={statusLabel(workStatus(work))} />
        ))}
      </ul>
      <p>
        <Link to={allPath}>{label} 모두 보기</Link>
      </p>
    </>
  );
}

function MyScenarios() {
  const scenarios = useInfiniteQuery(assetsQuery('scenarios'));
  const campaigns = useInfiniteQuery(assetsQuery('campaigns'));
  const items = [
    ...(scenarios.data?.pages[0]?.items ?? []).map((item) => ({ ...item, kind: 'scenarios' as const })),
    ...(campaigns.data?.pages[0]?.items ?? []).map((item) => ({ ...item, kind: 'campaigns' as const })),
  ].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  const pending = scenarios.isPending || campaigns.isPending;
  const failed = scenarios.isError || campaigns.isError;
  return (
    <>
      <LoadState
        pending={pending}
        failed={failed}
        retry={() => {
          void scenarios.refetch();
          void campaigns.refetch();
        }}
      />
      {!pending && !failed && items.length === 0 ? <EmptyWorks /> : null}
      <ul className="plain-list my-works__list" aria-label="내 시나리오와 캠페인">
        {items.map((item) => (
          <WorkCard key={`${item.kind}-${item.id}`} name={item.title} updatedAt={item.updated_at} to={studioPath(item.kind, item.id)} badge={kindText(item.kind).label} />
        ))}
      </ul>
      <p>
        <Link to={studioPath('scenarios')}>시나리오 모두 보기</Link> · <Link to={studioPath('campaigns')}>캠페인 모두 보기</Link>
      </p>
    </>
  );
}

function MyMaterials() {
  return (
    <ul className="plain-list my-works__links" aria-label="내 재료">
      {(['rulebooks', 'worlds', 'lorebooks', 'bestiaries'] as const).map((kind) => (
        <li key={kind}>
          <Link to={studioPath(kind)}>{kindText(kind).title}</Link>
        </li>
      ))}
    </ul>
  );
}

/** 작품 하나의 카드. 이름, 상태(또는 종류), 마지막으로 고친 때, "고치기" */
function WorkCard({ name, updatedAt, to, badge }: { name: string; updatedAt: string; to: string; badge: ReactNode }) {
  return (
    <li className="my-works__card">
      <p className="my-works__name">{name}</p>
      <p className="my-works__meta">
        <span className="ui-chip my-works__badge">{badge}</span>
        <span className="hint">
          <time dateTime={updatedAt}>{formatDate(updatedAt)}</time> 고침
        </span>
      </p>
      <Link to={to} className="ui-button ui-button--secondary my-works__edit" aria-label={`${name} 고치기`}>
        고치기
      </Link>
    </li>
  );
}

function LoadState({ pending, failed, retry }: { pending: boolean; failed: boolean; retry: () => void }) {
  if (pending) return <p aria-busy="true">불러오는 중</p>;
  if (!failed) return null;
  return (
    <Notice tone="error">
      불러오지 못했습니다.{' '}
      <Button variant="quiet" onClick={retry}>
        다시 시도
      </Button>
    </Notice>
  );
}

function EmptyWorks() {
  return (
    <p className="empty-state">
      아직 만든 작품이 없습니다. <Link to="/create">새로 만들기</Link>
    </p>
  );
}
