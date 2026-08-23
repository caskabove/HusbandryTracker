FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY db/ db/
COPY web/ web/
COPY collectors/ collectors/

EXPOSE 22255

CMD ["uvicorn", "web.main:app", "--host", "0.0.0.0", "--port", "22255"]
