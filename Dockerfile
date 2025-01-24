FROM python:3.12-slim
LABEL maintainer="Martin Jones <whatdaybob@outlook.com>"

# Set volumes
VOLUME /config
VOLUME /sonarr_root
VOLUME /logs

# Set environment variables
ENV APP_HOME=/app \
    CONFIG_DIR=/config \
    SONARR_ROOT=/sonarr_root \
    LOGS_DIR=/logs \
    CONFIGPATH=/config/config.yml

# Update packages, install ffmpeg, and upgrade pip
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    pip install uv && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user (abc) and necessary directories
RUN groupmod -g 100 users && \
    useradd -u 1000 -U -d /config -s /bin/false abc && \
    usermod -G users abc && \
    mkdir -p $CONFIG_DIR $APP_HOME $SONARR_ROOT $LOGS_DIR && \
    touch /var/lock/sonarr_youtube.lock && \
    chown -R abc:users $CONFIG_DIR $APP_HOME $SONARR_ROOT $LOGS_DIR

# Set work directory
WORKDIR $APP_HOME

# Copy uv project files
COPY pyproject.toml .
COPY uv.lock .

# Install dependencies using uv
RUN uv sync --frozen --no-install-project --no-editable

# Copy application code
COPY app/ .

# Update file permissions
RUN chmod a+x $APP_HOME/sonarr_youtubedl.py $APP_HOME/utils.py $APP_HOME/config.yml.template

# Switch to the non-root user
USER abc

# Set the default command
CMD [ "uv", "run", "/app/sonarr_youtubedl.py" ]
