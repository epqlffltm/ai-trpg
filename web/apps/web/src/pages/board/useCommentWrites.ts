// web/apps/web/src/pages/board/useCommentWrites.ts
// 댓글 쓰기, 고치기, 지우기. 쓰는 곳(폼, 댓글 한 줄)마다 따로 부른다. 그래야 한 곳의 실패와 기다림이 다른 곳에 보이지 않는다.
// 하고 나면 댓글과 글(댓글 수)을 다시 읽는다. 결과는 성공했는가(boolean)만 돌려준다(실패는 error 로 본다).

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { createComment, deleteComment, updateComment } from '../../api/board';
import { commentsQuery, postQuery } from './boardQueries';

function useRefresh(postId: string) {
  const queryClient = useQueryClient();
  return async () => {
    await queryClient.invalidateQueries({ queryKey: commentsQuery(postId).queryKey });
    await queryClient.invalidateQueries({ queryKey: postQuery(postId).queryKey });
  };
}

/** 댓글이나 답글(parentId) 쓰기 */
export function useCreateComment(postId: string, parentId: string | null) {
  const refresh = useRefresh(postId);
  const mutation = useMutation({
    mutationFn: (content: string) => createComment(postId, { content, parent_id: parentId }),
    onSuccess: refresh,
  });
  return { ...mutation, submit: (content: string) => mutation.mutateAsync(content).then(() => true, () => false) };
}

export function useUpdateComment(postId: string, commentId: string) {
  const refresh = useRefresh(postId);
  const mutation = useMutation({ mutationFn: (content: string) => updateComment(commentId, content), onSuccess: refresh });
  return { ...mutation, submit: (content: string) => mutation.mutateAsync(content).then(() => true, () => false) };
}

export function useDeleteComment(postId: string, commentId: string) {
  const refresh = useRefresh(postId);
  const mutation = useMutation({ mutationFn: () => deleteComment(commentId), onSuccess: refresh });
  return { ...mutation, submit: () => mutation.mutateAsync().then(() => true, () => false) };
}
