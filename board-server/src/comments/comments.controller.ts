// board-server/src/comments/comments.controller.ts

/**
 * 댓글의 API. 주소를 받아 서비스를 부르고, 결과를 응답의 모양으로 바꾼다.
 *
 *   GET    /posts/:postId/comments   한 글의 댓글 목록(답글 포함)    로그인 불필요
 *   POST   /posts/:postId/comments   댓글 쓰기, 답글 쓰기            로그인 필요
 *   PATCH  /comments/:id             댓글 고치기(글쓴이)             로그인 필요
 *   DELETE /comments/:id             댓글 지우기(글쓴이, 운영자)     로그인 필요
 *
 * 쓰기는 글 아래에 둔다. 댓글은 글에 다는 것이다. 답글도 같은 주소로 쓰고, 어느 댓글에 다는지를
 * 본문(parent_id)으로 알린다. 고치고 지울 때는 댓글 번호만으로 가리킨다.
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
import { PostIdPipe } from '../posts/post-id.pipe.js';
import { countWrite } from '../observability/counted.interceptor.js';
import { CommentIdPipe } from './comment-id.pipe.js';
import { Comment } from './comment.entity.js';
import {
  authorsOf,
  CommentListResponse,
  CommentResponse,
  toCommentResponse,
  toCommentThreadResponse,
} from './comment.response.js';
import { CommentsService } from './comments.service.js';
import { CreateCommentDto } from './create-comment.dto.js';
import { ListCommentsQuery } from './list-comments.query.js';
import { UpdateCommentDto } from './update-comment.dto.js';

@Controller()
export class CommentsController {
  constructor(
    private readonly comments: CommentsService,
    private readonly authors: AuthorsService,
  ) {}

  /** 한 글의 댓글을 한 토막 돌려준다. 먼저 쓴 것부터고, 댓글마다 답글이 모두 붙어 있다. */
  @Public()
  @Get('posts/:postId/comments')
  @HttpCode(HttpStatus.OK)
  async list(
    @Param('postId', PostIdPipe) postId: string,
    @Query() query: ListCommentsQuery,
  ): Promise<CommentListResponse> {
    const slice = await this.comments.listIn(postId, query.after, query.size);
    const nicknames = await this.authors.nicknamesOf(authorsOf(slice.items));
    return {
      items: slice.items.map((thread) =>
        toCommentThreadResponse(thread, nicknames),
      ),
      next: slice.next,
    };
  }

  /** 글에 댓글을 단다. parent_id 를 적으면 그 댓글에 답글을 단다. 쓴 댓글을 돌려준다. */
  @Post('posts/:postId/comments')
  @HttpCode(HttpStatus.CREATED)
  @UseInterceptors(countWrite('comment', 'create'))
  async create(
    @Param('postId', PostIdPipe) postId: string,
    @Body() input: CreateCommentDto,
    @CurrentUser() user: AccessClaims,
  ): Promise<CommentResponse> {
    const comment = await this.comments.create(postId, user, {
      content: input.content,
      parentId: input.parent_id ?? undefined,
    });
    return this.toResponse(comment);
  }

  /** 댓글의 내용을 고친다. 고친 댓글을 돌려준다. */
  @Patch('comments/:id')
  @HttpCode(HttpStatus.OK)
  @UseInterceptors(countWrite('comment', 'update'))
  async update(
    @Param('id', CommentIdPipe) id: string,
    @Body() input: UpdateCommentDto,
    @CurrentUser() user: AccessClaims,
  ): Promise<CommentResponse> {
    const comment = await this.comments.update(id, user.userId, input.content);
    return this.toResponse(comment);
  }

  /** 댓글을 지운다. 돌려줄 내용이 없다. */
  @Delete('comments/:id')
  @HttpCode(HttpStatus.NO_CONTENT)
  @UseInterceptors(countWrite('comment', 'delete'))
  async remove(
    @Param('id', CommentIdPipe) id: string,
    @CurrentUser() user: AccessClaims,
  ): Promise<void> {
    await this.comments.remove(id, user);
  }

  /** 댓글 하나를 응답의 모양으로 바꾼다. 글쓴이의 이름을 따로 읽는다. */
  private async toResponse(comment: Comment): Promise<CommentResponse> {
    const nicknames = await this.authors.nicknamesOf([comment.authorId]);
    return toCommentResponse(comment, nicknames);
  }
}
