FROM python:3.7-slim
WORKDIR /app

COPY . /app
RUN pip install -e ".[dev,test]"

ENTRYPOINT ["/bin/bash", "/app/run.sh"]
CMD ["main"]
