"""app.py / ingest.py 共通: 埋め込みモデルと文書ロード。"""
import os

from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader, TextLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter


class E5Embeddings(HuggingFaceEmbeddings):
    """multilingual-e5 系は query:/passage: プレフィックスが必須(付け忘れると精度が大きく落ちる)。"""

    def embed_documents(self, texts):
        return super().embed_documents([f"passage: {t}" for t in texts])

    def embed_query(self, text):
        return super().embed_query(f"query: {text}")


def build_embeddings():
    model = os.getenv("EMBED_MODEL", "intfloat/multilingual-e5-large")
    cls = E5Embeddings if "e5" in model.lower() else HuggingFaceEmbeddings
    return cls(model_name=model, encode_kwargs={"normalize_embeddings": True})


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
