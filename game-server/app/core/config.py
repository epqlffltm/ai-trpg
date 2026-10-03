# game-server/app/core/config.py

"""
게임 서버의 설정. 환경 변수와 game-server/.env 에서 읽는다.

비밀값과 환경마다 달라지는 값은 코드에 적지 않는다.
인증 서버의 .env 와 따로 둔다. 한 서버가 다른 서버의 비밀값을 읽을 수 없게 하기 위해서다.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    설정 값의 목록과 형식.

    같은 이름의 환경 변수가 있으면 그 값을 쓰고, 없으면 .env 파일, 그것도 없으면 여기 적힌 기본값을 쓴다.
    형식이 맞지 않으면(예: DEBUG=maybe) 서버가 뜨기 전에 오류가 난다.
    """

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        # .env 에 이 서버가 모르는 값이 있어도 무시한다
        extra='ignore',
    )

    # 개발용 기능(API 문서 화면)을 켠다. 기본은 꺼짐이다.
    # 켜는 것을 잊으면 불편할 뿐이지만, 끄는 것을 잊으면 운영 서버의 API 구조가 드러난다
    debug: bool = False


@lru_cache
def get_settings() -> Settings:
    """
    설정을 읽어 돌려준다. 처음 한 번만 읽고 그 뒤로는 같은 객체를 돌려준다.

    요청마다 .env 파일을 다시 읽지 않기 위해서다.
    """
    return Settings()
