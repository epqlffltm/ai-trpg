// web/apps/web/src/pages/story/studio/WorldCastTab.tsx
// 세계관의 인물 탭(D7). 인물마다 내 캐릭터(게시한 판이 있는 것), 기본 장소와 일정, 호감도(보이는 방식, 처음 값, 단계, 선물),
// 고백(성공하는 단계와 조건, 실패하면 계속 또는 끝), 보이기의 덮어쓰기를 정한다. 조건은 표로 고른다(ConditionsEditor).
// 장소, 물건, 시간대, 이벤트는 저장된 것에서 고르고, 조건의 인물은 지금 고치는 인물들에서 고른다(castForm.ts 의 castChoices).
// 인물의 이야기 속 모습(이름, 소개, 말투, 그림)은 그 캐릭터의 게시한 판에서 온다. 게시할 때 복사한다.

import { Button, Checkbox, Notice, SelectField, TextField } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router';
import type { StoryWorldDetail, StoryWorldShow } from '../../../api/storyWorlds';
import { CharacterForm as StudioForm } from '../../chat/studio/characters/CharacterForm';
import { newKey } from '../../chat/studio/characters/keys';
import {
  addGift,
  addMember,
  addScheduleLine,
  addStage,
  CAST_MAX,
  castChoices,
  castDrafts,
  castHints,
  changeConfession,
  changeGift,
  changeMember,
  changeScheduleLine,
  changeStage,
  GIFTS_MAX,
  hasCastHints,
  removeGift,
  removeMember,
  removeScheduleLine,
  removeStage,
  SCHEDULE_MAX,
  STAGE_NAME_MAX,
  STAGES_MAX,
  stageNames,
  toCastBody,
  toggleConfession,
  togglePanelField,
  togglePanelOverride,
  type CastDraft,
  type MemberHints,
} from './castForm';
import { ConditionsEditor } from './ConditionsEditor';
import type { ConditionChoices } from './conditionsForm';
import { useWorldSave } from './useWorldSave';
import { labelOr, MAP_LABELS, PANEL_LABELS, REVEAL_LABELS } from './worldLabels';
import { castCharactersQuery } from './worldQueries';

type Named = { id: string; name: string };
type PanelField = StoryWorldShow['panel'][number];
type MemberUpdate = (change: (member: CastDraft) => CastDraft) => void;

export function WorldCastTab({ world }: { world: StoryWorldDetail }) {
  const [cast, setCast] = useState<CastDraft[]>(() => castDrafts(world));
  const saving = useWorldSave(world.id);
  const characters = useQuery(castCharactersQuery());
  const published: Named[] = (characters.data?.items ?? []).filter((character) => character.latest_version !== null).map((character) => ({ id: character.id, name: character.name }));
  const choices = castChoices(world, cast, published);
  const hints = castHints(cast, choices, published);

  async function submit() {
    const saved = await saving.save(toCastBody(cast));
    if (saved) setCast(castDrafts(saved));
  }

  return (
    <StudioForm label="인물" busy={saving.busy} problem={saving.problem} saved={saving.saved} blocked={!characters.isSuccess || hasCastHints(hints)} onSubmit={() => void submit()}>
      <p className="hint">
        인물마다 게시한 내 chat 캐릭터를 하나 고릅니다. 이름, 소개, 말투, 그림은 그 캐릭터의 판에서 오고, 세계관을 게시할 때 복사합니다.{' '}
        <Link to="/chat/studio/characters">내 캐릭터</Link>
      </p>
      {characters.isError ? <Notice tone="error">내 캐릭터를 불러오지 못했습니다. 잠시 뒤에 다시 열어 주세요.</Notice> : null}
      {characters.isSuccess && published.length === 0 ? <p>게시한 chat 캐릭터가 없습니다. 캐릭터를 먼저 만들고 게시해 주세요.</p> : null}
      {cast.length === 0 ? <p>아직 인물이 없습니다. 인물이 하나는 있어야 게시합니다.</p> : null}
      <ol className="plain-list" aria-label="인물">
        {cast.map((member, index) => (
          <MemberItem
            key={member.id}
            world={world}
            member={member}
            label={labelOr(published.find((character) => character.id === member.characterId)?.name ?? '', `인물 ${index + 1}`)}
            characters={published}
            choices={choices}
            hints={hints[member.id] as MemberHints}
            update={(change) => setCast((current) => changeMember(current, member.id, change))}
            onRemove={() => setCast((current) => removeMember(current, member.id))}
          />
        ))}
      </ol>
      <p>
        <Button variant="secondary" disabled={cast.length >= CAST_MAX} onClick={() => setCast((current) => addMember(current, newKey('cast', current.map((member) => member.id))))}>
          인물 더하기
        </Button>{' '}
        <span className="hint">
          {cast.length} / {CAST_MAX}
        </span>
      </p>
    </StudioForm>
  );
}

type ItemProps = {
  world: StoryWorldDetail;
  member: CastDraft;
  label: string;
  characters: Named[];
  choices: ConditionChoices;
  hints: MemberHints;
  update: MemberUpdate;
  onRemove: () => void;
};

function MemberItem({ world, member, label, characters, choices, hints, update, onRemove }: ItemProps) {
  return (
    <li className="scenario-opening">
      <h3>{label}</h3>
      <SelectField label={`${label}의 캐릭터`} value={member.characterId} onChange={(event) => update((current) => ({ ...current, characterId: event.target.value }))} error={hints.character}>
        <option value="">고르지 않음</option>
        {characters.map((character) => (
          <option key={character.id} value={character.id}>
            {character.name}
          </option>
        ))}
      </SelectField>
      <PlaceSection world={world} member={member} label={label} choices={choices} hints={hints} update={update} />
      <AffectionSection world={world} member={member} label={label} hints={hints} update={update} />
      <ConfessionSection member={member} label={label} choices={choices} hints={hints} update={update} />
      <ShowSection world={world} member={member} label={label} hints={hints} update={update} />
      <div className="form-actions">
        <Button variant="quiet" aria-label={`${label} 지우기`} onClick={onRemove}>
          인물 지우기
        </Button>
        <span className="hint">이 인물을 가리키는 조건과 이벤트는 게시 점검이 알립니다.</span>
      </div>
    </li>
  );
}

type SectionProps = { world: StoryWorldDetail; member: CastDraft; label: string; hints: MemberHints; update: MemberUpdate };

function PlaceSection({ world, member, label, choices, hints, update }: SectionProps & { choices: ConditionChoices }) {
  return (
    <fieldset className="scenario-choices">
      <legend>{label}의 자리</legend>
      <SelectField label={`${label}의 기본 장소`} value={member.home} onChange={(event) => update((current) => ({ ...current, home: event.target.value }))} error={hints.home}>
        <option value="">어디에도 없음(이벤트로만 나온다)</option>
        {world.places.map((place, index) => (
          <option key={place.id} value={place.id}>
            {labelOr(place.name, `장소 ${index + 1}`)}
          </option>
        ))}
      </SelectField>
      <p className="hint">일정은 위의 줄부터 맞춰 봅니다. 그 시간대에 조건이 맞는 첫 줄의 장소에 있고, 맞는 줄이 없으면 기본 장소에 있습니다.</p>
      <ol className="plain-list" aria-label={`${label}의 일정`}>
        {member.schedule.map((line, index) => {
          const lineLabel = `${label}의 일정 ${index + 1}`;
          return (
            <li key={index} className="scenario-opening">
              <SelectField label={`${lineLabel}의 시간대`} value={line.slot} onChange={(event) => update((current) => changeScheduleLine(current, index, { slot: event.target.value }))}>
                <option value="">고르지 않음</option>
                {world.slots.map((slot) => (
                  <option key={slot.id} value={slot.id}>
                    {slot.name}
                  </option>
                ))}
              </SelectField>
              <SelectField label={`${lineLabel}의 장소`} value={line.place} onChange={(event) => update((current) => changeScheduleLine(current, index, { place: event.target.value }))} error={hints.schedule[index]}>
                <option value="">고르지 않음</option>
                {world.places.map((place, at) => (
                  <option key={place.id} value={place.id}>
                    {labelOr(place.name, `장소 ${at + 1}`)}
                  </option>
                ))}
              </SelectField>
              <ConditionsEditor
                prefix={lineLabel}
                draft={line.when}
                choices={choices}
                hints={hints.scheduleWhen[index] ?? {}}
                onChange={(when) => update((current) => changeScheduleLine(current, index, { when }))}
                emptyText="조건이 없으면 그 시간대에는 늘 이 장소에 있습니다."
              />
              <div className="form-actions">
                <Button variant="quiet" aria-label={`${lineLabel} 지우기`} onClick={() => update((current) => removeScheduleLine(current, index))}>
                  지우기
                </Button>
              </div>
            </li>
          );
        })}
      </ol>
      <p>
        <Button variant="secondary" disabled={member.schedule.length >= SCHEDULE_MAX || world.places.length === 0} onClick={() => update(addScheduleLine)}>
          {label}의 일정 더하기
        </Button>
      </p>
    </fieldset>
  );
}

function AffectionSection({ world, member, label, hints, update }: SectionProps) {
  return (
    <fieldset className="scenario-choices">
      <legend>{label}의 호감도</legend>
      <SelectField label={`${label}의 호감도를 보이는 방식`} value={member.display} onChange={(event) => update((current) => ({ ...current, display: event.target.value as CastDraft['display'] }))}>
        <option value="stage">단계의 이름</option>
        <option value="number">숫자</option>
      </SelectField>
      <TextField label={`${label}의 처음 호감도(0~100)`} inputMode="numeric" value={member.start} onChange={(event) => update((current) => ({ ...current, start: event.target.value }))} error={hints.start} />
      <p>단계</p>
      <ol className="plain-list" aria-label={`${label}의 단계`}>
        {member.stages.map((stage, index) => (
          <li key={index} className="scenario-opening">
            <TextField label={`${label}의 단계 ${index + 1}의 이름`} maxLength={STAGE_NAME_MAX} value={stage.name} onChange={(event) => update((current) => changeStage(current, index, { name: event.target.value }))} />
            <TextField
              label={`${label}의 단계 ${index + 1}의 경계`}
              inputMode="numeric"
              value={stage.at}
              onChange={(event) => update((current) => changeStage(current, index, { at: event.target.value }))}
              error={hints.stages[index]}
            />
            <Button variant="quiet" aria-label={`${label}의 단계 ${index + 1} 지우기`} disabled={member.stages.length <= 1} onClick={() => update((current) => removeStage(current, index))}>
              지우기
            </Button>
          </li>
        ))}
      </ol>
      <p>
        <Button variant="secondary" disabled={member.stages.length >= STAGES_MAX} onClick={() => update(addStage)}>
          {label}의 단계 더하기
        </Button>{' '}
        <span className="hint">단계의 이름을 바꾸면 그 이름을 가리키는 조건을 다시 골라야 합니다.</span>
      </p>
      <p>선물</p>
      {world.items.length === 0 ? <p className="hint">물건 탭에서 물건을 먼저 저장해 주세요.</p> : null}
      <ol className="plain-list" aria-label={`${label}의 선물`}>
        {member.gifts.map((gift, index) => {
          const giftLabel = `${label}의 선물 ${index + 1}`;
          return (
            <li key={gift.id} className="scenario-opening">
              <SelectField label={`${giftLabel}의 물건`} value={gift.item} onChange={(event) => update((current) => changeGift(current, gift.id, { item: event.target.value }))}>
                <option value="">고르지 않음</option>
                {world.items.map((item, at) => (
                  <option key={item.id} value={item.id}>
                    {labelOr(item.name, `물건 ${at + 1}`)}
                  </option>
                ))}
              </SelectField>
              <TextField
                label={`${giftLabel}의 변화(-20~20)`}
                inputMode="numeric"
                value={gift.change}
                onChange={(event) => update((current) => changeGift(current, gift.id, { change: event.target.value }))}
                error={hints.gifts[gift.id]}
              />
              <Checkbox label="처음 한 번만" checked={gift.once} onChange={(event) => update((current) => changeGift(current, gift.id, { once: event.target.checked }))} />
              <Button variant="quiet" aria-label={`${giftLabel} 지우기`} onClick={() => update((current) => removeGift(current, gift.id))}>
                지우기
              </Button>
            </li>
          );
        })}
      </ol>
      <p>
        <Button
          variant="secondary"
          disabled={member.gifts.length >= GIFTS_MAX || world.items.length === 0}
          onClick={() => update((current) => addGift(current, newKey('gift', current.gifts.map((gift) => gift.id))))}
        >
          {label}의 선물 더하기
        </Button>
      </p>
    </fieldset>
  );
}

function ConfessionSection({ member, label, choices, hints, update }: Omit<SectionProps, 'world'> & { choices: ConditionChoices }) {
  const confession = member.confession;
  return (
    <fieldset className="scenario-choices">
      <legend>{label}의 고백</legend>
      <Checkbox label={`${label}에게 고백할 수 있다`} checked={confession !== null} onChange={() => update(toggleConfession)} />
      {confession ? (
        <>
          <SelectField label={`${label}의 고백이 성공하는 단계`} value={confession.stage} onChange={(event) => update((current) => changeConfession(current, { stage: event.target.value }))} error={hints.confession}>
            <option value="">고르지 않음</option>
            {stageNames(member).map((name) => (
              <option key={name} value={name}>
                {name} 이상
              </option>
            ))}
          </SelectField>
          <ConditionsEditor
            prefix={`${label}의 고백`}
            draft={confession.when}
            choices={choices}
            hints={hints.confessionWhen}
            onChange={(when) => update((current) => changeConfession(current, { when }))}
            emptyText="조건이 없으면 단계만 맞으면 성공합니다."
          />
          <SelectField label={`${label}의 고백이 실패하면`} value={confession.onFail} onChange={(event) => update((current) => changeConfession(current, { onFail: event.target.value as 'continue' | 'end' }))}>
            <option value="continue">계속(호감도가 내려가고 며칠 동안 다시 못 한다)</option>
            <option value="end">끝(고백 실패의 엔딩)</option>
          </SelectField>
          {confession.onFail === 'continue' ? (
            <>
              <TextField label={`${label}의 고백 실패로 내려가는 값`} inputMode="numeric" value={confession.failDrop} onChange={(event) => update((current) => changeConfession(current, { failDrop: event.target.value }))} />
              <TextField
                label={`${label}에게 다시 고백하지 못하는 날`}
                inputMode="numeric"
                value={confession.cooldownDays}
                onChange={(event) => update((current) => changeConfession(current, { cooldownDays: event.target.value }))}
              />
            </>
          ) : null}
        </>
      ) : (
        <p className="hint">고백할 수 없는 인물입니다.</p>
      )}
    </fieldset>
  );
}

function ShowSection({ world, member, label, hints, update }: SectionProps) {
  return (
    <fieldset className="scenario-choices">
      <legend>{label}의 보이기</legend>
      <SelectField label={`${label}의 공개`} value={member.reveal} onChange={(event) => update((current) => ({ ...current, reveal: event.target.value as CastDraft['reveal'] }))}>
        <option value="">세계관의 기본({REVEAL_LABELS[world.show.reveal]})</option>
        {Object.entries(REVEAL_LABELS).map(([value, text]) => (
          <option key={value} value={value}>
            {text}
          </option>
        ))}
      </SelectField>
      <SelectField label={`${label}의 지도`} value={member.map} onChange={(event) => update((current) => ({ ...current, map: event.target.value as CastDraft['map'] }))}>
        <option value="">세계관의 기본({MAP_LABELS[world.show.map]})</option>
        {Object.entries(MAP_LABELS).map(([value, text]) => (
          <option key={value} value={value}>
            {text}
          </option>
        ))}
      </SelectField>
      {member.map === 'stage' ? (
        <SelectField label={`${label}이(가) 지도에 보이는 단계`} value={member.mapStage} onChange={(event) => update((current) => ({ ...current, mapStage: event.target.value }))} error={hints.mapStage}>
          <option value="">고르지 않음</option>
          {stageNames(member).map((name) => (
            <option key={name} value={name}>
              {name} 이상
            </option>
          ))}
        </SelectField>
      ) : null}
      <Checkbox label={`${label}의 인물 창 항목을 따로 정한다`} checked={member.panel !== null} onChange={() => update((current) => togglePanelOverride(current, world.show.panel))} />
      {member.panel
        ? Object.entries(PANEL_LABELS).map(([field, text]) => (
            <Checkbox
              key={field}
              label={`${label}의 인물 창: ${text}`}
              checked={(member.panel ?? []).includes(field as PanelField)}
              onChange={() => update((current) => togglePanelField(current, field as PanelField))}
            />
          ))
        : null}
    </fieldset>
  );
}
