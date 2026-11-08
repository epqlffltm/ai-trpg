// web/apps/web/src/pages/board/PostNewPage.tsx
// 글쓰기(A11, /board/:slug/new). 로그인해야 열린다(RequireSession). 쓰면 그 글로 간다.
// 운영자만 쓰는 게시판(공지, 이벤트)에서 운영자가 아니면 폼 대신 까닭을 보인다(서버도 403 으로 막는다).
// 모양은 글 화면(PostPage)과 같다(Stitch 11번): 위에 게시판 고르기, 카드의 머리에 게시판 표시와 제목, 그 아래 폼.

import { Notice } from '@ai-trpg/ui';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router';
import { createPost } from '../../api/board';
import { EMPTY_POST, postBody, type PostDraft } from './boardForm';
import { canWritePost } from './boardPermissions';
import { BOARD_KEY, boardsQuery, postQuery } from './boardQueries';
import { describeBoardWriteProblem } from './boardWriteProblem';
import { PostForm } from './PostForm';
import { BoardTabs } from './BoardTabs';
import { useBoardMe } from './useBoardMe';
import { putQueryData } from '../../queryClient';

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
      await putQueryData(queryClient, postQuery(post.id).queryKey, post);
      await queryClient.invalidateQueries({ queryKey: [...BOARD_KEY, 'posts', slug] });
      void navigate(`/board/posts/${encodeURIComponent(post.id)}`);
    },
  });

  return (
    <main className="page board-page">
      <BoardTabs current={slug} />
      <section className="post board-card" aria-labelledby="post-write-title">
        <header className="post__head">
          <div className="post__heading">
            <Link className="post__board" to={listPath}>
              {board?.name ?? '게시판'}
            </Link>
            <h1 id="post-write-title">글쓰기</h1>
          </div>
        </header>
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
      </section>
    </main>
  );
}
