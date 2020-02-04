import json
import logging
from types import TracebackType
from typing import Optional

from django.core import serializers


def setup_logger(name, log_file, level=logging.INFO, formatter=logging.Formatter('%(msg)s')):
    """Function setup as many loggers as you want"""
    handler = logging.FileHandler(log_file)
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)
    return logger


def serialize_one(django_model_instance):
    fields = json.dumps(json.loads(serializers.serialize("json", [django_model_instance])[1: -1])["fields"])
    pk = django_model_instance.id
    return fields[:-1] + f', "pk": {pk}' + "}"


class CarrierXError(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

    def with_traceback(self, tb: Optional[TracebackType]) -> BaseException:
        return super().with_traceback(tb)


class DjangoStatusArchiver(object):
    def __init__(self, statuses):
        self.choices = list(enumerate(statuses))
        self.map = dict(self.choices)

    def __getattr__(self, item):
        try:
            value = next(key for key, value in self.map.items() if value == item)
        except StopIteration:
            value = None
        return value
