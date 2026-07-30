# Node A-3 vLLM 設定

Node A-3(16bit 非量子化・最大 32k)のノード別設定です。実行時は [node-a/docker-compose.yml](../node-a/docker-compose.yml)を共通利用し、本ディレクトリの `.env.example` を `.env` として指定します。

```bash
cp -v .env.example .env
docker compose --env-file .env -f ../node-a/docker-compose.yml up -d
```

venv + systemd 方式では [node-a/vllm.service](../node-a/vllm.service)をベースに、`--max-model-len 32768`と`--gpu-memory-utilization 0.90`を設定します。単一 A100/H100 80GB 案は`--tensor-parallel-size 1`、2×L40S 案を採用した場合のみ`--tensor-parallel-size 2`とします。
