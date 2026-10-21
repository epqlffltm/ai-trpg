# chat-server/app/conversation/__init__.py

"""
대화의 핵심. chat 과 story 가 함께 쓸 것을 여기에 모은다(docs/architecture/shared-code.md 의 "대화의 핵심").

대화 트리(다시 생성, 분기), 요약, 기억, 프롬프트를 붙이는 순서, 스트리밍한 답을 저장하는 흐름이 여기에 온다.
chat 만의 것(캐릭터 하나, 호감도, 그림)은 여기에 두지 않는다.

story-server 를 만들 때 이 폴더를 파일째 shared/conversation-core 로 옮긴다. 그때 import 만 바꾸면 되게
이 폴더는 앱의 다른 코드(app.*)를 가져오지 않는다(tests/test_conversation_boundary.py 가 지킨다).
공용 코드(server_core)와 바깥 라이브러리, 표준 라이브러리는 쓴다. 아직 비어 있다(뼈대, #590).
"""
