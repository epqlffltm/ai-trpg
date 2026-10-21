// board-server/src/posts/posts-search.controller.ts

/**
 * 글 검색의 API.
 *
 *   GET /posts?q=고정+버그&board=free&page=1&size=20     로그인 불필요
 *
 * 게시판 아래(/boards/:slug/posts)에 두지 않았다. 모든 게시판에서 찾는 것이 기본이고,
 * 게시판 하나로 좁히는 것은 고르는 값(board)이다.
 * 결과는 글 목록과 같은 모양이다. 고정한 글을 따로 싣지 않는다. 찾은 글을 새 글부터 보여 줄 뿐이다.
 */

import { Controller, Get, HttpCode, HttpStatus, Query } from '@nestjs/common';
import { Public } from '../auth/public.decorator.js';
import { AuthorsService } from '../authors/authors.service.js';
import { nicknameOf } from '../authors/nicknames.js';
import { Board } from '../boards/board.entity.js';
import { BoardsService } from '../boards/boards.service.js';
import { CommentCountsService } from '../comment-counts/comment-counts.service.js';
import { countOf } from '../comment-counts/counts.js';
import { pageOf } from './page.js';
import {
  PostSummaryPageResponse,
  toPostSummaryResponse,
} from './post.response.js';
import { PostsSearchService } from './posts-search.service.js';
import { SearchPostsQuery } from './search-posts.query.js';
import { termsOf } from './search.js';

/** 게시판의 번호로 주소 이름(slug)을 찾는 표를 만든다. */
export function slugsById(boards: readonly Board[]): Map<number, string> {
  return new Map(boards.map((board) => [board.id, board.slug]));
}

@Controller('posts')
export class PostsSearchController {
  constructor(
    private readonly boards: BoardsService,
    private readonly search: PostsSearchService,
    private readonly commentCounts: CommentCountsService,
    private readonly authors: AuthorsService,
  ) {}

  /** 낱말이 모두 들어 있는 글을 한 쪽 돌려준다. 새 글부터다. 본문은 싣지 않는다. 없는 게시판이면 404 다. */
  @Public()
  @Get()
  @HttpCode(HttpStatus.OK)
  async find(
    @Query() query: SearchPostsQuery,
  ): Promise<PostSummaryPageResponse> {
    const now = new Date();
    const board =
      query.board === undefined
        ? undefined
        : await this.boards.getBySlug(query.board);
    const page = await this.search.search(
      { terms: termsOf(query.q), boardId: board?.id },
      query.page,
      query.size,
    );
    const slugs = slugsById(board ? [board] : await this.boards.list());
    const [counts, nicknames] = await Promise.all([
      this.commentCounts.countForMany(page.items.map((post) => post.id)),
      this.authors.nicknamesOf(page.items.map((post) => post.authorId)),
    ]);
    return pageOf(
      page.items.map((post) =>
        toPostSummaryResponse(post, {
          // 글이 있는 게시판은 지울 수 없다(posts 의 외래 키). 표에 없을 수 없다
          boardSlug: slugs.get(post.boardId) ?? '',
          commentCount: countOf(counts, post.id),
          authorNickname: nicknameOf(nicknames, post.authorId),
          now,
        }),
      ),
      page.page,
      page.size,
      page.total,
    );
  }
}
