FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Placed after COPY so a new commit does not bust the pip layer.
ARG GIT_COMMIT=unknown
ARG DEPLOYED_AT=unknown
ENV GIT_COMMIT=${GIT_COMMIT}
ENV DEPLOYED_AT=${DEPLOYED_AT}

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
