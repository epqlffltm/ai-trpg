# auth-server/support/views.py

"""
문의의 주소. 일은 inquiries.py 가 한다.

    POST /api/v1/auth/inquiries                          문의를 보낸다(로그인 없어도 된다. 그때는 답 받을 주소를 적는다)
    GET  /api/v1/auth/me/inquiries                       내 문의와 답(로그인)
    GET  /api/v1/auth/admin/inquiries                    문의 목록과 상자마다의 수(운영자)
    GET  /api/v1/auth/admin/inquiries/{id}               문의 하나를 연다. 처음이면 읽음으로 적는다(운영자)
    DELETE /api/v1/auth/admin/inquiries/{id}             문의 하나를 지운다(운영자)
    POST /api/v1/auth/admin/inquiries/delete             고른 것(ids) 또는 상자 하나(folder)를 지운다(운영자)
    POST /api/v1/auth/admin/inquiries/{id}/reply         답을 적고 메일로 보낸다(운영자)

운영자 화면은 메일함처럼 본다. 상자는 상태(답 기다림, 답함)와 모두, 줄마다 읽었는지(read_at)가 있다.

운영자의 주소는 다른 서버처럼 admin 아래다. 운영자가 아니면 404 다(support/permissions.py).

목록은 최근 것부터 한 쪽씩이다. 다음 쪽은 응답의 next_before 를 before 로 실어 부른다.
"""

import uuid

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_field
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.api_schema import TOO_MANY_ATTEMPTS, bad_request, coded, unauthenticated
from support.inquiries import (
    ALL_FOLDER,
    SELECTED_MAX,
    FolderCounts,
    InquiryAlreadyAnsweredError,
    InquiryNotFoundError,
    Page,
    delete_inquiry,
    delete_selected_inquiries,
    empty_folder,
    folder_counts,
    my_inquiries,
    operator_inquiries,
    read_inquiry,
    reply_to_inquiry,
    submit_inquiry,
)
from support.models import (
    BODY_MAX_LENGTH,
    REPLY_MAX_LENGTH,
    TITLE_MAX_LENGTH,
    Inquiry,
    InquiryCategory,
    InquiryStatus,
)
from support.permissions import IsOperator
from support.throttles import InquiryIpThrottle


class InquiryRequestSerializer(serializers.Serializer):
    """보낼 문의. 로그인했으면 email 은 보지 않는다(계정의 주소로 답한다)."""

    category = serializers.ChoiceField(choices=InquiryCategory.choices)
    title = serializers.CharField(max_length=TITLE_MAX_LENGTH)
    body = serializers.CharField(max_length=BODY_MAX_LENGTH)
    email = serializers.EmailField(required=False, help_text='답 받을 주소. 로그인하지 않았으면 꼭 적는다')


class InquiryCreatedSerializer(serializers.Serializer):
    """받은 문의."""

    id = serializers.UUIDField()
    created_at = serializers.DateTimeField()


class MyInquirySerializer(serializers.Serializer):
    """내 문의 하나. 답하지 않았으면 reply 가 빈 글이고 answered_at 이 null 이다."""

    id = serializers.UUIDField()
    category = serializers.ChoiceField(choices=InquiryCategory.choices)
    title = serializers.CharField()
    body = serializers.CharField()
    status = serializers.ChoiceField(choices=InquiryStatus.choices)
    created_at = serializers.DateTimeField()
    reply = serializers.CharField(allow_blank=True)
    answered_at = serializers.DateTimeField(allow_null=True)


class MyInquiryPageSerializer(serializers.Serializer):
    items = MyInquirySerializer(many=True)
    next_before = serializers.DateTimeField(allow_null=True, help_text='다음 쪽을 부를 before. 마지막 쪽이면 null')


# 문의를 보낸 계정. 로그인하지 않고 보냈으면 null 이다. 객체를 바로 적는다.
# 참조(allOf)에 nullable 을 붙이면 OpenAPI 3.0 에서 null 이 통하지 않는다(accounts/attendance_views.py 의 상자와 같다)
SENDER_SCHEMA = {
    'type': 'object',
    'nullable': True,
    'description': '문의를 보낸 계정. 로그인하지 않고 보냈으면 null 이다',
    'additionalProperties': False,
    'required': ['public_id', 'nickname'],
    'properties': {
        'public_id': {'type': 'string', 'format': 'uuid'},
        'nickname': {'type': 'string'},
    },
}


@extend_schema_field(SENDER_SCHEMA)
class SenderField(serializers.Field):
    """보낸 계정의 칸. 값을 그대로 낸다({public_id, nickname} 또는 None)."""

    def to_representation(self, value: dict) -> dict:
        return {'public_id': str(value['public_id']), 'nickname': value['nickname']}


class OperatorInquirySerializer(MyInquirySerializer):
    """운영자가 보는 문의 하나. 보낸 계정(로그인하지 않고 보냈으면 null), 답 받을 주소, 답 메일의 결과를 더한다."""

    sender = SenderField(allow_null=True)
    email = serializers.EmailField()
    read_at = serializers.DateTimeField(allow_null=True, help_text='운영자가 처음 연 시각. null 이면 아직 읽지 않았다')
    reply_sent_at = serializers.DateTimeField(allow_null=True, help_text='메일 서버가 답 메일을 받은 시각')
    reply_discarded_at = serializers.DateTimeField(
        allow_null=True, help_text='답 메일을 끝내 보내지 못하고 버린 시각. 그러면 다른 길로 알려야 한다'
    )


class FolderCountsSerializer(serializers.Serializer):
    """상자마다의 수. unread 는 운영자가 아직 열지 않은 것이다."""

    all = serializers.IntegerField()
    open = serializers.IntegerField()
    answered = serializers.IntegerField()
    unread = serializers.IntegerField()


class OperatorInquiryPageSerializer(serializers.Serializer):
    items = OperatorInquirySerializer(many=True)
    counts = FolderCountsSerializer()
    next_before = serializers.DateTimeField(allow_null=True, help_text='다음 쪽을 부를 before. 마지막 쪽이면 null')


class PageQuerySerializer(serializers.Serializer):
    before = serializers.DateTimeField(required=False)


class OperatorPageQuerySerializer(PageQuerySerializer):
    status = serializers.ChoiceField(choices=InquiryStatus.choices, required=False)


class DeleteRequestSerializer(serializers.Serializer):
    """지울 것. 고른 문의들(ids)과 상자 하나(folder) 가운데 하나만 싣는다."""

    ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        max_length=SELECTED_MAX,
        required=False,
        help_text=f'고른 문의들. {SELECTED_MAX}개까지',
    )
    folder = serializers.ChoiceField(
        choices=[ALL_FOLDER, *InquiryStatus.values],
        required=False,
        help_text='통째로 비울 상자. all 은 모든 문의다',
    )

    def validate(self, attrs: dict) -> dict:
        if ('ids' in attrs) == ('folder' in attrs):
            raise serializers.ValidationError('ids 와 folder 가운데 하나만 적어 주세요.')
        return attrs


class DeletedSerializer(serializers.Serializer):
    deleted = serializers.IntegerField(help_text='지운 문의의 수')


class ReplyRequestSerializer(serializers.Serializer):
    reply = serializers.CharField(max_length=REPLY_MAX_LENGTH)


# 404 의 모양. 운영자가 아니면 {"detail"}, 그런 문의가 없으면 {"detail", "code": "inquiry.not_found"} 다
NOT_FOUND = OpenApiResponse(
    response={
        'type': 'object',
        'required': ['detail'],
        'properties': {'detail': {'type': 'string'}, 'code': {'type': 'string'}},
        'additionalProperties': False,
    },
    description='운영자가 아니다. 답하기에서는 그런 문의가 없을 때도다(inquiry.not_found)',
)

BEFORE_PARAMETER = OpenApiParameter(
    'before', str, description='이 시각보다 앞에 보낸 것부터. 앞 쪽의 next_before 를 싣는다', required=False
)
STATUS_PARAMETER = OpenApiParameter(
    'status', str, enum=InquiryStatus.values, description='이 상태의 것만. 없으면 모두', required=False
)


def my_inquiry_body(inquiry: Inquiry) -> dict:
    """내 문의를 응답의 모양으로."""
    return {
        'id': inquiry.id,
        'category': inquiry.category,
        'title': inquiry.title,
        'body': inquiry.body,
        'status': inquiry.status,
        'created_at': inquiry.created_at,
        'reply': inquiry.reply,
        'answered_at': inquiry.answered_at,
    }


def operator_inquiry_body(inquiry: Inquiry) -> dict:
    """운영자가 보는 문의를 응답의 모양으로."""
    sender = None
    if inquiry.user is not None:
        sender = {'public_id': inquiry.user.public_id, 'nickname': inquiry.user.nickname}
    receipt = inquiry.reply_receipt
    return {
        **my_inquiry_body(inquiry),
        'sender': sender,
        'email': inquiry.email,
        'read_at': inquiry.read_at,
        'reply_sent_at': receipt.sent_at if receipt else None,
        'reply_discarded_at': receipt.discarded_at if receipt else None,
    }


def page_body(page: Page, body_of) -> dict:
    return {'items': [body_of(inquiry) for inquiry in page.items], 'next_before': page.next_before}


def counts_body(counts: FolderCounts) -> dict:
    return {'all': counts.all, 'open': counts.open, 'answered': counts.answered, 'unread': counts.unread}


def not_found() -> Response:
    """그런 문의가 없다(404 inquiry.not_found)."""
    return Response({'detail': '그런 문의가 없습니다.', 'code': 'inquiry.not_found'}, status=status.HTTP_404_NOT_FOUND)


class InquiriesView(APIView):
    """POST /api/v1/auth/inquiries. 로그인하지 못하는 사람도 보낸다."""

    permission_classes = [AllowAny]
    throttle_classes = [InquiryIpThrottle]

    @extend_schema(
        summary='문의를 보낸다. 로그인했으면 계정의 주소로, 아니면 적은 주소로 답한다',
        request=InquiryRequestSerializer,
        responses={
            201: InquiryCreatedSerializer,
            400: bad_request('칸이 틀렸거나, 로그인하지 않았는데 답 받을 주소(email)가 없다'),
            401: unauthenticated(),
            429: TOO_MANY_ATTEMPTS,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = InquiryRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user if request.user.is_authenticated else None
        if user is None and not serializer.validated_data.get('email'):
            raise serializers.ValidationError({'email': ['답 받을 주소를 적어 주세요.']})
        inquiry = submit_inquiry(user=user, **serializer.validated_data)
        body = InquiryCreatedSerializer({'id': inquiry.id, 'created_at': inquiry.created_at})
        return Response(body.data, status=status.HTTP_201_CREATED)


class MyInquiriesView(APIView):
    """GET /api/v1/auth/me/inquiries. 내 문의와 답."""

    # 로그인한 본인만. 기본 권한(IsAuthenticated)을 쓴다

    @extend_schema(
        summary='내 문의와 답. 최근 것부터 한 쪽씩',
        parameters=[BEFORE_PARAMETER],
        responses={200: MyInquiryPageSerializer, 400: bad_request('before 가 시각이 아니다'), 401: unauthenticated()},
    )
    def get(self, request: Request) -> Response:
        query = PageQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        page = my_inquiries(request.user, before=query.validated_data.get('before'))
        return Response(MyInquiryPageSerializer(page_body(page, my_inquiry_body)).data, status=status.HTTP_200_OK)


class OperatorInquiriesView(APIView):
    """GET /api/v1/auth/admin/inquiries. 운영자의 문의 목록."""

    permission_classes = [IsOperator]

    @extend_schema(
        summary='문의 목록(운영자). 상태로 고르고, 최근 것부터 한 쪽씩',
        # 하나를 여는 주소(GET .../{id})와 이름이 겹치지 않게 정한다
        operation_id='admin_inquiries_list',
        parameters=[STATUS_PARAMETER, BEFORE_PARAMETER],
        responses={
            200: OperatorInquiryPageSerializer,
            400: bad_request('status 나 before 가 틀렸다'),
            401: unauthenticated(),
            404: NOT_FOUND,
        },
    )
    def get(self, request: Request) -> Response:
        query = OperatorPageQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        page = operator_inquiries(status=query.validated_data.get('status'), before=query.validated_data.get('before'))
        body = OperatorInquiryPageSerializer(
            {**page_body(page, operator_inquiry_body), 'counts': counts_body(folder_counts())}
        )
        return Response(body.data, status=status.HTTP_200_OK)


class OperatorInquiryView(APIView):
    """GET, DELETE /api/v1/auth/admin/inquiries/{id}. 문의 하나를 열고 지운다."""

    permission_classes = [IsOperator]

    @extend_schema(
        summary='문의 하나를 연다(운영자). 처음 열면 읽음으로 적는다',
        operation_id='admin_inquiry_retrieve',
        responses={200: OperatorInquirySerializer, 401: unauthenticated(), 404: NOT_FOUND},
    )
    def get(self, request: Request, inquiry_id: uuid.UUID) -> Response:
        try:
            inquiry = read_inquiry(inquiry_id)
        except InquiryNotFoundError:
            return not_found()
        return Response(OperatorInquirySerializer(operator_inquiry_body(inquiry)).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary='문의 하나를 지운다(운영자)',
        responses={204: None, 401: unauthenticated(), 404: NOT_FOUND},
    )
    def delete(self, request: Request, inquiry_id: uuid.UUID) -> Response:
        try:
            delete_inquiry(inquiry_id)
        except InquiryNotFoundError:
            return not_found()
        return Response(status=status.HTTP_204_NO_CONTENT)


class OperatorInquiryDeleteView(APIView):
    """POST /api/v1/auth/admin/inquiries/delete. 고른 것 또는 상자 하나를 통째로 지운다."""

    permission_classes = [IsOperator]

    @extend_schema(
        summary='고른 문의들(ids) 또는 상자 하나(folder: all, open, answered)를 지운다(운영자)',
        request=DeleteRequestSerializer,
        responses={
            200: DeletedSerializer,
            400: bad_request('ids 와 folder 를 함께 적었거나 둘 다 없다, 또는 칸이 틀렸다'),
            401: unauthenticated(),
            404: NOT_FOUND,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = DeleteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if 'ids' in serializer.validated_data:
            deleted = delete_selected_inquiries(serializer.validated_data['ids'])
        else:
            deleted = empty_folder(serializer.validated_data['folder'])
        return Response(DeletedSerializer({'deleted': deleted}).data, status=status.HTTP_200_OK)


class OperatorInquiryReplyView(APIView):
    """POST /api/v1/auth/admin/inquiries/{id}/reply. 답을 적고 메일로 보낸다."""

    permission_classes = [IsOperator]

    @extend_schema(
        summary='문의에 답한다(운영자). 답은 한 번만 쓰고, 문의의 주소로 메일을 보낸다',
        request=ReplyRequestSerializer,
        responses={
            200: OperatorInquirySerializer,
            400: bad_request(),
            401: unauthenticated(),
            404: NOT_FOUND,
            409: coded('이미 답한 문의다(inquiry.already_answered)'),
        },
    )
    def post(self, request: Request, inquiry_id: uuid.UUID) -> Response:
        serializer = ReplyRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            inquiry = reply_to_inquiry(
                inquiry_id=inquiry_id, operator=request.user, reply=serializer.validated_data['reply']
            )
        except InquiryNotFoundError:
            return not_found()
        except InquiryAlreadyAnsweredError:
            return Response(
                {'detail': '이미 답한 문의입니다.', 'code': 'inquiry.already_answered'}, status=status.HTTP_409_CONFLICT
            )
        inquiry = Inquiry.objects.select_related('user', 'reply_receipt').get(pk=inquiry.pk)
        return Response(OperatorInquirySerializer(operator_inquiry_body(inquiry)).data, status=status.HTTP_200_OK)
