from django.urls import path

from . import views

urlpatterns = [
    path('call/status/<int:call_id>', views.call_status_listener, name='status'),
    path('call/instructions/<int:message_id>', views.instructions, name='instructions'),
    path('call/gather/<int:call_id>', views.call_gather, name='call-gather'),
    path('record/gather/<int:message_id>', views.record_gather, name='record-gather'),
    path('record/error/<int:message_id>', views.record_error, name='record-error'),
    path('record/verify/<int:message_id>', views.record_verify, name='record-verify'),
    path('record/status/<int:message_id>', views.record_status, name='record-status'),
    path('verify/gather/<int:message_id>', views.verify_gather, name='verify-gather'),
    path('message/amd/<int:call_id>', views.amd, name='message-amd'),
    path('message/send/<int:call_id>', views.message_send, name='message-send'),
    path('message/status/<int:message_id>', views.message_status, name='message-status'),
    path('message/recording/status/<int:message_id>', views.message_recording_status, name='message-recording-status'),
]
