// board-server/src/comments/comment-id.pipe.ts

/**
 * 주소의 댓글 번호(/comments/57)를 검사한다.
 *
 * 번호의 모양(ids/record-id.ts)이 아니면 그런 댓글이 없는 것이므로 404 다. DB 에 묻지 않는다.
 */

import { Injectable, PipeTransform } from '@nestjs/common';
import { isRecordId } from '../ids/record-id.js';
import { commentNotFound } from './comments.errors.js';

@Injectable()
export class CommentIdPipe implements PipeTransform<unknown, string> {
  transform(value: unknown): string {
    if (!isRecordId(value)) {
      throw commentNotFound();
    }
    return value;
  }
}
