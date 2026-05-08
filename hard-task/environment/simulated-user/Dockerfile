FROM python:3.12-slim

WORKDIR /simulated-user

RUN pip install --no-cache-dir tyro==1.0.13

COPY worker.py simulated_user_instruction.md /simulated-user/

CMD ["python3", "/simulated-user/worker.py"]
