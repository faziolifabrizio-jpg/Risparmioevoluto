FROM python:3.11

# Serve per far funzionare chromium headless
RUN apt-get update && apt-get install -y wget gnupg ca-certificates \
    libnss3 libatk1.0-0 libcups2 libxcomposite1 libxrandr2 libxdamage1 \
    libpango-1.0-0 libcairo2 libasound2 libatspi2.0-0 libcurl4 \
    libxkbcommon0 libxshmfence1 libgbm1 libgtk-3-0 libdbus-1-3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# ⚠️ installiamo chromium headless APPOSTA per railway
RUN playwright install chromium

COPY . .

CMD ["python", "bot.py"]
