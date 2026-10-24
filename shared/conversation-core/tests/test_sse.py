# shared/conversation-core/tests/test_sse.py

"""
SSE 의 글자(conversation_core/sse.py). 메시지는 id, event, 줄마다의 data 와 빈 줄이고, 주석은 ':' 로 시작한다.
"""

from conversation_core.sse import Comment, Frame, encode


def test_a_frame_and_a_comment_are_encoded():
    assert encode(Frame(event='delta', data='{"text":"a"}')) == 'event: delta\ndata: {"text":"a"}\n\n'
    assert encode(Frame(event='x', data='1\n2', id='7')) == 'id: 7\nevent: x\ndata: 1\ndata: 2\n\n'
    assert encode(Comment('heartbeat')) == ': heartbeat\n\n'
