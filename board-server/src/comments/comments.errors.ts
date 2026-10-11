// board-server/src/comments/comments.errors.ts

/**
 * 댓글을 다루다 거절할 때의 응답들. 문장을 한곳에 모아 둔다.
 */

import {
  BadRequestException,
  ConflictException,
  ForbiddenException,
  NotFoundException,
} from '@nestjs/common';

/** 그런 댓글이 없다. 지운 댓글도 없는 댓글이다. */
export function commentNotFound(): NotFoundException {
  return new NotFoundException({ detail: '댓글을 찾을 수 없습니다.' });
}

/** 답글을 달려는 댓글이 없다. 지웠거나, 다른 글의 댓글이다. */
export function parentNotFound(): BadRequestException {
  return new BadRequestException({
    detail: '답글을 달 댓글을 찾을 수 없습니다.',
  });
}

/** 답글에 답글을 달려 했다. */
export function cannotReplyToReply(): BadRequestException {
  return new BadRequestException({
    detail: '답글에는 답글을 달 수 없습니다.',
  });
}

/** 한 댓글에 달 수 있는 답글이 다 찼다. */
export function tooManyReplies(): ConflictException {
  return new ConflictException({
    detail: '이 댓글에는 답글을 더 달 수 없습니다.',
  });
}

/** 남의 댓글을 고치려 했다. */
export function notYourCommentToEdit(): ForbiddenException {
  return new ForbiddenException({ detail: '자신의 댓글만 고칠 수 있습니다.' });
}

/** 남의 댓글을 지우려 했다. */
export function notYourCommentToDelete(): ForbiddenException {
  return new ForbiddenException({ detail: '자신의 댓글만 지울 수 있습니다.' });
}
