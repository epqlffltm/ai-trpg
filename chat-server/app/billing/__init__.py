# chat-server/app/billing/__init__.py

"""
말 한 번의 값을 결제 서버에서 받는다(docs/architecture/chat-server.md 의 "과금").

결제 서버를 부르는 것(Billing, 가격 목록, 셈, 설정)은 공용 코드(server_core/billing/)에 있다(#1266).
게임 서버와 함께 쓴다.
여기에는 이 서버만의 것이 남는다.

  - prices.py: 가격표 이름의 머리(chat)와 이름을 짓는 법(chat.<이름표>.i0.o0)
  - routing.py, router.py: 라우터가 쓰는 가격 목록의 의존성과, 가격 목록을 받지 못했을 때의 503
"""
