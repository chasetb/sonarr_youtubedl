FROM python:3.12
LABEL maintainer="Martin Jones <whatdaybob@outlook.com>"

# Update packages, install ffmpeg, and upgrade pip
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    pip install --upgrade pip && \
    rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

# Create a non-root user (abc) and necessary directories
RUN groupmod -g 1000 users && \
    useradd -u 911 -U -d /config -s /bin/false abc && \
    usermod -G users abc && \
    mkdir -p /config /app /sonarr_root /logs && \
    touch /var/lock/sonarr_youtube.lock && \
    chown -R abc:users /config /app /sonarr_root /logs

# Set volumes
VOLUME /config
VOLUME /sonarr_root
VOLUME /logs

# Copy application files
COPY app/ /app

# Update file permissions
RUN chmod a+x /app/sonarr_youtubedl.py /app/utils.py /app/config.yml.template

# Set environment variables
ENV CONFIGPATH=/config/config.yml

# Switch to the non-root user
USER abc

# Set the default command
CMD [ "python", "-u", "/app/sonarr_youtubedl.py" ]
