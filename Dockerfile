# Python 3.10 OS ulla kondu varom
FROM python:3.10-slim

# Railway-a force panni FFmpeg install panna vaikkurom! 🔥
RUN apt-get update && apt-get install -y ffmpeg

# Namma code-kaga oru folder create panrom
WORKDIR /app

# Requirements install panrom
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Namma bot files ellathayum ulla anuppurom
COPY . .

# Bot-a start panrom
CMD ["python", "bot.py"]
