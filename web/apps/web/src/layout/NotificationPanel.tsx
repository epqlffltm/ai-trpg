// web/apps/web/src/layout/NotificationPanel.tsx
// 알림 종 아래로 펼쳐지는 창(Stitch 설계서의 [모든 화면의 틀]). 최근 알림 몇 개, 모두 읽음, 맨 아래 "모두 보기"(알림 화면으로).
// 목록은 알림 화면(A10)과 같은 열쇠의 첫 쪽이다. 한 줄의 모양과 글, 읽음은 알림 화면의 것을 그대로 쓴다.
// 길을 누르면 창을 닫는다. 끄고 켜기(받을 알림)는 여기 두지 않는다(알림 화면).

import { Button, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import type { MouseEvent } from 'react';
import { NotificationItem } from '../pages/notifications/NotificationItem';
import { notificationProblemText } from '../pages/notifications/notificationProblem';
import { notificationsQuery } from '../pages/notifications/notificationQueries';
import { describeNotification, needsModelNames, newestId } from '../pages/notifications/notificationText';
import { useReadAll } from '../pages/notifications/useReadAll';
import { useReadNotification } from '../pages/notifications/useReadNotification';
import { narrationModelsQuery } from '../pages/trpg/queries';

/** 창에 보이는 최근 알림의 수. 더 보려면 알림 화면으로 간다 */
export const PANEL_SIZE = 5;

type Props = { unread: number; onClose: () => void };

export function NotificationPanel({ unread, onClose }: Props) {
  const query = useInfiniteQuery(notificationsQuery());
  const items = (query.data?.pages[0]?.items ?? []).slice(0, PANEL_SIZE);
  const models = useQuery({ ...narrationModelsQuery(), enabled: needsModelNames(items) });
  const read = useReadNotification();
  const reading = useReadAll();
  const upTo = newestId(items);
  const ctx = { modelName: (slug: string) => models.data?.models.find((model) => model.slug === slug)?.display_name ?? slug };

  // 알림의 길을 누르면 그 화면으로 가며 창을 닫는다. "읽음" 단추는 창을 닫지 않는다
  function closeOnLink(event: MouseEvent<HTMLUListElement>) {
    if ((event.target as HTMLElement).closest('a')) onClose();
  }

  return (
    <section className="header-popover__panel notification-panel" aria-label="알림 창">
      <div className="header-popover__head">
        <strong>알림</strong>
        {upTo !== null && unread > 0 ? (
          <Button variant="quiet" busy={reading.busy} onClick={() => void reading.readAll(upTo)}>
            모두 읽음
          </Button>
        ) : null}
      </div>
      {query.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {query.isError ? <Notice tone="error">{notificationProblemText(query.error)}</Notice> : null}
      {reading.problem ? <Notice tone="error">{reading.problem}</Notice> : null}
      {query.isSuccess && items.length === 0 ? <p className="hint">새 알림이 없습니다.</p> : null}
      {items.length > 0 ? (
        <ul className="plain-list notifications" aria-label="최근 알림" onClick={closeOnLink}>
          {items.map((notification) => (
            <NotificationItem key={notification.id} notification={notification} line={describeNotification(notification, ctx)} onRead={read} />
          ))}
        </ul>
      ) : null}
      <Link to="/notifications" className="header-popover__more" onClick={onClose}>
        모두 보기
      </Link>
    </section>
  );
}
