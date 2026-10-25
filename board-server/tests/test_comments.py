# board-server/tests/test_comments.py

"""
댓글의 주소(app/comments/). 계약 시험이 보지 못하는 것을 본다.

  - 쓰기, 고치기, 지우기를 결과마다 센다(board_writes_total)
  - 입력 오류의 칸과 문장, 검사의 차례(토큰 -> 주소 -> 본문)가 NestJS 때와 같다
  - 글쓴이가 탈퇴한 댓글, 같은 내용으로 고치기, 알림과 댓글이 한 트랜잭션인 것
  - 목록을 묶는 순수한 함수들
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.metrics import MetricsRecorder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.boards.models import Board
from app.comments import policy, service
from app.comments.models import Comment
from app.comments.schemas import authors_of, threads_of
from app.comments.service import CommentView
from app.notifications.models import OutgoingNotification
from app.posts.models import Post

pytestmark = pytest.mark.usefixtures('clean_tables')

API = '/api/v1/board'
WRITER = uuid.uuid4()
STRANGER = uuid.uuid4()
OPERATOR = uuid.uuid4()
WRITTEN_AT = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)

Headers = Callable[..., dict[str, str]]


def post_comments(post_id: object) -> str:
    return f'{API}/posts/{post_id}/comments'


def comment_path(comment_id: object) -> str:
    return f'{API}/comments/{comment_id}'


def operator_headers(headers_for: Headers) -> dict[str, str]:
    return headers_for(str(OPERATOR), roles=['operator'])


async def add_post(session: AsyncSession) -> int:
    board_id = await session.scalar(select(Board.id).where(Board.slug == 'free'))
    post = Post(board_id=board_id, author_id=WRITER, title='첫 모험', content='본문입니다.')
    session.add(post)
    await session.commit()
    return post.id


async def add_comment(
    session: AsyncSession, post_id: int, author_id: uuid.UUID | None, parent_id: int | None = None
) -> int:
    comment = Comment(
        post_id=post_id, parent_id=parent_id, author_id=author_id, content='댓글입니다.', updated_at=WRITTEN_AT
    )
    session.add(comment)
    await session.commit()
    return comment.id


async def count_rows(session: AsyncSession, model: type) -> int:
    return await session.scalar(select(func.count()).select_from(model))


async def write(client: AsyncClient, headers: dict[str, str], post_id: object, body: object):
    return await client.post(post_comments(post_id), headers=headers, json=body)


# 메트릭


async def test_writes_are_counted_by_result(
    client: AsyncClient, session: AsyncSession, headers_for: Headers, metrics: MetricsRecorder
):
    post_id = await add_post(session)
    writer = headers_for(str(WRITER))

    created = await write(client, writer, post_id, {'content': '댓글'})
    await write(client, writer, post_id, {'content': '답글', 'parent_id': '999'})
    comment_id = created.json()['id']
    await client.patch(comment_path(comment_id), headers=writer, json={'content': '고친 댓글'})
    await client.patch(comment_path(comment_id), headers=headers_for(str(STRANGER)), json={'content': '남의 것'})
    await client.delete(comment_path(comment_id), headers=headers_for(str(STRANGER)))
    await client.delete(comment_path(comment_id), headers=writer)

    for action in ('create', 'update', 'delete'):
        assert metrics.value('board_writes', resource='comment', action=action, result='success') == 1
        assert metrics.value('board_writes', resource='comment', action=action, result='rejected') == 1


async def test_rate_limited_comment_is_counted(
    client: AsyncClient, session: AsyncSession, headers_for: Headers, metrics: MetricsRecorder
):
    post_id = await add_post(session)
    writer = headers_for(str(WRITER))
    for _ in range(10):
        assert (await write(client, writer, post_id, {'content': '댓글'})).status_code == status.HTTP_201_CREATED

    response = await write(client, writer, post_id, {'content': '하나 더'})

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert int(response.headers['Retry-After']) >= 1
    assert metrics.value('board_writes', resource='comment', action='create', result='rate_limited') == 1


async def test_input_errors_are_not_counted(
    client: AsyncClient, session: AsyncSession, headers_for: Headers, metrics: MetricsRecorder
):
    post_id = await add_post(session)

    await write(client, headers_for(str(WRITER)), post_id, {'content': '   '})

    assert metrics.value('board_writes', resource='comment', action='create', result='rejected') is None


# 입력의 검사


async def test_content_errors_come_in_nest_order(client: AsyncClient, session: AsyncSession, headers_for: Headers):
    post_id = await add_post(session)

    response = await write(client, headers_for(str(WRITER)), post_id, {'content': 57, 'author_id': 'x'})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {
        'detail': '입력이 올바르지 않습니다.',
        'errors': {
            'author_id': ['property author_id should not exist'],
            'content': ['댓글은 2000자를 넘을 수 없습니다.', '댓글을 적어야 합니다.', '댓글은 글자여야 합니다.'],
        },
    }


@pytest.mark.parametrize(
    ('content', 'message'),
    [
        ('가' * 2001, '댓글은 2000자를 넘을 수 없습니다.'),
        ('a\x00b', '댓글에 쓸 수 없는 글자가 있습니다.'),
        ('　\n', '댓글을 적어야 합니다.'),
    ],
)
async def test_each_content_rule_has_its_message(
    client: AsyncClient, session: AsyncSession, headers_for: Headers, content: str, message: str
):
    post_id = await add_post(session)

    response = await write(client, headers_for(str(WRITER)), post_id, {'content': content})

    assert response.json()['errors'] == {'content': [message]}


async def test_content_is_stored_as_sent(client: AsyncClient, session: AsyncSession, headers_for: Headers):
    post_id = await add_post(session)

    response = await write(client, headers_for(str(WRITER)), post_id, {'content': '  들여쓴 댓글\n'})

    assert response.json()['content'] == '  들여쓴 댓글\n'


@pytest.mark.parametrize(
    ('parent_id', 'messages'),
    [
        (57, ['parent_id 는 댓글 번호여야 합니다.', 'parent_id 는 글자로 적은 댓글 번호여야 합니다.']),
        ('57\n', ['parent_id 는 댓글 번호여야 합니다.']),
        ('٥٧', ['parent_id 는 댓글 번호여야 합니다.']),
        ('0', ['parent_id 는 댓글 번호여야 합니다.']),
        ('1' * 19, ['parent_id 는 댓글 번호여야 합니다.']),
    ],
)
async def test_malformed_parent_id_messages(
    client: AsyncClient, session: AsyncSession, headers_for: Headers, parent_id: object, messages: list[str]
):
    post_id = await add_post(session)

    response = await write(client, headers_for(str(WRITER)), post_id, {'content': '답글', 'parent_id': parent_id})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()['errors'] == {'parent_id': messages}


async def test_update_rejects_unknown_fields_and_missing_content(
    client: AsyncClient, session: AsyncSession, headers_for: Headers
):
    post_id = await add_post(session)
    comment_id = await add_comment(session, post_id, WRITER)

    response = await client.patch(comment_path(comment_id), headers=headers_for(str(WRITER)), json={'parent_id': '1'})

    assert response.json()['errors'] == {
        'parent_id': ['property parent_id should not exist'],
        'content': ['댓글은 2000자를 넘을 수 없습니다.', '댓글을 적어야 합니다.', '댓글은 글자여야 합니다.'],
    }


@pytest.mark.parametrize(
    ('query', 'errors'),
    [
        ('?after=1&after=2', {'after': ['after 는 댓글 번호여야 합니다.']}),
        ('?after=%EF%BC%91', {'after': ['after 는 댓글 번호여야 합니다.']}),
        (
            '?size=abc',
            {'size': ['size 는 50 이하여야 합니다.', 'size 는 1 이상이어야 합니다.', 'size 는 정수여야 합니다.']},
        ),
        ('?size=1.5', {'size': ['size 는 정수여야 합니다.']}),
        (
            '?size=2&size=3',
            {'size': ['size 는 50 이하여야 합니다.', 'size 는 1 이상이어야 합니다.', 'size 는 정수여야 합니다.']},
        ),
        ('?page=1', {'page': ['property page should not exist']}),
    ],
)
async def test_list_query_errors(client: AsyncClient, session: AsyncSession, query: str, errors: dict):
    post_id = await add_post(session)

    response = await client.get(f'{post_comments(post_id)}{query}')

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()['errors'] == errors


async def test_size_accepts_number_forms_like_javascript(client: AsyncClient, session: AsyncSession):
    post_id = await add_post(session)
    for _ in range(3):
        await add_comment(session, post_id, WRITER)

    response = await client.get(f'{post_comments(post_id)}?size=0x2')

    assert len(response.json()['items']) == 2
    assert response.json()['next'] is not None


# 검사의 차례


async def test_token_is_checked_before_the_address(client: AsyncClient):
    response = await client.post(post_comments('abc'), json={'content': '댓글'})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_malformed_ids_are_404_before_the_body(client: AsyncClient, headers_for: Headers):
    headers = headers_for(str(WRITER))

    on_post = await client.post(post_comments('abc'), headers=headers, json={})
    on_comment = await client.patch(comment_path('١'), headers=headers, json={})
    listing = await client.get(f'{post_comments("0")}?size=0')

    assert [on_post.status_code, on_comment.status_code, listing.status_code] == [404, 404, 404]
    assert on_post.json() == {'detail': '글을 찾을 수 없습니다.'}
    assert on_comment.json() == {'detail': '댓글을 찾을 수 없습니다.'}


# 고치기와 지우기


async def test_editing_with_the_same_content_keeps_updated_at(
    client: AsyncClient, session: AsyncSession, headers_for: Headers
):
    post_id = await add_post(session)
    comment_id = await add_comment(session, post_id, WRITER)

    response = await client.patch(
        comment_path(comment_id), headers=headers_for(str(WRITER)), json={'content': '댓글입니다.'}
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()['updated_at'] == '2026-10-01T09:00:00.000Z'


async def test_edit_response_carries_nickname(client: AsyncClient, session: AsyncSession, headers_for: Headers):
    post_id = await add_post(session)
    comment_id = await add_comment(session, post_id, WRITER)

    response = await client.patch(
        comment_path(comment_id), headers=headers_for(str(WRITER), nickname='모험가'), json={'content': '고친 댓글'}
    )

    assert response.json()['author_nickname'] == '모험가'
    assert response.json()['updated_at'] != '2026-10-01T09:00:00.000Z'


async def test_comment_of_withdrawn_author(client: AsyncClient, session: AsyncSession, headers_for: Headers):
    post_id = await add_post(session)
    comment_id = await add_comment(session, post_id, None)

    [item] = (await client.get(post_comments(post_id))).json()['items']
    edited = await client.patch(comment_path(comment_id), headers=headers_for(str(WRITER)), json={'content': '고침'})
    removed = await client.delete(comment_path(comment_id), headers=operator_headers(headers_for))

    assert [item['author_id'], item['author_nickname'], item['author_withdrawn']] == [None, None, True]
    assert edited.status_code == status.HTTP_403_FORBIDDEN
    assert removed.status_code == status.HTTP_204_NO_CONTENT


async def test_delete_records_deleted_and_updated_time(
    client: AsyncClient, session: AsyncSession, headers_for: Headers
):
    post_id = await add_post(session)
    comment_id = await add_comment(session, post_id, WRITER)

    await client.delete(comment_path(comment_id), headers=headers_for(str(WRITER)))

    session.expire_all()
    row = await session.get(Comment, comment_id)
    assert row.deleted_at is not None
    assert row.updated_at == row.deleted_at


async def test_placeholder_has_no_author_withdrawn_flag(
    client: AsyncClient, session: AsyncSession, headers_for: Headers
):
    post_id = await add_post(session)
    parent = await add_comment(session, post_id, None)
    await add_comment(session, post_id, STRANGER, parent)
    await client.delete(comment_path(parent), headers=operator_headers(headers_for))

    [item] = (await client.get(post_comments(post_id))).json()['items']

    assert [item['deleted'], item['author_withdrawn'], item['content']] == [True, False, None]


# 알림


async def test_comment_and_notification_are_one_transaction(
    client: AsyncClient, session: AsyncSession, headers_for: Headers, monkeypatch: pytest.MonkeyPatch
):
    post_id = await add_post(session)

    def broken(*_args, **_kwargs):
        raise RuntimeError('발송함에 적지 못했다')

    monkeypatch.setattr(service, 'queue_for_comment', broken)

    with pytest.raises(RuntimeError):
        await write(client, headers_for(str(STRANGER)), post_id, {'content': '댓글'})

    assert await count_rows(session, Comment) == 0
    assert await count_rows(session, OutgoingNotification) == 0


async def test_reply_to_withdrawn_comment_is_not_notified(
    client: AsyncClient, session: AsyncSession, headers_for: Headers
):
    post_id = await add_post(session)
    parent = await add_comment(session, post_id, None)

    response = await write(client, headers_for(str(STRANGER)), post_id, {'content': '답글', 'parent_id': str(parent)})

    assert response.status_code == status.HTTP_201_CREATED
    assert await count_rows(session, OutgoingNotification) == 0


# 순수한 함수


def view(comment_id: int, parent_id: int | None = None, deleted: bool = False) -> CommentView:
    return CommentView(
        id=comment_id,
        post_id=1,
        parent_id=parent_id,
        author_id=uuid.UUID(int=comment_id),
        content='댓글',
        created_at=WRITTEN_AT,
        updated_at=WRITTEN_AT,
        deleted_at=WRITTEN_AT if deleted else None,
    )


def test_threads_drop_replies_of_unknown_comments():
    threads = threads_of([view(1), view(2)], [view(3, 1), view(4, 9), view(5, 1)])

    assert [[reply.id for reply in thread.replies] for thread in threads] == [[3, 5], []]


def test_authors_skip_deleted_comments():
    threads = threads_of([view(1, deleted=True)], [view(2, 1)])

    assert authors_of(threads) == [uuid.UUID(int=2)]


def test_slice_of_empty_and_exact():
    assert policy.slice_of([], 2, lambda item: item) == policy.Slice(items=[], next=None)
    assert policy.slice_of([1, 2], 2, lambda item: item) == policy.Slice(items=[1, 2], next=None)
    assert policy.slice_of([1, 2, 3], 2, lambda item: item) == policy.Slice(items=[1, 2], next=2)


def test_permissions():
    assert policy.can_edit(WRITER, WRITER)
    assert not policy.can_edit(None, WRITER)
    assert policy.can_delete(WRITER, STRANGER, is_operator=True)
    assert not policy.can_delete(WRITER, STRANGER, is_operator=False)
    assert policy.has_room_for_reply(policy.MAX_REPLIES_PER_COMMENT - 1)
    assert not policy.has_room_for_reply(policy.MAX_REPLIES_PER_COMMENT)
    assert not policy.can_have_replies(1)


# 답글의 거절과 목록의 토막


async def test_reply_refusals(client: AsyncClient, session: AsyncSession, headers_for: Headers):
    post_id = await add_post(session)
    full = await add_comment(session, post_id, WRITER)
    session.add_all(
        Comment(post_id=post_id, parent_id=full, author_id=WRITER, content='답글')
        for _ in range(policy.MAX_REPLIES_PER_COMMENT)
    )
    await session.commit()
    reply = await add_comment(session, post_id, WRITER, full)
    stranger = headers_for(str(STRANGER))

    on_reply = await write(client, stranger, post_id, {'content': '답글', 'parent_id': str(reply)})
    on_full = await write(client, stranger, post_id, {'content': '답글', 'parent_id': str(full)})

    assert [on_reply.status_code, on_full.status_code] == [400, 409]
    assert on_reply.json() == {'detail': '답글에는 답글을 달 수 없습니다.'}
    assert on_full.json() == {'detail': '이 댓글에는 답글을 더 달 수 없습니다.'}


async def test_missing_comment_is_404(client: AsyncClient, headers_for: Headers):
    response = await client.delete(comment_path('999'), headers=headers_for(str(WRITER)))

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {'detail': '댓글을 찾을 수 없습니다.'}


async def test_after_past_the_last_comment_is_empty(client: AsyncClient, session: AsyncSession):
    post_id = await add_post(session)
    comment_id = await add_comment(session, post_id, WRITER)

    response = await client.get(f'{post_comments(post_id)}?after={comment_id}')

    assert response.json() == {'items': [], 'next': None}
