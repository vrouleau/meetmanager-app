FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY template_struct.json /app/template_struct.json
ENV TEMPLATE_JSON=/app/template_struct.json
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
