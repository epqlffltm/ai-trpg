# trpg-server/app/engine/keys.py

"""
규칙과 데이터가 서로를 가리킬 때 쓰는 이름의 모양.

규칙(app/engine/ruleset.py)과 물건의 효과(app/engine/item_effects.py)가 함께 쓴다. 규칙이 효과를 품게 되어(#805 의
기술) 둘이 서로를 가져오지 않도록 여기에 둔다. 무엇도 가져오지 않는다.
"""

from typing import Annotated

from pydantic import StringConstraints

# 코드와 데이터가 서로를 가리킬 때 쓰는 이름. 영어 소문자로 시작하고, 소문자와 숫자와 밑줄만 쓴다
Key = Annotated[str, StringConstraints(pattern=r'^[a-z][a-z0-9_]*$', max_length=20)]
# 사람에게 보여 주는 이름
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
