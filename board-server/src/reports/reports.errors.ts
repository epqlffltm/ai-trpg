// board-server/src/reports/reports.errors.ts

/**
 * 신고를 다루다 거절할 때의 응답들. 문장을 한곳에 모아 둔다.
 *
 * 받은 설명은 어느 문장에도 넣지 않는다. 응답과 로그에 신고의 설명이 실리지 않게 한다.
 */

import {
  ConflictException,
  ForbiddenException,
  NotFoundException,
} from '@nestjs/common';
import { QueryFailedError } from 'typeorm';
import { ReportTargetType } from './report-target.js';

/** PostgreSQL 의 오류 번호: 유일해야 하는 값이 겹쳤다 */
const UNIQUE_VIOLATION = '23505';

/** 자기 글이나 자기 댓글을 신고하려 했다. */
export function cannotReportOwn(type: ReportTargetType): ForbiddenException {
  return new ForbiddenException({
    detail:
      type === 'post'
        ? '자신의 글은 신고할 수 없습니다.'
        : '자신의 댓글은 신고할 수 없습니다.',
  });
}

/** 이미 신고했다. 같은 것을 두 번 신고하지 못한다. */
export function alreadyReported(): ConflictException {
  return new ConflictException({ detail: '이미 신고했습니다.' });
}

/** 운영자가 아닌 사람이 신고를 읽거나 처리하려 했다. */
export function operatorOnlyReports(): ForbiddenException {
  return new ForbiddenException({
    detail: '운영자만 신고를 볼 수 있습니다.',
  });
}

/** 처리할 신고가 없다. 신고가 없거나 이미 모두 처리했다. */
export function noOpenReports(): NotFoundException {
  return new NotFoundException({ detail: '처리할 신고가 없습니다.' });
}

/** 이 오류는 DB 의 유일 제약에 걸린 것인가. 같은 신고가 동시에 두 번 들어오면 늦은 쪽이 여기에 걸린다. */
export function isUniqueViolation(error: unknown): boolean {
  if (!(error instanceof QueryFailedError)) {
    return false;
  }
  const driverError: unknown = error.driverError;
  return (
    typeof driverError === 'object' &&
    driverError !== null &&
    (driverError as { code?: unknown }).code === UNIQUE_VIOLATION
  );
}
