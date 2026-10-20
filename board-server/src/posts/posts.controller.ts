// board-server/src/posts/posts.controller.ts

/**
 * 글의 API. 주소를 받아 서비스를 부르고, 결과를 응답의 모양으로 바꾼다.
 *
 *   GET    /boards/:slug/posts   한 게시판의 글 목록(쪽 번호)      로그인 불필요
 *   POST   /boards/:slug/posts   글 쓰기                            로그인 필요
 *   GET    /posts/:id            글 읽기                            로그인 불필요
 *   PATCH  /posts/:id            글 고치기(글쓴이)                  로그인 필요
 *   DELETE /posts/:id            글 지우기(글쓴이, 운영자)          로그인 필요
 *
 * 쓰기는 게시판 아래에 둔다. 글은 게시판에 쓰는 것이다. 읽고 고치고 지울 때는 글 번호만으로 가리킨다.
 * 글 번호는 게시판마다 따로 세지 않는다.
 *
 * 글을 돌려줄 때마다 댓글 수(comment_count)를 함께 싣는다. 수는 따로 센다(comment-counts/).
 * 목록은 그 쪽의 글을 모아 한 번에 센다. 방금 쓴 글은 세지 않는다. 댓글이 있을 수 없다.
 *
 * 글쓴이의 닉네임(author_nickname)도 함께 싣는다. 이름도 따로 읽는다(authors/). 목록은 그 쪽의 글쓴이를 모아 한 번에 읽는다.
 *
 * 목록의 첫 쪽에는 고정한 글(pinned)을 따로 싣는다. 고정한 글은 items 와 total 에 들지 않는다.
 * 고정하고 풀어도 다른 글의 쪽이 밀리지 않는다. 고정하고 푸는 주소는 pins.controller.ts 에 있다.
 * 쓰기, 고치기, 지우기는 결과마다 센다(board_writes_total, observability/counted.interceptor.ts).
 */

import {
  Body,
  Controller,
  Delete,
  Get,
  HttpCode,
  HttpStatus,
  Param,
  Patch,
  Post,
  Query,
  UseInterceptors,
} from '@nestjs/common';
import { CurrentUser } from '../auth/current-user.decorator.js';
import { Public } from '../auth/public.decorator.js';
// 타입만 가져온다(import type). 데코레이터가 붙은 인자의 타입이 인터페이스면 이렇게 적어야 빌드된다
import type { AccessClaims } from '../auth/tokens.js';
import { AuthorsService } from '../authors/authors.service.js';
import { nicknameOf } from '../authors/nicknames.js';
import { BoardSlugPipe } from '../boards/board-slug.pipe.js';
import { BoardsService } from '../boards/boards.service.js';
import { CommentCountsService } from '../comment-counts/comment-counts.service.js';
import { countOf } from '../comment-counts/counts.js';
import { countWrite } from '../observability/counted.interceptor.js';
import { CreatePostDto } from './create-post.dto.js';
import { ListPostsQuery } from './list-posts.query.js';
import { DEFAULT_PAGE } from './page.js';
import { PinsService } from './pins.service.js';
import { PostIdPipe } from './post-id.pipe.js';
import {
  PostListResponse,
  PostResponse,
  PostSummary,
  toPostResponse,
  toPostSummaryResponse,
} from './post.response.js';
import { Post as PostEntity } from './post.entity.js';
import { PostsService } from './posts.service.js';
import { UpdatePostDto } from './update-post.dto.js';

@Controller()
export class PostsController {
  constructor(
    private readonly boards: BoardsService,
    private readonly posts: PostsService,
    private readonly pins: PinsService,
    private readonly commentCounts: CommentCountsService,
    private readonly authors: AuthorsService,
  ) {}

  /** 한 게시판의 글 목록을 한 쪽 돌려준다. 새 글부터다. 본문은 싣지 않는다. 첫 쪽에는 고정한 글을 따로 싣는다. */
  @Public()
  @Get('boards/:slug/posts')
  @HttpCode(HttpStatus.OK)
  async list(
    @Param('slug', BoardSlugPipe) slug: string,
    @Query() query: ListPostsQuery,
  ): Promise<PostListResponse> {
    const now = new Date();
    const board = await this.boards.getBySlug(slug);
    const page = await this.posts.listIn(board, query.page, query.size, now);
    const pinned =
      query.page === DEFAULT_PAGE ? await this.pins.listIn(board, now) : [];
    const shown = [...pinned, ...page.items];
    const [counts, nicknames] = await Promise.all([
      this.commentCounts.countForMany(shown.map((post) => post.id)),
      this.authors.nicknamesOf(shown.map((post) => post.authorId)),
    ]);
    const toSummary = (post: PostSummary) =>
      toPostSummaryResponse(post, {
        boardSlug: board.slug,
        commentCount: countOf(counts, post.id),
        authorNickname: nicknameOf(nicknames, post.authorId),
        now,
      });
    return {
      pinned: pinned.map(toSummary),
      items: page.items.map(toSummary),
      page: page.page,
      size: page.size,
      total: page.total,
    };
  }

  /** 게시판에 글을 쓴다. 쓴 글을 돌려준다. */
  @Post('boards/:slug/posts')
  @HttpCode(HttpStatus.CREATED)
  @UseInterceptors(countWrite('post', 'create'))
  async create(
    @Param('slug', BoardSlugPipe) slug: string,
    @Body() input: CreatePostDto,
    @CurrentUser() user: AccessClaims,
  ): Promise<PostResponse> {
    const board = await this.boards.getBySlug(slug);
    const post = await this.posts.create(board, user, input);
    return toPostResponse(post, {
      boardSlug: board.slug,
      commentCount: 0,
      authorNickname: await this.authors.nicknameOf(post.authorId),
      now: new Date(),
    });
  }

  /** 글 하나를 본문까지 돌려준다. */
  @Public()
  @Get('posts/:id')
  @HttpCode(HttpStatus.OK)
  async read(@Param('id', PostIdPipe) id: string): Promise<PostResponse> {
    const post = await this.posts.get(id);
    return this.toFullResponse(post);
  }

  /** 글을 고친다. 보낸 칸만 고친다. 고친 글을 돌려준다. */
  @Patch('posts/:id')
  @HttpCode(HttpStatus.OK)
  @UseInterceptors(countWrite('post', 'update'))
  async update(
    @Param('id', PostIdPipe) id: string,
    @Body() changes: UpdatePostDto,
    @CurrentUser() user: AccessClaims,
  ): Promise<PostResponse> {
    const post = await this.posts.update(id, user, changes);
    return this.toFullResponse(post);
  }

  /** 글을 지운다. 돌려줄 내용이 없다. */
  @Delete('posts/:id')
  @HttpCode(HttpStatus.NO_CONTENT)
  @UseInterceptors(countWrite('post', 'delete'))
  async remove(
    @Param('id', PostIdPipe) id: string,
    @CurrentUser() user: AccessClaims,
  ): Promise<void> {
    await this.posts.remove(id, user);
  }

  /** 게시판과 함께 읽은 글 하나를 본문까지 응답의 모양으로 바꾼다. 댓글 수와 글쓴이의 이름을 따로 읽는다. */
  private async toFullResponse(post: PostEntity): Promise<PostResponse> {
    const [commentCount, authorNickname] = await Promise.all([
      this.commentCounts.countFor(post.id),
      this.authors.nicknameOf(post.authorId),
    ]);
    return toPostResponse(post, {
      boardSlug: post.board.slug,
      commentCount,
      authorNickname,
      now: new Date(),
    });
  }
}
