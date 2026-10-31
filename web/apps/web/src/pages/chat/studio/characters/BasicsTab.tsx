// web/apps/web/src/pages/chat/studio/characters/BasicsTab.tsx
// 캐릭터의 기본 탭(C6): 이름, 나이, 성별, 장르, 태그, 등급, 공개 범위. 지우기도 여기에 둔다.

import { SelectField, TextField } from '@ai-trpg/ui';
import { useState } from 'react';
import type { AssetCharacterDetail, AssetRating, AssetVisibility } from '../../../../api/types';
import { AGE_MAX, basicsDraft, basicsHints, GENDER_MAX, NAME_MAX, toBasicsBody, type BasicsDraft } from './basicsForm';
import { CharacterForm } from './CharacterForm';
import { GenreSelect } from './GenreSelect';
import { DeleteCharacterButton } from './DeleteCharacterButton';
import { useCharacterSave } from './useCharacterSave';

const RATINGS: Record<AssetRating, string> = { all: '전체 이용가', adult: '성인용' };
const VISIBILITIES: Record<AssetVisibility, string> = { private: '비공개(나만 대화한다)', public: '공개(게시한 판으로 누구나 대화한다)' };

export function BasicsTab({ character }: { character: AssetCharacterDetail }) {
  const [draft, setDraft] = useState<BasicsDraft>(() => basicsDraft(character));
  const saving = useCharacterSave(character.id);
  const hints = basicsHints(draft);
  const fields = saving.problem?.fields ?? {};

  function update(changes: Partial<BasicsDraft>) {
    setDraft((current) => ({ ...current, ...changes }));
  }

  async function submit() {
    const saved = await saving.save(toBasicsBody(draft));
    // 서버가 다듬은 값(앞뒤 공백을 뗀 이름, 겹친 태그)으로 다시 채운다
    if (saved) setDraft(basicsDraft(saved));
  }

  return (
    <CharacterForm
      label="기본"
      busy={saving.busy}
      problem={saving.problem}
      saved={saving.saved}
      blocked={Object.keys(hints).length > 0}
      onSubmit={() => void submit()}
      actions={<DeleteCharacterButton characterId={character.id} name={character.name} />}
    >
      <TextField
        label="이름"
        name="name"
        maxLength={NAME_MAX}
        value={draft.name}
        onChange={(event) => update({ name: event.target.value })}
        error={hints.name}
      />
      <TextField
        label="나이(선택)"
        name="age"
        maxLength={AGE_MAX}
        value={draft.age}
        onChange={(event) => update({ age: event.target.value })}
        error={hints.age}
      />
      <TextField
        label="성별(선택)"
        name="gender"
        maxLength={GENDER_MAX}
        value={draft.gender}
        onChange={(event) => update({ gender: event.target.value })}
        error={hints.gender}
      />
      <GenreSelect value={draft.genre} error={fields.genre} onChange={(genre) => update({ genre })} where="대화" />
      <TextField
        label="태그(쉼표로 나눈다)"
        name="tags"
        value={draft.tags}
        onChange={(event) => update({ tags: event.target.value })}
        error={hints.tags}
      />
      <SelectField
        label="등급"
        name="rating"
        value={draft.rating}
        onChange={(event) => update({ rating: event.target.value as AssetRating })}
        error={fields.rating}
        hint="성인용은 본인인증으로 성인 확인을 한 사람만 고를 수 있고, 성인 확인을 한 사람에게만 보입니다."
      >
        {Object.entries(RATINGS).map(([rating, label]) => (
          <option key={rating} value={rating}>
            {label}
          </option>
        ))}
      </SelectField>
      <SelectField
        label="공개 범위"
        name="visibility"
        value={draft.visibility}
        onChange={(event) => update({ visibility: event.target.value as AssetVisibility })}
        error={fields.visibility}
        hint="공개해도 게시한 판이 있어야 목록에 나옵니다. 지금은 운영자만 공개로 둘 수 있습니다."
      >
        {Object.entries(VISIBILITIES).map(([visibility, label]) => (
          <option key={visibility} value={visibility}>
            {label}
          </option>
        ))}
      </SelectField>
    </CharacterForm>
  );
}
