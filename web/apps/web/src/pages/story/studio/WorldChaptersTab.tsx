// web/apps/web/src/pages/story/studio/WorldChaptersTab.tsx
// 세계관의 장 탭(D7, docs/architecture/chapters.md). 장마다 이름, 넘어오는 조건(첫 장은 없다), 그 장부터 열리는 장소와 이벤트.
// 장은 엔진이 행동의 맨 끝에 조건을 보고 한 장씩 넘긴다. 어느 장에도 고르지 않은 장소와 이벤트는 처음부터 열려 있다.
// 장소, 이벤트, 인물, 물건, 시간대는 저장된 것에서 고른다. 로어북 항목은 저장된 세계관에 붙인 로어북의 지금 글에서 고른다
// (게시할 때는 그 마지막 판에 있어야 한다. 게시 점검이 본다).

import { Button, Checkbox, TextField } from '@ai-trpg/ui';
import { useQueries, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import type { StoryWorldDetail } from '../../../api/storyWorlds';
import { CharacterForm as StudioForm } from '../../chat/studio/characters/CharacterForm';
import { newKey } from '../../chat/studio/characters/keys';
import { lorebookQuery } from '../../chat/studio/lorebooks/lorebookQueries';
import {
  addChapter,
  changeChapter,
  CHAPTER_NAME_MAX,
  chapterDrafts,
  CHAPTERS_MAX,
  chaptersHints,
  hasChaptersHints,
  loreChoices,
  moveChapterUp,
  removeChapter,
  toChaptersBody,
  toggleOpen,
  type ChapterDraft,
  type ChapterHints,
  type OpenKind,
} from './chaptersForm';
import { ConditionsEditor } from './ConditionsEditor';
import { savedChoices, type Choice, type ConditionChoices } from './conditionsForm';
import { useWorldSave } from './useWorldSave';
import { labelOr } from './worldLabels';
import { castCharactersQuery } from './worldQueries';

export function WorldChaptersTab({ world }: { world: StoryWorldDetail }) {
  const [chapters, setChapters] = useState<ChapterDraft[]>(() => chapterDrafts(world));
  const saving = useWorldSave(world.id);
  const characters = useQuery(castCharactersQuery());
  const names = (characters.data?.items ?? []).map((character) => ({ id: character.id, name: character.name }));
  const events = world.events.map((event) => ({ id: event.id, name: event.name }));
  const saved = savedChoices(world, names, events);
  const books = useQueries({ queries: world.lorebooks.map((lorebookId) => lorebookQuery(lorebookId)) });
  const lore = loreChoices(books.flatMap((book) => (book.data ? [book.data] : [])));
  // 조건이 고를 장은 고치는 중인 장이다(이름을 바꾸거나 더한 장도 고른다)
  const choices: ConditionChoices = { ...saved, chapters: chapters.map((chapter, at) => ({ id: chapter.id, name: labelOr(chapter.name, `${at + 1}장`) })) };
  const hints = chaptersHints(chapters, choices, world.start_place);

  async function submit() {
    const result = await saving.save(toChaptersBody(chapters));
    if (result) setChapters(chapterDrafts(result));
  }

  return (
    <StudioForm label="장" busy={saving.busy} problem={saving.problem} saved={saving.saved} blocked={hasChaptersHints(hints)} onSubmit={() => void submit()}>
      <p className="hint">
        이야기를 장으로 나눕니다. 첫 장에서 시작하고, 행동마다 다음 장의 조건을 보아 맞으면 한 장씩 넘어갑니다. 장마다 그 장부터 열리는 장소와 이벤트, 로어북 항목을 고릅니다.
        어느 장에도 고르지 않은 것은 처음부터 열려 있습니다. 장이 없으면 모두 처음부터 열려 있습니다.
      </p>
      <p className="hint">뒤 장의 비밀을 적은 로어북 항목은 그 장에서 열어 주세요. 열리기 전에는 상시 항목이어도 모델에 가지 않습니다.</p>
      {chapters.length === 0 ? <p>아직 장이 없습니다.</p> : null}
      <ol className="plain-list" aria-label="장">
        {chapters.map((chapter, index) => (
          <ChapterItem
            key={chapter.id}
            chapter={chapter}
            index={index}
            choices={choices}
            places={saved.places}
            events={events}
            lore={lore}
            hints={hints[chapter.id] as ChapterHints}
            update={(change) => setChapters((current) => changeChapter(current, chapter.id, change))}
            toggle={(kind, contentId) => setChapters((current) => toggleOpen(current, chapter.id, kind, contentId))}
            onUp={() => setChapters((current) => moveChapterUp(current, index))}
            onRemove={() => setChapters((current) => removeChapter(current, chapter.id))}
          />
        ))}
      </ol>
      <p>
        <Button variant="secondary" disabled={chapters.length >= CHAPTERS_MAX} onClick={() => setChapters((current) => addChapter(current, newKey('chapter', current.map((chapter) => chapter.id))))}>
          장 더하기
        </Button>{' '}
        <span className="hint">
          {chapters.length} / {CHAPTERS_MAX}
        </span>
      </p>
    </StudioForm>
  );
}

type ItemProps = {
  chapter: ChapterDraft;
  index: number;
  choices: ConditionChoices;
  places: Choice[];
  events: Choice[];
  lore: Choice[];
  hints: ChapterHints;
  update: (change: (chapter: ChapterDraft) => ChapterDraft) => void;
  toggle: (kind: OpenKind, contentId: string) => void;
  onUp: () => void;
  onRemove: () => void;
};

function ChapterItem({ chapter, index, choices, places, events, lore, hints, update, toggle, onUp, onRemove }: ItemProps) {
  const label = labelOr(chapter.name, `${index + 1}장`);
  return (
    <li className="scenario-opening">
      <h3>
        {index + 1}장: {label}
      </h3>
      <TextField label={`${index + 1}장의 이름`} maxLength={CHAPTER_NAME_MAX} value={chapter.name} onChange={(change) => update((current) => ({ ...current, name: change.target.value }))} error={hints.name} />
      {index === 0 ? (
        <p className="hint">첫 장은 처음부터 이 장입니다. 넘어오는 조건이 없습니다.</p>
      ) : (
        <>
          <ConditionsEditor prefix={label} draft={chapter.when} choices={choices} hints={hints.conditions} onChange={(when) => update((current) => ({ ...current, when }))} emptyText="조건을 하나 이상 적어야 합니다." />
          {hints.when ? <p className="ui-field__error">{hints.when}</p> : null}
        </>
      )}
      <fieldset className="scenario-choices">
        <legend>{label}부터 열리는 장소</legend>
        {places.length === 0 ? <p className="hint">지도 탭에서 장소를 먼저 저장해 주세요.</p> : null}
        {places.map((place, at) => (
          <Checkbox key={place.id} label={`${label}: ${labelOr(place.name, `장소 ${at + 1}`)}`} checked={chapter.places.includes(place.id)} onChange={() => toggle('places', place.id)} />
        ))}
        {hints.opens ? <p className="ui-field__error">{hints.opens}</p> : null}
      </fieldset>
      <fieldset className="scenario-choices">
        <legend>{label}부터 열리는 이벤트</legend>
        {events.length === 0 ? <p className="hint">이벤트 탭에서 이벤트를 먼저 저장해 주세요.</p> : null}
        {events.map((event, at) => (
          <Checkbox key={event.id} label={`${label}: ${labelOr(event.name, `이벤트 ${at + 1}`)}`} checked={chapter.events.includes(event.id)} onChange={() => toggle('events', event.id)} />
        ))}
      </fieldset>
      {lore.length > 0 ? (
        <fieldset className="scenario-choices">
          <legend>{label}부터 모델에 가는 로어북 항목</legend>
          {lore.map((entry) => (
            <Checkbox key={entry.id} label={`${label}: ${entry.name}`} checked={chapter.lore.includes(entry.id)} onChange={() => toggle('lore', entry.id)} />
          ))}
        </fieldset>
      ) : null}
      <div className="form-actions">
        <Button variant="quiet" aria-label={`${label}을(를) 위로`} disabled={index === 0} onClick={onUp}>
          위로
        </Button>
        <Button variant="quiet" aria-label={`${label} 지우기`} onClick={onRemove}>
          장 지우기
        </Button>
      </div>
    </li>
  );
}
