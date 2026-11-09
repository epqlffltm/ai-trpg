# auth-server/support/urls.py

"""문의의 주소. config/urls.py 가 /api/v1/auth/ 아래에 잇는다(인증 서버의 다른 주소와 같은 앞부분)."""

from django.urls import path

from support.views import (
    InquiriesView,
    MyInquiriesView,
    OperatorInquiriesView,
    OperatorInquiryActionsView,
    OperatorInquiryDeleteView,
    OperatorInquiryReplyView,
    OperatorInquiryView,
)

app_name = 'support'

urlpatterns = [
    path('inquiries', InquiriesView.as_view(), name='inquiries'),
    path('me/inquiries', MyInquiriesView.as_view(), name='my-inquiries'),
    path('admin/inquiries', OperatorInquiriesView.as_view(), name='operator-inquiries'),
    # actions, delete 는 UUID 가 아니라 inquiry_id 의 주소와 겹치지 않는다
    path('admin/inquiries/actions', OperatorInquiryActionsView.as_view(), name='operator-inquiry-actions'),
    path('admin/inquiries/delete', OperatorInquiryDeleteView.as_view(), name='operator-inquiries-delete'),
    path('admin/inquiries/<uuid:inquiry_id>', OperatorInquiryView.as_view(), name='operator-inquiry'),
    path('admin/inquiries/<uuid:inquiry_id>/reply', OperatorInquiryReplyView.as_view(), name='operator-inquiry-reply'),
]
