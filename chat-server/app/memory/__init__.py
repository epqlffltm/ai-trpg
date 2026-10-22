# chat-server/app/memory/__init__.py

"""
기억(docs/architecture/chat-server.md 의 "기억"). 대화마다 따로 있다.

  - 기억 메모(memory_notes): 사용자가 보고 고치는 짧은 글. 모델에 "[기억]" 으로 늘 간다. 틀린 기억을 사람이 바로잡는다
  - 굴리는 요약: 창 밖으로 밀려난 앞부분의 요약(다음 PR)
"""
