# story-server/app/core/config.py

"""
story 서버의 설정. 환경 변수와 story-server/.env 에서 읽는다.

FastAPI 서버들이 함께 쓰는 칸(DB, 인증 서버, 로그, 수집기)은 공용 코드의 설정(server_core.settings.CoreSettings)에 있다.
여기에는 이 서버의 이름과 기본값, 이 서버만의 칸을 둔다.

비밀값과 환경마다 달라지는 값은 코드에 적지 않는다.
다른 서버의 .env 와 따로 둔다. 한 서버가 다른 서버의 비밀값을 읽을 수 없게 하기 위해서다.
"""

from functools import lru_cache
from typing import ClassVar

from pydantic import Field
from server_core.settings import SCHEMA_PATTERN, CoreSettings


class Settings(CoreSettings):
    """
    설정 값의 목록과 형식. 함께 쓰는 칸은 CoreSettings 에 있다.

    같은 이름의 환경 변수가 있으면 그 값을 쓰고, 없으면 .env 파일, 그것도 없으면 여기 적힌 기본값을 쓴다.
    형식이 맞지 않으면(예: DEBUG=maybe) 서버가 뜨기 전에 오류가 난다.
    """

    # 이 서버의 이름. 로그의 service 칸, span 과 메트릭의 출처다. 규격(docs/observability.md)에 적힌 이름이다
    service_name: ClassVar[str] = 'story-server'

    # 테이블을 두는 스키마. 테스트는 story_test 로 바꿔서 개발용 데이터와 섞이지 않게 한다
    db_schema: str = Field(default='story', pattern=SCHEMA_PATTERN)

    # 이 서버의 이름. 토큰의 대상 목록(aud)에 이 이름이 있어야 받는다.
    # 다른 서버용으로 발급된 토큰을 이 서버에 쓰는 것을 막는다
    jwt_audience: str = 'ai-trpg-story'


@lru_cache
def get_settings() -> Settings:
    """
    설정을 읽어 돌려준다. 처음 한 번만 읽고 그 뒤로는 같은 객체를 돌려준다.

    요청마다 .env 를 다시 읽지 않는다. 테스트는 이 함수를 거치지 않고 Settings 를 직접 만들어 앱에 넣는다.
    """
    return Settings()
