// web/apps/web/src/pages/me/MyFollowingSection.tsx
// 마이페이지의 "팔로잉"(#989). 내가 팔로우한 제작자를 최근에 한 것부터 보이고, 누르면 제작자 페이지로 간다.
// 알림 서버를 부르는 것은 "팔로잉 보기"를 눌렀을 때다(마이페이지는 그동안 인증 서버만 부른다). 한 번에 20명씩 더 읽는다.
// 이름은 인증 서버에 쪽마다 묻는다. 탈퇴한 제작자는 이름만 보이고 잇지 않는다. 팔로우를 끊는 것은 작품의 "만든 사람" 줄에서 한다.

import { Button } from '@ai-trpg/ui';
import { useInfiniteQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router';
import { fetchFollowing, FOLLOWING_PAGE_SIZE, type FollowingPage } from '../../api/follows';
import { FOLLOWING_KEY } from '../../components/FollowButton';
import { UNKNOWN_PERSON, usePublicNames } from '../../hooks/usePublicNames';

export function MyFollowingSection() {
  const [open, setOpen] = useState(false);
  return (
    <section className="page-section" aria-labelledby="my-following-heading">
      <h2 id="my-following-heading">팔로잉</h2>
      {open ? (
        <FollowingList />
      ) : (
        <p>
          <Button variant="quiet" onClick={() => setOpen(true)}>
            팔로잉 보기
          </Button>
        </p>
      )}
    </section>
  );
}

/** 다음 쪽의 offset. 다 받았으면 undefined */
export function nextFollowingOffset(pages: FollowingPage[]): number | undefined {
  const received = pages.reduce((sum, page) => sum + page.items.length, 0);
  const last = pages.at(-1);
  if (!last || last.items.length < FOLLOWING_PAGE_SIZE || received >= last.total) return undefined;
  return received;
}

function FollowingList() {
  const following = useInfiniteQuery({
    queryKey: FOLLOWING_KEY,
    queryFn: ({ pageParam, signal }) => fetchFollowing(pageParam, signal),
    initialPageParam: 0,
    getNextPageParam: (_last, pages) => nextFollowingOffset(pages),
  });
  const pages = following.data?.pages ?? [];
  const nameOf = usePublicNames(pages.map((page) => page.items.map((item) => item.creator_id)));

  if (following.isPending) return <p className="hint">읽는 중입니다.</p>;
  if (following.isError) {
    return (
      <p role="alert">
        팔로잉을 읽지 못했습니다.{' '}
        <Button variant="quiet" onClick={() => void following.refetch()}>
          다시 읽기
        </Button>
      </p>
    );
  }
  const items = pages.flatMap((page) => page.items);
  if (items.length === 0) return <p className="hint">팔로우한 제작자가 없습니다. 작품의 "만든 사람" 줄에서 팔로우할 수 있습니다.</p>;
  return (
    <>
      <p className="hint">{(pages.at(-1)?.total ?? items.length).toLocaleString('ko-KR')}명</p>
      <ul>
        {items.map((item) => (
          <li key={item.creator_id}>
            <CreatorName creatorId={item.creator_id} name={nameOf(item.creator_id)} />
          </li>
        ))}
      </ul>
      {following.hasNextPage ? (
        <Button variant="secondary" busy={following.isFetchingNextPage} onClick={() => void following.fetchNextPage()}>
          더 보기
        </Button>
      ) : null}
    </>
  );
}

function CreatorName({ creatorId, name }: { creatorId: string; name: string | undefined }) {
  if (name === UNKNOWN_PERSON) return <span>{name}</span>;
  return <Link to={`/creators/${encodeURIComponent(creatorId)}`}>{name ?? '이름을 읽는 중'}</Link>;
}
