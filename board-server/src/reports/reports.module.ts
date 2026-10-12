// board-server/src/reports/reports.module.ts

/**
 * 신고를 맡는 모듈. 신고하기(ReportsService)와 운영자가 읽고 처리하기(ReportReviewsService)가 있다.
 *
 * 글과 댓글은 테이블을 바로 읽는다. 글 모듈과 댓글 모듈을 가져다 쓰지 않는다.
 * 신고는 그 둘이 있는지와 누가 썼는지만 알면 되고, 댓글 모듈은 이미 글 모듈을 쓴다.
 * 운영자인지는 OperatorsModule 에, 너무 자주 하는지는 WriteLimitsModule 에 묻는다.
 */

import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Comment } from '../comments/comment.entity.js';
import { OperatorsModule } from '../operators/operators.module.js';
import { Post } from '../posts/post.entity.js';
import { WriteLimitsModule } from '../write-limits/write-limits.module.js';
import { Report } from './report.entity.js';
import { ReportReviewsController } from './report-reviews.controller.js';
import { ReportReviewsService } from './report-reviews.service.js';
import { ReportsController } from './reports.controller.js';
import { ReportsService } from './reports.service.js';

@Module({
  imports: [
    TypeOrmModule.forFeature([Report, Post, Comment]),
    OperatorsModule,
    WriteLimitsModule,
  ],
  controllers: [ReportsController, ReportReviewsController],
  providers: [ReportsService, ReportReviewsService],
})
export class ReportsModule {}
