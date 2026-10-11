// board-server/src/posts/create-post.dto.ts

/**
 * 글을 쓸 때 받는 값의 모양과 규칙. 어느 게시판인지는 주소에 있고, 글쓴이는 토큰에서 안다.
 */

import { Transform } from 'class-transformer';
import { IsString, Matches, MaxLength } from 'class-validator';
import { CONTENT_MAX_LENGTH, TITLE_MAX_LENGTH } from './post.entity.js';
import { HAS_VISIBLE_TEXT, NO_NUL, trimText } from './post-text.js';

export class CreatePostDto {
  /** 제목. 앞뒤 빈칸은 떼고 저장한다 */
  @Transform(trimText)
  @IsString({ message: '제목은 글자여야 합니다.' })
  @Matches(HAS_VISIBLE_TEXT, { message: '제목을 적어야 합니다.' })
  @Matches(NO_NUL, { message: '제목에 쓸 수 없는 글자가 있습니다.' })
  @MaxLength(TITLE_MAX_LENGTH, {
    message: `제목은 ${TITLE_MAX_LENGTH}자를 넘을 수 없습니다.`,
  })
  title: string;

  /** 본문. 받은 그대로 저장한다. 줄바꿈과 들여쓰기가 글의 일부다 */
  @IsString({ message: '본문은 글자여야 합니다.' })
  @Matches(HAS_VISIBLE_TEXT, { message: '본문을 적어야 합니다.' })
  @Matches(NO_NUL, { message: '본문에 쓸 수 없는 글자가 있습니다.' })
  @MaxLength(CONTENT_MAX_LENGTH, {
    message: `본문은 ${CONTENT_MAX_LENGTH}자를 넘을 수 없습니다.`,
  })
  content: string;
}
