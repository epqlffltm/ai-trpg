// board-server/src/write-limits/write-limits.module.ts

/**
 * 글과 댓글의 쓰기 횟수, 신고의 횟수를 제한하는 모듈. 글, 댓글, 신고 모듈이 쓴다.
 *
 * 그 모듈들 어느 쪽에도 두지 않고 따로 뺐다. 세 테이블을 읽는데, 댓글 모듈은 이미 글 모듈을 가져다 쓴다.
 * 이 모듈은 테이블만 읽고 그 모듈들을 쓰지 않는다. 그래서 모두가 가져다 써도 고리가 생기지 않는다.
 */

import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Comment } from '../comments/comment.entity.js';
import { OperatorsModule } from '../operators/operators.module.js';
import { Post } from '../posts/post.entity.js';
import { Report } from '../reports/report.entity.js';
import { WRITE_LIMITS } from './write-limits.policy.js';
import {
  WRITE_LIMITS_TOKEN,
  WriteLimitsService,
} from './write-limits.service.js';

@Module({
  imports: [TypeOrmModule.forFeature([Post, Comment, Report]), OperatorsModule],
  providers: [
    WriteLimitsService,
    { provide: WRITE_LIMITS_TOKEN, useValue: WRITE_LIMITS },
  ],
  exports: [WriteLimitsService],
})
export class WriteLimitsModule {}
