// web/apps/web/src/pages/notifications/NotificationMutes.tsx
// 알림 끄기(#525). 서버가 준 끌 수 있는 종류마다 체크 상자 하나. 체크하면 받는다(켬), 풀면 끈다.
// 끈 종류는 서버가 넣을 때 거른다. 다시 켜도 꺼 둔 동안의 알림은 없고, 끄기 전에 받은 것은 남는다.
// 설정(A12)에 둔다(Stitch 9번: 종류마다 끄고 켜기는 알림 화면에 두지 않는다). 로그인했을 때만 보인다.

import { Checkbox, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { mutesQuery } from './notificationQueries';
import { notificationProblemText } from './notificationProblem';
import { muteLabel } from './notificationText';
import { useMuteToggle } from './useMuteToggle';

export function NotificationMutes() {
  const mutes = useQuery(mutesQuery());
  const toggling = useMuteToggle();
  return (
    <section className="page-section" aria-labelledby="mutes-heading">
      <h2 id="mutes-heading">받을 알림</h2>
      <p className="hint">끈 알림은 그동안 오지 않습니다. 다시 켜도 꺼 둔 동안의 알림은 없습니다. 결제와 환불, 운영자의 조치, 내 테이블의 모델이 바뀐 일은 끌 수 없습니다.</p>
      {mutes.isError ? <Notice tone="error">{notificationProblemText(mutes.error)}</Notice> : null}
      {toggling.problem ? <Notice tone="error">{toggling.problem}</Notice> : null}
      {mutes.data ? (
        <div className="choice-list">
          {mutes.data.kinds.map((item) => (
            <Checkbox
              key={item.kind}
              label={muteLabel(item.kind)}
              checked={!item.muted}
              disabled={toggling.busyKind !== null}
              onChange={() => void toggling.toggle(item.kind, !item.muted)}
            />
          ))}
        </div>
      ) : null}
    </section>
  );
}
