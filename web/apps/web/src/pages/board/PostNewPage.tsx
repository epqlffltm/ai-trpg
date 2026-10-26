// web/apps/web/src/pages/board/PostNewPage.tsx
// 글쓰기(A11, /board/:slug/new). 로그인해야 열린다(RequireSession). 쓰면 그 글로 간다.
// 운영자만 쓰는 게시판(공지, 이벤트)에서 운영자가 아니면 폼 대신 까닭을 보인다(서버도 403 으로 막는다).

import { Notice } from '@ai-trpg/ui';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router';
import { createPost } from '../../api/board';
import { EMPTY_POST, postBody, type PostDraft } from './boardForm';
import { canWritePost } from './boardPermissions';
import { BOARD_KEY, boardsQuery, postQuery } from './boardQueries';
import { describeBoardWriteProblem } from './boardWriteProblem';
import { PostForm } from './PostForm';
import { useBoardMe } from './useBoardMe';

export function PostNewPage() {
  const { slug = '' } = useParams();
  const boards = useQuery(boardsQuery());
  const { me } = useBoardMe();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const board = boards.data?.find((item) => item.slug === slug);
  const listPath = `/board/${encodeURIComponent(slug)}`;
  const creating = useMutation({
    mutationFn: (draft: PostDraft) => createPost(slug, postBody(draft)),
    onSuccess: async (post) => {
      queryClient.setQueryData(postQuery(post.id).queryKey, post);
      await queryClient.invalidateQueries({ queryKey: [...BOARD_KEY, 'posts', slug] });
      void navigate(`/board/posts/${encodeURIComponent(post.id)}`);
    },
  });

  return (
    <main className="page page--medium">
      <p>
        <Link to={listPath}>{board?.name ?? '게시판'}</Link>
      </p>
      <h1>글쓰기</h1>
      {boards.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {boards.isSuccess && !board ? <Notice tone="error">없는 게시판입니다.</Notice> : null}
      {board && board.write_policy === 'operator' && me === undefined ? <p aria-busy="true">불러오는 중</p> : null}
      {board && me !== undefined && !canWritePost(board, me) ? <Notice tone="info">이 게시판에는 운영자만 글을 씁니다.</Notice> : null}
      {board && (board.write_policy === 'member' || canWritePost(board, me)) ? (
        <PostForm
          initial={EMPTY_POST}
          submitLabel="올리기"
          busy={creating.isPending}
          problem={creating.error ? describeBoardWriteProblem(creating.error, '글') : undefined}
          cancelTo={listPath}
          onSubmit={(draft) => creating.mutate(draft)}
        />
      ) : null}
    </main>
  );
}
