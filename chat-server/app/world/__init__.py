# chat-server/app/world/__init__.py

"""
장소와 소지품(docs/architecture/chat-server.md 의 "장소와 소지품"). 상태는 DB 가 갖고, 모델은 읽고 반응만 한다.

  - state.py: 지금의 상태(장소, 흐른 시간, 소지품, 가 본 곳)와 시작 상태. 가지의 끝에서 거슬러 올라가 읽는다
  - moves.py: 지도에서 이동하는 규칙(갈 수 있는가, 가면 어떻게 되나). DB 를 모르는 순수 함수다
  - scene.py: 모델에 보내는 "[지금]" 블록
  - models.py, repository.py: 말마다의 상태(message_states)

규칙의 순수 함수는 TRPG 와 함께 쓸 때 shared/ 로 옮긴다(설계의 "규칙의 집").
"""
