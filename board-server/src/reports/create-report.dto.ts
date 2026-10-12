// board-server/src/reports/create-report.dto.ts

/**
 * 신고할 때 받는 값의 모양과 규칙. 무엇을 신고하는지는 주소에 있고, 신고한 사람은 토큰에서 안다.
 *
 * 설명은 적지 않아도 된다. 다만 기타(other)를 고르면 꼭 적는다. 적었다면 빈칸만 적을 수는 없다.
 *
 * 설명의 검사는 한 함수(descriptionProblem)에 모았다. 검사기를 여럿 붙이면 설명을 적지 않았을 때
 * "글자여야 합니다", "500자를 넘을 수 없습니다"까지 한꺼번에 나와서 무엇이 틀렸는지 흐려진다.
 * 이 함수는 틀린 까닭 하나만 돌려준다.
 */

import {
  IsIn,
  maxLength,
  registerDecorator,
  ValidationArguments,
} from 'class-validator';
import { HAS_VISIBLE_TEXT, NO_NUL } from '../posts/post-text.js';
import {
  DESCRIPTION_MAX_LENGTH,
  needsDescription,
  REPORT_REASONS,
} from './reports.policy.js';
// 타입만 가져온다(import type). 칸의 타입으로만 쓴다
import type { ReportReason } from './reports.policy.js';

/**
 * 설명이 왜 틀렸는지 돌려준다. 맞으면 undefined 다.
 * 받은 설명은 문장에 넣지 않는다. 오류 응답과 로그에 신고의 설명이 실리지 않게 한다.
 */
export function descriptionProblem(
  reason: unknown,
  description: unknown,
): string | undefined {
  if (description === undefined || description === null) {
    return needsDescription(reason)
      ? '기타(other)를 고르면 설명을 적어야 합니다.'
      : undefined;
  }
  if (typeof description !== 'string') {
    return '설명은 글자여야 합니다.';
  }
  if (!HAS_VISIBLE_TEXT.test(description)) {
    return '설명을 적어야 합니다.';
  }
  if (!NO_NUL.test(description)) {
    return '설명에 쓸 수 없는 글자가 있습니다.';
  }
  // 글과 댓글의 길이 검사(@MaxLength)와 같은 함수로 센다
  if (!maxLength(description, DESCRIPTION_MAX_LENGTH)) {
    return `설명은 ${DESCRIPTION_MAX_LENGTH}자를 넘을 수 없습니다.`;
  }
  return undefined;
}

/** 이 칸이 같은 객체의 사유에 맞는 설명인지 검사한다(descriptionProblem). */
function IsReportDescription(): PropertyDecorator {
  return (target, propertyName) => {
    const problemOf = (args: ValidationArguments): string | undefined =>
      descriptionProblem(
        (args.object as Partial<CreateReportDto>).reason,
        args.value,
      );
    registerDecorator({
      name: 'isReportDescription',
      target: target.constructor,
      propertyName: String(propertyName),
      validator: {
        validate: (_value: unknown, args: ValidationArguments) =>
          problemOf(args) === undefined,
        defaultMessage: (args: ValidationArguments) => problemOf(args) ?? '',
      },
    });
  };
}

export class CreateReportDto {
  /** 사유 */
  @IsIn(REPORT_REASONS, {
    message: `reason 은 ${REPORT_REASONS.join(', ')} 가운데 하나여야 합니다.`,
  })
  reason: ReportReason;

  /** 설명. 받은 그대로 저장한다. 적지 않거나 null 이면 설명이 없는 것이다 */
  @IsReportDescription()
  description?: string | null;
}
