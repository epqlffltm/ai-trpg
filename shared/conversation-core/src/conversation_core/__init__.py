# shared/conversation-core/src/conversation_core/__init__.py

"""
대화의 핵심. chat 과 story 가 함께 쓰는 것을 모은다(docs/architecture/shared-code.md 의 "대화의 핵심").

chat 서버의 app/conversation 을 파일째 옮겼다(#591). 지금 있는 것은 DB 도 모델도 모르는 순수한 조각이다.
  - 스트림: SSE 의 글자(sse), 모델을 부르는 작업과 응답을 잇는 통로(relay)
  - 프롬프트: 최근 대화 창(window), 로어북 항목 고르기(lorebook), 이어서 출력의 지시와 겹친 앞부분 떼기(continuation)
  - 답의 블록: 표식(markers), 다음 답 추천(suggestions), 상태 바꾸기의 제안(changes), 표정 고르기(expressions)
대화와 메시지의 표(ORM 모델)는 서버마다 자기 스키마에 둔다. 여기에 두지 않는다.

서버의 코드(app.*)와 다른 공용 패키지(server_core, ai_core)를 가져오지 않는다. 표준 라이브러리만 쓴다
(tests/test_boundary.py 가 지킨다).
"""
