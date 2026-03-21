FROM python:3.12-slim

RUN apt-get update && apt-get install -y git curl sudo \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Claude Code
RUN npm install -g @anthropic-ai/claude-code

# Non-root user
RUN useradd -m -s /bin/bash claude && \
    echo "claude ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Install pleng CLI tool globally
RUN pip install -e /app/tools

# Setup workspace
RUN mkdir -p /projects && chown -R claude:claude /projects && \
    mkdir -p /home/claude/.claude && chown -R claude:claude /home/claude

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
CMD ["/entrypoint.sh"]
