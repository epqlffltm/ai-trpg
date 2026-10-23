// web/apps/web/src/pages/trpg/studio/collection/CollectionNewPage.tsx
// 묶음 재료(로어북, 몬스터 모음) 만들기. 제목과 소개만 받고, 만들면 그 묶음의 화면으로 가서 담을 것을 더한다.

import { Link, useNavigate } from 'react-router';
import type { StudioKind } from '../../../../api/studio';
import type { AssetSummary } from '../../../../api/types';
import { kindText, studioPath } from '../studioKinds';
import { useSaveAsset } from '../useAssetActions';
import { CREATED_STATE } from '../useSavedNotice';
import { newCollectionDraft, toCollectionBody, type CollectionDraft } from './collectionForm';
import { CollectionEditor } from './CollectionEditor';

type Props = { kind: StudioKind; create: (body: { title: string; description: string }) => Promise<AssetSummary> };

export function CollectionNewPage({ kind, create }: Props) {
  const navigate = useNavigate();
  const saving = useSaveAsset<AssetSummary>(kind);
  const text = kindText(kind);

  async function submit(draft: CollectionDraft) {
    const made = await saving.save(() => create(toCollectionBody(draft)));
    if (made) navigate(studioPath(kind, made.id), { replace: true, state: CREATED_STATE });
  }

  return (
    <main className="page page--medium">
      <p>
        <Link to={studioPath(kind)}>{text.title}</Link>
      </p>
      <h1>{text.create}</h1>
      <CollectionEditor
        label={text.label}
        initial={newCollectionDraft()}
        submitLabel="만들기"
        busy={saving.busy}
        problem={saving.problem}
        onSubmit={(draft) => void submit(draft)}
      />
    </main>
  );
}
