// web/apps/web/src/pages/trpg/studio/AssetLoad.tsx
// 재료 하나를 읽는 동안과 읽지 못했을 때(B9). 없거나 남의 것이면(404) 찾을 수 없다고만 알린다.

import { Button, Notice } from '@ai-trpg/ui';
import type { StudioKind } from '../../../api/studio';
import { kindText } from './studioKinds';
import { isMissing } from './studioProblem';

type Props = { kind: StudioKind; pending: boolean; error: unknown; retry: () => void };

export function AssetLoad({ kind, pending, error, retry }: Props) {
  if (pending) return <p aria-busy="true">불러오는 중</p>;
  if (!error) return null;
  if (isMissing(error)) return <Notice>{kindText(kind).missing}</Notice>;
  return (
    <Notice tone="error">
      불러오지 못했습니다.{' '}
      <Button variant="quiet" onClick={retry}>
        다시 시도
      </Button>
    </Notice>
  );
}
