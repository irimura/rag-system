# perf-001 セットアップ手順

> コマンド中の `${...}` は環境に合わせて置換してください。

[AWS インフラ構築手順](../02-provisioning/aws-provisioning.md)で perf-001 を起動し、NAT を一時的に有効化してから実施します。

## 1. EICE 経由でログイン

管理者端末の `~/.ssh/config` に `ragsys-perf-001` が登録済みであることを確認し、接続します。

```bash
ssh ragsys-perf-001
```

## 2. Python 仮想環境と Locust の導入

Locust は 2026-07-29 時点の最新安定版 `2.44.4` に固定します。

```bash
sudo apt-get update && sudo apt-get install -y python3-venv
python3 -m venv ${HOME}/locust-venv
source ${HOME}/locust-venv/bin/activate
pip install locust==2.44.4
```

## 3. locustfile.py の配置

管理者端末で、リポジトリのルートから実行します。

```bash
scp 07-performance/locustfile.py 'ragsys-perf-001:${HOME}/locustfile.py'
```

## 4. 確認

perf-001 で実行します。

```bash
source ${HOME}/locust-venv/bin/activate && locust --version
```
