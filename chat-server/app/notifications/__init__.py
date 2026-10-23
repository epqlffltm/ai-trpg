# chat-server/app/notifications/__init__.py

"""
사람에게 보내는 알림을 알림 서버에 넣는다(#678). 발송함과 보내는 작업은 공용 코드에 있다(server_core/notifications/).

  - models.py: 이 서버의 발송함 표(outgoing_notifications)
  - outbox.py: 무엇을 누구에게 알리는가. 대화 속 답의 신고를 처리한 것을 신고한 사람에게

알림을 정한 일(운영자의 처리)과 같은 트랜잭션에 적는다. 알림 서버에는 뒤에서 몇 초마다 보낸다(app/main.py 가 돌린다).
NOTIFICATION_URL 을 비우면 적기만 하고 보내지 않는다.
"""
