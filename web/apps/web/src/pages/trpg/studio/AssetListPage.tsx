// web/apps/web/src/pages/trpg/studio/AssetListPage.tsx
// 내 재료의 목록(B9). 재료마다 같은 모양이다: 최근에 만든 것부터 한 쪽씩(더 보기), 제목·소개·고친 날, 비었으면 첫 만들기.
// 재료마다의 화면(RulebooksPage 같은 것)은 종류만 넘긴다.

import { Button, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import type { StudioKind } from '../../../api/studio';
import { formatDate } from '../../../format/dateTime';
import { kindText, studioNewPath, studioPath } from './studioKinds';
import { assetsQuery } from './studioQueries';

export function AssetListPage({ kind }: { kind: StudioKind }) {
  const query = useInfiniteQuery(assetsQuery(kind));
  const text = kindText(kind);
  const assets = query.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <main className="page page--medium">
      <p>
        <Link to="/trpg/studio">만들기</Link>
      </p>
      <h1>{text.title}</h1>
      <p className="hint">{text.intro} 재료는 나만 봅니다.</p>
      <p>
        <Link to={studioNewPath(kind)}>{text.create}</Link>
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
      {query.isSuccess && assets.length === 0 ? (
        <div className="empty-state">
          <p>{text.empty}</p>
          <Link to={studioNewPath(kind)}>{text.first}</Link>
        </div>
      ) : null}
      <ul className="plain-list studio-list" aria-label={text.label}>
        {assets.map((asset) => (
          <li key={asset.id} className="studio-list__item">
            <Link to={studioPath(kind, asset.id)}>{asset.title}</Link>
            {asset.description ? <p className="studio-list__description">{asset.description}</p> : null}
            <p className="hint">고친 날 {formatDate(asset.updated_at)}</p>
          </li>
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
