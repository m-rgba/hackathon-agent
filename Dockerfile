FROM python:3.12-slim

WORKDIR /ops

# Install Docker and inotify-tools
RUN apt-get update && \
    apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    inotify-tools && \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && \
    echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \
    $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null && \
    apt-get update && \
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin && \
    rm -rf /var/lib/apt/lists/* # Clean up to reduce image size

# Copy files
COPY ./requirements.txt /ops/requirements.txt
COPY ./app /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create and copy the watch script
COPY ./watch.sh watch.sh
RUN chmod +x watch.sh

# Create entrypoint script
COPY ./entrypoint.sh entrypoint.sh
RUN chmod +x entrypoint.sh

WORKDIR /app

ENTRYPOINT ["/ops/entrypoint.sh"]
