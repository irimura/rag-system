"""OpenSearch のサービスユーザー、グループ別 DLS role/user を冪等作成する。"""
import json
import os
import time

from opensearchpy.exceptions import OpenSearchException

from auth import derive_group_password, load_group_config
from opensearch_client import build_opensearch_client

INDEX = os.getenv("OS_INDEX", "knowledge")
TIMEOUT_SECONDS = 180


def put(client, path: str, body: dict) -> None:
    client.transport.perform_request("PUT", path, body=body)


def main() -> None:
    admin = build_opensearch_client()
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while True:
        try:
            if admin.cluster.health().get("status") in {"green", "yellow"}:
                break
        except OpenSearchException as exc:
            if time.monotonic() >= deadline:
                raise SystemExit(f"OpenSearch の起動待ちがタイムアウトしました: {exc}") from exc
        if time.monotonic() >= deadline:
            raise SystemExit("OpenSearch の起動待ちがタイムアウトしました")
        time.sleep(5)

    put(admin, "/_plugins/_security/api/roles/rag_reader", {
        "cluster_permissions": ["cluster_monitor"],
        "index_permissions": [{
            "index_patterns": [INDEX],
            "allowed_actions": ["read", "indices:admin/get"],
        }],
    })
    put(admin, "/_plugins/_security/api/roles/rag_ingest", {
        "cluster_permissions": ["cluster_monitor"],
        "index_permissions": [{
            "index_patterns": [INDEX],
            "allowed_actions": ["indices_all"],
        }],
    })
    put(admin, "/_plugins/_security/api/internalusers/rag_api", {
        "password": os.environ["OS_RAG_PASSWORD"],
        "opendistro_security_roles": ["rag_reader"],
    })
    put(admin, "/_plugins/_security/api/internalusers/ingest", {
        "password": os.environ["OS_INGEST_PASSWORD"],
        "opendistro_security_roles": ["rag_ingest"],
    })

    for group in load_group_config()["groups"]:
        role_name = f"rag_reader_{group}"
        user_name = f"rag_{group}"
        put(admin, f"/_plugins/_security/api/roles/{role_name}", {
            "cluster_permissions": ["cluster_monitor"],
            "index_permissions": [{
                "index_patterns": [INDEX],
                "allowed_actions": ["read", "indices:admin/get"],
                "dls": json.dumps({"terms": {"group": [group]}}, separators=(",", ":")),
            }],
        })
        put(admin, f"/_plugins/_security/api/internalusers/{user_name}", {
            "password": derive_group_password(group),
            "opendistro_security_roles": [role_name],
        })

    put(admin, "/_plugins/_security/api/internalusers/rag_eval", {
        "password": derive_group_password("eval"),
        "opendistro_security_roles": ["rag_reader"],
    })
    print("OpenSearch のサービスユーザーとグループ別 DLS role/user を設定しました")


if __name__ == "__main__":
    main()
