// board-server/src/posts/pins.controller.ts

/**
 * 글 고정의 API. 운영자만 부른다.
 *
 *   PUT    /posts/:id/pin   글을 고정한다. 본문의 days 로 며칠 동안인지 정한다(적지 않으면 7일)
 *   DELETE /posts/:id/pin   글의 고정을 푼다
 *
 * 글을 고치는 주소(PATCH /posts/:id)와 따로 둔다. 고치는 것은 글쓴이만, 고정하는 것은 운영자만 한다.
 * 한 주소에 두면 "누가 불러도 되는가"의 규칙 둘이 섞인다.
 * 둘 다 여러 번 불러도 결과가 같다. 그래서 POST 가 아니라 PUT 과 DELETE 다. 돌려줄 내용이 없다.
 */

import {
  Body,
  Controller,
  Delete,
  HttpCode,
  HttpStatus,
  Param,
  Put,
} from '@nestjs/common';
import { CurrentUser } from '../auth/current-user.decorator.js';
// 타입만 가져온다(import type). 데코레이터가 붙은 인자의 타입이 인터페이스면 이렇게 적어야 빌드된다
import type { AccessClaims } from '../auth/tokens.js';
import { PinPostDto } from './pin-post.dto.js';
import { PinsService } from './pins.service.js';
import { PostIdPipe } from './post-id.pipe.js';

@Controller('posts/:id/pin')
export class PinsController {
  constructor(private readonly pins: PinsService) {}

  /** 글을 고정한다. */
  @Put()
  @HttpCode(HttpStatus.NO_CONTENT)
  async pin(
    @Param('id', PostIdPipe) id: string,
    @Body() input: PinPostDto,
    @CurrentUser() user: AccessClaims,
  ): Promise<void> {
    await this.pins.pin(id, user.userId, input.days, new Date());
  }

  /** 글의 고정을 푼다. */
  @Delete()
  @HttpCode(HttpStatus.NO_CONTENT)
  async unpin(
    @Param('id', PostIdPipe) id: string,
    @CurrentUser() user: AccessClaims,
  ): Promise<void> {
    await this.pins.unpin(id, user.userId);
  }
}
