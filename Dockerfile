FROM python:3.11

# install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libxdamage1 \
    libxcomposite1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libxshmfence1 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libxcursor1 \
    libxfixes3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# install python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# install playwright browsers
RUN playwright install --with-deps chromium

COPY . .

CMD ["python", "server.py"]
