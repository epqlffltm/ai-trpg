// board-server/src/comments/update-comment.dto.ts

/**
 * 댓글을 고칠 때 받는 값의 모양과 규칙. 고칠 수 있는 것은 내용뿐이다.
 * 어느 글의 댓글인지, 어느 댓글의 답글인지는 옮길 수 없다.
 */

import { IsString, Matches, MaxLength } from 'class-validator';
import { HAS_VISIBLE_TEXT, NO_NUL } from '../posts/post-text.js';
import { COMMENT_MAX_LENGTH } from './comment.entity.js';

export class UpdateCommentDto {
  @IsString({ message: '댓글은 글자여야 합니다.' })
  @Matches(HAS_VISIBLE_TEXT, { message: '댓글을 적어야 합니다.' })
  @Matches(NO_NUL, { message: '댓글에 쓸 수 없는 글자가 있습니다.' })
  @MaxLength(COMMENT_MAX_LENGTH, {
    message: `댓글은 ${COMMENT_MAX_LENGTH}자를 넘을 수 없습니다.`,
  })
  content: string;
}
