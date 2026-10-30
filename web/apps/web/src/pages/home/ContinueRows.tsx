// web/apps/web/src/pages/home/ContinueRows.tsx
// 이어하기. 서비스마다 한 줄이고 서버 사이에 섞지 않는다(#593). "더 보기"는 그 서비스의 목록으로 간다.
// TRPG 줄에는 떠난 테이블(B10)로 가는 길도 둔다.
// story 줄은 최근 세션과 진행 한 줄(날짜, 엔딩, 후일담)이다.

import { ListSection } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { ItemCard } from '../../components/ItemCard';
import { progressLine } from '../story/storyCastView';
import { tableStatusLabel } from './labels';
import { listStatus } from './listStatus';
import { myConversationsQuery, myStorySessionsQuery, myTablesQuery, ROW_LIMIT } from './queries';

export function ContinueRows() {
  return (
    <>
      <MyTablesRow />
      <MyConversationsRow />
      <MyStorySessionsRow />
    </>
  );
}

function MyTablesRow() {
  const query = useQuery(myTablesQuery());
  const items = query.data?.items ?? [];
  return (
    <ListSection
      title="TRPG 이어하기"
      status={listStatus(query, items.length)}
      action={
        <span>
          <Link to="/trpg/tables/past">떠난 테이블</Link> · <Link to="/trpg">더 보기</Link>
        </span>
      }
      emptyText={
        <>
          앉아 있는 테이블이 없습니다. <Link to="/trpg">시나리오를 골라</Link> 첫 테이블을 만들어 보세요.
        </>
      }
      onRetry={() => void query.refetch()}
    >
      <ul className="item-grid">
        {items.map((table) => (
          <ItemCard
            key={table.id}
            to={`/trpg/tables/${table.id}`}
            title={table.title}
            meta={[tableStatusLabel(table.status), `${table.member_count}/${table.capacity}명`]}
          />
        ))}
      </ul>
    </ListSection>
  );
}

function MyConversationsRow() {
  const query = useQuery(myConversationsQuery());
  const items = query.data?.items ?? [];
  return (
    <ListSection
      title="chat 이어하기"
      status={listStatus(query, items.length)}
      action={<Link to="/chat">더 보기</Link>}
      emptyText={
        <>
          아직 대화가 없습니다. <Link to="/chat">캐릭터를 골라</Link> 말을 걸어 보세요.
        </>
      }
      onRetry={() => void query.refetch()}
    >
      <ul className="item-grid">
        {items.map((conversation) => (
          <ItemCard
            key={conversation.id}
            to={`/chat/conversations/${conversation.id}`}
            title={conversation.title}
            description={conversation.character.name}
          />
        ))}
      </ul>
    </ListSection>
  );
}

function MyStorySessionsRow() {
  const query = useQuery(myStorySessionsQuery());
  const items = (query.data?.items ?? []).slice(0, ROW_LIMIT);
  return (
    <ListSection
      title="story 이어하기"
      status={listStatus(query, items.length)}
      action={<Link to="/story">더 보기</Link>}
      emptyText={
        <>
          아직 세션이 없습니다. <Link to="/story">세계관을 골라</Link> 이야기를 시작해 보세요.
        </>
      }
      onRetry={() => void query.refetch()}
    >
      <ul className="item-grid">
        {items.map((session) => (
          <ItemCard key={session.id} to={`/story/sessions/${session.id}`} title={session.title} description={session.world.name} meta={[progressLine(session.progress)]} />
        ))}
      </ul>
    </ListSection>
  );
}
