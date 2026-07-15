"""main.py / ingest.py 共通: 文書ロード、グループ付与、チャンク分割。"""
import os
from pathlib import Path

from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter


def load_documents(docs_dir: str):
    loaders = [
        DirectoryLoader(docs_dir, glob="**/*.pdf", loader_cls=PyPDFLoader),
        DirectoryLoader(docs_dir, glob="**/*.md", loader_cls=TextLoader,
                        loader_kwargs={"autodetect_encoding": True}),
        DirectoryLoader(docs_dir, glob="**/*.txt", loader_cls=TextLoader,
                        loader_kwargs={"autodetect_encoding": True}),
    ]
    docs = []
    for loader in loaders:
        docs.extend(loader.load())
    return docs


def assign_group_metadata(docs, docs_dir: str):
    """documents/<group>/... の第1階層を metadata.group に設定する。"""
    root = Path(docs_dir).resolve()
    direct_files = []
    resolved = []
    for doc in docs:
        source = Path(doc.metadata.get("source", "")).resolve()
        try:
            relative = source.relative_to(root)
        except ValueError as exc:
            raise SystemExit(f"文書が DOCS_DIR 外です: {source}") from exc
        if len(relative.parts) < 2:
            direct_files.append(str(source))
            continue
        resolved.append((doc, relative.parts[0]))

    if direct_files:
        listing = "\n".join(f"- {path}" for path in sorted(direct_files))
        raise SystemExit(
            "documents/ 直下の文書にはグループを決定できません。"
            "documents/<group>/ 配下へ移動してください:\n" + listing
        )
    for doc, group in resolved:
        doc.metadata["group"] = group
    return docs


def split_documents(docs):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=int(os.getenv("CHUNK_SIZE", "500")),
        chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "100")),
        separators=["\n\n", "\n", "。", "、", " ", ""],
    )
    return splitter.split_documents(docs)
