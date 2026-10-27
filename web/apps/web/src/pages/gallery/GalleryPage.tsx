// web/apps/web/src/pages/gallery/GalleryPage.tsx
// 갤러리(C7, /gallery?tab=chat|story). 내가 연 일러스트(이벤트 씬)를 다시 본다. 로그인해야 열린다.
// 서비스마다 탭이고 탭마다 그 서버만 부른다(#593). chat 은 캐릭터마다, 최근에 연 캐릭터부터. 연 것은 그림과 연 날, 열지 않은 것은 흐린 그림이다.
// story 는 내 세션의 세계관마다, 인물마다 묶는다(StoryGallery).

import { Button, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router';
import { CharacterGallery } from './CharacterGallery';
import { chatUnlocksQuery } from './galleryQueries';
import { StoryGallery } from './StoryGallery';
import { groupUnlocks } from './galleryView';

const TABS = [
  { key: 'chat', label: 'chat' },
  { key: 'story', label: 'story' },
] as const;

export function GalleryPage() {
  const [params] = useSearchParams();
  const tab = params.get('tab') === 'story' ? 'story' : 'chat';
  return (
    <main className="page page--medium">
      <h1>갤러리</h1>
      <nav className="board-tabs" aria-label="서비스">
        {TABS.map((item) => (
          <Link key={item.key} to={`/gallery?tab=${item.key}`} aria-current={item.key === tab ? 'page' : undefined}>
            {item.label}
          </Link>
        ))}
      </nav>
      {tab === 'chat' ? <ChatGallery /> : <StoryGallery />}
    </main>
  );
}

function ChatGallery() {
  const unlocks = useInfiniteQuery(chatUnlocksQuery());
  const groups = groupUnlocks(unlocks.data?.pages.flatMap((page) => page.items) ?? []);
  if (unlocks.isPending) return <p aria-busy="true">불러오는 중</p>;
  if (unlocks.isError && !unlocks.data) {
    return (
      <Notice tone="error">
        갤러리를 불러오지 못했습니다.{' '}
        <Button variant="quiet" onClick={() => void unlocks.refetch()}>
          다시 시도
        </Button>
      </Notice>
    );
  }
  return (
    <>
      {groups.size === 0 ? <p className="empty-state">아직 연 일러스트가 없습니다. 대화하며 일러스트를 엽니다.</p> : null}
      {[...groups].map(([characterId, unlocked]) => (
        <CharacterGallery key={characterId} characterId={characterId} unlocked={unlocked} />
      ))}
      {unlocks.hasNextPage ? (
        <div className="load-more">
          <Button variant="secondary" busy={unlocks.isFetchingNextPage} onClick={() => void unlocks.fetchNextPage()}>
            더 보기
          </Button>
        </div>
      ) : null}
    </>
  );
}
