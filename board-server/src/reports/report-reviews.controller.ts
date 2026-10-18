// board-server/src/reports/report-reviews.controller.ts

/**
 * 운영자가 신고를 읽고 처리하는 API. 운영자만 부른다.
 *
 *   GET /reports                       열린 신고를 신고당한 것마다 묶은 목록. 오래 기다린 것부터
 *   GET /posts/:id/reports             한 글에 걸린 신고 모두(처리한 것도). 설명과 신고한 사람이 나온다
 *   GET /comments/:id/reports          한 댓글에 걸린 신고 모두
 *   PUT /posts/:id/reports/outcome     한 글에 걸린 열린 신고를 모두 처리해서 닫는다
 *   PUT /comments/:id/reports/outcome  한 댓글에 걸린 열린 신고를 모두 처리해서 닫는다
 *
 * 처리는 신고 한 건이 아니라 신고당한 것 단위다. 한 글에 일곱 명이 신고해도 운영자는 한 번 처리한다.
 * 글을 지우는 것은 이미 있는 지우기 API 로 따로 한다(DELETE /posts/:id).
 */

import {
  Body,
  Controller,
  Get,
  HttpCode,
  HttpStatus,
  Param,
  Put,
  Query,
} from '@nestjs/common';
import { CurrentUser } from '../auth/current-user.decorator.js';
// 타입만 가져온다(import type). 데코레이터가 붙은 인자의 타입이 인터페이스면 이렇게 적어야 빌드된다
import type { AccessClaims } from '../auth/tokens.js';
import { CommentIdPipe } from '../comments/comment-id.pipe.js';
import { Page } from '../posts/page.js';
import { PostIdPipe } from '../posts/post-id.pipe.js';
import { HandleReportsDto } from './handle-reports.dto.js';
import { ListReportsQuery } from './list-reports.query.js';
import { ReportReviewsService } from './report-reviews.service.js';
import {
  OpenReportGroupResponse,
  ReportResponse,
  toOpenReportGroupResponse,
  toReportResponse,
} from './report.response.js';
import { commentTarget, postTarget, ReportTarget } from './report-target.js';

@Controller()
export class ReportReviewsController {
  constructor(private readonly reviews: ReportReviewsService) {}

  /** 열린 신고의 목록. 신고당한 것마다 한 줄이다. */
  @Get('reports')
  @HttpCode(HttpStatus.OK)
  async listOpen(
    @Query() query: ListReportsQuery,
    @CurrentUser() user: AccessClaims,
  ): Promise<Page<OpenReportGroupResponse>> {
    const page = await this.reviews.listOpen(user, query.page, query.size);
    return {
      ...page,
      items: page.items.map(({ group, state }) =>
        toOpenReportGroupResponse(group, state),
      ),
    };
  }

  /** 한 글에 걸린 신고들. */
  @Get('posts/:id/reports')
  @HttpCode(HttpStatus.OK)
  listForPost(
    @Param('id', PostIdPipe) id: string,
    @Query() query: ListReportsQuery,
    @CurrentUser() user: AccessClaims,
  ): Promise<Page<ReportResponse>> {
    return this.listFor(postTarget(id), query, user);
  }

  /** 한 댓글에 걸린 신고들. */
  @Get('comments/:id/reports')
  @HttpCode(HttpStatus.OK)
  listForComment(
    @Param('id', CommentIdPipe) id: string,
    @Query() query: ListReportsQuery,
    @CurrentUser() user: AccessClaims,
  ): Promise<Page<ReportResponse>> {
    return this.listFor(commentTarget(id), query, user);
  }

  /** 한 글에 걸린 열린 신고를 모두 처리한다. */
  @Put('posts/:id/reports/outcome')
  @HttpCode(HttpStatus.NO_CONTENT)
  async handlePost(
    @Param('id', PostIdPipe) id: string,
    @Body() input: HandleReportsDto,
    @CurrentUser() user: AccessClaims,
  ): Promise<void> {
    await this.reviews.handle(postTarget(id), user, input.outcome);
  }

  /** 한 댓글에 걸린 열린 신고를 모두 처리한다. */
  @Put('comments/:id/reports/outcome')
  @HttpCode(HttpStatus.NO_CONTENT)
  async handleComment(
    @Param('id', CommentIdPipe) id: string,
    @Body() input: HandleReportsDto,
    @CurrentUser() user: AccessClaims,
  ): Promise<void> {
    await this.reviews.handle(commentTarget(id), user, input.outcome);
  }

  /** 글이나 댓글 하나에 걸린 신고들을 응답의 모양으로 돌려준다. */
  private async listFor(
    target: ReportTarget,
    query: ListReportsQuery,
    user: AccessClaims,
  ): Promise<Page<ReportResponse>> {
    const page = await this.reviews.listFor(
      target,
      user,
      query.page,
      query.size,
    );
    return { ...page, items: page.items.map(toReportResponse) };
  }
}
