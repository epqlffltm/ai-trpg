// web/apps/web/src/components/HeartButton.tsx
// 작품 소개의 관심(하트) 단추(#989). 누르면 두고, 다시 누르면 거둔다(aria-pressed). 옆에 관심의 수를 보인다.
// 로그인하지 않았으면 수만 보이고 로그인으로 가는 길을 둔다. 로그인했으면 내가 두었는지를 서버에 묻는다.
// 바꾸지 못하면 그대로 두고 알린다. 내 관심 작품의 목록은 바꾼 뒤 다시 읽는다.

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useLocation } from 'react-router';
import { fetchHeart, setHeart, type HeartKind, type HeartState } from '../api/hearts';
import { useSession } from '../auth/useSession';

/** count 는 작품에 실린 관심의 수다. 서버가 아직 싣지 않으면(먼저 올라간 화면) 0 으로 본다 */
type Props = { kind: HeartKind; id: string; count: number | undefined };

/** 관심의 열쇠. 내 관심 작품의 열쇠는 ['hearts', 'mine', kind] 다 */
export function heartQueryKey(kind: HeartKind, id: string) {
  return ['hearts', kind, id] as const;
}

export function HeartButton({ kind, id, count }: Props) {
  const session = useSession();
  const location = useLocation();
  if (!session) {
    return (
      <p className="hint">
        ♡ {(count ?? 0).toLocaleString('ko-KR')} ·{' '}
        <Link to="/login" state={{ from: location.pathname }}>
          로그인하고 관심 두기
        </Link>
      </p>
    );
  }
  return <SignedInHeart kind={kind} id={id} count={count} />;
}

function SignedInHeart({ kind, id, count }: Props) {
  const queryClient = useQueryClient();
  const key = heartQueryKey(kind, id);
  const state = useQuery({ queryKey: key, queryFn: ({ signal }) => fetchHeart(kind, id, signal) });
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const hearted = state.data?.hearted ?? false;
  const shown = state.data?.heart_count ?? count ?? 0;

  async function toggle() {
    setBusy(true);
    setFailed(false);
    try {
      const next = await setHeart(kind, id, !hearted);
      queryClient.setQueryData<HeartState>(key, next);
      void queryClient.invalidateQueries({ queryKey: ['hearts', 'mine', kind] });
    } catch {
      setFailed(true);
    }
    setBusy(false);
  }

  return (
    <p>
      <button type="button" className="ui-button ui-button--secondary" aria-pressed={hearted} disabled={busy || state.isPending} onClick={() => void toggle()}>
        {hearted ? '♥ 관심' : '♡ 관심'} {shown.toLocaleString('ko-KR')}
      </button>
      {failed ? <span role="alert"> 바꾸지 못했습니다. 잠시 뒤에 다시 해 보세요.</span> : null}
    </p>
  );
}
