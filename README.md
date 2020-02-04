# blast-api

# Setup
_This assumes Python 3.X is installed and setup as python, pip, etc as well as the Development tools for making uwsgi_

## System Requirements
- Python 3

**Checkout source**
```bash
git clone git@gitlab.int:carrierx/blast-api.git
cd blast-api
```

**Virtutal Env**
```bash
python -m venv env
source env/bin/activate
```

**Install Python Deps**
```bash
pip install -r requirements.txt
```

**Edit Configuration**  

For the service to function correctly you need to create the file `blast_api_project/configuration.py` from the template [configuration.py.template](blast_api_project/configuration.py.template) and fill in the values for your project. See [Configuration](#configuration) and [Required files](#required-files) below.

```bash
cp blast_api_project/configuration.py.template blast_api_project/configuration.py
```

For a production installation you will also need to create the `blast_api_project/settings/prod.py` file from the template [prod.py.template](blast_api_project/settings/prod.py.template).


**Create DB**
```bash
python manage.py makemigrations
python manage.py migrate 
```

## Required files

The blast-api service needs prerecorded audio prompts to function correctly. The files must be available on the internet for CarrierX to access when placing calls. When storing the files in CarrierX Storage, they should be placed in a separate container in your account. Edit the URLs in the `VOICE_MENU` dict in `configuration.py` to point to your prompt files. See [Installing the prompts](#installing-the-prompts).

### Installing the prompts
A set of voice prompts to use with the service has been provided in the `prompts` directory. To use them they need to be publicly accessible on the internet so that CarrierX can access them. CarrierX storage is a good way to do this. You will need a CarrierX storage container for the files, if you don;t already have one create it by going to `Storage -> Containers`, clicking `Add New Container`. See the [Storage quick start guide](https://www.carrierx.com/documentation/quick-start/flexml-storage-record#i-configure-container).

For each file to upload it to your CarrierX account.

- Select `Storage -> Files` from the menu
- Click `Add New File`
- Fill in fields
  - Name, the name of the file
  - Container Sid, the sid of the container in which to store the file
  - Publish, set to `file_access_name` to make it accessible on the internet
  - File Access Name, the name of the file in it's URL
  - Data, select the file to upload
- Click `Add File`

Once uploaded, select the file (search by name if you have many) and copy the `Publish URI` to the appropriate entry in the `VOICE_MENU` dict in `configuration.py`

## Configuration
Configuration is done via `blast_api_project/configuration.py` (_described below_) and the files in `blast_api_project/settings` for environment specific config. 

### URLS

Public URL for your service CarrierX will use to control the calls via FlexML
```py
BASE_CALLCONTROL_API_URL = f'{PROTOCOL}://{HOST}:{PORT}/api/v1/call-control'

# example
BASE_CALLCONTROL_API_URL = 'https://example.com:8000/api/v1/call-control'
```
The URL of the CarrierX API
```py
BASE_CARRIERX_API_URL = 'https://api.carrierx.com/'
```

### API credentials
Credentials used to make requests to the CarrierX API. To create a token see the [token quick start guide](https://www.carrierx.com/documentation/quick-start/token#security-token). The FlexML credentials can be found on your FlexML endpoint, see [Configure a FlexML Endpoint](https://www.carrierx.com/documentation/video-tutorials/configure-a-flexml-endpoint)
```py
CARRIERX_API_TOKEN = ''
FLEXML_API_USER = ''
FLEXML_API_PASSWORD = ''
```

### Answering Machine Detection 
For more about AMD see the [AMD documentation](https://www.carrierx.com/documentation/flexml-api#amd-experimental)  
_Values in milliseconds_
```py
AMD_INITIAL_SILENCE = "5000"
AMD_GREETING = "2000"
AMD_AFTER_GREETING_SILENCE = "500"
AMD_TOTAL_ANALYSIS_TIME = "10000"
```

### Prerecorded voice menu
See [Installing the prompts](#installing-the-prompts) for details.
```py
VOICE_MENU = {"no_key_pressed": "http://path/to/No_key_pressed.wav",
              "goodbye": "http://path/to/Goodbye.wav",
              "invalid_entry": "http://path/to/Invalid_entry.wav",
              "opt_out": "http://path/to/Opt_out.wav",
              "ready_for_delivery": "http://path/to/Ready_for_delivery.wav",
              "record_verification": "http://path/to/Record_verification.wav",
              "record_welcome": "http://path/to/Record_welcome.wav",
              "recording_cancelled": "http://path/to/Recording_cancelled.wav",
              "recording_saved": "http://path/to/Recording_saved.wav",
              "start_recording": "http://path/to/Start_recording.wav"}
```

### CarrierX phone number (DID)
The number that is used for calling the user and recipients. See [Configure a FlexML Endpoint](https://www.carrierx.com/documentation/video-tutorials/configure-a-flexml-endpoint) for how to link a number to you FlexML endpoint.
```py
DID = 'CarrierX DID to place recording calls from'
```

### Call rate throttling
Number of calls to place with the CarrierX API per second
```py
MAX_CALLS_PER_SECOND = 25
```
Number of calls to place with the same delay
```py
CALL_BATCH_SIZE = 50
```
Ratio of call duration / recording duration
```py
CALL_LENGTH_RATIO = 1.5
```
Maximum number of times to retry a failed call
```py
MAX_RETRIES = 3
```
### Timeouts
Calls (and basts) are timed out if various thresholds are exceeded to prevent stuck calls in the case of a service outage or other failure.  

Timeout in seconds for all calls for a message to complete
```py
MESSAGE_TIMEOUT = 300
```
Window in hours that the system will check messages that have timed out to see if they have completed
```py
MESSAGE_TIMEOUT_CHECK_WINDOW = 12
```
Timeouts for recording call stages (values in seconds)
```py
REC_CALL_STATUS_TIMEOUTS = {
    "NO_REC_CALL": None,
    "PLACED": 300,
    "USER_ANSWERED": 15,
    "PRESSED_STAR": 600,
    "RECORDED": 600,
    "CONFIRMED": None,
    "CARRIERX_ERROR": None
}
```

### Debug recordings
Debug recordings, enable/configure to record all calls for debugging. 
Debug recordings for a TTL of 3 days, and are automatically deleted after that by CarrierX. See the [Storage quick start guide](https://www.carrierx.com/documentation/quick-start/flexml-storage-record#i-configure-container) for how to create a container.
```py
RECORD_ALL_CALLS = False 
DEBUG_RECORDING_CONTAINER = 'CarrierX container SID for storing call recordings'
```


# Development

## Run the server
```bash
python manage.py runserver
```

## Place queued/retry failed calls
The management of calls with CarrierX is done by a cron job [cron.py](blast_api/cron.py) which is run by cron in a production installation [crontab](etc/cron.d/blast-api). While running in dev mode you can place calls by running the cron job manually
```bash
python manage.py runcrons
```

## Interactive documentation
The interactive docs for the service are available at http://localhost:8000/docs

# Production Setup

## CRON job
```bash
cp etc/cron.d/blast-api /etc/cron.d/
```

## Logrotate
```bash
cp etc/blast-api.logrotate /etc/logrotate.d
logrotate -d /etc/logrotate.d/blast-api.logrotate  //check whether logrotate was set up correctly
logrotate -d -f /etc/logrotate.d/blast-api.logrotate
```

## Systemd service
```bash
cp etc/blast-api.service /etc/systemd/system
systemctl enable blast-api
```

## Start the app
```bash
systemctl start blast-api
```

## Logstash for analytics in Elasticsearch
Edit files in `etc/logstash` to set your Elasticsearch host info then
```bash
cp etc/logstash/*  /etc/logstash/conf.d/
```

## Securing a public instance
You will want to make sure access to the interactive documentation is disabled or secured in some way. To disable it, remove the render from the Django Rest Framework configuration in [base.py](blast_api_project/settings/base.py)

```python
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    )
}
```

# API
The API has three parts, [calls](#calls), [DNC](#dnc), and [shouts](#shouts). 

## Calls
Calls are the outbound calls placed by the system when delivering a shout. They do not include the recording calls. They are created by the system when sending a shout, and can be listed by the associated shout id. Calls are represented by the `Call` class in [models.py](blast_api/models.py).

**List**
```http
GET /api/v1/calls?shout-id={shoutId}
```

See http://localhost:8000/docs/#calls

## DNC
The Do Not Call list (DNC) is a list of numbers (per user `userdata`) that have been opted to not receive shouts from the user any longer. DNC entries are created when a shout recipient presses `5` while listing to the message. They can be listed by `userdata` or deleted. DNC entries are represented by the `DoNotCallNumber` class in [models.py](blast_api/models.py).

**List**
```http
GET /api/v1/dnc/{userdata}
```

**Delete**
```http
DELETE /api/v1/dnc/{userdata}/{number}
```

See http://localhost:8000/docs/#dnc

## Shouts
Shouts are the messages sent out by the system. Each shout will have a `Call` for each recipient and `Recording` for the message the is played to them. Shouts are represented by the `Message` class in [models.py](blast_api/models.py). They can be listed by `userdata`, created, read, and canceled.

**List**
```http
GET /api/v1/shouts?userdata={userdata}
```

**Read**
```http
GET /api/v1/shouts/{shout_id}
```

**Create**
```http
POST /api/v1/shouts
```

**Cancel**
```http
DELETE /api/v1/shouts/{shout_id};cancel
```

See http://localhost:8000/docs/#shouts

## API Status Values

### Shouts (Messages)
- scheduled – this shout is set to go out at the specific time in the future
- ongoing – this shout is going out now
- finished – all calls of this shout ended
- canceled – this shout is canceled
- timed-out – this shout reached its time out
- error - something went very wrong processing this blast

### Calls
- ready - Call has been processed, but not yet submitted to CarrierX
- pending - Call has been submitted to CarrierX but has not yet been placed
- completed	- Call was success full
- no-answer	- The call rang with no connection being made
- failed - An error occurred when placing the call. Usually this is an invalid number  
- busy - Busy signal received when placing the call
- app-error - The API server had an error while processing the call with CarrierX. Typically this is a crash on the API server
- added to do not call - Call was successful and the user opted to be added to the Do Not Call list for this customer 

# Logging
The system creates five different logs.

- **blast-api.log** The main log from Django
- **blast-api-message-check.log** Logs from the cron jobs, placing calls, checking message status
- **cdr.log** Call Detail Records for the calls configured by `CDR_LOGGER_PATH`
- **bdr.log** Detail Records for the shouts configured by `BDR_LOG_PATH`
- **rec_cdr.log** Recording Call Detail Records for the recording calls configured by `REC_CDR_LOG_PATH`


# Operational analysis

## jq for log processing

Sum the total minutes of use in a cdr log file.
```bash
zcat cdr.log-20190909.gz | jq -s 'map(.duration) | add' | xargs -I{} expr {} / 60
```