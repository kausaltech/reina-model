#!/bin/sh

cd /app

# Log to stdout
exec gunicorn --access-logfile - -R -w 4 --bind 0.0.0.0:5000 graphql_backend:app 
