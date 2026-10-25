// web/apps/web/src/pages/chat/character/CharacterConversations.tsx
// 이 캐릭터와의 내 대화(C2). 최근에 말한 것부터, 제목과 마지막으로 말한 때와 모델. 누르면 그 대화(C3)로 간다.
// 대화가 가져온 판보다 새 판이 공개되었으면 "새 판이 있음"만 알린다(대화는 시작할 때의 판을 그대로 쓴다).
// 로그인한 사람에게만 보인다.

import { Button, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { conversationsWithQuery } from '../chatQueries';
import { conversationLine, hasNewerVersion } from './characterView';

export function CharacterConversations({ characterId, latestVersion }: { characterId: string; latestVersion: number }) {
  const query = useInfiniteQuery(conversationsWithQuery(characterId));
  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <section className="character-conversations" aria-labelledby="character-conversations">
      <h2 id="character-conversations">이 캐릭터와의 대화</h2>
      {query.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {query.isError && items.length === 0 ? (
        <Notice tone="error">
          대화를 불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void query.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {query.isSuccess && items.length === 0 ? <p className="hint">아직 대화가 없습니다. 시작 상황을 골라 첫 대화를 시작해 보세요.</p> : null}
      {items.length > 0 ? (
        <ul className="plain-list character-conversations__list" aria-label="내 대화">
          {items.map((conversation) => (
            <li key={conversation.id}>
              <Link to={`/chat/conversations/${conversation.id}`}>{conversation.title}</Link>
              <p className="hint">
                {conversationLine(conversation)}
                {hasNewerVersion(conversation, latestVersion) ? ' · 새 판이 있음' : null}
              </p>
            </li>
          ))}
        </ul>
      ) : null}
      {query.hasNextPage ? (
        <Button variant="secondary" busy={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
          더 보기
        </Button>
      ) : null}
    </section>
  );
}
