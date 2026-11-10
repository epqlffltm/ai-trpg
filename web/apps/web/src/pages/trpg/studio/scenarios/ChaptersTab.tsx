// web/apps/web/src/pages/trpg/studio/scenarios/ChaptersTab.tsx
// 시나리오의 장 탭(B9, #481). 장을 차례대로 늘어놓고 줄마다 넘어오는 조건과 여는 것을 한 줄로 보인다.
// 줄을 고치면 창이 열리고, 창의 저장이 장 목록을 통째로 바로 보낸다. 위로·아래로도 바로 저장한다.
// 첫 장은 처음부터 그 장이라 넘어오는 조건이 없다. 첫 자리는 옮기지 않고, 다른 장이 있으면 첫 장은 지우지 않는다(chaptersForm.ts).
// 장이 여는 장소와 퀘스트는 그 장이 오기 전까지 테이블에서 닫혀 있다(지도에 없고, 갈 수 없고, 드러나지 않는다).
// 갈림길(#289): 장마다 앞의 장을 고른다. 고르지 않으면 바로 앞의 장 다음이다. 줄에 "「마을」, 「들」 다음"을 보인다.

import { Button, Checkbox, Dialog, Notice, TextField } from '@ai-trpg/ui';
import { useCallback, useState, type FormEvent } from 'react';
import type { Chapter, ScenarioDetail } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import {
  canMove,
  canRemove,
  CHAPTER_NAME_MAX_LENGTH,
  chapterDraft,
  chapterHints,
  chapterLine,
  earlierChapters,
  followsLine,
  hasChapterHints,
  MAX_CHAPTERS,
  moved,
  newChapterId,
  openedElsewhere,
  toChapter,
  withChapter,
  withoutChapter,
  type ChapterDraft,
} from './chaptersForm';
import { ConditionsEditor } from './ConditionsEditor';
import { KINDS_FOR, type Targets } from './conditionsForm';
import { mapPlaces } from './placesForm';
import { useConditionTargets } from './useConditionTargets';
import type { EntryChoice } from './useLoreEntries';
import { useScenarioSave } from './useScenarioSave';

type Props = { scenario: ScenarioDetail };

/** 고치는 장. index 가 null 이면 새 장이다 */
type Editing = { id: string; index: number | null };

export function ChaptersTab({ scenario }: Props) {
  const { targets, pending, failed } = useConditionTargets(scenario);
  const [editing, setEditing] = useState<Editing | null>(null);
  const close = useCallback(() => setEditing(null), []);
  const saving = useScenarioSave(scenario.id);
  if (pending) return <p aria-busy="true">불러오는 중</p>;
  const chapters = scenario.chapters;
  const full = chapters.length >= MAX_CHAPTERS;

  async function move(index: number, step: -1 | 1) {
    await saving.save({ chapters: moved(chapters, index, step) });
  }

  return (
    <section className="page-section" aria-labelledby="chapters-heading">
      <h2 id="chapters-heading">
        장{' '}
        <span className="hint">
          ({chapters.length} / {MAX_CHAPTERS})
        </span>
      </h2>
      <p className="hint">
        이야기를 장으로 나눕니다. 테이블은 첫 장에서 시작하고, 다음 장의 넘어오는 조건이 채워지면 라운드가 닫힐 때 엔진이 한 장씩 넘깁니다. 장마다 앞의 장을 고르면 갈림길로
        갈라지고 다시 모입니다. 장이 여는 장소와 퀘스트는 그 장이 오기 전까지 닫혀 있고, 고르지 않은 갈림길의 장이 여는 것은 그 테이블에서 계속 닫혀 있습니다. 어느 장에도 적지
        않은 것은 처음부터 열려 있습니다. 창에서 저장하면 바로 저장됩니다.
      </p>
      {failed ? <Notice tone="error">로어북의 항목을 불러오지 못했습니다. 이름이 보이지 않을 수 있습니다.</Notice> : null}
      <ProblemNotice problem={saving.problem} />
      {chapters.length === 0 ? <p className="hint">장이 없습니다. 장이 없으면 모든 것이 처음부터 열려 있습니다.</p> : null}
      <ol className="plain-list studio-list" aria-label="장">
        {chapters.map((chapter, index) => (
          <li key={chapter.id} className="studio-list__item studio-item">
            <div>
              <strong>
                {index + 1}장: {chapter.name}
              </strong>
              {followsLine(chapter, index, chapters) ? <div className="studio-list__description hint">{followsLine(chapter, index, chapters)}</div> : null}
              <div className="studio-list__description hint">{chapterLine(chapter, index, targets)}</div>
            </div>
            <div className="actions">
              <Button variant="quiet" aria-label={`${chapter.name} 위로`} disabled={saving.busy || !canMove(chapters.length, index, -1)} onClick={() => void move(index, -1)}>
                위로
              </Button>
              <Button variant="quiet" aria-label={`${chapter.name} 아래로`} disabled={saving.busy || !canMove(chapters.length, index, 1)} onClick={() => void move(index, 1)}>
                아래로
              </Button>
              <Button variant="quiet" aria-label={`${chapter.name} 고치기`} onClick={() => setEditing({ id: chapter.id, index })}>
                고치기
              </Button>
            </div>
          </li>
        ))}
      </ol>
      <p>
        <Button variant="secondary" disabled={full} onClick={() => setEditing({ id: newChapterId(chapters), index: null })}>
          장 더하기
        </Button>
      </p>
      <Dialog title={editing ? chapterTitle(scenario, editing) : '장'} open={editing !== null} onClose={close}>
        {editing ? <ChapterForm scenario={scenario} targets={targets} editing={editing} done={close} /> : null}
      </Dialog>
    </section>
  );
}

function chapterTitle(scenario: ScenarioDetail, editing: Editing): string {
  if (editing.index === null) return `새 장(${scenario.chapters.length + 1}장)`;
  return `${editing.index + 1}장: ${scenario.chapters[editing.index]?.name ?? ''}`;
}

type FormProps = Props & { targets: Targets; editing: Editing; done: () => void };

function ChapterForm({ scenario, targets, editing, done }: FormProps) {
  const chapter = editing.index === null ? undefined : scenario.chapters[editing.index];
  const first = (editing.index ?? scenario.chapters.length) === 0;
  const [draft, setDraft] = useState<ChapterDraft>(() => chapterDraft(chapter));
  const saving = useScenarioSave(scenario.id);
  const hints = chapterHints(draft, { first, chapters: scenario.chapters, chapterId: editing.id, startPlace: scenario.start_place ?? null });
  const blocked = hasChapterHints(hints);
  const elsewhere = openedElsewhere(scenario.chapters, editing.id);
  const onMap = mapPlaces(scenario);

  function update(changes: Partial<ChapterDraft>) {
    setDraft((current) => ({ ...current, ...changes }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (blocked) return;
    if (await saving.save({ chapters: withChapter(scenario.chapters, toChapter(editing.id, draft, first)) })) done();
  }

  async function remove() {
    if (await saving.save({ chapters: withoutChapter(scenario.chapters, editing.id) })) done();
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate aria-label="장">
      <ProblemNotice problem={saving.problem} />
      <TextField label="이름" maxLength={CHAPTER_NAME_MAX_LENGTH} value={draft.name} onChange={(event) => update({ name: event.target.value })} error={hints.fields.name} />
      {first ? null : <AfterChoices earlier={earlierChapters(scenario.chapters, editing.index)} picked={draft.after} onChange={(after) => update({ after })} />}
      {first ? (
        <p className="ui-field__hint">첫 장입니다. 테이블은 이 장에서 시작하므로 넘어오는 조건이 없습니다.</p>
      ) : (
        <fieldset className="scenario-choices">
          <legend>넘어오는 조건</legend>
          <p className="ui-field__hint">앞의 장에 있을 때 채워지면 라운드가 닫힐 때 이 장으로 넘어갑니다. 한 번에 한 장씩, 앞으로만 갑니다.</p>
          <ConditionsEditor
            label="넘어오는 조건"
            kinds={KINDS_FOR.any}
            drafts={draft.when}
            onChange={(when) => update({ when })}
            match={draft.match}
            onMatch={(match) => update({ match })}
            targets={targets}
            hints={hints.when}
          />
          {hints.fields.when ? <p className="ui-field__error">{hints.fields.when}</p> : null}
        </fieldset>
      )}
      <fieldset className="scenario-choices">
        <legend>이 장이 여는 장소</legend>
        <p className="ui-field__hint">
          {first ? '첫 장이 여는 것은 처음부터 열려 있습니다.' : '이 장이 오기 전까지 지도에 없고 갈 수 없습니다. 고르지 않은 갈림길이면 그 테이블에서 계속 닫혀 있습니다.'} 맵의 장소만 고릅니다.
        </p>
        <OpenChoices
          label="장소"
          choices={targets.places.filter((place) => onMap.has(place.id) || draft.places.includes(place.id))}
          picked={draft.places}
          elsewhere={elsewhere}
          onChange={(places) => update({ places })}
        />
        {hints.fields.places ? <p className="ui-field__error">{hints.fields.places}</p> : null}
      </fieldset>
      <fieldset className="scenario-choices">
        <legend>이 장이 여는 퀘스트</legend>
        <p className="ui-field__hint">이 장이 오기 전까지 드러나지도 이루지도 않습니다. 진행 중으로 시작하는 퀘스트는 이 장이 올 때 드러납니다.</p>
        <OpenChoices label="퀘스트" choices={targets.quests} picked={draft.quests} elsewhere={elsewhere} onChange={(quests) => update({ quests })} />
        {hints.fields.quests ? <p className="ui-field__error">{hints.fields.quests}</p> : null}
      </fieldset>
      {hints.fields.opens ? <Notice tone="error">{hints.fields.opens}</Notice> : null}
      <p className="hint">이름표: {editing.id}</p>
      <div className="actions">
        <Button type="submit" busy={saving.busy} disabled={blocked}>
          저장
        </Button>
        {chapter && editing.index !== null ? (
          <Button variant="quiet" disabled={saving.busy || !canRemove(scenario.chapters, editing.index)} onClick={() => void remove()}>
            장 지우기
          </Button>
        ) : null}
      </div>
      {chapter && editing.index !== null && !canRemove(scenario.chapters, editing.index) ? <p className="hint">다른 장이 있으면 첫 장은 지우지 못합니다. 뒤의 장부터 지우세요.</p> : null}
    </form>
  );
}

type AfterProps = { earlier: Chapter[]; picked: string[]; onChange: (picked: string[]) => void };

/** 앞의 장을 고르는 체크 상자들(#289). 목록에서 이 장보다 앞의 장만 고른다 */
function AfterChoices({ earlier, picked, onChange }: AfterProps) {
  const before = earlier[earlier.length - 1];
  return (
    <fieldset className="scenario-choices">
      <legend>앞의 장</legend>
      <p className="ui-field__hint">
        고르지 않으면 바로 앞의 장({before ? `「${before.name}」` : '없음'}) 다음입니다. 여럿 고르면 그 어느 장에서든 넘어옵니다. 같은 장 다음에 올 장이 여럿이면 갈림길이고, 조건이 함께
        맞으면 목록에서 앞의 장으로 갑니다.
      </p>
      {earlier.map((one, index) => (
        <Checkbox
          key={one.id}
          label={`${index + 1}장: ${one.name}`}
          checked={picked.includes(one.id)}
          onChange={(event) => onChange(event.target.checked ? [...picked, one.id] : picked.filter((id) => id !== one.id))}
        />
      ))}
    </fieldset>
  );
}

type OpenProps = { label: string; choices: EntryChoice[]; picked: string[]; elsewhere: Map<string, number>; onChange: (picked: string[]) => void };

/** 열 것을 고르는 체크 상자들. 다른 장이 연 것은 그 장을 적고 고르지 못하게 한다 */
function OpenChoices({ label, choices, picked, elsewhere, onChange }: OpenProps) {
  if (choices.length === 0) return <p className="hint">고를 {label}가 없습니다.</p>;
  return (
    <div role="group" aria-label={`여는 ${label}`}>
      {choices.map((one) => {
        const other = elsewhere.get(one.id);
        const checked = picked.includes(one.id);
        return (
          <Checkbox
            key={one.id}
            label={one.name}
            checked={checked}
            disabled={other !== undefined && !checked}
            description={other !== undefined ? `${other}장이 엽니다` : undefined}
            onChange={(event) => onChange(event.target.checked ? [...picked, one.id] : picked.filter((id) => id !== one.id))}
          />
        );
      })}
    </div>
  );
}
