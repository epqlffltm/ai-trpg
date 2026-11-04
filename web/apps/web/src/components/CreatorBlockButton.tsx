// web/apps/web/src/components/CreatorBlockButton.tsx
// 제작자 페이지의 "차단하기"(#988). 누르면 그 제작자의 작품이 공개 목록, 검색, 랭킹, 배너에서 빠진다. 다시 누르면 푼다(aria-pressed).
// 로그인했고 나 자신이 아닐 때만 보인다. 막은 것의 관리는 마이페이지의 "차단"에서 한다.

import { useSession } from '../auth/useSession';
import { useBlocks } from '../hooks/useBlocks';
import { sessionPublicId } from './FollowButton';

export function CreatorBlockButton({ creatorId }: { creatorId: string }) {
  const session = useSession();
  if (!session || sessionPublicId(session) === creatorId) return null;
  return <BlockToggle creatorId={creatorId} />;
}

function BlockToggle({ creatorId }: { creatorId: string }) {
  const actions = useBlocks();
  const blocked = actions.blocks.creators.includes(creatorId);
  return (
    <>
      {' '}
      <button
        type="button"
        className="ui-button ui-button--quiet"
        aria-pressed={blocked}
        disabled={actions.busy}
        onClick={() => void actions.setCreator(creatorId, !blocked)}
      >
        {blocked ? '차단 풀기' : '차단하기'}
      </button>
      {actions.failure ? <span role="alert"> {actions.failure}</span> : null}
    </>
  );
}
