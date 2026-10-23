// web/apps/web/src/pages/trpg/studio/DeleteAssetButton.tsx
// 재료 하나를 지우는 단추(B9). 한 번 더 묻고, 지우면 그 종류의 목록으로 간다.
// 쓰는 시나리오가 있으면 지우지 못하고 그 제목들을 창에 알린다(studioProblem.ts). 시나리오는 창의 알림이 다르다(deleteNote).

import { useNavigate } from 'react-router';
import type { StudioKind } from '../../../api/studio';
import { ConfirmButton } from '../../../components/ConfirmButton';
import { kindText, studioPath } from './studioKinds';
import { useDeleteAsset } from './useAssetActions';

type Props = { kind: StudioKind; assetId: string; title: string };

export function DeleteAssetButton({ kind, assetId, title }: Props) {
  const navigate = useNavigate();
  const deleting = useDeleteAsset(kind, assetId);
  const text = kindText(kind);

  async function remove(): Promise<boolean> {
    const done = await deleting.remove();
    if (done) navigate(studioPath(kind), { replace: true });
    return done;
  }

  return (
    <ConfirmButton label="지우기" title={`${text.label} 지우기`} confirm="지우기" busy={deleting.busy} problem={deleting.problem} onConfirm={remove}>
      <p>「{title}」</p>
      <p>{text.deleteNote ?? '지우면 되돌릴 수 없습니다. 이 재료를 쓰는 시나리오가 있으면 지우지 못합니다.'}</p>
    </ConfirmButton>
  );
}
