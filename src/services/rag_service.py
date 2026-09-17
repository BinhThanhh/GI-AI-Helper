import os
from pathlib import Path
# pyrefly: ignore [missing-import]
from langchain_community.document_loaders import DirectoryLoader, TextLoader
# pyrefly: ignore [missing-import]
from langchain_text_splitters import RecursiveCharacterTextSplitter
# pyrefly: ignore [missing-import]
from langchain_community.embeddings import HuggingFaceEmbeddings
# pyrefly: ignore [missing-import]
from langchain_community.vectorstores import Chroma

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CHROMA_PATH = str(BASE_DIR / "chroma_db")
DATA_PATH = str(BASE_DIR / "data")

embedding_model = HuggingFaceEmbeddings(
    model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)

def ingest_data():
    print(f"Bắt đầu quét folder: {DATA_PATH}")
    
    # Bắt buộc thêm recursive=True để vét sạch folder lồng nhau
    loader = DirectoryLoader(
        DATA_PATH,
        glob="**/*.txt",
        recursive=True,
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8", "autodetect_encoding": True}
    )
    docs = loader.load()
    print(f"Đã load xong {len(docs)} files tài liệu.")

    # Check nhanh xem có bốc trúng file Columbina ko
    has_columbina = any("Columbina" in d.metadata.get("source", "") for d in docs)
    print(f"--> Đã tóm được file Columbina chưa: {'RỒI NHA' if has_columbina else 'CHƯA THẤY ĐÂU :('}")

    # Tăng chunk_size lên 800 để giữ trọn vẹn cụm stat nhân vật
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    chunks = text_splitter.split_documents(docs)
    print(f"Đã chia thành {len(chunks)} chunks.")

    vector_db = Chroma.from_documents(
        chunks, 
        embedding_model, 
        persist_directory=CHROMA_PATH
    )
    print("Ingest data vào Vector DB thành công rực rỡ!")
    return vector_db

def query_rag(question: str, k: int = 6) -> str:
    if not os.path.exists(CHROMA_PATH):
        return ""
    vector_db = Chroma(persist_directory=CHROMA_PATH, embedding_function=embedding_model)
    results = vector_db.similarity_search(question, k=k)
    context = "\n---\n".join([f"[{doc.metadata.get('source')}]: {doc.page_content}" for doc in results])
    return context