# game-server/tests/previews.py

"""
미리 보기를 받는 테스트가 함께 쓰는 도구. 받은 것을 시도마다 적어 두는 미리 보기가 여기 있다.
"""

from dataclasses import dataclass, field


@dataclass
class RecordingPreview:
    """
    받은 것을 시도마다 적어 두는 미리 보기. app/rounds/narrator.py 의 Preview 모양을 따른다.

    begin 없이 text 가 오면 IndexError 가 난다. 시도를 시작하지 않고 글을 보내는 실수를 잡는다.
    """

    attempts: list[list[str]] = field(default_factory=list)

    def begin(self) -> None:
        self.attempts.append([])

    def text(self, piece: str) -> None:
        self.attempts[-1].append(piece)

    def shown(self) -> list[str]:
        """시도마다 보여 준 글. 조각을 이어 붙인 것이다."""
        return [''.join(pieces) for pieces in self.attempts]
