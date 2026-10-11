// board-server/src/posts/search-posts.query.ts

/**
 * 글을 검색할 때 주소에 붙이는 값(?q=고정+버그&board=free&page=1&size=20)의 모양과 규칙.
 * 쪽을 나누는 값(page, size)은 글 목록과 같다.
 */

import { Transform } from 'class-transformer';
import { IsOptional, IsString, Matches, MaxLength } from 'class-validator';
import { BOARD_SLUG } from '../boards/board-slug.pipe.js';
import { ListPostsQuery } from './list-posts.query.js';
import { NO_NUL } from './post-text.js';
import {
  MAX_QUERY_LENGTH,
  MAX_TERMS,
  MIN_TERM_LENGTH,
  normalizeQuery,
  NOT_TOO_MANY_TERMS,
  TERMS_LONG_ENOUGH,
} from './search.js';

export class SearchPostsQuery extends ListPostsQuery {
  /** 검색어. 빈칸으로 낱말을 나눈다. 모든 낱말이 제목이나 본문에 들어 있는 글을 찾는다 */
  @Transform(normalizeQuery)
  @IsString({ message: 'q 는 글자여야 합니다.' })
  @Matches(TERMS_LONG_ENOUGH, {
    message: `검색어는 낱말마다 ${MIN_TERM_LENGTH}자 이상이어야 합니다.`,
  })
  @Matches(NOT_TOO_MANY_TERMS, {
    message: `검색어의 낱말은 ${MAX_TERMS}개를 넘을 수 없습니다.`,
  })
  @Matches(NO_NUL, { message: '검색어에 쓸 수 없는 글자가 있습니다.' })
  @MaxLength(MAX_QUERY_LENGTH, {
    message: `검색어는 ${MAX_QUERY_LENGTH}자를 넘을 수 없습니다.`,
  })
  q: string;

  /** 어느 게시판에서 찾는가. 주소 이름(slug)이다. 적지 않으면 모든 게시판에서 찾는다 */
  @IsOptional()
  @IsString({ message: 'board 는 글자여야 합니다.' })
  @Matches(BOARD_SLUG, { message: 'board 는 게시판의 이름이어야 합니다.' })
  board?: string;
}
