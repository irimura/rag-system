FROM python:3.11-slim

WORKDIR /app

# CPU 版 PyTorch を先に入れる(既定の CUDA 版は数 GB 大きい)
RUN pip install --no-cache-dir "torch~=2.7.0" --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common.py app.py ingest.py ./

EXPOSE 8000
CMD ["chainlit", "run", "app.py", "--headless", "--host", "0.0.0.0", "--port", "8000"]
