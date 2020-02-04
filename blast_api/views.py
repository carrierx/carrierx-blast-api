import logging
import json
import coreapi
import coreschema
from django.shortcuts import get_object_or_404
from django.db.models import Q
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes, schema
from rest_framework.response import Response
from rest_framework.schemas import AutoSchema
from rfc3339 import parse_datetime
from threading import Thread

from .models import Message, DoNotCallNumber
from .serializers import MessageSerializer, CallSerializer, DNCNumberSerializer

# Get an instance of a logger
logger = logging.getLogger(__name__)


class CallsSchema(AutoSchema):
    def get_manual_fields(self, path, method):
        extra_fields = [coreapi.Field(
            "shout-id",
            required=True,
            location="query",
            schema=coreschema.Integer(description="The ID of the shout to retrieve calls for.")
        )]

        manual_fields = super().get_manual_fields(path, method)
        return manual_fields + extra_fields


class ShoutsSchema(AutoSchema):
    def get_manual_fields(self, path, method):

        extra_fields = []
        if method == 'GET':
            extra_fields = [coreapi.Field(
                "userdata",
                required=True,
                location="query",
                schema=coreschema.String(
                    description="Reference data for the calling application, typically an identifier for a user "
                                "in that system.")
            )]  # ... list of extra fields for GET ...
        if method == 'POST':
            extra_fields = [
                coreapi.Field(
                    "title",
                    required=False,
                    location="form",
                    schema=coreschema.String(description="The title of the shout.")
                ),
                coreapi.Field(
                    "caller",
                    required=True,
                    location="form",
                    schema=coreschema.String(
                        description="The phone number from which the calls will be placed. "
                                    "Phone number format: 15555551010")
                ),
                coreapi.Field(
                    "recipients",
                    required=True,
                    location="form",
                    schema=coreschema.Array(
                        description="A list of phone numbers to deliver the shout to. Phone number format: 15555551010")
                ),
                coreapi.Field(
                    "schedule",
                    required=False,
                    location="form",
                    schema=coreschema.String(
                        description="Time when shout should be sent. If not set, the shout will be scheduled "
                                    "immediately. MUST conform to RFC 3339 and Time Zone MUST also be given.")
                ),
                coreapi.Field(
                    "userdata",
                    required=True,
                    location="form",
                    schema=coreschema.String(
                        description="Reference data for the calling application, typically an identifier for a user "
                                    "in that system.")
                ),
                coreapi.Field(
                    "old-shout-id",
                    required=False,
                    location="form",
                    schema=coreschema.Integer(
                        description="The ID of an existing shout. The recording from this shout will be used for the "
                                    "one being created. A new recording will not be made.")
                ),
            ]  # ... list of extra fields for POST ...

        manual_fields = super().get_manual_fields(path, method)
        return manual_fields + extra_fields


class DNCNumbersSchema(AutoSchema):
    def get_manual_fields(self, path, method):
        extra_fields = []
        if method == "GET":
            extra_fields = [
                coreapi.Field(
                    "userdata",
                    required=True,
                    location="path",
                    schema=coreschema.String(description="Userdata of the requested DNC list.")
                )]
        elif method == "DELETE":
            extra_fields = [
                coreapi.Field(
                    "userdata",
                    required=True,
                    location="path",
                    schema=coreschema.String(description="The callee number.")
            ),
                coreapi.Field(
                    "number",
                    required=True,
                    location="path",
                    schema=coreschema.String(description="Userdata of the requested DNC list.")
                )
            ]

        manual_fields = super().get_manual_fields(path, method)
        return manual_fields + extra_fields


@api_view(['GET', 'POST'])
@schema(ShoutsSchema())
@permission_classes((permissions.AllowAny,))
def shouts(request):
    """
    The `shouts` API allows you to create new shouts, or list existing shouts.
    """
    logger.info('/shouts')
    logger.info("%s", request.data)

    if request.method == 'POST':
        body = request.data
        title = body.get('title')
        caller = body.get('caller')
        recipients = body.get('recipients')
        schedule = body.get('schedule')
        user_data = body.get('userdata')
        old_shout_id = body.get('old-shout-id')

        scheduled_datetime = None
        if schedule:
            try:
                scheduled_datetime = parse_datetime(schedule)
            except ValueError:
                logger.exception('Error parsing schedule "%s"', schedule)
                return Response(f'Invalid schedule format: "{schedule}". Schedule must be an RFC 3339 date',
                                status=status.HTTP_400_BAD_REQUEST)

        if not user_data:
            logger.error('There was no userdata specified')
            return Response('You have to specify userdata', status=status.HTTP_404_NOT_FOUND)

        if old_shout_id:
            try:
                old_message = Message.objects.get(pk=old_shout_id)
            except Message.DoesNotExist:
                return Response(exception=True, status=404, data=json.dumps({"status": 404,
                                                                             "error": f"The shout with ID {old_shout_id} "
                                                                             f"does not exist"}))
        message = Message.objects.create(title=title,
                                         schedule=scheduled_datetime,
                                         user_data=user_data,
                                         caller=caller,
                                         status="pending")

        if not recipients:
            logger.error('There were no recipients specified')
            return Response('You have to specify at least one recipient', status=status.HTTP_404_NOT_FOUND)

        for recipient in set(recipients):
            try:
                DoNotCallNumber.objects.get(number=recipient, user_data=user_data)
                message.call_set.create(to_number=recipient, status="do not call")
            except DoNotCallNumber.DoesNotExist:
                message.call_set.create(to_number=recipient, status="pending")

        if old_shout_id:
            message.recording = old_message.recording
            message.confirm()
        else:
            logger.info('Starting recording')
            thread = Thread(target=message.record)
            thread.start()

        serializer = MessageSerializer(message)

        return Response(serializer.data)

    elif request.method == 'GET':
        user_data = request.GET.get('userdata')
        if user_data:
            messages = Message.objects.filter(user_data=user_data)
            serializer = MessageSerializer(messages, many=True)
            return Response(serializer.data)
        else:
            return Response('User data is required', status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@schema(ShoutsSchema())
@permission_classes((permissions.AllowAny,))
def get_shout(request, shout_id):
    """Get the detail for a shout record"""
    logger.info(f'/get_shout/{shout_id}')
    message = get_object_or_404(Message, pk=shout_id)
    serializer = MessageSerializer(message)

    return Response(serializer.data)


@api_view(['DELETE'])
@schema(ShoutsSchema())
@permission_classes((permissions.AllowAny,))
def cancel_shout(request, shout_id):
    """Cancel a shout that is scheduled for the future or in progress"""
    logger.info('/cancel_shout')
    logger.info("%s", request.body)

    message = get_object_or_404(Message, pk=shout_id)
    message.cancel()
    return Response(status=201)


@api_view(['GET'])
@schema(CallsSchema())
@permission_classes((permissions.AllowAny,))
def calls(request):
    """List call details for a shout"""
    logger.info('/calls')
    logger.info("%s", request.GET)
    shout_id = request.GET.get('shout-id')

    if not shout_id:
        return Response('shout-id is a required parameter', status=status.HTTP_404_NOT_FOUND)

    message = get_object_or_404(Message, pk=shout_id)
    db_calls = message.call_set.all()
    serializer = CallSerializer(db_calls, many=True)

    return Response(serializer.data)

@api_view(['GET'])
@schema(DNCNumbersSchema())
@permission_classes((permissions.AllowAny, ))
def dnc(request, userdata):
    logger.info('/dnc')
    logger.info(request.GET)
    dnc_entries = DoNotCallNumber.objects.filter(user_data=userdata)
    serializer = DNCNumberSerializer(dnc_entries, many=True)
    return Response(serializer.data)


@api_view(['DELETE'])
@schema(DNCNumbersSchema())
@permission_classes((permissions.AllowAny, ))
def dnc_delete(request, userdata, number):
    logger.info('/dnc')
    logger.info(request.GET)
    try:
        dnc_entry = DoNotCallNumber.objects.get(user_data=userdata, number=number)
        dnc_entry.delete()
        return Response(status=201)
    except DoNotCallNumber.DoesNotExist:
        return Response("There is no such combination of userdata and number")
