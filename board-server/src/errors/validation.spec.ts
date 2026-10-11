// board-server/src/errors/validation.spec.ts

/**
 * 입력 검사의 결과를 오류 응답으로 바꾸는 함수들(validation.ts)을 검증한다.
 * DTO 마다의 규칙은 그 DTO 의 테스트가 본다.
 */

import { HttpStatus, ValidationError } from '@nestjs/common';
import {
  fieldErrors,
  INVALID_INPUT_DETAIL,
  invalidInput,
} from './validation.js';

/** 검사 결과 하나를 만든다. */
function makeError(
  property: string,
  constraints?: Record<string, string>,
): ValidationError {
  return { property, constraints };
}

describe('fieldErrors', () => {
  it('칸의 이름마다 틀린 까닭들을 모은다', () => {
    const errors = [
      makeError('title', { matches: '제목을 적어야 합니다.' }),
      makeError('content', {
        isString: '본문은 글자여야 합니다.',
        maxLength: '본문은 20000자를 넘을 수 없습니다.',
      }),
    ];

    expect(fieldErrors(errors)).toEqual({
      title: ['제목을 적어야 합니다.'],
      content: [
        '본문은 글자여야 합니다.',
        '본문은 20000자를 넘을 수 없습니다.',
      ],
    });
  });

  it('까닭이 없는 칸은 싣지 않는다', () => {
    expect(fieldErrors([makeError('title'), makeError('content', {})])).toEqual(
      {},
    );
  });

  it('틀린 것이 없으면 비어 있다', () => {
    expect(fieldErrors([])).toEqual({});
  });
});

describe('invalidInput', () => {
  it('400 이고, 어느 칸이 왜 틀렸는지 싣는다', () => {
    const exception = invalidInput([
      makeError('title', { matches: '제목을 적어야 합니다.' }),
    ]);

    expect(exception.getStatus()).toBe(HttpStatus.BAD_REQUEST);
    expect(exception.getResponse()).toEqual({
      detail: INVALID_INPUT_DETAIL,
      errors: { title: ['제목을 적어야 합니다.'] },
    });
  });
});
