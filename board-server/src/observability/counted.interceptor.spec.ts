// board-server/src/observability/counted.interceptor.spec.ts

/**
 * 쓰기와 신고를 결과마다 세는 인터셉터(counted.interceptor.ts)를 검증한다. 핸들러 대신 정해 둔 Observable 을 넘긴다.
 * 실제 주소로 쓴 것은 test/metrics.e2e-spec.ts 가 본다.
 */

import {
  BadRequestException,
  ForbiddenException,
  HttpException,
  HttpStatus,
  InternalServerErrorException,
  NotFoundException,
} from '@nestjs/common';
import { lastValueFrom, of, throwError } from 'rxjs';
import { recordMetrics } from '../../test/metrics.js';
import {
  countReport,
  countWrite,
  resultOfError,
} from './counted.interceptor.js';

const metrics = recordMetrics();

describe('resultOfError', () => {
  it.each([
    [new HttpException('많다', HttpStatus.TOO_MANY_REQUESTS), 'rate_limited'],
    [new BadRequestException(), 'rejected'],
    [new ForbiddenException(), 'rejected'],
    [new NotFoundException(), 'rejected'],
    [new HttpException('같다', HttpStatus.CONFLICT), 'rejected'],
  ])('%s 는 %s 다', (error, result) => {
    expect(resultOfError(error)).toBe(result);
  });

  it('서버의 잘못과 그 밖의 예외는 세지 않는다', () => {
    expect(resultOfError(new InternalServerErrorException())).toBeUndefined();
    expect(resultOfError(new Error('버그'))).toBeUndefined();
  });
});

describe('Counted', () => {
  it('답을 돌려주면 success 다. 돌려줄 것이 없어도(204) 같다', async () => {
    await lastValueFrom(
      countWrite('post', 'create').intercept(undefined, {
        handle: () => of({ id: '1' }),
      }),
    );
    await lastValueFrom(
      countWrite('post', 'delete').intercept(undefined, {
        handle: () => of(undefined),
      }),
      { defaultValue: undefined },
    );

    expect(
      await metrics.current.value('board_writes', {
        resource: 'post',
        action: 'create',
        result: 'success',
      }),
    ).toBe(1);
    expect(
      await metrics.current.value('board_writes', {
        resource: 'post',
        action: 'delete',
        result: 'success',
      }),
    ).toBe(1);
  });

  it('받지 않은 것은 센 뒤에 예외를 그대로 올린다', async () => {
    const refused = new HttpException('많다', HttpStatus.TOO_MANY_REQUESTS);

    await expect(
      lastValueFrom(
        countReport('comment').intercept(undefined, {
          handle: () => throwError(() => refused),
        }),
      ),
    ).rejects.toBe(refused);

    expect(
      await metrics.current.value('board_reports', {
        target: 'comment',
        result: 'rate_limited',
      }),
    ).toBe(1);
  });

  it('서버의 잘못은 세지 않는다', async () => {
    await expect(
      lastValueFrom(
        countWrite('comment', 'update').intercept(undefined, {
          handle: () => throwError(() => new Error('버그')),
        }),
      ),
    ).rejects.toThrow('버그');

    expect(await metrics.current.points('board_writes')).toEqual([]);
  });
});
