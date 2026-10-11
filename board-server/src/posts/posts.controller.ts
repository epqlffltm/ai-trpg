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
} from '@nestjs/common';
import { CurrentUser } from '../auth/current-user.decorator.js';
import { Public } from '../auth/public.decorator.js';
// 타입만 가져온다(import type). 데코레이터가 붙은 인자의 타입이 인터페이스면 이렇게 적어야 빌드된다
import type { AccessClaims } from '../auth/tokens.js';
import { BoardSlugPipe } from '../boards/board-slug.pipe.js';
import { BoardsService } from '../boards/boards.service.js';
import { CreatePostDto } from './create-post.dto.js';
import { ListPostsQuery } from './list-posts.query.js';
import { Page, pageOf } from './page.js';
import { PostIdPipe } from './post-id.pipe.js';
import {
  PostResponse,
  PostSummaryResponse,
  toPostResponse,
  toPostSummaryResponse,
} from './post.response.js';
import { PostsService } from './posts.service.js';
import { UpdatePostDto } from './update-post.dto.js';

@Controller()
export class PostsController {
  constructor(
    private readonly boards: BoardsService,
    private readonly posts: PostsService,
  ) {}

  /** 한 게시판의 글 목록을 한 쪽 돌려준다. 새 글부터다. 본문은 싣지 않는다. */
  @Public()
  @Get('boards/:slug/posts')
  @HttpCode(HttpStatus.OK)
  async list(
    @Param('slug', BoardSlugPipe) slug: string,
    @Query() query: ListPostsQuery,
  ): Promise<Page<PostSummaryResponse>> {
    const board = await this.boards.getBySlug(slug);
    const page = await this.posts.listIn(board, query.page, query.size);
    return pageOf(
      page.items.map((post) => toPostSummaryResponse(post, board.slug)),
      page.page,
      page.size,
      page.total,
    );
  }

  /** 게시판에 글을 쓴다. 쓴 글을 돌려준다. */
  @Post('boards/:slug/posts')
  @HttpCode(HttpStatus.CREATED)
  async create(
    @Param('slug', BoardSlugPipe) slug: string,
    @Body() input: CreatePostDto,
    @CurrentUser() user: AccessClaims,
  ): Promise<PostResponse> {
    const board = await this.boards.getBySlug(slug);
    const post = await this.posts.create(board, user.userId, input);
    return toPostResponse(post, board.slug);
  }

  /** 글 하나를 본문까지 돌려준다. */
  @Public()
  @Get('posts/:id')
  @HttpCode(HttpStatus.OK)
  async read(@Param('id', PostIdPipe) id: string): Promise<PostResponse> {
    const post = await this.posts.get(id);
    return toPostResponse(post, post.board.slug);
  }

  /** 글을 고친다. 보낸 칸만 고친다. 고친 글을 돌려준다. */
  @Patch('posts/:id')
  @HttpCode(HttpStatus.OK)
  async update(
    @Param('id', PostIdPipe) id: string,
    @Body() changes: UpdatePostDto,
    @CurrentUser() user: AccessClaims,
  ): Promise<PostResponse> {
    const post = await this.posts.update(id, user.userId, changes);
    return toPostResponse(post, post.board.slug);
  }

  /** 글을 지운다. 돌려줄 내용이 없다. */
  @Delete('posts/:id')
  @HttpCode(HttpStatus.NO_CONTENT)
  async remove(
    @Param('id', PostIdPipe) id: string,
    @CurrentUser() user: AccessClaims,
  ): Promise<void> {
    await this.posts.remove(id, user.userId);
  }
}
