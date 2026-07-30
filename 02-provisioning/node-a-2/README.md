# Node A-2 vLLM 設定

Node A-2(GPTQ 8bit・最大 16k)のノード別設定です。実行時は [node-a/docker-compose.yml](../node-a/docker-compose.yml)を共通利用し、本ディレクトリの `.env.example` を `.env` として指定します。

```bash
cp -v .env.example .env
docker compose --env-file .env -f ../node-a/docker-compose.yml up -d
```

venv + systemd 方式では [node-a/vllm.service](../node-a/vllm.service)をベースに、`--max-model-len 16384`、`--gpu-memory-utilization 0.90`、`--tensor-parallel-size 1`を設定します。
