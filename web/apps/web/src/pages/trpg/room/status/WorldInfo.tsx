// web/apps/web/src/pages/trpg/room/status/WorldInfo.tsx
// 퀘스트와 장소(J). 게임 안의 시각, 서술 모델과 그 값, 퀘스트(이름, 상태, 기한), 내가 선 곳과 갈 수 있는 곳, 장소마다 누가 있는지.
// 퀘스트의 글은 서버가 주지 않는다. 숨긴 퀘스트는 방장에게만 온다. 맵이 없는 판이면 장소를 숨긴다.
// 기한이 지난 퀘스트는 서버가 다음에 닫히는 라운드에서 실패로 바꾼다. 화면이 스스로 바꾸지 않는다.
// 갈 수 있는 곳에는 "가기", 지금 있는 곳에는 "찾기", 놓인 물건에는 "줍기" 단추가 있다. 누르면 선언 입력의 행동 칸이 채워진다.
// 갈 수 있는 곳에는 걸리는 시간과 길을 막거나 굴리게 하는 것(잠긴 자물쇠, 걸린 빗장, 넘기 판정)을 적는다.
// 지금 있는 곳에 닿은 길의 문(#281)은 상태(자물쇠, 빗장, 부서짐)와 지금 할 수 있어 보이는 행동의 단추를 보인다.

import { useQuery } from '@tanstack/react-query';
import type { TableDetail, TableMember } from '../../../../api/types';
import { stepName } from '../../models/modelChoice';
import { ModelPrice } from '../../models/ModelPicker';
import { narrationModelsQuery } from '../../queries';
import { ACTION_LABELS } from '../round/action/actionLabels';
import { canHandleDoor, DOOR_KINDS, doorsHere, doorState } from '../round/action/doorOptions';
import { ActionButton, type ActionShortcuts } from './ActionButton';
import {
  clockLabel,
  clockTimeLabel,
  minutesLabel,
  placeCover,
  placeName,
  questStatusLabel,
  waysFrom,
  wayNotes,
  whoIsWhere,
} from './statusView';

type Props = { table: TableDetail; mine: TableMember | undefined; shortcuts: ActionShortcuts };

export function WorldInfo({ table, mine, shortcuts }: Props) {
  return (
    <div className="world">
      <section aria-labelledby="clock-heading">
        <h3 id="clock-heading" className="waiting-room__label">
          시각
        </h3>
        <p className="world__clock">{clockLabel(table.clock)}</p>
        <p className="hint">다음 라운드에 {minutesLabel(table.clock.next_step_minutes)}이 흐릅니다.</p>
      </section>
      <Narration table={table} />
      <Quests table={table} />
      {table.map ? <Places table={table} map={table.map} mine={mine} shortcuts={shortcuts} /> : null}
    </div>
  );
}

/** 서술 모델과 단계, 그 값. 방장이 바꾸면 이벤트로 다시 읽어 바뀐다(B8) */
function Narration({ table }: { table: TableDetail }) {
  const models = useQuery(narrationModelsQuery());
  const name = models.data?.models.find((model) => model.slug === table.narration_model)?.display_name;
  const value = { model: table.narration_model ?? '', inputStep: table.input_step, outputStep: table.output_step };
  return (
    <section aria-labelledby="narration-heading">
      <h3 id="narration-heading" className="waiting-room__label">
        서술
      </h3>
      <p>
        {name ?? table.narration_model ?? '서버의 기본 모델'}
        <span className="hint">
          {' '}
          · 기억 {stepName(table.input_step)} · 장면 {stepName(table.output_step)}
        </span>
      </p>
      <ModelPrice models={models.data} value={value} recommended={null} />
    </section>
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

type PlacesProps = {
  table: TableDetail;
  map: NonNullable<TableDetail['map']>;
  mine: TableMember | undefined;
  shortcuts: ActionShortcuts;
};

function Places({ table, map, mine, shortcuts }: PlacesProps) {
  const here = mine?.sheet?.place_id;
  const ways = waysFrom(map, here);
  const place = map.places.find((entry) => entry.entry_id === here);
  const cover = placeCover(table, here);
  return (
    <section aria-labelledby="places-heading">
      <h3 id="places-heading" className="waiting-room__label">
        장소
      </h3>
      <p>
        지금 있는 곳: {placeName(map, here) ?? '맵에 서 있지 않음'}{' '}
        {here ? <ActionButton shortcuts={shortcuts} patch={{ kind: 'search' }} label="찾기" what="지금 있는 곳" /> : null}
        {cover > 0 ? <ActionButton shortcuts={shortcuts} patch={{ kind: 'cover' }} label="엄폐" what="지금 있는 곳" /> : null}
      </p>
      {cover > 0 ? <p className="hint">숨을 곳: 커버 {cover}. 엄폐하면 그 라운드 동안 이 값으로 커버 세이브를 받습니다.</p> : null}
      {place && place.items.length > 0 ? (
        <>
          <p className="hint">여기 놓인 것</p>
          <ul className="ways" aria-label="여기 놓인 것">
            {place.items.map((item) => (
              <li key={item.entry_id}>
                {item.name} ×{item.count}{' '}
                <ActionButton shortcuts={shortcuts} patch={{ kind: 'take', item: item.entry_id, count: 1 }} label="줍기" what={item.name} />
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {ways.length > 0 ? <p className="hint">갈 수 있는 곳</p> : null}
      {ways.length > 0 ? (
        <ul className="ways" aria-label="갈 수 있는 곳">
          {ways.map((way) => (
            <li key={way.placeId}>
              {way.name}{' '}
              <span className="hint">
                ({[way.minutes === null ? '걸리는 시간 모름' : minutesLabel(way.minutes), ...(here ? wayNotes(way, here, table.rules) : [])].join(' · ')})
              </span>{' '}
              <ActionButton shortcuts={shortcuts} patch={{ kind: 'move', place: way.placeId, carry: '' }} label="가기" what={way.name} />
            </li>
          ))}
        </ul>
      ) : here ? (
        <p className="hint">아는 길이 없습니다.</p>
      ) : null}
      {here ? <Doors map={map} here={here} shortcuts={shortcuts} /> : null}
      <WhoIsWhere map={map} members={table.members} />
    </section>
  );
}

type DoorsProps = { map: NonNullable<TableDetail['map']>; here: string; shortcuts: ActionShortcuts };

/** 지금 있는 곳에 닿은 길의 문. 문마다 상태와, 지금 할 수 있어 보이는 행동(열기, 잠그기, 따기, 부수기, 고치기)의 단추 */
function Doors({ map, here, shortcuts }: DoorsProps) {
  const doors = doorsHere(map, here);
  if (doors.length === 0) return null;
  return (
    <>
      <p className="hint">문</p>
      <ul className="ways" aria-label="문">
        {doors.map((door) => (
          <li key={door.place}>
            {door.name} 쪽 문 <span className="hint">({doorState(door, map)})</span>{' '}
            {DOOR_KINDS.filter((kind) => canHandleDoor(kind, door.route, here)).map((kind) => (
              <ActionButton
                key={kind}
                shortcuts={shortcuts}
                patch={{ kind, place: door.place, device: '' }}
                label={ACTION_LABELS[kind]}
                what={`${door.name} 쪽 문`}
              />
            ))}
          </li>
        ))}
      </ul>
    </>
  );
}
