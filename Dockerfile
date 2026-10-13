FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && pip check

COPY src/ ./src/
COPY tests/ ./tests/
COPY dbt/dbt_project.yml ./dbt/dbt_project.yml
COPY dbt/models/ ./dbt/models/
COPY dbt/tests/ ./dbt/tests/
COPY config/*_schema.json ./config/
COPY config/profiles.example.yml ./config/profiles.example.yml
RUN mkdir -p data logs

ENTRYPOINT ["python"]
CMD ["src/run_batch.py", "--help"]
