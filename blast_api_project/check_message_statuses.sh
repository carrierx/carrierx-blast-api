#!/usr/bin/env bash
export DJANGO_SETTINGS_MODULE=blast_api_project.settings.prod
source /opt/blast-api/env/bin/activate
python /opt/blast-api/manage.py runcrons