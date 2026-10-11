// board-server/src/posts/post-id.pipe.ts

/**
 * 주소의 글 번호(/posts/1234)를 검사한다.
 *
 * 번호의 모양(ids/record-id.ts)이 아니면 그런 글이 없는 것이므로 404 다. DB 에 묻지 않는다.
 * 번호는 글자 그대로 넘긴다. 숫자로 바꾸지 않는다.
 */

import { Injectable, PipeTransform } from '@nestjs/common';
import { isRecordId } from '../ids/record-id.js';
import { postNotFound } from './posts.errors.js';

@Injectable()
export class PostIdPipe implements PipeTransform<unknown, string> {
  transform(value: unknown): string {
    if (!isRecordId(value)) {
      throw postNotFound();
    }
    return value;
  }
}
