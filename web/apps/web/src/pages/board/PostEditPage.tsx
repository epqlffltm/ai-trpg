// web/apps/web/src/pages/board/PostEditPage.tsx
// 글 고치기(A11, /board/posts/:postId/edit). 로그인해야 열린다. 글쓴이만 고친다(운영자 게시판은 지금도 운영자인 글쓴이만).
// 바뀐 칸만 보낸다. 바뀐 것이 없으면 보내지 않고 글로 돌아간다.

import { Button, Notice } from '@ai-trpg/ui';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router';
import { updatePost } from '../../api/board';
import type { Post, PostUpdate } from '../../api/types';
import { postDraftOf, postPatch, type PostDraft } from './boardForm';
import { canEditPost } from './boardPermissions';
import { boardProblemText } from './boardProblem';
import { BOARD_KEY, boardsQuery, postQuery } from './boardQueries';
import { describeBoardWriteProblem } from './boardWriteProblem';
import { PostForm } from './PostForm';
import { useBoardMe } from './useBoardMe';

export function PostEditPage() {
  const { postId = '' } = useParams();
  const post = useQuery(postQuery(postId));
  const boards = useQuery(boardsQuery());
  const { me } = useBoardMe();
  const board = boards.data?.find((item) => item.slug === post.data?.board);
  const postPath = `/board/posts/${encodeURIComponent(postId)}`;
  const saving = useSavePost(postId, postPath);
  const ready = post.data !== undefined && me !== undefined && boards.data !== undefined;

  return (
    <main className="page page--medium">
      <p>
        <Link to={postPath}>글로 돌아가기</Link>
      </p>
      <h1>글 고치기</h1>
      {post.isError ? (
        <Notice tone="error">
          {boardProblemText(post.error, '글')}{' '}
          <Button variant="quiet" onClick={() => void post.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {!ready && !post.isError ? <p aria-busy="true">불러오는 중</p> : null}
      {ready && !canEditPost(post.data, board, me) ? <Notice tone="info">자신의 글만 고칠 수 있습니다.</Notice> : null}
      {ready && canEditPost(post.data, board, me) ? (
        <PostForm
          initial={postDraftOf(post.data)}
          submitLabel="저장"
          busy={saving.isPending}
          problem={saving.error ? describeBoardWriteProblem(saving.error, '글') : undefined}
          cancelTo={postPath}
          onSubmit={(draft) => saving.save(post.data, draft)}
        />
      ) : null}
    </main>
  );
}

/** 저장하고 글로 돌아간다. 목록과 검색의 제목도 다시 읽게 한다 */
function useSavePost(postId: string, postPath: string) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const mutation = useMutation({
    mutationFn: (patch: PostUpdate) => updatePost(postId, patch),
    onSuccess: async (saved: Post) => {
      queryClient.setQueryData(postQuery(postId).queryKey, saved);
      await queryClient.invalidateQueries({ queryKey: [...BOARD_KEY, 'posts', saved.board] });
      await queryClient.invalidateQueries({ queryKey: [...BOARD_KEY, 'search'] });
      void navigate(postPath);
    },
  });
  function save(current: Post, draft: PostDraft) {
    const patch = postPatch(postDraftOf(current), draft);
    if (patch === null) void navigate(postPath);
    else mutation.mutate(patch);
  }
  return { save, isPending: mutation.isPending, error: mutation.error };
}
