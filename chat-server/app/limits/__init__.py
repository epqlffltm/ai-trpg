# chat-server/app/limits/__init__.py

"""
요청 수 제한(#671). 한 사람이 정해진 시간 안에 몇 번 했는가를 세고, 넘으면 429 로 막는다.

  - counters.py: 세는 곳의 모양(Counter)과 서버 안의 메모리로 세는 것(MemoryCounter)
  - redis_counter.py: Redis 로 세는 것. 서버가 여럿이어도 같은 수를 본다
  - attempts.py: 제한 하나(AttemptLimit)와, 세고 막는 규칙(Limiter)
  - setup.py: 설정을 보고 어디서 셀지 고르고, chat 의 제한들(Limits)을 만든다
  - routing.py: API 가 받는 의존성(생성, 쓰기)
  - responses.py: 막혔을 때의 응답(429)

게임 서버의 것(trpg-server/app/limits/)에서 chat 이 쓰는 부분만 옮겼다. 고정 구간, Lua 로 올리고 만료를 건다,
대상은 해시해서 키에 넣는다, 막히면 429 와 Retry-After. 셋째로 쓰는 곳이 생기면 server-core 로 뽑는다.
Redis 에 닿지 못하면 막지 않고 경고만 남긴다(대화를 막아서 잃는 것이 더 크다).
"""
