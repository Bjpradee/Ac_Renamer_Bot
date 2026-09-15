FROM python:3.10-slim

# System-la FFmpeg & FFprobe-a force panna install panrom
RUN apt-get update && apt-get install -y ffmpeg libavcodec-extra

WORKDIR /app

# Requirements file-a copy panni dependencies install panrom
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Matra ellam files-ayum ulla copy panrom
COPY . .

# Bot-a start panrom
CMD ["python", "bot.py"]
