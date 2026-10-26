// web/apps/web/src/pages/board/PostActions.tsx
// 글 아래의 단추(A11). 고치기(글쓴이), 지우기(글쓴이와 운영자, 한 번 더 묻는다), 고정과 풀기(운영자), 신고(로그인한 사람이 남의 글을).
// 누구에게 보일지는 boardPermissions.ts 가 정한다. 나를 모르면(로그인 전, 읽는 중) 아무것도 보이지 않는다.

import type { Board, BoardMe, Post } from '../../api/types';
import { ConfirmButton } from '../../components/ConfirmButton';
import { Link } from 'react-router';
import { canDeletePost, canEditPost, canPin, canReport } from './boardPermissions';
import { describeBoardWriteProblem } from './boardWriteProblem';
import { PinControl } from './PinControl';
import { ReportButton } from './ReportButton';
import { usePostActions } from './usePostActions';

type Props = { post: Post; board: Board | undefined; me: BoardMe | undefined };

export function PostActions({ post, board, me }: Props) {
  const actions = usePostActions(post);
  if (me === undefined) return null;
  return (
    <div className="post-actions">
      {canEditPost(post, board, me) ? <Link to={`/board/posts/${encodeURIComponent(post.id)}/edit`}>고치기</Link> : null}
      {canDeletePost(post, board, me) ? (
        <ConfirmButton
          label="지우기"
          ariaLabel="글 지우기"
          title="글 지우기"
          confirm="지우기"
          busy={actions.removing.isPending}
          problem={actions.removing.error ? describeBoardWriteProblem(actions.removing.error, '글') : undefined}
          onConfirm={actions.remove}
        >
          <p>이 글과 달린 댓글이 모두 보이지 않게 됩니다. 되돌리지 못합니다.</p>
        </ConfirmButton>
      ) : null}
      {canPin(me) ? (
        <PinControl
          post={post}
          busy={actions.pinning.isPending}
          problem={actions.pinning.error ? describeBoardWriteProblem(actions.pinning.error, '고정') : undefined}
          onPin={actions.pin}
        />
      ) : null}
      {canReport(post, me) ? <ReportButton target={{ kind: 'post', id: post.id }} ariaLabel="글 신고" /> : null}
    </div>
  );
}
