# game-server/app/engine/dice.py

"""
주사위. 판정에 쓰는 난수의 출처다.

주사위를 모양(Dice)과 구현으로 나눈다. 판정하는 코드는 모양만 안다.
실제 서비스에서는 예측할 수 없는 주사위를, 테스트에서는 정해진 눈을 내는 주사위를 꽂는다.
같은 눈이면 같은 결과가 나오는지 볼 수 있어야 판정을 테스트할 수 있다.

주사위는 서버만 굴린다. 화면이 굴린 값을 받아 쓰지 않는다. 받아 쓰면 원하는 눈을 보낼 수 있다.
"""

import random
from typing import Protocol


class Dice(Protocol):
    """주사위의 모양. 이 메서드가 있으면 주사위다."""

    def roll(self, sides: int) -> int:
        """면이 sides 개인 주사위를 한 번 굴린다. 1 부터 sides 까지의 수가 나온다."""
        ...


class RandomDice:
    """
    진짜 주사위. 운영체제의 난수를 쓴다.

    random 모듈의 기본 난수는 앞의 값들을 보면 다음 값을 맞힐 수 있다.
    SystemRandom 은 운영체제가 주는 난수를 써서 그렇게 할 수 없다.
    """

    def __init__(self) -> None:
        self._random = random.SystemRandom()

    def roll(self, sides: int) -> int:
        """1 부터 sides 까지 중 하나를 고르게 낸다."""
        return self._random.randint(1, sides)


class ScriptedDice:
    """
    정해진 눈을 순서대로 내는 주사위. 테스트에 쓴다.

    눈이 다 떨어졌거나, 굴리는 주사위에 없는 눈이 적혀 있으면 오류를 낸다.
    테스트가 생각한 것과 다르게 굴렸다는 뜻이라, 조용히 넘어가지 않는다.
    """

    def __init__(self, rolls: list[int]) -> None:
        self._rolls = list(rolls)

    def roll(self, sides: int) -> int:
        """다음 눈을 낸다."""
        if not self._rolls:
            raise IndexError('적어 둔 눈을 다 썼습니다.')
        value = self._rolls.pop(0)
        if not 1 <= value <= sides:
            raise ValueError(f'{sides} 면 주사위에 {value} 는 없습니다.')
        return value

    @property
    def remaining(self) -> int:
        """아직 내지 않은 눈의 수."""
        return len(self._rolls)
