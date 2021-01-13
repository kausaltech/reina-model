#!/bin/sh

cd /app

# Download updated mobility dataset
python -m data_import.google_covid_mobility

# Log to stdout
exec gunicorn --access-logfile - -R -w 4 --bind 0.0.0.0:5000 graphql_backend:app 
