// web/apps/web/src/pages/trpg/studio/scenarios/ListingTab.tsx
// 시나리오의 소개 탭(B9). 공개 목록(B1)과 소개(B2)에 보일 한줄소개, 소개글, 장르, 태그를 탭의 저장으로 보낸다.
// 판에 굳지 않는다. 공개 중이면 저장하자마자 공개된 소개가 바뀐다. 공개할 판은 게시 탭에서 고른다.

import { Button, Checkbox, Notice, TextField } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router';
import type { Genre, ListingDetail, ScenarioDetail } from '../../../../api/types';
import { TextAreaField } from '../../../../components/TextAreaField';
import { GENRE_VALUES, genreLabel } from '../../labels';
import { GENRES_MAX, LISTING_DESCRIPTION_MAX, listingDraft, listingHints, TAGLINE_MAX, TAG_MAX, TAGS_MAX, toggleGenre, toListingBody, type ListingDraft } from './listingForm';
import { listingQuery } from './scenarioQueries';
import { ScenarioForm } from './ScenarioForm';
import { useListingSave } from './useListingSave';

export function ListingTab({ scenario }: { scenario: ScenarioDetail }) {
  const listing = useQuery(listingQuery(scenario.id));
  if (listing.isPending) return <p aria-busy="true">불러오는 중</p>;
  if (listing.isError) {
    return (
      <Notice tone="error">
        소개 페이지를 불러오지 못했습니다.{' '}
        <Button variant="quiet" onClick={() => void listing.refetch()}>
          다시 시도
        </Button>
      </Notice>
    );
  }
  return <ListingForm scenarioId={scenario.id} listing={listing.data} />;
}

function ListingForm({ scenarioId, listing }: { scenarioId: string; listing: ListingDetail }) {
  const [draft, setDraft] = useState<ListingDraft>(() => listingDraft(listing));
  const saving = useListingSave(scenarioId);
  const hints = listingHints(draft, listing.version !== null);

  function update(changes: Partial<ListingDraft>) {
    setDraft((current) => ({ ...current, ...changes }));
  }

  async function submit() {
    const saved = await saving.save(toListingBody(draft));
    // 서버가 다듬은 값(앞뒤 공백을 뗀 한줄소개와 태그)으로 다시 채운다
    if (saved) setDraft(listingDraft(saved));
  }

  return (
    <ScenarioForm label="소개" busy={saving.busy} problem={saving.problem} saved={saving.saved} blocked={Object.keys(hints).length > 0} onSubmit={() => void submit()}>
      <PublicationStatus scenarioId={scenarioId} listing={listing} />
      <div className="field-with-hint">
        <TextField
          label="한줄소개"
          name="tagline"
          maxLength={TAGLINE_MAX}
          value={draft.tagline}
          onChange={(event) => update({ tagline: event.target.value })}
          error={hints.tagline}
        />
        <p className="ui-field__hint">
          공개 목록의 카드에 보입니다. 공개하려면 있어야 합니다. {draft.tagline.length} / {TAGLINE_MAX}자.
        </p>
      </div>
      <TextAreaField
        label="소개글(선택)"
        name="listing_description"
        rows={8}
        maxLength={LISTING_DESCRIPTION_MAX}
        value={draft.description}
        onChange={(event) => update({ description: event.target.value })}
        error={hints.description}
        hint={`소개 화면에 보입니다. 진행 지침이나 GM 메모와 달리 누구나 봅니다. ${draft.description.length.toLocaleString('ko-KR')} / ${LISTING_DESCRIPTION_MAX.toLocaleString('ko-KR')}자.`}
      />
      <GenreChoices genres={draft.genres} error={hints.genres} onChange={(genres) => update({ genres })} />
      <div className="field-with-hint">
        <TextField label="태그(선택, 쉼표로 나눔)" name="tags" value={draft.tags} onChange={(event) => update({ tags: event.target.value })} error={hints.tags} />
        <p className="ui-field__hint">
          공개 목록에서 태그로 찾을 수 있습니다. {TAGS_MAX}개까지, 하나에 {TAG_MAX}자까지입니다.
        </p>
      </div>
    </ScenarioForm>
  );
}

function PublicationStatus({ scenarioId, listing }: { scenarioId: string; listing: ListingDetail }) {
  if (listing.version === null) {
    return <p className="hint">공개하지 않았습니다. 한줄소개와 장르를 적어 저장한 뒤, 게시 탭에서 낸 판 가운데 하나를 공개하세요.</p>;
  }
  return (
    <Notice>
      {listing.version}판을 공개 중입니다. 저장하면 공개된 소개가 바로 바뀝니다. <Link to={`/trpg/scenarios/${scenarioId}`}>공개된 소개 보기</Link>
    </Notice>
  );
}

type GenreProps = { genres: Genre[]; error: string | undefined; onChange: (genres: Genre[]) => void };

function GenreChoices({ genres, error, onChange }: GenreProps) {
  const full = genres.length >= GENRES_MAX;
  return (
    <fieldset className="scenario-choices scenario-genres">
      <legend>장르</legend>
      <p className="ui-field__hint">
        공개하려면 하나는 있어야 합니다. {GENRES_MAX}개까지 고릅니다({genres.length} / {GENRES_MAX}).
      </p>
      <div className="scenario-genres__list">
        {GENRE_VALUES.map((genre) => (
          <Checkbox
            key={genre}
            label={genreLabel(genre)}
            checked={genres.includes(genre)}
            disabled={full && !genres.includes(genre)}
            onChange={() => onChange(toggleGenre(genres, genre))}
          />
        ))}
      </div>
      {error ? <p className="ui-field__error">{error}</p> : null}
    </fieldset>
  );
}
