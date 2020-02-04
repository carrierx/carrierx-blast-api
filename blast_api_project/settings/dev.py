from .base import *

ALLOWED_HOSTS = ["*"]

DEBUG = True

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    },
}
SECRET_KEY = '!stq@eu*thpw0*ou@9x5x_js&zts=8vwqo*hgy8&n%k6_vax#*'

BDR_LOG_PATH = 'bdr.log'
CDR_LOG_PATH = 'cdr.log'
REC_CDR_LOG_PATH = 'rec_cdr.log'

LOGGING["handlers"].update({
    'cdr_file': {
        'level': 'INFO',
        'class': 'logging.handlers.WatchedFileHandler',
        'filename': CDR_LOG_PATH,
    },
    'bdr_file': {
        'level': 'INFO',
        'class': 'logging.handlers.WatchedFileHandler',
        'filename': BDR_LOG_PATH,
    },
    'rec_cdr_file': {
        'level': 'INFO',
        'class': 'logging.handlers.WatchedFileHandler',
        'filename': REC_CDR_LOG_PATH,
    }
})
