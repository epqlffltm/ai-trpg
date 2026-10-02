# auth-server/config/redis_client.py

"""
Redis 연결.

Redis 에는 없어도 서비스가 도는 보조 장치(시도 횟수)만 둔다.
그래서 여기의 연결은 "빨리 실패하는" 쪽으로 잡는다. Redis 가 응답하지 않을 때
요청이 그것을 기다리느라 느려지면, 보조 장치가 서비스를 끌어내리는 꼴이 된다.
"""

from functools import lru_cache

import redis
from django.conf import settings

# Redis 에 연결하거나 응답을 기다리는 최대 시간(초).
# 같은 기기나 같은 망에 있는 Redis 는 보통 1밀리초 안에 응답한다. 이만큼 기다려도 안 오면 죽은 것으로 본다
REDIS_TIMEOUT_SECONDS = 0.2


@lru_cache(maxsize=1)
def get_redis() -> redis.Redis:
    """
    Redis 클라이언트를 돌려준다. 프로세스마다 하나만 만들어 계속 쓴다.

    만드는 시점에는 접속하지 않는다. 처음 명령을 보낼 때 접속한다.
    그래서 Redis 가 죽어 있어도 서버는 뜬다.
    """
    return redis.Redis.from_url(
        settings.REDIS_URL,
        socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
        socket_timeout=REDIS_TIMEOUT_SECONDS,
        # 응답을 bytes 가 아니라 str 로 받는다
        decode_responses=True,
    )
