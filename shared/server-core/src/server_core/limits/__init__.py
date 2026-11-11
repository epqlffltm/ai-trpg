# shared/server-core/src/server_core/limits/__init__.py

"""
요청 수 제한의 공통부(#1266). 게임, chat, story 가 함께 쓴다.

  - attempts: 제한 하나(AttemptLimit)와 세고 막는 규칙(Limiter), 막혔다는 오류
  - counters: 세는 곳의 모양(Counter)과 메모리로 세는 것(MemoryCounter)
  - redis_counter: Redis 로 세는 것. server-core[redis] 를 받은 서버만 쓴다
  - responses: 막혔을 때의 응답(429, 503)과 그것을 앱에 거는 use_limit_errors

어떤 제한을 몇 번으로 둘지(Limits), 무엇을 기준으로 셀지, Redis 의 DB 번호는 서버가 정한다(서버의 app/limits/).
"""
