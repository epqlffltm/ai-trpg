# shared/conversation-core/src/conversation_core/markers.py

"""
답의 본문 뒤에 모델이 쓰는 블록의 표식들. DB 도 모델도 모른다.

본문 뒤에는 블록이 둘 올 수 있다.
다음 답 추천(conversation_core/suggestions.py)과 상태 바꾸기의 제안(conversation_core/changes.py)이다.
어느 것이 먼저 와도 본문은 처음 나온 표식 앞까지다. 블록은 자기 표식부터 닫는 태그나 다음 블록의 표식까지다.
"""

# 다음 답 추천의 표식과 닫는 태그
SUGGESTIONS_MARKER = '<suggestions>'
SUGGESTIONS_CLOSING = '</suggestions>'
# 상태 바꾸기의 제안의 표식과 닫는 태그(#676)
CHANGES_MARKER = '<changes>'
CHANGES_CLOSING = '</changes>'
# 본문을 끝내는 표식들
END_MARKERS = (SUGGESTIONS_MARKER, CHANGES_MARKER)


def first_marker(text: str) -> int:
    """text 에서 처음 나온 표식의 자리. 없으면 -1."""
    found = [index for index in (text.find(marker) for marker in END_MARKERS) if index >= 0]
    return min(found) if found else -1


def block_after(text: str, marker: str, closing: str) -> str | None:
    """
    marker 뒤의 블록. 닫는 태그나 다른 블록의 표식 앞까지다. marker 가 없으면 None.
    """
    index = text.find(marker)
    if index < 0:
        return None
    block = text[index + len(marker) :].split(closing, 1)[0]
    for other in END_MARKERS:
        if other != marker:
            block = block.split(other, 1)[0]
    return block
