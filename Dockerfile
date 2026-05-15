FROM python:3.13-slim

WORKDIR /app

RUN pip install uv --quiet

COPY pyproject.toml .
RUN uv sync --no-dev --quiet

COPY src/ src/
COPY main.py .

RUN uv sync --no-dev --quiet

EXPOSE 8000

CMD ["uv", "run", "bot"]
