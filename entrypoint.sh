#!/bin/sh
set -e

# Write the cron job using env vars
echo "$CRON_SCHEDULE /bin/sh -c 'cd /app && /usr/local/bin/python script.py \"$PARAM1\" \"$PARAM2\" \"$PARAM3\" \"$PARAM4\" >> /var/log/cron.log 2>&1'" > /etc/cron.d/my-cron

# Apply cron job
crontab /etc/cron.d/my-cron

# Ensure log file exists
touch /var/log/cron.log

echo "✅ Cron job installed: $CRON_SCHEDULE python script.py $PARAM1 $PARAM2 $PARAM3 $PARAM4"

# Start cron in foreground
cron -f
