// board-server/src/posts/list-posts.query.ts

/**
 * 글 목록을 부를 때 주소에 붙이는 값(?page=2&size=20)의 모양과 규칙.
 */

import { Type } from 'class-transformer';
import { IsInt, Max, Min } from 'class-validator';
import {
  DEFAULT_PAGE,
  DEFAULT_PAGE_SIZE,
  MAX_PAGE,
  MAX_PAGE_SIZE,
} from './page.js';

export class ListPostsQuery {
  /** 몇 번째 쪽인가. 1 부터 센다 */
  @Type(() => Number)
  @IsInt({ message: 'page 는 정수여야 합니다.' })
  @Min(1, { message: 'page 는 1 이상이어야 합니다.' })
  @Max(MAX_PAGE, { message: `page 는 ${MAX_PAGE} 이하여야 합니다.` })
  page: number = DEFAULT_PAGE;

  /** 한 쪽에 몇 개를 담는가 */
  @Type(() => Number)
  @IsInt({ message: 'size 는 정수여야 합니다.' })
  @Min(1, { message: 'size 는 1 이상이어야 합니다.' })
  @Max(MAX_PAGE_SIZE, { message: `size 는 ${MAX_PAGE_SIZE} 이하여야 합니다.` })
  size: number = DEFAULT_PAGE_SIZE;
}
