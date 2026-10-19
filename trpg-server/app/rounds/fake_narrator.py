# trpg-server/app/rounds/fake_narrator.py

"""
가짜 서술자. AI 를 부르지 않는 서술자(Narrator)의 구현.

AI 가 붙기 전에 라운드의 흐름을 돌려 보는 데 쓴다. 자동 테스트도 이것을 쓴다(NARRATOR=fake).
같은 입력에 늘 같은 글을 낸다. 각자 한 일의 줄(app/rounds/move_lines.py)을 그대로 늘어놓는다.
맞붙은 몬스터가 있던 라운드는 차례 순서로 캐릭터와 몬스터의 줄을 섞는다(round_lines).
"""

from app.rounds.move_lines import round_lines
from app.rounds.narrator import NO_PREVIEW, NarrationRequest, Preview


class FakeNarrator:
    """
    가짜 서술자. AI 를 부르지 않고 선언과 판정의 결과를 그대로 늘어놓는다.

    AI 가 붙기 전에 라운드의 흐름을 돌려 보는 데 쓴다. 자동 테스트도 이것을 쓴다.
    """

    async def narrate(self, request: NarrationRequest, preview: Preview = NO_PREVIEW) -> str:
        """한 일을 한 줄씩 늘어놓은 글을 돌려준다. 미리 보기에는 그 글을 한 번에 보낸다."""
        lines = [f'[{request.round_number} 라운드의 결과]']
        lines.extend(round_lines(request.moves, request.turns))
        scene = '\n'.join(lines)
        preview.begin()
        preview.text(scene)
        return scene
