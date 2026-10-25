# board-server/contract/tests/urls.py

"""시험이 부르는 주소. API 목록(docs/api/board.openapi.json)의 경로와 같다."""

API = '/api/v1/board'
BOARDS = f'{API}/boards'
POSTS = f'{API}/posts'
COMMENTS = f'{API}/comments'
REPORTS = f'{API}/reports'
ME = f'{API}/me'
HEALTH = '/health'
READY = '/health/ready'


def board_posts(slug: str) -> str:
    return f'{BOARDS}/{slug}/posts'


def post(post_id: object) -> str:
    return f'{POSTS}/{post_id}'


def post_comments(post_id: object) -> str:
    return f'{POSTS}/{post_id}/comments'


def post_pin(post_id: object) -> str:
    return f'{POSTS}/{post_id}/pin'


def post_reports(post_id: object) -> str:
    return f'{POSTS}/{post_id}/reports'


def post_outcome(post_id: object) -> str:
    return f'{POSTS}/{post_id}/reports/outcome'


def comment(comment_id: object) -> str:
    return f'{COMMENTS}/{comment_id}'


def comment_reports(comment_id: object) -> str:
    return f'{COMMENTS}/{comment_id}/reports'


def comment_outcome(comment_id: object) -> str:
    return f'{COMMENTS}/{comment_id}/reports/outcome'


def withdrawal(user_id: object) -> str:
    return f'{API}/service/users/{user_id}/withdrawal'
