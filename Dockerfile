FROM python:3.11-slim

# Install cron
RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY BoursoBankScrap.py /app/script.py

# Default env variables (can be overridden at runtime)
ENV PARAM1=true \
    PARAM2=11111111 \
    PARAM3=12345678 \
    PARAM4=fake_account \
    CRON_SCHEDULE="0 2 * * *"

# dependencies:
COPY requirements.txt .
RUN pip install -r requirements.txt

# Create an entrypoint script that writes the cron job dynamically
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Run cron in foreground via entrypoint
CMD ["/entrypoint.sh"]
