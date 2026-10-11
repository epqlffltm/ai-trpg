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
import { PostIdPipe } from '../posts/post-id.pipe.js';
import { CommentIdPipe } from './comment-id.pipe.js';
import {
  CommentResponse,
  CommentThreadResponse,
  toCommentResponse,
  toCommentThreadResponse,
} from './comment.response.js';
import { CommentsService } from './comments.service.js';
import { CreateCommentDto } from './create-comment.dto.js';
import { ListCommentsQuery } from './list-comments.query.js';
import { Slice } from './slice.js';
import { UpdateCommentDto } from './update-comment.dto.js';

@Controller()
export class CommentsController {
  constructor(private readonly comments: CommentsService) {}

  /** 한 글의 댓글을 한 토막 돌려준다. 먼저 쓴 것부터고, 댓글마다 답글이 모두 붙어 있다. */
  @Public()
  @Get('posts/:postId/comments')
  @HttpCode(HttpStatus.OK)
  async list(
    @Param('postId', PostIdPipe) postId: string,
    @Query() query: ListCommentsQuery,
  ): Promise<Slice<CommentThreadResponse>> {
    const slice = await this.comments.listIn(postId, query.after, query.size);
    return {
      items: slice.items.map(toCommentThreadResponse),
      next: slice.next,
    };
  }

  /** 글에 댓글을 단다. parent_id 를 적으면 그 댓글에 답글을 단다. 쓴 댓글을 돌려준다. */
  @Post('posts/:postId/comments')
  @HttpCode(HttpStatus.CREATED)
  async create(
    @Param('postId', PostIdPipe) postId: string,
    @Body() input: CreateCommentDto,
    @CurrentUser() user: AccessClaims,
  ): Promise<CommentResponse> {
    const comment = await this.comments.create(postId, user.userId, {
      content: input.content,
      parentId: input.parent_id ?? undefined,
    });
    return toCommentResponse(comment);
  }

  /** 댓글의 내용을 고친다. 고친 댓글을 돌려준다. */
  @Patch('comments/:id')
  @HttpCode(HttpStatus.OK)
  async update(
    @Param('id', CommentIdPipe) id: string,
    @Body() input: UpdateCommentDto,
    @CurrentUser() user: AccessClaims,
  ): Promise<CommentResponse> {
    const comment = await this.comments.update(id, user.userId, input.content);
    return toCommentResponse(comment);
  }

  /** 댓글을 지운다. 돌려줄 내용이 없다. */
  @Delete('comments/:id')
  @HttpCode(HttpStatus.NO_CONTENT)
  async remove(
    @Param('id', CommentIdPipe) id: string,
    @CurrentUser() user: AccessClaims,
  ): Promise<void> {
    await this.comments.remove(id, user.userId);
  }
}
