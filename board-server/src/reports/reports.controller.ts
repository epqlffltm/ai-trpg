// board-server/src/reports/reports.controller.ts

/**
 * 신고하기의 API. 로그인한 사람 누구나 부른다.
 *
 *   POST /posts/:id/reports      글을 신고한다
 *   POST /comments/:id/reports   댓글(답글 포함)을 신고한다
 *
 * 신고를 읽고 처리하는 운영자의 API 는 report-reviews.controller.ts 다. 부를 수 있는 사람이 다르다.
 * 신고한 사람에게는 접수했다는 것만 돌려준다.
 * 신고는 결과마다 센다(board_reports_total, observability/counted.interceptor.ts).
 */

import {
  Body,
  Controller,
  HttpCode,
  HttpStatus,
  Param,
  Post,
  UseInterceptors,
} from '@nestjs/common';
import { CurrentUser } from '../auth/current-user.decorator.js';
// 타입만 가져온다(import type). 데코레이터가 붙은 인자의 타입이 인터페이스면 이렇게 적어야 빌드된다
import type { AccessClaims } from '../auth/tokens.js';
import { CommentIdPipe } from '../comments/comment-id.pipe.js';
import { PostIdPipe } from '../posts/post-id.pipe.js';
import { countReport } from '../observability/counted.interceptor.js';
import { CreateReportDto } from './create-report.dto.js';
import {
  ReportReceiptResponse,
  toReportReceiptResponse,
} from './report.response.js';
import { commentTarget, postTarget } from './report-target.js';
import { ReportsService } from './reports.service.js';

@Controller()
export class ReportsController {
  constructor(private readonly reports: ReportsService) {}

  /** 글을 신고한다. */
  @Post('posts/:id/reports')
  @HttpCode(HttpStatus.CREATED)
  @UseInterceptors(countReport('post'))
  async reportPost(
    @Param('id', PostIdPipe) id: string,
    @Body() input: CreateReportDto,
    @CurrentUser() user: AccessClaims,
  ): Promise<ReportReceiptResponse> {
    const report = await this.reports.file(postTarget(id), user, input);
    return toReportReceiptResponse(report);
  }

  /** 댓글을 신고한다. 답글도 같다. */
  @Post('comments/:id/reports')
  @HttpCode(HttpStatus.CREATED)
  @UseInterceptors(countReport('comment'))
  async reportComment(
    @Param('id', CommentIdPipe) id: string,
    @Body() input: CreateReportDto,
    @CurrentUser() user: AccessClaims,
  ): Promise<ReportReceiptResponse> {
    const report = await this.reports.file(commentTarget(id), user, input);
    return toReportReceiptResponse(report);
  }
}
