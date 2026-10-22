// web/apps/web/src/pages/home/ContinueRows.tsx
// 이어하기. 서비스마다 한 줄이고 서버 사이에 섞지 않는다(#593). "더 보기"는 그 서비스의 목록으로 간다.
// story 는 서버가 아직 없어 줄이 없다.

import { ListSection } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { ItemCard } from '../../components/ItemCard';
import { tableStatusLabel } from './labels';
import { listStatus } from './listStatus';
import { myConversationsQuery, myTablesQuery } from './queries';

export function ContinueRows() {
  return (
    <>
      <MyTablesRow />
      <MyConversationsRow />
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
      action={<Link to="/trpg">더 보기</Link>}
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
