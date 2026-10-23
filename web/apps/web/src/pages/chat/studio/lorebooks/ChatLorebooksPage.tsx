// web/apps/web/src/pages/chat/studio/lorebooks/ChatLorebooksPage.tsx
// 내 로어북(chat, /chat/studio/lorebooks). 최근에 고친 것부터 한 쪽씩(더 보기). 마이페이지의 "만들기"와 캐릭터의 로어북 탭에서 온다.
// 로어북은 캐릭터가 붙이는 설정의 모음이다. 지금(1~2단계)은 운영자만 만든다. 만들기에서 막히면 그 화면이 알린다.

import { Button, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import type { AssetLorebookSummary } from '../../../../api/types';
import { formatDate } from '../../../../format/dateTime';
import { lorebookPath, NEW_LOREBOOK_PATH } from './lorebookPaths';
import { myLorebooksQuery } from './lorebookQueries';

export function ChatLorebooksPage() {
  const query = useInfiniteQuery(myLorebooksQuery());
  const lorebooks = query.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <main className="page page--medium">
      <h1>내 로어북</h1>
      <p className="hint">
        로어북은 인물, 장소, 사건 같은 설정의 모음입니다. 캐릭터에 붙이면 대화에서 키워드가 나올 때 모델이 그 항목을 읽습니다. 로어북은 나만 봅니다.
      </p>
      <p>
        <Link to={NEW_LOREBOOK_PATH}>로어북 만들기</Link>
      </p>
      {query.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {query.isError ? (
        <Notice tone="error">
          불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void query.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {query.isSuccess && lorebooks.length === 0 ? (
        <div className="empty-state">
          <p>아직 만든 로어북이 없습니다.</p>
          <Link to={NEW_LOREBOOK_PATH}>첫 로어북 만들기</Link>
        </div>
      ) : null}
      <ul className="plain-list studio-list" aria-label="내 로어북">
        {lorebooks.map((lorebook) => (
          <LorebookItem key={lorebook.id} lorebook={lorebook} />
        ))}
      </ul>
      {query.hasNextPage ? (
        <div className="load-more">
          <Button variant="secondary" busy={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
            더 보기
          </Button>
        </div>
      ) : null}
    </main>
  );
}

function LorebookItem({ lorebook }: { lorebook: AssetLorebookSummary }) {
  return (
    <li className="studio-list__item">
      <Link to={lorebookPath(lorebook.id)}>{lorebook.name}</Link>
      <p className="hint">
        항목 {lorebook.entry_count}개 · {lorebook.latest_version === null ? '아직 게시하지 않음' : `${lorebook.latest_version}판까지 게시`} · 고친 날{' '}
        {formatDate(lorebook.updated_at)}
      </p>
    </li>
  );
}
