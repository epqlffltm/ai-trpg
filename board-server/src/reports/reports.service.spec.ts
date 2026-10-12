// board-server/src/reports/reports.service.spec.ts

/**
 * 같은 신고가 동시에 둘 들어왔을 때를 본다(reports.service.ts 의 save).
 *
 * 둘이 "이미 신고했는가"의 확인을 함께 지나치면 늦은 쪽은 저장할 때 DB 의 유일 제약에 걸린다.
 * 실제 DB 에서는 이 틈을 일부러 만들기 어렵다. 그래서 확인은 지나치고 저장은 유일 제약에 걸리는
 * 가짜 테이블을 넣어, 그 오류를 409 로 돌려주는지만 본다. 나머지는 test/reports.e2e-spec.ts 가 실제 DB 에서 본다.
 */

import { ConflictException } from '@nestjs/common';
import { QueryFailedError, Repository } from 'typeorm';
import { Comment } from '../comments/comment.entity.js';
import { Post } from '../posts/post.entity.js';
import { WriteLimitsService } from '../write-limits/write-limits.service.js';
import { Report } from './report.entity.js';
import { postTarget } from './report-target.js';
import { ReportsService } from './reports.service.js';

const WRITER = '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b';
const READER = '7d0e3a52-1f4b-4c8e-8a21-9b6c5d4e3f2a';

/** DB 가 이 번호의 오류를 낸 것처럼 만든다. */
function queryFailed(code: string): QueryFailedError {
  return new QueryFailedError(
    'INSERT',
    [],
    Object.assign(new Error('db'), { code }),
  );
}

/** 확인은 늘 "아직 없다"로 지나치고, 저장할 때 error 를 내는 신고 테이블. */
function reportsThatFailToSave(error: Error): Repository<Report> {
  return {
    existsBy: () => Promise.resolve(false),
    create: (values: Partial<Report>) => values,
    save: () => Promise.reject(error),
  } as unknown as Repository<Report>;
}

/** 남이 쓴 글 하나만 있는 글 테이블. */
const posts = {
  findOneBy: () => Promise.resolve({ id: '1', authorId: WRITER }),
} as unknown as Repository<Post>;

/** 늘 한도 안이다. */
const noLimits = {
  ensureCanReport: () => Promise.resolve(),
} as unknown as WriteLimitsService;

function service(reports: Repository<Report>): ReportsService {
  return new ReportsService(
    reports,
    posts,
    {} as Repository<Comment>,
    noLimits,
  );
}

describe('ReportsService.file 이 저장하다 걸렸을 때', () => {
  it('유일 제약에 걸리면 409 다', async () => {
    const reports = reportsThatFailToSave(queryFailed('23505'));

    await expect(
      service(reports).file(postTarget('1'), READER, { reason: 'spam' }),
    ).rejects.toBeInstanceOf(ConflictException);
  });

  it('다른 오류는 그대로 올린다', async () => {
    const error = queryFailed('08006');
    const reports = reportsThatFailToSave(error);

    await expect(
      service(reports).file(postTarget('1'), READER, { reason: 'spam' }),
    ).rejects.toBe(error);
  });
});
