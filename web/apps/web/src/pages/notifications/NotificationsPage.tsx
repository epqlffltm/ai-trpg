// web/apps/web/src/pages/notifications/NotificationsPage.tsx
// 알림(A10, /notifications). 로그인해야 열린다(RequireSession). 머리의 "알림"에서 온다.
// 최근 것부터 한 쪽씩(더 보기). 글은 notificationText.ts 가 짓는다. 누르면 읽음으로 하고 그 화면으로 간다.
// 모두 읽음은 받은 것 가운데 가장 새 번호까지만. 아래에 받을 알림(끄기). 30일이 지난 알림은 서버가 지운다.
// PC 의 머리에서 여는 패널은 두지 않았다. 같은 목록을 나중에 감싸면 된다.

import { Button, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { narrationModelsQuery } from '../trpg/queries';
import { NotificationItem } from './NotificationItem';
import { NotificationMutes } from './NotificationMutes';
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
    <main className="page page--medium">
      <h1>알림</h1>
      <p className="hint">받은 지 30일이 지난 알림은 지워집니다.</p>
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
      {upTo !== null && (unread.data?.unread ?? 0) > 0 ? (
        <p>
          <Button variant="secondary" busy={reading.busy} onClick={() => void reading.readAll(upTo)}>
            모두 읽음
          </Button>
        </p>
      ) : null}
      {query.isSuccess && items.length === 0 ? <p className="empty-state">알림이 없습니다.</p> : null}
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
      <NotificationMutes />
    </main>
  );
}
