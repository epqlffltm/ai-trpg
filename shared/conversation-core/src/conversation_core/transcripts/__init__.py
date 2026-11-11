# shared/conversation-core/src/conversation_core/transcripts/__init__.py

"""
기록 파일을 쓰는 공통부(#1266). chat, story, trpg 가 함께 쓴다.

  - blocks: 기록의 조각(구분, 문단, 말, 한 줄의 일). 형식을 모른다
  - markdown, html, text: 조각을 형식마다 글로 쓰는 것과 파일의 머리. 파일 전체를 한 번에 쓰는 document 도 있다
무엇을 쓸지(대화의 말, 이벤트와 채팅을 조각으로 바꾸기), 기록의 제목과 범위의 말은 서버가 정한다
(서버의 app/transcripts/).
DB 와 HTTP 를 모른다. 표준 라이브러리만 쓴다.
"""
