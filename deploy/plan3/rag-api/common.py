"""main.py / ingest.py 共通: 文書ロードとチャンク分割。"""
import os

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


def split_documents(docs):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=int(os.getenv("CHUNK_SIZE", "500")),
        chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "100")),
        separators=["\n\n", "\n", "。", "、", " ", ""],  # 日本語向けセパレータ
    )
    return splitter.split_documents(docs)
