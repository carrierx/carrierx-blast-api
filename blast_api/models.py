import logging
from datetime import datetime, timezone, timedelta
import time
import requests
import re
from django.db import models, connection

from blast_api_project.utils import serialize_one, DjangoStatusArchiver
from blast_api_project import configuration, utils
from callcontrol import constants

# Get an instance of a logger
logger = logging.getLogger(__name__)

cdr_logger = logging.getLogger('cdr_logger')
bdr_logger = logging.getLogger('bdr_logger')


class Recording(models.Model):
    name = models.CharField(max_length=200, null=True)
    sid = models.CharField(max_length=200, null=True)
    duration = models.IntegerField(default=0, null=True)
    url = models.CharField(max_length=200, null=True)
    created = models.DateTimeField(auto_now_add=True)

    def confirm(self):
        response = requests.patch(url=f'{configuration.BASE_CARRIERX_API_URL}/core/v2/storage/files/{self.sid}',
                                  json={"lifecycle_ttl": -1},
                                  headers = {"Authorization": f"Bearer {configuration.CARRIERX_API_TOKEN}"})
        if response.status_code == 200:
            logger.info("Recording with sid '%s' was confirmed\nCarrierX API responded with %s", self.sid, response.content)
        else:
            raise utils.CarrierXError("CarrierX responded with status code %s", response.status_code)

    @property
    def is_confirmed(self):
        response = requests.get(url=f'{configuration.BASE_CARRIERX_API_URL}/core/v2/storage/files/{self.sid}',
                                headers = {"Authorization": f"Bearer {configuration.CARRIERX_API_TOKEN}"})
        is_confirmed = dict(response.json()).get("lifecycle_ttl") == -1
        logger.info(f"Recording with sid '%s' is confirmed: {is_confirmed}\nCarrierX API responded with %s",
                    self.sid, response.content)
        return is_confirmed

    def delete(self, using=None, keep_parents=False):
        if self.sid:
            response = requests.delete(url=f'{configuration.BASE_CARRIERX_API_URL}/core/v2/storage/files/{self.sid}',
                                       headers = {"Authorization": f"Bearer {configuration.CARRIERX_API_TOKEN}"})
            logger.info("Recording with sid '%s' was successfully deleted\nCarrierX API responded with %s",
                        self.sid,
                        response.status_code)
        return super().delete(using, keep_parents)

    def __str__(self):
        if self.name:
            return self.name
        return self.created.strftime("%Y-%m-%d %H:%M:%S")


REC_CALL_STATUSES = DjangoStatusArchiver(
    ("NO_REC_CALL",
     "PLACED",
     "USER_ANSWERED",
     "PRESSED_STAR",
     "RECORDED",
     "CONFIRMED",
     "CARRIERX_ERROR")
)


class Message(models.Model):
    title = models.CharField(max_length=200, null=True)
    user_data = models.CharField(max_length=250, blank=False, null=False)
    recording = models.ForeignKey(Recording, null=True, on_delete=models.SET_NULL)
    schedule = models.DateTimeField(null=True)
    status = models.CharField(max_length=200, null=True, default="pending")
    created = models.DateTimeField(auto_now_add=True)
    caller = models.CharField(max_length=16, null=False)
    started = models.DateTimeField(auto_now_add=False, null=True)
    finished = models.DateTimeField(auto_now_add=False, null=True)
    recording_call_status = models.PositiveSmallIntegerField(choices=REC_CALL_STATUSES.choices,
                                                             default=REC_CALL_STATUSES.NO_REC_CALL)
    rec_call_status_updated_at = models.DateTimeField(auto_now_add=False, null=True)

    def update_rec_call_status(self, status):
        self.recording_call_status = getattr(REC_CALL_STATUSES, status)
        self.rec_call_status_updated_at = datetime.now(timezone.utc)
        self.save()

    def cancel(self):
        if not (self.status == 'canceled' or self.status == 'error'):
            for call in self.call_set.all():
                call.cancel()
            self.status = 'canceled'
            self.save()
            logging.info("Blast %i was cancelled", self.id)
            bdr_logger.info(serialize_one(self))
        else:
            logger.warning(f"The blast {self.pk} has already been canceled.")

    def cancel_with_error(self):
        for call in self.call_set.all():
            call.cancel()
        self.status = 'error'
        self.save()
        logging.error("Blast %i had unrecoverable error", self.id)
        bdr_logger.info(serialize_one(self))

    def place_calls(self):
        if not self.schedule:
            self.status = "ongoing"
            self.started = datetime.now(timezone.utc)
        else:
            self.status = "scheduled"
            self.started = self.schedule
        self.save()

        recording_length = self.recording.duration
        call_offset = 0
        count = 1
        for call in self.call_set.filter(status="ready"):
            call.start(call_offset)
            count += 1
            if count % configuration.CALL_BATCH_SIZE == 0:
                call_offset += recording_length
            if count % configuration.MAX_CALLS_PER_SECOND == 0:
                time.sleep(1)

    def record(self):
        self.recording = Recording.objects.create()
        self.save()
        data = {
            "calling_did": configuration.DID,
            "called_did": self.caller,
            "url": f"{configuration.BASE_CALLCONTROL_API_URL}/call/instructions/{self.id}",
            "status_callback_url": f"{configuration.BASE_CALLCONTROL_API_URL}/message/recording/status/{self.id}"
        }

        response = requests.post(f'{configuration.BASE_CARRIERX_API_URL}/flexml/v1/calls',
                                 json=data,
                                 auth=(configuration.FLEXML_API_USER, configuration.FLEXML_API_PASSWORD))
        logger.info('Calling the user to record their message %s -> %s', configuration.BASE_CARRIERX_API_URL,
                    response.json())
        if response.status_code != 200:
            self.update_rec_call_status("CARRIERX_ERROR")
            self.cancel_with_error()
            return
        self.update_rec_call_status("PLACED")
        connection.close()

    def check_timeout(self) -> bool:
        """
        Checks if the message recording call is stuck in one state for too long and if it is, it sets the message status to 'timed-out'
        and returns True, else it returns False.
        :return:
        """
        raw_status = self.recording_call_status
        rec_call_status = REC_CALL_STATUSES.map[raw_status]
        raw_time_out = configuration.REC_CALL_STATUS_TIMEOUTS[rec_call_status]
        if raw_time_out:
            max_time = timedelta(seconds=float(raw_time_out))
            if datetime.now(timezone.utc) - self.rec_call_status_updated_at > max_time:
                self.status = "timed-out"
                logger.warning("The message with id %i has been timed out with rec_call_status '%s'", self.id,
                               rec_call_status)
                self.save()
                return True
        return False

    def confirm(self):
        self.call_set.filter(~models.Q(status="do not call")).update(status="ready")
        if len(self.call_set.filter(status="ready")):
            self.status = "ready"
            logging.info("Blast %i calls were set ready", self.id)
        else:
            self.status = "canceled"
            logger.info(f"The blast {self.id} was canceled due to its having no callable recipients.")
        self.save()

    @property
    def recipients_requested_dnc(self) -> bool:
        return bool(len(self.call_set.filter(status="added to do not call")))

    def __str__(self):
        return f'{self.recording} - {self.status}'


class Call(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE)
    to_number = models.CharField(max_length=200, blank=True)
    sid = models.CharField(max_length=200, blank=True)
    duration = models.IntegerField(default=0, blank=True)
    status = models.CharField(max_length=200, default='pending')
    created = models.DateTimeField(auto_now_add=True)
    started = models.DateTimeField(auto_now_add=False, null=True)
    finished = models.DateTimeField(auto_now_add=False, null=True)
    q850 = models.IntegerField(default=0)
    num_retries = models.IntegerField(default=0)

    valid_number_pattern = re.compile(configuration.VALID_NUMBER_PATTERN)

    def number_is_valid(self):
        return self.valid_number_pattern.match(f'{self.to_number}') is not None

    def cancel(self):
        if self.status not in ("completed", "failed", "no-answer", "cancelled"):
            if self.sid:
                logger.info('Canceling call %s', self.sid)
                response = requests.delete(url=f'{configuration.BASE_CARRIERX_API_URL}/flexml/v1/calls/{self.sid}',
                                           auth=(configuration.FLEXML_API_USER, configuration.FLEXML_API_PASSWORD))
                logger.info(response.content)
            self.status = "cancelled"
            self.save()
        else:
            logger.warning('The call %i has already reached its terminal state, cannot cancel', self.id)

    def start(self, offset=0, retry=False):
        if self.number_is_valid():
            if retry:
                self.status = "ready"
            if self.status != "ready":
                logging.error(f"This call {self.id} cannot be started because it is not ready")
                return
            delay = 0
            status = 'ongoing'
            if self.message.schedule or retry:
                now = datetime.now(timezone.utc)
                if self.message.schedule:
                    calculated_delay = (self.message.schedule - now).total_seconds() + offset
                else:
                    calculated_delay = offset
                if calculated_delay > 0:
                    delay = calculated_delay
                    logger.info('Scheduling call in %is', delay)
                    status = 'pending'

            calling_did = self.message.caller
            called_did = self.to_number
            if calling_did == called_did:
                calling_did, called_did = configuration.DID, calling_did
            data = {
                "calling_did": calling_did,
                "called_did": called_did,
                "delay": delay if delay > 0 else offset,
                "url": f'{configuration.BASE_CALLCONTROL_API_URL}/message/send/{self.pk}',
                'status_callback_url': f'{configuration.BASE_CALLCONTROL_API_URL}/call/status/{self.pk}'
            }
            self.status = status

            logger.info('Posting this call to CarrierX %s "%s"', configuration.BASE_CARRIERX_API_URL, data)
            if self.message.schedule:
                self.started = self.message.schedule + timedelta(seconds=offset)
            else:
                self.started = datetime.now(timezone.utc) + timedelta(seconds=offset)

            response = requests.post(url=f'{configuration.BASE_CARRIERX_API_URL}/flexml/v1/calls',
                                    json=data,
                                    auth=(configuration.FLEXML_API_USER, configuration.FLEXML_API_PASSWORD))
            logger.info("Calling -> %s", response.json())
            response_dict = dict(response.json())
            errors = response_dict.get("errors")
            if errors:
                self.status = "failed"
                cdr_logger.info(serialize_one(self))
                logging.error(f"This call could not be placed: {errors}")
            else:
                self.sid = response_dict.get("call_sid")
        else:
            self.status = "failed"
            self.started = datetime.now(timezone.utc)
            self.finished = datetime.now(timezone.utc)
            self.q850 = constants.CARRIERX_CALL_STATUS_TO_Q850.get('invalid-number', 1)

            cdr_logger.info(serialize_one(self))

        self.save()

    def retry(self, offset=0):
        if self.status != 'failed' or not self.number_is_valid():
            logger.info(f"The call with id={self.id} status is not 'failed' or the number is invalid, skipping")
            return
        if self.num_retries == configuration.MAX_RETRIES:
            self.status = 'failed'
            self.save()
            logger.info(f"The call with id={self.id} reached maximum number of retries, skipping")
            return
        self.num_retries += 1
        self.save()
        self.start(offset=offset, retry=True)



class DoNotCallNumber(models.Model):
    number = models.CharField(max_length=200)
    user_data = models.CharField(max_length=250, blank=False, null=False)
