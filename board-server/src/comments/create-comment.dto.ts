// board-server/src/comments/create-comment.dto.ts

/**
 * 댓글을 쓸 때 받는 값의 모양과 규칙. 어느 글인지는 주소에 있고, 글쓴이는 토큰에서 안다.
 */

import { IsOptional, IsString, Matches, MaxLength } from 'class-validator';
import { RECORD_ID } from '../ids/record-id.js';
import { HAS_VISIBLE_TEXT, NO_NUL } from '../posts/post-text.js';
import { COMMENT_MAX_LENGTH } from './comment.entity.js';

export class CreateCommentDto {
  /** 내용. 받은 그대로 저장한다 */
  @IsString({ message: '댓글은 글자여야 합니다.' })
  @Matches(HAS_VISIBLE_TEXT, { message: '댓글을 적어야 합니다.' })
  @Matches(NO_NUL, { message: '댓글에 쓸 수 없는 글자가 있습니다.' })
  @MaxLength(COMMENT_MAX_LENGTH, {
    message: `댓글은 ${COMMENT_MAX_LENGTH}자를 넘을 수 없습니다.`,
  })
  content: string;

  /**
   * 답글이면 어느 댓글에 다는가. 적지 않거나 null 이면 글에 다는 댓글이다. 번호는 글자로 보낸다("57").
   * null 을 받는 것은 화면이 "답글이 아님"을 null 로 보내기 쉬워서다
   */
  @IsOptional()
  @IsString({ message: 'parent_id 는 글자로 적은 댓글 번호여야 합니다.' })
  @Matches(RECORD_ID, { message: 'parent_id 는 댓글 번호여야 합니다.' })
  parent_id?: string | null;
}
