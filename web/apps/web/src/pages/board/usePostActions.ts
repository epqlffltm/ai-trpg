// web/apps/web/src/pages/board/usePostActions.ts
// 글 하나에 하는 일(지우기, 고정, 풀기)과 그 뒤에 다시 읽을 것. 화면은 결과(성공했는가)만 받는다.
//   - 지우면 그 글을 저장소에서 빼고 게시판으로 간다
//   - 고정과 풀기는 글과 그 게시판의 목록(고정한 글이 첫 쪽에 온다)을 다시 읽는다

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router';
import { deletePost, pinPost, unpinPost } from '../../api/board';
import type { Post } from '../../api/types';
import { BOARD_KEY, postQuery } from './boardQueries';

export function usePostActions(post: Post) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  async function refreshLists() {
    await queryClient.invalidateQueries({ queryKey: [...BOARD_KEY, 'posts', post.board] });
    await queryClient.invalidateQueries({ queryKey: [...BOARD_KEY, 'search'] });
  }

  const removing = useMutation({
    mutationFn: () => deletePost(post.id),
    onSuccess: async () => {
      queryClient.removeQueries({ queryKey: postQuery(post.id).queryKey });
      queryClient.removeQueries({ queryKey: [...BOARD_KEY, 'comments', post.id] });
      await refreshLists();
      void navigate(`/board/${encodeURIComponent(post.board)}`, { replace: true });
    },
  });

  const pinning = useMutation({
    mutationFn: (days: number | null) => (days === null ? unpinPost(post.id) : pinPost(post.id, days)),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: postQuery(post.id).queryKey });
      await refreshLists();
    },
  });

  return {
    remove: () => removing.mutateAsync().then(succeeded, failed),
    removing,
    /** days 일 동안 고정한다. null 이면 푼다 */
    pin: (days: number | null) => pinning.mutateAsync(days).then(succeeded, failed),
    pinning,
  };
}

function succeeded(): boolean {
  return true;
}

function failed(): boolean {
  return false;
}
