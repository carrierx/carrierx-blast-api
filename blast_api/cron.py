from django_cron import CronJobBase, Schedule
from django.db.models import Q, Count
from itertools import chain

from blast_api_project.utils import serialize_one
from .models import Message, Call
from blast_api_project.configuration import MESSAGE_TIMEOUT, MAX_RETRIES, MAX_CALLS_PER_SECOND, CALL_BATCH_SIZE, CALL_LENGTH_RATIO, MESSAGE_TIMEOUT_CHECK_WINDOW
import logging
from datetime import datetime as dt
from datetime import timezone, timedelta
import time


bdr_logger = logging.getLogger('bdr_logger')
cdr_logger = logging.getLogger('cdr_logger')


class CheckMessageStatuses(CronJobBase):
    schedule = Schedule(run_every_mins=1)
    code = 'blast_api.check_message_statuses'  # a unique code

    def do(self):
        logging.info("Checking shout statuses...")
        messages = Message.objects \
            .filter(status='ongoing') \
            .annotate(num_unfinished_calls=Count('call', filter=Q(call__status__in=["ongoing", "ready"]) | (Q(call__num_retries__lt=MAX_RETRIES) & Q(call__status='failed'))))
        logging.info("There is/are %i ongoing message(s)", len(messages))
        for message in messages:
            logging.info("Message id: %i", message.id)
            message_timeout = (message.call_set.count() / CALL_BATCH_SIZE) * message.recording.duration * CALL_LENGTH_RATIO + MESSAGE_TIMEOUT
            if not message.num_unfinished_calls:
                logging.info("Either all the calls finished or no calls finished at all")
                message.status = 'finished'
                try:
                    message.finished = message.call_set.filter(finished__isnull=False).latest('finished').finished
                except Call.DoesNotExist:
                    logging.error(f"No calls have been finished")
                    message.finished = dt.now(timezone.utc)
                message.save()
                logging.info("finished")
                bdr_logger.info(serialize_one(message))
            elif dt.now(timezone.utc) - message.started > timedelta(seconds=float(message_timeout)):
                logging.info(f"timed out with {message.num_unfinished_calls} of {message.call_set.count()} calls unfinished")
                message.status = 'timed-out'
                ongoing_calls = message.call_set.filter(status="ongoing")
                ongoing_calls.update(status="timed-out")
                for call in ongoing_calls:
                    cdr_logger.info(serialize_one(call))
                message.save()
                bdr_logger.info(serialize_one(message))
            else:
                logging.info("still ongoing")

        logging.info("Checking for messages, that are pending, but do not have a recording")
        for message in Message.objects.filter(status="pending", recording__sid__isnull=True):
            if message.check_timeout():
                bdr_logger.info(serialize_one(message))

        logging.info("Checking to see if messages that previously timed out eventually completed...")
        timeout_experation = dt.now(timezone.utc) - timedelta(hours = MESSAGE_TIMEOUT_CHECK_WINDOW)
        messages = Message.objects \
            .filter(status='timed-out', started__gte=timeout_experation) \
            .annotate(num_unfinished_calls=Count('call', filter=Q(call__status__in=["ongoing", "ready", "pending", "timed-out"])))
        logging.info("There is/are %i timed-out message(s)", len(messages))
        for message in messages:
            logging.info("Timed-out message id: %i with %i unfinished calls", message.id, message.num_unfinished_calls)
            if not message.num_unfinished_calls:
                logging.info(f"All calls completed by {dt.now(timezone.utc)}")
                message.status = 'finished'
                try:
                    message.finished = message.call_set.filter(finished__isnull=False).latest('finished').finished
                except Call.DoesNotExist:
                    logging.error(f"No calls have been finished")
                    message.finished = dt.now(timezone.utc)
                message.save()
                logging.info("finished")
                bdr_logger.info(serialize_one(message))

        logging.info("End.")


class PlaceCalls(CronJobBase):
    schedule = Schedule(run_every_mins=1)
    code = 'blast_api.place_calls'

    def do(self):
        logging.info("Checking for ready messages")
        ready_messages = Message.objects.filter(status="ready")
        for message in ready_messages:
            message.place_calls()
            logging.info("Message %i was posted.", message.id)


class Retry(CronJobBase):
    schedule = Schedule(run_every_mins=1)
    code = 'blast_api.retry'

    def do(self):
        logging.info("Looking for failed calls")
        ongoing_messages = Message.objects \
            .filter(status='ongoing') \
            .annotate(num_unanswered_calls=Count('call', filter=Q(call__status="failed")))

        placed_count = 0
        for message in ongoing_messages:
            if message.num_unanswered_calls:
                recording_length = message.recording.duration
                call_offset = 0
                for call in message.call_set.filter(num_retries__lte=MAX_RETRIES, status='failed'):
                    call.retry(call_offset)
                    placed_count += 1
                    if placed_count % CALL_BATCH_SIZE == 0:
                        call_offset += recording_length
                    if placed_count % MAX_CALLS_PER_SECOND == 0:
                        time.sleep(1)
