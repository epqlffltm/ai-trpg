// board-server/src/errors/validation.ts

/**
 * 요청의 입력을 검사하는 규칙. 앱 전체에 건다(app.module.ts 의 APP_PIPE).
 *
 * 컨트롤러가 인자의 타입으로 적은 클래스(DTO)에 붙은 표시(@IsString 같은 것)대로 검사한다.
 * 검사는 class-validator 가 하고, 여기서는 그 결과를 이 서버의 오류 응답으로 바꾼다.
 */

import {
  BadRequestException,
  ValidationError,
  ValidationPipe,
} from '@nestjs/common';
import { FieldErrors } from './error-body.js';

/** 입력이 틀렸을 때의 문장. 어느 칸이 왜 틀렸는지는 errors 에 싣는다 */
export const INVALID_INPUT_DETAIL = '입력이 올바르지 않습니다.';

/** 검사 결과를 칸의 이름마다 틀린 까닭들로 모은다. 까닭이 없는 칸은 싣지 않는다. */
export function fieldErrors(errors: ValidationError[]): FieldErrors {
  const fields: FieldErrors = {};
  for (const error of errors) {
    const messages = Object.values(error.constraints ?? {});
    if (messages.length > 0) {
      fields[error.property] = messages;
    }
  }
  return fields;
}

/** 검사 결과를 400 응답으로 바꾼다. */
export function invalidInput(errors: ValidationError[]): BadRequestException {
  return new BadRequestException({
    detail: INVALID_INPUT_DETAIL,
    errors: fieldErrors(errors),
  });
}

/**
 * 입력을 검사하는 파이프를 만든다.
 *
 *   - whitelist, forbidNonWhitelisted: DTO 에 없는 칸이 오면 거부한다. 모르는 칸을 조용히 버리면
 *     칸 이름을 잘못 적은 클라이언트가 왜 반영이 안 되는지 알 수 없다.
 *   - transform: 받은 값을 DTO 의 타입으로 바꾼다. 주소의 ?page=2 는 글자로 오는데 숫자로 바꿔 준다.
 */
export function validationPipe(): ValidationPipe {
  return new ValidationPipe({
    whitelist: true,
    forbidNonWhitelisted: true,
    transform: true,
    exceptionFactory: invalidInput,
  });
}
