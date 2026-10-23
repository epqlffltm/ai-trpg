// web/apps/web/src/pages/operator/LoadMore.tsx
// 목록의 아래: 읽지 못했으면 다시 시도, 남은 쪽이 있으면 더 보기. 신고의 두 목록이 함께 쓴다.

import { Button, Notice } from '@ai-trpg/ui';

type Props = {
  failed: boolean;
  hasMore: boolean;
  loadingMore: boolean;
  onRetry: () => void;
  onMore: () => void;
};

export function LoadMore({ failed, hasMore, loadingMore, onRetry, onMore }: Props) {
  if (failed) {
    return (
      <Notice tone="error">
        불러오지 못했습니다.{' '}
        <Button variant="quiet" onClick={onRetry}>
          다시 시도
        </Button>
      </Notice>
    );
  }
  if (!hasMore) return null;
  return (
    <div className="load-more">
      <Button variant="secondary" busy={loadingMore} onClick={onMore}>
        더 보기
      </Button>
    </div>
  );
}
