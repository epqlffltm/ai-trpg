# auth-server/support/mail.py

"""
문의의 답 메일. 문구만 만든다. 맡기는 일은 inquiries.py 가 한다.
제목의 사이트 이름은 인증 서버의 다른 메일과 같다(accounts/mail.py).

답은 운영자가 쓴 글이라 하루 늦어도 쓸모가 있다. 인증 코드(5분)보다 오래 다시 시도한다.
"""

from datetime import timedelta

from accounts.mail import SITE_NAME
from support.models import Inquiry

# 답 메일을 버리기까지의 시간
REPLY_DEADLINE = timedelta(days=1)

# 보낸 메일의 기록(MailReceipt)의 용도
REPLY_RECEIPT_PURPOSE = 'inquiry_reply'


def build_reply_message(inquiry: Inquiry) -> tuple[str, str]:
    """답 메일의 제목과 본문. 받는 사람이 무엇의 답인지 알게 보낸 제목과 내용을 아래에 붙인다."""
    subject = f'[{SITE_NAME}] 문의에 답했습니다: {inquiry.title}'
    body = (
        f'{inquiry.reply}\n\n'
        '----------\n'
        f'보낸 문의: {inquiry.title}\n\n'
        f'{inquiry.body}\n\n'
        '이 메일에는 답장할 수 없습니다. 더 물어볼 것이 있으면 사이트의 고객센터에서 새로 문의해 주세요.'
    )
    return subject, body
