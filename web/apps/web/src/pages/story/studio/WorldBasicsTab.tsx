// web/apps/web/src/pages/story/studio/WorldBasicsTab.tsx
// 세계관의 기본 탭(D7): 이름, 태그, 등급, 공개 범위, 대표 그림. 지우기도 여기에 둔다.

import { SelectField, TextField } from '@ai-trpg/ui';
import { useState } from 'react';
import type { StoryWorldDetail } from '../../../api/storyWorlds';
import { ImagePicker } from '../../../components/ImagePicker';
import { CharacterForm as StudioForm } from '../../chat/studio/characters/CharacterForm';
import { DeleteWorldButton } from './DeleteWorldButton';
import { useWorldSave } from './useWorldSave';
import { NAME_MAX, toWorldBasicsBody, worldBasicsDraft, worldBasicsHints, type WorldBasicsDraft, type WorldRating, type WorldVisibility } from './worldBasicsForm';

const RATINGS: Record<WorldRating, string> = { all: '전체 이용가', adult: '성인용' };
const VISIBILITIES: Record<WorldVisibility, string> = { private: '비공개(나만 시작한다)', public: '공개(게시한 판으로 누구나 시작한다)' };

export function WorldBasicsTab({ world }: { world: StoryWorldDetail }) {
  const [draft, setDraft] = useState<WorldBasicsDraft>(() => worldBasicsDraft(world));
  const saving = useWorldSave(world.id);
  const hints = worldBasicsHints(draft);
  const fields = saving.problem?.fields ?? {};

  function update(changes: Partial<WorldBasicsDraft>) {
    setDraft((current) => ({ ...current, ...changes }));
  }

  async function submit() {
    const saved = await saving.save(toWorldBasicsBody(draft));
    if (saved) setDraft(worldBasicsDraft(saved));
  }

  return (
    <StudioForm
      label="기본"
      busy={saving.busy}
      problem={saving.problem}
      saved={saving.saved}
      blocked={Object.keys(hints).length > 0}
      onSubmit={() => void submit()}
      actions={<DeleteWorldButton worldId={world.id} name={world.name} />}
    >
      <TextField label="이름" name="name" maxLength={NAME_MAX} value={draft.name} onChange={(event) => update({ name: event.target.value })} error={hints.name} />
      <TextField label="태그(쉼표로 나눈다)" name="tags" value={draft.tags} onChange={(event) => update({ tags: event.target.value })} error={hints.tags} />
      <SelectField
        label="등급"
        name="rating"
        value={draft.rating}
        onChange={(event) => update({ rating: event.target.value as WorldRating })}
        error={fields.rating}
        hint="성인용은 본인인증으로 성인 확인을 한 사람만 고를 수 있습니다. 전체 이용가 세계관에는 성인 등급 캐릭터를 넣지 못합니다."
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
        onChange={(event) => update({ visibility: event.target.value as WorldVisibility })}
        error={fields.visibility}
        hint="공개해도 게시한 판이 있어야 목록에 나옵니다. 지금은 운영자만 공개로 둘 수 있습니다."
      >
        {Object.entries(VISIBILITIES).map(([visibility, label]) => (
          <option key={visibility} value={visibility}>
            {label}
          </option>
        ))}
      </SelectField>
      <ImagePicker label="대표 그림" imageId={draft.imageId} onChange={(imageId) => update({ imageId })} hint="목록과 소개에 나오는 그림입니다. 저장해야 붙습니다." />
    </StudioForm>
  );
}
