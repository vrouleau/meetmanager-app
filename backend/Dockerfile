FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY template.mdb /app/template.mdb
ENV TEMPLATE_MDB=/app/template.mdb
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
