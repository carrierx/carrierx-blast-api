import json
import logging
from datetime import datetime as dt, timezone

import requests
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q

from blast_api.models import Recording, Call, Message, DoNotCallNumber
from blast_api_project import configuration
from blast_api_project.utils import serialize_one
from . import constants
from blast_api_project.utils import CarrierXError

# Get an instance of a logger
logger = logging.getLogger(__name__)

cdr_logger = logging.getLogger('cdr_logger')
rec_cdr_logger = logging.getLogger('rec_cdr_logger')
# Create your views here.

@csrf_exempt
def message_status(request, message_id):
    logger.info('/message/status')
    logger.info("%s", request.body.decode('utf-8'))
    return HttpResponse(status=201)


@csrf_exempt
def record_status(request, message_id):
    logger.info('/record/status/%s', message_id)
    logger.info("%s", request.body)
    return HttpResponse(status=201)


@csrf_exempt
def instructions(request, message_id):
    logger.info("/call/instructions/%s", message_id)
    logger.info("%s", request.body)
    Message.objects.get(id=message_id).update_rec_call_status("USER_ANSWERED")
    return render(request, 'flexml/promptForRecording.xml', {'message_id': message_id,
                                                             'voice_menu': configuration.VOICE_MENU,
                                                             'container_sid': configuration.DEBUG_RECORDING_CONTAINER,
                                                             'record_call': configuration.RECORD_ALL_CALLS})


def get_user_container(user_data: str) -> str:
    get_container_response = requests.get(url=f'{configuration.BASE_CARRIERX_API_URL}/core/v2/storage/containers',
                                          params={"filter": f"string_key_1 eq {user_data}"},
                                          headers = {"Authorization": f"Bearer {configuration.CARRIERX_API_TOKEN}"})
    logger.info(get_container_response.content)
    matching_containers = get_container_response.json()
    if matching_containers["count"]:
        container = matching_containers["items"][0]
        container_sid = container["container_sid"]
        logger.info("Fetched the storage container for userdata %s -> %s",
                    user_data,
                    get_container_response.content)
        ensure_storage(container)
    else:
        create_container_response = requests.post(
            url=f'{configuration.BASE_CARRIERX_API_URL}/core/v2/storage/containers',
            json={"string_key_1": user_data,
                  "name": f"{user_data}'s messages",
                  "unique": True,
                  "quota_files": 10000,
                  "quota_bytes": 1024000000},
            headers = {"Authorization": f"Bearer {configuration.CARRIERX_API_TOKEN}"})
        logger.info("Created a storage container for userdata %s -> %s", user_data, create_container_response.content)
        container_sid = create_container_response.json()["container_sid"]
    logger.info("Container SID for user %s is %s", user_data, container_sid)
    return container_sid

def ensure_storage(container):
    container_sid = container["container_sid"]
    available_bytes_percent = container['available_bytes_percent']
    available_files_percent = container['available_files_percent']
    quota_bytes = container['quota_bytes']
    quota_files = container['quota_files']
    container_updated = False
    if available_bytes_percent < 5:
        container_updated = True
        quota_bytes += 1024000000
        logger.info(f'Container "{container_sid}" bytes increased to "{quota_bytes}"')
    if available_files_percent < 5:
        container_updated = True
        quota_files += 10000
        logger.info(f'Container "{container_sid}" files increased to "{quota_files}"')

    if container_updated:
        update_container_response = requests.patch(
            url=f'{configuration.BASE_CARRIERX_API_URL}/core/v2/storage/containers/{container_sid}',
            json={
                'quota_bytes': quota_bytes,
                'quota_files': quota_files
            },
            headers = {"Authorization": f"Bearer {configuration.CARRIERX_API_TOKEN}"})
        logger.info("Updated storage container %s -> %s", container_sid, update_container_response.content)


@csrf_exempt
def record_gather(request, message_id):
    logger.info("/record/gather/%s", message_id)
    logger.info("%s", request.body)

    data = json.loads(request.body)
    digits = data['Digits']

    logger.info(f'digits {digits}')
    if digits:
        if digits == '*':
            message = get_object_or_404(Message, pk=message_id)
            user_data = message.user_data
            message.update_rec_call_status("PRESSED_STAR")
            container_sid = get_user_container(user_data)
            data = {'message_id': message_id,
                    'place': {"type": "container",
                              "sid": container_sid},
                    'voice_menu': configuration.VOICE_MENU}
            return render(request, 'flexml/startRecording.xml', data)
        else:
            data = {'message_id': message_id,
                    'reprompt': True,
                    'voice_menu': configuration.VOICE_MENU}
            return render(request, 'flexml/promptForRecording.xml', data)
    else:
        return render(request, 'flexml/hangup.xml')

@csrf_exempt
def record_error(request, message_id):
    logger.info("/record/error/%s", message_id)
    logger.info("%s", request.body)

    message = Message.objects.get(pk=message_id)

    message.update_rec_call_status("CARRIERX_ERROR")
    message.cancel_with_error()

    return render(request, 'flexml/hangup.xml', {'app_error': True})

@csrf_exempt
def record_verify(request, message_id):
    logger.info(f'/record/verify/{message_id}')
    data = json.loads(request.body)
    logger.info("%s", data)
    call_sid = data['CallSid']
    recording_url = data['RecordingUrl']
    recording_file_sid = data['RecordingFileSid']
    recording_duration = data['RecordingDuration']
    message = Message.objects.get(pk=message_id)
    if call_sid and recording_url and recording_file_sid:
        Recording.objects.update_or_create(message=message,
                                           defaults=dict(
                                               url=f"{recording_url}?format={dt.now().timestamp()}.wav",
                                               sid=recording_file_sid,
                                               duration=recording_duration))
        message.update_rec_call_status("RECORDED")
        return render(request, 'flexml/verifyRecording.xml', {'message_id': message_id,
                                                              'voice_menu': configuration.VOICE_MENU})
    else:
        return render(request, 'flexml/promptForRecording.xml', {'message_id': message_id,
                                                                 'voice_menu': configuration.VOICE_MENU})


@csrf_exempt
def verify_gather(request, message_id):
    logger.info(f'/verify/gather/{message_id}')
    data = json.loads(request.body)
    logger.info("%s", data)
    message = Message.objects.get(pk=message_id)
    recording = message.recording
    digit = data['Digits']

    if digit:
        if digit == '1':  # Replay the recording
            # TODO: Do callback
            return render(request, 'flexml/playRecording.xml',
                          {'message_id': message_id,
                           'recording_url': recording.url,
                           'voice_menu': configuration.VOICE_MENU})
        elif digit == '2':  # Confirm sending of the message
            try:
                recording.confirm()
            except CarrierXError as e:
                logger.error("While recording confirmation CarrierX responded with error: %s", e)
                return render(request, 'flexml/verifyRecording.xml', {'message_id': message_id,
                                                                      'voice_menu': configuration.VOICE_MENU,
                                                                      'reprompt': True})
            message.update_rec_call_status("CONFIRMED")
            return render(request, 'flexml/saved.xml', {'voice_menu': configuration.VOICE_MENU})
        elif digit == '3':  # Delete and rerecord the message
            place = {"type": "file",
                     "sid": message.recording.sid}
            return render(request, 'flexml/startRecording.xml',
                          {'message_id': message_id,
                           'place': place,
                           'voice_menu': configuration.VOICE_MENU})
        elif digit == '7':  # Cancel the message
            message.cancel()
            return render(request, 'flexml/hangup.xml', {'voice_menu': configuration.VOICE_MENU})
        elif digit == '0':  # Replay the message verification menu
            return render(request, 'flexml/verifyRecording.xml', {'message_id': message_id,
                                                                  'voice_menu': configuration.VOICE_MENU})
        else:
            return render(request, 'flexml/verifyRecording.xml', {'message_id': message_id,
                                                                  'voice_menu': configuration.VOICE_MENU,
                                                                  'reprompt': True})
    else:
        # TODO: do callback
        message.cancel()
        return render(request, 'flexml/hangup.xml')


# Message Sending Views
@csrf_exempt
def call_status_listener(request, call_id):
    logger.info(f'/call/status/{call_id}')
    logger.info("%s", request.body)

    data = json.loads(request.body)
    call_sid = data['CallSid']
    call_status = data['CallStatus']
    call_duration = data['CallDuration']

    if call_status:
        call = get_object_or_404(Call, pk=call_id)
        if call_sid is not None:
            call.sid = call_sid
        if call.status != 'added to do not call':
            call.status = call_status
        call.duration = call_duration
        call.q850 = constants.CARRIERX_CALL_STATUS_TO_Q850.get(call_status, 41)
        call.finished = dt.now()
        call.save()
        if call.message.status == "scheduled":
            call.message.status = "ongoing"
            call.message.save()
        cdr_logger.info(serialize_one(call))

    return HttpResponse(status=201)


@csrf_exempt
def call_gather(request, call_id):
    logger.info("/call/gather/%s", call_id)
    logger.info("%s", request.body)

    data = json.loads(request.body)
    digits = data['Digits']
    callee_number = data['OriginalTo']
    call = Call.objects.get(pk=call_id)

    logger.info(f'digits {digits}')
    if digits:
        if digits == '0':
            return render(request, 'flexml/playRecordingForCall.xml', {
                'recording_url': call.message.recording.url,
                'wait_for_silence': False,
                'play_twice': False,
                'call_id': call_id})
        elif digits == '5':
            DoNotCallNumber.objects.create(number=callee_number, user_data=call.message.user_data)
            logger.info(f'User requested to be added to the DNC: {call.to_number}, {call.message.user_data}')
            call.status = 'added to do not call'
            call.save()
            return render(request, 'flexml/hangup.xml')
        else:
            # TODO: switch to hang up when we can set the digits allowed in the menu
            #return render(request, 'flexml/hangup.xml')
            return render(request, 'flexml/playRecordingForCall.xml', {
                'recording_url': call.message.recording.url,
                'wait_for_silence': False,
                'play_twice': False,
                'call_id': call_id})
    else:
        return render(request, 'flexml/hangup.xml')


@csrf_exempt
def message_recording_status(request, message_id):
    logger.info(f'/message/recording/status/{message_id}')
    rec_cdr = request.body.decode("utf-8")
    logger.info("Message recording finished with -> %s", rec_cdr)

    data = json.loads(request.body)
    call_status = data['CallStatus']

    message = get_object_or_404(Message, pk=message_id)
    if message.recording.sid and message.recording.is_confirmed and call_status == "completed":
        message.confirm()
    else:
        message.cancel()
    rec_cdr_logger.info(rec_cdr[:-1] + f', "message_id": "{message_id}", "finished": "{dt.now(timezone.utc)}"' + "}")
    return HttpResponse(201)


@csrf_exempt
def message_send(request, call_id):
    logger.info(f'/message/send/{call_id}')
    template_context = {
        'call_id': call_id,
        'initial_silence': configuration.AMD_INITIAL_SILENCE,
        'greeting': configuration.AMD_GREETING,
        'after_greeting_silence': configuration.AMD_AFTER_GREETING_SILENCE,
        'total_analysis_time': configuration.AMD_TOTAL_ANALYSIS_TIME,
        'container_sid': configuration.DEBUG_RECORDING_CONTAINER,
        'record_call': configuration.RECORD_ALL_CALLS
    }

    return render(request, 'flexml/amdForCall.xml', template_context)


@csrf_exempt
def amd(request, call_id):
    logger.info(f'/message/amd/{call_id}')
    data = json.loads(request.body)
    logger.info("%s", data)

    amd_status = data.get('AMDStatus', 'UNK')
    wait_for_silence = amd_status == "MACHINE"
    play_twice = amd_status == "NOTSURE"

    call = get_object_or_404(Call, pk=call_id)
    call.q850 = constants.AMD_TO_Q850.get(amd_status, 0)
    call.save()

    return render(request, 'flexml/playRecordingForCall.xml', {'recording_url': call.message.recording.url,
                                                               'wait_for_silence': wait_for_silence,
                                                               'play_twice': play_twice,
                                                               'call_id': call_id})
