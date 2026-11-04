// web/apps/web/src/components/FollowButton.tsx
// 제작자 팔로우 단추(#989). "만든 사람" 줄의 이름 옆에 둔다. 누르면 팔로우하고, 다시 누르면 끊는다(aria-pressed).
// 로그인하지 않았으면 팔로워 수와 로그인으로 가는 길만 보인다. 나 자신이면 수만 보인다(서버도 422 로 막는다).
// 바꾸지 못하면 그대로 두고 알린다. 1,000명을 넘으면(409) 그 까닭을 알린다. 수를 읽지 못하면 아무것도 그리지 않는다.

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useLocation } from 'react-router';
import { ApiError } from '../api/errors';
import { fetchFollow, fetchFollowerCount, setFollow, type FollowState } from '../api/follows';
import type { Session } from '../api/session';
import { tokenClaims } from '../auth/roles';
import { useSession } from '../auth/useSession';

type Props = { creatorId: string };

/** 팔로우의 열쇠. 내 팔로잉의 열쇠는 FOLLOWING_KEY 다 */
export function followQueryKey(creatorId: string) {
  return ['follows', 'state', creatorId] as const;
}

export const FOLLOWING_KEY = ['follows', 'mine'] as const;

/** 로그인한 사람의 공개 ID(토큰의 sub). 서명은 확인하지 않는다. 단추를 숨기는 데만 쓴다 */
export function sessionPublicId(session: Session): string | undefined {
  const sub = tokenClaims(session.accessToken)?.sub;
  return typeof sub === 'string' ? sub : undefined;
}

export function FollowButton({ creatorId }: Props) {
  const session = useSession();
  if (session && sessionPublicId(session) !== creatorId) return <SignedInFollow creatorId={creatorId} />;
  return <FollowerCountOnly creatorId={creatorId} signedIn={session !== null} />;
}

function FollowerCountOnly({ creatorId, signedIn }: Props & { signedIn: boolean }) {
  const location = useLocation();
  const count = useQuery({ queryKey: ['follows', 'count', creatorId], queryFn: ({ signal }) => fetchFollowerCount(creatorId, signal) });
  if (!count.data) return null;
  return (
    <>
      {' · '}팔로워 {count.data.follower_count.toLocaleString('ko-KR')}
      {signedIn ? null : (
        <>
          {' · '}
          <Link to="/login" state={{ from: location.pathname }}>
            로그인하고 팔로우
          </Link>
        </>
      )}
    </>
  );
}

function SignedInFollow({ creatorId }: Props) {
  const queryClient = useQueryClient();
  const key = followQueryKey(creatorId);
  const state = useQuery({ queryKey: key, queryFn: ({ signal }) => fetchFollow(creatorId, signal) });
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  if (!state.data) return null;
  const { following, follower_count } = state.data;

  async function toggle() {
    setBusy(true);
    setFailure(null);
    try {
      const next = await setFollow(creatorId, !following);
      queryClient.setQueryData<FollowState>(key, next);
      void queryClient.invalidateQueries({ queryKey: FOLLOWING_KEY });
    } catch (error) {
      setFailure(failureText(error));
    }
    setBusy(false);
  }

  return (
    <>
      {' · '}팔로워 {follower_count.toLocaleString('ko-KR')}{' '}
      <button type="button" className="ui-button ui-button--secondary" aria-pressed={following} disabled={busy} onClick={() => void toggle()}>
        {following ? '팔로잉' : '팔로우'}
      </button>
      {failure ? <span role="alert"> {failure}</span> : null}
    </>
  );
}

function failureText(error: unknown): string {
  if (error instanceof ApiError && error.status === 409) return '팔로우는 1,000명까지입니다. 다른 제작자를 끊고 다시 해 보세요.';
  return '바꾸지 못했습니다. 잠시 뒤에 다시 해 보세요.';
}
