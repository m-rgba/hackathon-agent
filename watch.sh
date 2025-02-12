#!/bin/bash
while inotifywait -e modify,create,delete -r /app --include '.*\.(html|css)$'; do
    touch /app/app.py
done 