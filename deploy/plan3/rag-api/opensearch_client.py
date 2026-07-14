"""OpenSearch Security Plugin 向けの TLS / Basic 認証済みクライアント。"""
import os
from urllib.parse import urlparse

from opensearchpy import OpenSearch


def build_opensearch_client(
    username: str | None = None,
    password: str | None = None,
) -> OpenSearch:
    url = urlparse(os.getenv("OPENSEARCH_URL", "https://node-0.example.com:9200"))
    if url.scheme != "https" or not url.hostname:
        raise RuntimeError("OPENSEARCH_URL は https://host:port 形式で指定してください")

    username = username or os.environ["OS_USERNAME"]
    password = password or os.environ["OS_PASSWORD"]
    ca_cert = os.getenv("OS_CA_CERT", "/app/certs/root-ca.pem")

    return OpenSearch(
        hosts=[{"host": url.hostname, "port": url.port or 443}],
        http_auth=(username, password),
        use_ssl=True,
        verify_certs=True,
        ssl_assert_hostname=True,
        ca_certs=ca_cert,
    )