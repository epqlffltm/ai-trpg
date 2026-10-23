// web/apps/web/src/pages/trpg/room/events/EventLog.tsx
// 일어난 일(L). 상태 패널의 탭이다. 이벤트를 한 줄씩, 최근 것을 위에. 라운드 안의 일이면 라운드의 번호를 붙인다.
// 처음에 끝부분(EVENT_TAIL)만 읽고 그 뒤는 스트림이 더한다(TableRoom). 여기서는 읽어 둔 것을 보이기만 한다.
// 서술, 선언, 판정은 가운데의 라운드에 있어 여기에 없다(eventLines.ts).

import { useQuery } from '@tanstack/react-query';
import type { TableDetail } from '../../../../api/types';
import { eventsQuery } from '../roomQueries';
import { eventRound, eventRows } from './eventLines';
import { useEventContext } from './useEventContext';

type Props = { table: TableDetail; nameOfMember: (userId: string) => string };

export function EventLog({ table, nameOfMember }: Props) {
  const events = useQuery(eventsQuery(table.id));
  const ctx = useEventContext(table, nameOfMember);

  if (events.isPending) return <p className="hint">일어난 일을 불러오는 중입니다.</p>;
  if (events.isError) return <p className="hint">일어난 일을 불러오지 못했습니다. 새로 고치면 다시 읽습니다.</p>;
  const rows = eventRows(events.data.items, ctx);
  const first = events.data.items[0];
  return (
    <div className="event-log">
      {rows.length === 0 ? <p className="hint">아직 적을 일이 없습니다.</p> : null}
      <ol className="plain-list event-log__list" aria-label="일어난 일, 최근 것이 위">
        {rows.map(({ event, line }) => (
          <li key={event.sequence} className={line.important ? 'event-line event-line--important' : 'event-line'}>
            {eventRound(event) !== null ? <span className="event-line__round">R{eventRound(event)}</span> : null}
            <span>{line.text}</span>
          </li>
        ))}
      </ol>
      {first && first.sequence > 1 ? <p className="hint">그 앞의 일은 여기에 보이지 않습니다.</p> : null}
    </div>
  );
}
