// board-server/src/comments/list-comments.query.ts

/**
 * 댓글 목록을 부를 때 주소에 붙이는 값(?after=57&size=20)의 모양과 규칙.
 */

import { Type } from 'class-transformer';
import { IsInt, IsOptional, Matches, Max, Min } from 'class-validator';
import { RECORD_ID } from '../ids/record-id.js';
import { DEFAULT_SLICE_SIZE, MAX_SLICE_SIZE } from './slice.js';

export class ListCommentsQuery {
  /** 이 번호의 댓글 다음부터 읽는다. 적지 않으면 처음부터다. 앞의 응답의 next 를 그대로 넣는다 */
  @IsOptional()
  @Matches(RECORD_ID, { message: 'after 는 댓글 번호여야 합니다.' })
  after?: string;

  /** 한 번에 댓글을 몇 개 담는가. 답글은 세지 않는다 */
  @Type(() => Number)
  @IsInt({ message: 'size 는 정수여야 합니다.' })
  @Min(1, { message: 'size 는 1 이상이어야 합니다.' })
  @Max(MAX_SLICE_SIZE, {
    message: `size 는 ${MAX_SLICE_SIZE} 이하여야 합니다.`,
  })
  size: number = DEFAULT_SLICE_SIZE;
}
