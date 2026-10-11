// board-server/src/posts/pin-post.dto.ts

/**
 * 글을 고정할 때 받는 값의 모양과 규칙. 본문 없이 불러도 된다.
 */

import { IsInt, Max, Min } from 'class-validator';
import { DEFAULT_PIN_DAYS, MAX_PIN_DAYS } from './pins.policy.js';

export class PinPostDto {
  /** 며칠 동안 고정하는가. 적지 않으면 DEFAULT_PIN_DAYS 다. 그날이 지나면 저절로 내려간다 */
  @IsInt({ message: 'days 는 정수여야 합니다.' })
  @Min(1, { message: 'days 는 1 이상이어야 합니다.' })
  @Max(MAX_PIN_DAYS, { message: `days 는 ${MAX_PIN_DAYS} 이하여야 합니다.` })
  days: number = DEFAULT_PIN_DAYS;
}
