// board-server/src/posts/update-post.dto.ts

/**
 * 글을 고칠 때 받는 값의 모양과 규칙. 고칠 칸만 보낸다. 보내지 않은 칸은 그대로 둔다.
 * 칸마다의 규칙은 쓸 때(create-post.dto.ts)와 같다.
 */

import { Transform } from 'class-transformer';
import { IsOptional, IsString, Matches, MaxLength } from 'class-validator';
import { CONTENT_MAX_LENGTH, TITLE_MAX_LENGTH } from './post.entity.js';
import { HAS_VISIBLE_TEXT, NO_NUL, trimText } from './post-text.js';

export class UpdatePostDto {
  @IsOptional()
  @Transform(trimText)
  @IsString({ message: '제목은 글자여야 합니다.' })
  @Matches(HAS_VISIBLE_TEXT, { message: '제목을 적어야 합니다.' })
  @Matches(NO_NUL, { message: '제목에 쓸 수 없는 글자가 있습니다.' })
  @MaxLength(TITLE_MAX_LENGTH, {
    message: `제목은 ${TITLE_MAX_LENGTH}자를 넘을 수 없습니다.`,
  })
  title?: string;

  @IsOptional()
  @IsString({ message: '본문은 글자여야 합니다.' })
  @Matches(HAS_VISIBLE_TEXT, { message: '본문을 적어야 합니다.' })
  @Matches(NO_NUL, { message: '본문에 쓸 수 없는 글자가 있습니다.' })
  @MaxLength(CONTENT_MAX_LENGTH, {
    message: `본문은 ${CONTENT_MAX_LENGTH}자를 넘을 수 없습니다.`,
  })
  content?: string;
}
