# game-server/app/realtime/sse.py

"""
SSE(Server-Sent Events)의 글자 형식. 스트림에 실을 것을 글자로 바꾼다.

SSE 는 끝나지 않는 HTTP 응답 하나에 메시지를 줄글로 흘려보내는 방식이다. 메시지 하나는 이렇게 생겼다.

    id: 17-5
    event: table_event
    data: {"sequence": 17, ...}
    (빈 줄)

빈 줄이 메시지의 끝이다. ':' 로 시작하는 줄은 주석이고 받는 쪽이 버린다. 연결이 살아 있는지 확인하는 데 쓴다.

DB 도 HTTP 도 모른다.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Frame:
    """
    스트림에 실을 메시지 하나.

    event: 종류. 받는 쪽이 이 이름으로 처리를 가른다.
    data: 내용. JSON 한 줄이다.
    id: 여기까지 받았다는 표시. 끊겼다 돌아온 쪽이 이 값을 보내면 그 뒤부터 이어 받는다.
        저장하지 않는 메시지(닫힘 알림 등)에는 붙이지 않는다. 붙이지 않으면 받는 쪽의 표시가 그대로 남는다.
    """

    event: str
    data: str
    id: str | None = None


@dataclass(frozen=True)
class Comment:
    """주석 한 줄. 내용을 전하지 않는다. 연결이 살아 있음을 알리고, 죽은 연결을 알아채는 데 쓴다."""

    text: str


def encode(item: Frame | Comment) -> str:
    """
    메시지나 주석을 SSE 의 글자로 바꾼다.

    data 에 줄바꿈이 있으면 줄마다 'data: ' 를 붙여야 한다. 받는 쪽이 다시 줄바꿈으로 이어 붙인다.
    JSON 은 줄바꿈을 \\n 으로 적으므로 실제로는 한 줄이지만, 형식의 규칙을 지켜 둔다.
    """
    if isinstance(item, Comment):
        return f': {item.text}\n\n'

    lines = []
    if item.id is not None:
        lines.append(f'id: {item.id}')
    lines.append(f'event: {item.event}')
    lines.extend(f'data: {line}' for line in item.data.split('\n'))
    return '\n'.join(lines) + '\n\n'
