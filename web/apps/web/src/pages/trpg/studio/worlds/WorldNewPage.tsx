// web/apps/web/src/pages/trpg/studio/worlds/WorldNewPage.tsx
// 세계관 만들기(B9, /trpg/studio/worlds/new). 만들면 그 세계관의 고치기로 간다.

import { Link, useNavigate } from 'react-router';
import { createWorld } from '../../../../api/worlds';
import type { WorldDetail } from '../../../../api/types';
import { studioPath } from '../studioKinds';
import { useSaveAsset } from '../useAssetActions';
import { CREATED_STATE } from '../useSavedNotice';
import { newWorldDraft, toWorldCreate, type WorldDraft } from './worldForm';
import { WorldEditor } from './WorldEditor';

export function WorldNewPage() {
  const navigate = useNavigate();
  const saving = useSaveAsset<WorldDetail>('worlds');

  async function submit(draft: WorldDraft) {
    const made = await saving.save(() => createWorld(toWorldCreate(draft)));
    if (made) navigate(studioPath('worlds', made.id), { replace: true, state: CREATED_STATE });
  }

  return (
    <main className="page page--medium">
      <p>
        <Link to={studioPath('worlds')}>내 세계관</Link>
      </p>
      <h1>새 세계관</h1>
      <WorldEditor
        initial={newWorldDraft()}
        submitLabel="만들기"
        busy={saving.busy}
        problem={saving.problem}
        onSubmit={(draft) => void submit(draft)}
      />
    </main>
  );
}
