// web/apps/web/src/pages/trpg/studio/scenarios/PicturesTab.tsx
// 시나리오의 그림 탭(B9, #1163). 붙인 로어북의 장소, 인물, 사건 항목마다 그림을 붙이고 바꾸고 뗀다(PortraitChooser 를 다시 쓴다).
// 장소는 테이블 방의 그림 창의 배경, 인물은 장면에 나올 때 배경 위에 겹치는 그림, 사건은 일어난 라운드의 컷신이다.
// 장소는 하루의 때마다 배경을 따로 붙일 수 있다(기본 그림이 있을 때, 펼쳐서). 없는 때는 기본 그림을 쓴다.
// 붙일 수 없는 항목(로어북을 뗐거나 항목을 지웠다)의 그림은 따로 모아 떼게 한다. 저장해야 붙고, 목록을 통째로 보낸다.
// 그림이 내가 올린 것인지는 저장할 때(422), 항목이 맞는지는 게시 점검이 본다.

import { Button } from '@ai-trpg/ui';
import { useState } from 'react';
import type { DayTime, LoreKind, ScenarioDetail } from '../../../../api/types';
import { MyPortrait } from '../../portraits/MyPortrait';
import { PortraitChooser } from '../../portraits/PortraitChooser';
import {
  MAX_PICTURES,
  pictureOf,
  picturesDraft,
  strayPictures,
  timeCount,
  timePictureOf,
  toPicturesBody,
  withoutTimes,
  withPicture,
  withTimePicture,
  type PictureRow,
} from './picturesForm';
import { ScenarioForm } from './ScenarioForm';
import { useLoreEntries, type EntryChoice } from './useLoreEntries';
import { useScenarioSave } from './useScenarioSave';
import { DAY_TIMES, dayTimeLabel } from './wandersForm';

type Group = { kind: LoreKind; legend: string; hint: string };

const GROUPS: Group[] = [
  { kind: 'place', legend: '장소의 배경', hint: '테이블 방의 그림 창에서 이 장소의 배경으로 씁니다. 가로로 긴 그림이 잘 맞습니다.' },
  { kind: 'person', legend: '인물의 그림', hint: '장면에 이 인물이 나오면 배경 위에 겹쳐 보입니다. 배경이 비치는 그림이 잘 맞습니다.' },
  { kind: 'event', legend: '사건의 컷신', hint: '이 사건이 일어나거나 이 사건의 퀘스트를 이루면 그 라운드 동안 배경 대신 보입니다.' },
];

type Change = (entryId: string, imageId: string | null) => void;
/** 줄들을 바꾸는 함수를 받아 고친다 */
type Edit = (update: (rows: PictureRow[]) => PictureRow[]) => void;

export function PicturesTab({ scenario }: { scenario: ScenarioDetail }) {
  const [rows, setRows] = useState<PictureRow[]>(() => picturesDraft(scenario));
  const saving = useScenarioSave(scenario.id);
  const places = useLoreEntries(scenario.lorebook_ids, 'place');
  const people = useLoreEntries(scenario.lorebook_ids, 'person');
  const events = useLoreEntries(scenario.lorebook_ids, 'event');
  const lists = [places, people, events];
  const known = lists.flatMap((list) => list.entries.map((entry) => entry.id));
  const settled = lists.every((list) => !list.pending && !list.failed);

  const change: Change = (entryId, imageId) => setRows((current) => withPicture(current, entryId, imageId));
  const edit: Edit = (update) => setRows(update);

  async function submit() {
    const saved = await saving.save(toPicturesBody(rows));
    if (saved) setRows(picturesDraft(saved));
  }

  return (
    <ScenarioForm label="그림" busy={saving.busy} problem={saving.problem} saved={saving.saved} blocked={false} onSubmit={() => void submit()}>
      <p className="hint">
        붙인 로어북의 장소, 인물, 사건 항목마다 그림을 하나씩 붙입니다. 그림은 그 항목이 테이블에 보일 때만 플레이어에게 갑니다. 저장해야 붙습니다. ({rows.length} /{' '}
        {MAX_PICTURES})
      </p>
      {scenario.lorebook_ids.length === 0 ? <p className="hint">재료 탭에서 로어북을 붙이면 그 안의 장소, 인물, 사건이 여기에 나옵니다.</p> : null}
      {GROUPS.map((group, index) => (
        <EntryGroup key={group.kind} group={group} entries={lists[index]?.entries ?? []} rows={rows} onChange={change} onEdit={edit} />
      ))}
      {lists.some((list) => list.pending) ? <p aria-busy="true">불러오는 중</p> : null}
      {lists.some((list) => list.failed) ? <p className="ui-field__error">로어북의 항목을 불러오지 못했습니다.</p> : null}
      {settled ? <StrayPictures rows={strayPictures(rows, known)} onChange={change} /> : null}
    </ScenarioForm>
  );
}

type GroupProps = { group: Group; entries: EntryChoice[]; rows: PictureRow[]; onChange: Change; onEdit: Edit };

/** 한 종류(장소, 인물, 사건)의 항목들. 항목마다 그림 칸 하나, 장소에는 때마다의 배경도 */
function EntryGroup({ group, entries, rows, onChange, onEdit }: GroupProps) {
  if (entries.length === 0) return null;
  return (
    <fieldset className="scenario-choices">
      <legend>{group.legend}</legend>
      {entries.map((entry) => (
        <div key={entry.id}>
          <PortraitChooser
            name={`${entry.name}의 그림`}
            label={entry.name}
            hint={group.hint}
            imageId={pictureOf(rows, entry.id)}
            onChange={(imageId) => onChange(entry.id, imageId)}
          />
          {group.kind === 'place' && pictureOf(rows, entry.id) ? <TimePictures entry={entry} rows={rows} onEdit={onEdit} /> : null}
          {group.kind !== 'place' && timeCount(rows, entry.id) > 0 ? <WrongTimes entry={entry} onEdit={onEdit} /> : null}
        </div>
      ))}
    </fieldset>
  );
}

type TimesProps = { entry: EntryChoice; rows: PictureRow[]; onEdit: Edit };

/** 장소의 때마다의 배경. 펼쳐서 고른다. 없는 때는 기본 그림이다 */
function TimePictures({ entry, rows, onEdit }: TimesProps) {
  const count = timeCount(rows, entry.id);
  // 이미 붙인 때가 있으면 펼친 채로 연다. 그 뒤는 사람이 접고 편다
  const [open, setOpen] = useState(count > 0);
  const change = (time: DayTime, imageId: string | null) => onEdit((current) => withTimePicture(current, entry.id, time, imageId));
  return (
    <details className="scenario-picture-times" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>
        {entry.name}의 때마다의 배경 ({count} / {DAY_TIMES.length})
      </summary>
      {DAY_TIMES.map((time) => (
        <PortraitChooser
          key={time}
          name={`${entry.name}의 ${dayTimeLabel(time)} 배경`}
          label={`${dayTimeLabel(time)}(선택)`}
          hint="게임 안의 시각이 이때면 이 그림을 씁니다. 없으면 기본 그림을 씁니다."
          imageId={timePictureOf(rows, entry.id, time)}
          onChange={(imageId) => change(time, imageId)}
        />
      ))}
    </details>
  );
}

/** 장소가 아닌 항목의 때마다의 그림. 게시 점검이 막으므로 떼게 한다 */
function WrongTimes({ entry, onEdit }: { entry: EntryChoice; onEdit: Edit }) {
  return (
    <p className="hint">
      때마다의 그림은 장소에만 둡니다.{' '}
      <Button variant="quiet" onClick={() => onEdit((current) => withoutTimes(current, entry.id))}>
        {entry.name}의 때마다의 그림 떼기
      </Button>
    </p>
  );
}

/** 붙일 수 없는 항목의 그림. 게시 점검이 문제로 보이므로 떼게 한다 */
function StrayPictures({ rows, onChange }: { rows: PictureRow[]; onChange: Change }) {
  if (rows.length === 0) return null;
  return (
    <fieldset className="scenario-choices">
      <legend>붙일 수 없는 항목의 그림</legend>
      <p className="hint">붙인 로어북에 없거나 장소, 인물, 사건이 아닌 항목의 그림입니다. 떼고 저장하세요.</p>
      <ul className="plain-list portrait-shelf__grid" aria-label="붙일 수 없는 항목의 그림">
        {rows.map((row, index) => (
          <li key={row.entryId} className="portrait-shelf__item">
            <MyPortrait portraitId={row.imageId} alt={`붙일 수 없는 그림 ${index + 1}`} />
            <Button variant="quiet" aria-label={`붙일 수 없는 그림 ${index + 1} 떼기`} onClick={() => onChange(row.entryId, null)}>
              떼기
            </Button>
          </li>
        ))}
      </ul>
    </fieldset>
  );
}
