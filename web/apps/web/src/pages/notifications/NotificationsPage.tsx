// web/apps/web/src/pages/notifications/NotificationsPage.tsx
// 알림(A10, /notifications, Stitch 9번). 로그인해야 열린다(RequireSession). 위쪽 줄 알림 창의 "모두 보기"에서 온다.
// 제목 줄 오른쪽에 "모두 읽음". 최근 것부터 한 쪽씩(더 보기). 글은 notificationText.ts 가 짓는다. 누르면 읽음으로 하고 그 화면으로 간다.
// 모두 읽음은 받은 것 가운데 가장 새 번호까지만. 30일이 지난 알림은 서버가 지운다.
// 받을 알림(끄기)은 여기 두지 않고 설정(A12)에 둔다. 맨 아래에 그리로 가는 길만 있다.

import { Button, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { narrationModelsQuery } from '../trpg/queries';
import { NotificationItem } from './NotificationItem';
import { notificationsQuery, unreadCountQuery } from './notificationQueries';
import { notificationProblemText } from './notificationProblem';
import { describeNotification, needsModelNames, newestId } from './notificationText';
import { useReadAll } from './useReadAll';
import { useReadNotification } from './useReadNotification';

export function NotificationsPage() {
  const query = useInfiniteQuery(notificationsQuery());
  const unread = useQuery(unreadCountQuery());
  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  const models = useQuery({ ...narrationModelsQuery(), enabled: needsModelNames(items) });
  const read = useReadNotification();
  const reading = useReadAll();
  const upTo = newestId(items);
  const ctx = { modelName: (slug: string) => models.data?.models.find((model) => model.slug === slug)?.display_name ?? slug };

  return (
    <main className="page page--medium notifications-page">
      <div className="notifications-page__head">
        <h1>알림</h1>
        {upTo !== null && (unread.data?.unread ?? 0) > 0 ? (
          <Button variant="secondary" busy={reading.busy} onClick={() => void reading.readAll(upTo)}>
            모두 읽음
          </Button>
        ) : null}
      </div>
      {query.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {query.isError ? (
        <Notice tone="error">
          {notificationProblemText(query.error)}{' '}
          <Button variant="quiet" onClick={() => void query.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {reading.problem ? <Notice tone="error">{reading.problem}</Notice> : null}
      {query.isSuccess && items.length === 0 ? <p className="empty-state">새 알림이 없습니다.</p> : null}
      <ul className="plain-list notifications" aria-label="알림">
        {items.map((notification) => (
          <NotificationItem key={notification.id} notification={notification} line={describeNotification(notification, ctx)} onRead={read} />
        ))}
      </ul>
      {query.hasNextPage ? (
        <div className="load-more">
          <Button variant="secondary" busy={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
            더 보기
          </Button>
        </div>
      ) : null}
      <p className="hint notifications-page__foot">
        받은 지 30일이 지난 알림은 지워집니다. 받을 알림은 <Link to="/settings">설정</Link>에서 고릅니다.
      </p>
    </main>
  );
}
