// web/apps/web/src/pages/story/studio/WorldEventsTab.tsx
// 세계관의 이벤트 탭(D7). 이벤트마다 이름, 열리는 조건, 되풀이, 장면 지시(상황, 나오는 인물, 일러스트), 열릴 때의 효과, 선택지(글과 효과).
// 위의 이벤트가 먼저 맞춰진다(행동 뒤에 하나만 열린다). 장소, 물건, 시간대, 인물은 저장된 것에서 고르고,
// "이벤트가 열린 적이 있다" 조건은 지금 고치는 이벤트에서 고른다.

import { Button, Checkbox, TextField } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import type { StoryWorldDetail } from '../../../api/storyWorlds';
import { TextAreaField } from '../../../components/TextAreaField';
import { CharacterForm as StudioForm } from '../../chat/studio/characters/CharacterForm';
import { newKey } from '../../chat/studio/characters/keys';
import { ConditionsEditor } from './ConditionsEditor';
import { savedChoices, type ConditionChoices } from './conditionsForm';
import { EffectsEditor } from './EffectsEditor';
import {
  addChoice,
  addEvent,
  CHOICE_TEXT_MAX,
  CHOICES_MAX,
  changeChoice,
  changeEvent,
  EVENT_NAME_MAX,
  eventDrafts,
  EVENTS_MAX,
  eventsHints,
  hasEventsHints,
  moveEventUp,
  removeChoice,
  removeEvent,
  toEventsBody,
  type EventDraft,
  type EventHints,
} from './eventsForm';
import { SceneEditor } from './SceneEditor';
import { useWorldSave } from './useWorldSave';
import { labelOr } from './worldLabels';
import { castCharactersQuery } from './worldQueries';

export function WorldEventsTab({ world }: { world: StoryWorldDetail }) {
  const [events, setEvents] = useState<EventDraft[]>(() => eventDrafts(world));
  const saving = useWorldSave(world.id);
  const characters = useQuery(castCharactersQuery());
  const names = (characters.data?.items ?? []).map((character) => ({ id: character.id, name: character.name }));
  const choices = savedChoices(world, names, events.map((event) => ({ id: event.id, name: event.name })));
  const hints = eventsHints(events, choices);

  async function submit() {
    const saved = await saving.save(toEventsBody(events));
    if (saved) setEvents(eventDrafts(saved));
  }

  return (
    <StudioForm label="이벤트" busy={saving.busy} problem={saving.problem} saved={saving.saved} blocked={hasEventsHints(hints)} onSubmit={() => void submit()}>
      <p className="hint">
        행동(이동, 시간 보내기, 건네기 같은 것) 뒤에 엔진이 조건을 맞춰 보고, 맞는 이벤트 가운데 위의 것 하나만 엽니다. 열리면 효과를 반영하고 모델이 장면을 씁니다.
        선택지가 있으면 사용자가 고르고, 그 효과를 반영한 뒤 모델이 반응을 씁니다.
      </p>
      {events.length === 0 ? <p>아직 이벤트가 없습니다.</p> : null}
      <ol className="plain-list" aria-label="이벤트">
        {events.map((event, index) => (
          <EventItem
            key={event.id}
            event={event}
            index={index}
            choices={choices}
            hints={hints[event.id] as EventHints}
            update={(change) => setEvents((current) => changeEvent(current, event.id, change))}
            onUp={() => setEvents((current) => moveEventUp(current, index))}
            onRemove={() => setEvents((current) => removeEvent(current, event.id))}
          />
        ))}
      </ol>
      <p>
        <Button variant="secondary" disabled={events.length >= EVENTS_MAX} onClick={() => setEvents((current) => addEvent(current, newKey('event', current.map((event) => event.id))))}>
          이벤트 더하기
        </Button>{' '}
        <span className="hint">
          {events.length} / {EVENTS_MAX}
        </span>
      </p>
    </StudioForm>
  );
}

type ItemProps = {
  event: EventDraft;
  index: number;
  choices: ConditionChoices;
  hints: EventHints;
  update: (change: (event: EventDraft) => EventDraft) => void;
  onUp: () => void;
  onRemove: () => void;
};

function EventItem({ event, index, choices, hints, update, onUp, onRemove }: ItemProps) {
  const label = labelOr(event.name, `이벤트 ${index + 1}`);
  return (
    <li className="scenario-opening">
      <h3>{label}</h3>
      <TextField
        label={`이벤트 ${index + 1}의 이름`}
        maxLength={EVENT_NAME_MAX}
        value={event.name}
        onChange={(change) => update((current) => ({ ...current, name: change.target.value }))}
        error={hints.name}
      />
      <Checkbox label={`${label}을(를) 되풀이한다`} checked={event.repeat} onChange={(change) => update((current) => ({ ...current, repeat: change.target.checked }))} description="끄면 한 번만 열립니다." />
      <ConditionsEditor prefix={label} draft={event.when} choices={choices} hints={hints.when} onChange={(when) => update((current) => ({ ...current, when }))} emptyText="조건이 없으면 행동 뒤에 바로 열립니다." />
      <SceneEditor prefix={label} scene={event.scene} cast={choices.cast} hint={hints.scene} onChange={(scene) => update((current) => ({ ...current, scene }))} />
      <EffectsEditor prefix={`${label}이(가) 열릴 때`} effects={event.onOpen} choices={choices} hints={hints.onOpen} onChange={(onOpen) => update((current) => ({ ...current, onOpen }))} emptyText="열릴 때 바뀌는 것이 없습니다." />
      <fieldset className="scenario-choices">
        <legend>{label}의 선택지</legend>
        {event.choices.length === 0 ? <p className="hint">선택지가 없으면 장면만 쓰고 이어 갑니다.</p> : null}
        <ol className="plain-list" aria-label={`${label}의 선택지`}>
          {event.choices.map((choice, at) => {
            const choiceLabel = `${label}의 선택지 ${at + 1}`;
            return (
              <li key={choice.id} className="scenario-opening">
                <TextAreaField
                  label={`${choiceLabel}의 글`}
                  rows={2}
                  maxLength={CHOICE_TEXT_MAX}
                  value={choice.text}
                  onChange={(change) => update((current) => changeChoice(current, choice.id, { text: change.target.value }))}
                  error={hints.choices[choice.id]}
                />
                <EffectsEditor
                  prefix={choiceLabel}
                  effects={choice.effects}
                  choices={choices}
                  hints={hints.choiceEffects[choice.id] ?? {}}
                  onChange={(effects) => update((current) => changeChoice(current, choice.id, { effects }))}
                  emptyText="고르면 바뀌는 것이 없습니다(모델의 반응만)."
                />
                <Button variant="quiet" aria-label={`${choiceLabel} 지우기`} onClick={() => update((current) => removeChoice(current, choice.id))}>
                  지우기
                </Button>
              </li>
            );
          })}
        </ol>
        <p>
          <Button variant="secondary" disabled={event.choices.length >= CHOICES_MAX} onClick={() => update((current) => addChoice(current, newKey('choice', current.choices.map((choice) => choice.id))))}>
            {label}의 선택지 더하기
          </Button>
        </p>
      </fieldset>
      <div className="form-actions">
        <Button variant="quiet" aria-label={`${label}을(를) 위로`} disabled={index === 0} onClick={onUp}>
          위로
        </Button>
        <Button variant="quiet" aria-label={`${label} 지우기`} onClick={onRemove}>
          이벤트 지우기
        </Button>
      </div>
    </li>
  );
}
