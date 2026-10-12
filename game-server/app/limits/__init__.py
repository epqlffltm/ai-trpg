# game-server/app/limits/__init__.py

"""
시도 횟수 제한(#56). "누가 정해진 시간 안에 몇 번 했는가"를 세고, 넘으면 막는다.

  - counters.py: 세는 곳의 모양(Counter)과 서버 안의 메모리로 세는 것(MemoryCounter)
  - redis_counter.py: Redis 로 세는 것. 서버가 여럿이어도 같은 수를 본다
  - attempts.py: 제한 하나(AttemptLimit)와, 세고 막는 규칙(Limiter)
  - setup.py: 설정을 보고 어느 것으로 셀지 고르고, 게임 서버의 제한들(Limits)을 만든다
  - responses.py: 막혔을 때의 HTTP 응답(429, 503)

인증 서버의 시도 제한(auth-server/accounts/attempt_limits.py)과 같은 방식이다. 고정 구간, Lua 로 올리고 만료를 건다,
대상은 해시해서 키에 넣는다, 막히면 429 와 Retry-After.
"""
