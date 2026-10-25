// web/apps/web/src/pages/trpg/past/PastTablePage.tsx
// 떠난 테이블 하나(B10, /trpg/tables/past/:tableId). 떠난 때까지의 이야기를 처음부터 읽는다. 로그인해야 열린다.
// 라운드의 모습으로는 읽을 수 없어(앉은 사람의 길이 404) 이벤트를 이야기로 묶어 보인다(pastStory.ts). 100 개씩 "이어 읽기".
// 판의 규칙을 모르므로 부상과 칸은 이름표 그대로 적는다. 사람의 이름은 공개 이름으로 찾는다. 기록 받기는 떠난 때까지다.

import { Button, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router';
import type { TableEvent } from '../../../api/types';
import { usePublicNames } from '../../../hooks/usePublicNames';
import { pastProblemText } from './pastProblem';
import { TranscriptButton } from '../room/transcript/TranscriptButton';
import { pastEventsQuery, pastTablesQuery } from './pastQueries';
import { pastStory, type StoryBlock } from './pastStory';

function actorsOf(events: TableEvent[]): string[] {
  return events.flatMap((event) => (event.actor_id ? [event.actor_id] : []));
}

export function PastTablePage() {
  const { tableId = '' } = useParams();
  const events = useInfiniteQuery(pastEventsQuery(tableId));
  const tables = useInfiniteQuery(pastTablesQuery());
  const items = events.data?.pages.flatMap((page) => page.items) ?? [];
  const names = usePublicNames([actorsOf(items)]);
  const past = tables.data?.pages.flatMap((page) => page.items).find((table) => table.table_id === tableId);
  const title = past?.title ?? '떠난 테이블';
  const story = pastStory(items, { table: { rules: null, currency: null }, nameOfMember: (id) => names(id) ?? '누군가', modelName: (slug) => slug });

  return (
    <main className="page page--medium">
      <p>
        <Link to="/trpg/tables/past">떠난 테이블</Link>
      </p>
      <header className="page-head">
        <h1>{title}</h1>
        <TranscriptButton tableId={tableId} title={title} past />
      </header>
      <p className="hint">떠난 때까지의 이야기입니다{past?.character_name ? ` · ${past.character_name}` : ''}. 그 뒤에 남은 사람들이 한 일은 보이지 않습니다.</p>
      {events.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {events.isError && !events.data ? (
        <Notice tone="error">
          {pastProblemText(events.error)}{' '}
          <Button variant="quiet" onClick={() => void events.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      <section className="story" aria-label="이야기">
        {story.map((block) => (
          <StoryPart key={block.key} block={block} />
        ))}
      </section>
      {events.hasNextPage || (events.isError && events.data) ? (
        <div className="load-more">
          <Button variant="secondary" busy={events.isFetchingNextPage} onClick={() => void events.fetchNextPage()}>
            {events.isError ? '다시 시도' : '이어 읽기'}
          </Button>
        </div>
      ) : null}
      {events.isSuccess && !events.hasNextPage ? <p className="hint">여기서 떠났습니다.</p> : null}
    </main>
  );
}

function StoryPart({ block }: { block: StoryBlock }) {
  switch (block.kind) {
    case 'round':
      return (
        <article className="round" aria-label={block.number !== null ? `라운드 ${block.number}` : '라운드'}>
          <h3 className="round__number">{block.number !== null ? `라운드 ${block.number}` : '라운드'}</h3>
          {block.scene ? <p className="prose scene">{block.scene}</p> : null}
        </article>
      );
    case 'narration':
      return <p className="prose scene">{block.text}</p>;
    case 'action':
      return (
        <p className="past-action">
          <strong>{block.name}</strong>
          {block.action ? <span className="hint"> · {block.action}</span> : null}: {block.content}
        </p>
      );
    case 'line':
      return <p className={block.important ? 'event-line event-line--important' : 'event-line hint'}>{block.text}</p>;
  }
}
