# game-server/app/core/dice.py

"""
앱에 꽂아 둔 주사위를 요청에 내준다.

주사위는 앱이 뜰 때 하나를 꽂아 둔다(app/main.py). 라우터는 이 의존성으로 받아 서비스에 넘긴다.
테스트는 정해진 눈을 내는 주사위를 꽂는다. 서비스와 엔진은 주사위가 어디서 왔는지 모른다.

주사위를 굴리는 주소가 여러 폴더에 있어서(라운드의 판정, 캐릭터의 능력치) 한곳에 둔다.
"""

from typing import Annotated

from fastapi import Depends, Request

from app.engine.dice import Dice


def get_dice(request: Request) -> Dice:
    """앱에 꽂아 둔 주사위를 내준다."""
    return request.app.state.dice


Rolling = Annotated[Dice, Depends(get_dice)]
