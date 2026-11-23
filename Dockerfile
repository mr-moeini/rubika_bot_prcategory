FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 STATE_FILE=/data/state.json
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot ./bot
COPY fonts ./fonts
VOLUME /data
CMD ["python", "-m", "bot.main"]
