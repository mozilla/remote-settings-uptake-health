FROM python:3.7-slim
WORKDIR /app

COPY ./main.py /app/main.py
COPY ./setup.py /app/setup.py
COPY ./README.md /app/README.md
RUN pip install -e ".[dev]"

ENTRYPOINT ["python", "main.py"]
CMD []
