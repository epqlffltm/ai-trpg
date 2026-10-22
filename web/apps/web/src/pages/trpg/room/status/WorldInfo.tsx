// web/apps/web/src/pages/trpg/room/status/WorldInfo.tsx
// 퀘스트와 장소(J). 게임 안의 시각, 퀘스트(이름, 상태, 기한), 내가 선 곳과 갈 수 있는 곳, 장소마다 누가 있는지.
// 퀘스트의 글은 서버가 주지 않는다. 숨긴 퀘스트는 방장에게만 온다. 맵이 없는 판이면 장소를 숨긴다.
// 기한이 지난 퀘스트는 서버가 다음에 닫히는 라운드에서 실패로 바꾼다. 화면이 스스로 바꾸지 않는다.

import type { TableDetail, TableMember } from '../../../../api/types';
import {
  clockLabel,
  clockTimeLabel,
  minutesLabel,
  placeName,
  questStatusLabel,
  waysFrom,
  whoIsWhere,
} from './statusView';

export function WorldInfo({ table, mine }: { table: TableDetail; mine: TableMember | undefined }) {
  return (
    <div className="world">
      <section aria-labelledby="clock-heading">
        <h3 id="clock-heading" className="waiting-room__label">
          시각
        </h3>
        <p className="world__clock">{clockLabel(table.clock)}</p>
        <p className="hint">다음 라운드에 {minutesLabel(table.clock.next_step_minutes)}이 흐릅니다.</p>
      </section>
      <Quests table={table} />
      {table.map ? <Places table={table} map={table.map} mine={mine} /> : null}
    </div>
  );
}

function Quests({ table }: { table: TableDetail }) {
  return (
    <section aria-labelledby="quests-heading">
      <h3 id="quests-heading" className="waiting-room__label">
        퀘스트
      </h3>
      {table.quests.length === 0 ? (
        <p className="hint">{table.status === 'recruiting' ? '시작하면 채워집니다.' : '아직 드러난 퀘스트가 없습니다.'}</p>
      ) : (
        <ul className="plain-list quests">
          {table.quests.map((quest) => (
            <li key={quest.entry_id} className={`quest quest--${quest.status}`}>
              <span>{quest.name}</span>
              <span className="hint">
                {questStatusLabel(quest.status)}
                {quest.due_at && quest.status === 'active' ? ` · 기한 ${clockTimeLabel(quest.due_at)}` : ''}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function WhoIsWhere({ map, members }: { map: NonNullable<TableDetail['map']>; members: TableMember[] }) {
  const entries = whoIsWhere(map, members);
  if (entries.length === 0) return null;
  return (
    <>
      <p className="hint">누가 어디에</p>
      <ul className="ways" aria-label="누가 어디에">
        {entries.map((entry) => (
          <li key={entry.name}>
            {entry.name}: {entry.characters.join(', ')}
          </li>
        ))}
      </ul>
    </>
  );
}

type PlacesProps = { table: TableDetail; map: NonNullable<TableDetail['map']>; mine: TableMember | undefined };

function Places({ table, map, mine }: PlacesProps) {
  const here = mine?.sheet?.place_id;
  const ways = waysFrom(map, here);
  const place = map.places.find((entry) => entry.entry_id === here);
  return (
    <section aria-labelledby="places-heading">
      <h3 id="places-heading" className="waiting-room__label">
        장소
      </h3>
      <p>지금 있는 곳: {placeName(map, here) ?? '맵에 서 있지 않음'}</p>
      {place && place.items.length > 0 ? (
        <p className="hint">여기 놓인 것: {place.items.map((item) => `${item.name} ×${item.count}`).join(', ')}</p>
      ) : null}
      {ways.length > 0 ? <p className="hint">갈 수 있는 곳</p> : null}
      {ways.length > 0 ? (
        <ul className="ways" aria-label="갈 수 있는 곳">
          {ways.map((way) => (
            <li key={way.placeId}>
              {way.name} <span className="hint">({way.minutes === null ? '걸리는 시간 모름' : minutesLabel(way.minutes)})</span>
            </li>
          ))}
        </ul>
      ) : here ? (
        <p className="hint">아는 길이 없습니다.</p>
      ) : null}
      <WhoIsWhere map={map} members={table.members} />
    </section>
  );
}
