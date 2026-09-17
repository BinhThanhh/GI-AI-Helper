import os
import json
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
from typing import List, Dict, Any
from dataclasses import dataclass
# pyrefly: ignore [missing-import]
from langchain_community.vectorstores import Chroma
# pyrefly: ignore [missing-import]
from langchain_community.embeddings import HuggingFaceEmbeddings
from google import genai
from google.genai import types

load_dotenv()

@dataclass
class RAGResult:
    answer: str
    sources: List[str]
    retrieved_chunks: int

class GenshinRAGHarness:
    def __init__(self, chroma_path: str = "./chroma_db"):
        self.chroma_path = chroma_path
        # Dùng model embedding đa ngôn ngữ
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        )
        self.client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        self.model_name = "gemini-3.1-flash-lite"

    # Mắt xích 1: Chuẩn hóa câu hỏi (xử lý lệch ngữ nghĩa Anh - Việt)
    def extract_search_intent(self, query: str) -> dict:
        prompt = f"""Phân tích câu hỏi về game Genshin Impact sau đây:
            Câu hỏi: {query}

            Hãy trả về DUY NHẤT 1 chuỗi JSON (không kèm markdown, không giải thích) có cấu trúc:
            {{
            "character": "tên tiếng Anh của nhân vật nếu có nhắc tới, ví dụ Columbina, Furina, Raiden Shogun, hoặc null nếu không có",
            "search_query": "dịch câu hỏi sang tiếng Anh ngắn gọn chứa các thuật ngữ game chuẩn như Ascension Materials, Talents, Build, Stats..."
            }}"""
        try:
            res = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            raw = res.text.strip().replace("```json", "").replace("```", "").strip()
            return json.loads(raw)
        except Exception:
            return {"character": None, "search_query": query}

    # Mắt xích 2: Trích xuất context từ Vector DB
    def retrieve(self, search_intent: dict, top_k: int = 8) -> List[Any]:
        if not os.path.exists(self.chroma_path):
            return []
        
        db = Chroma(persist_directory=self.chroma_path, embedding_function=self.embeddings)
        query = search_intent.get("search_query") or ""
        char_name = search_intent.get("character")

        # 1. Search lấy rộng hơn một chút (ví dụ lấy top 30 chunk)
        raw_results = db.similarity_search(query, k=30)
        
        if not char_name:
            return raw_results[:top_k]

        # 2. Nếu có tên nhân vật, lọc và đẩy các chunk có đường dẫn chứa tên nhân vật lên đầu!
        matched_chunks = []
        other_chunks = []
        
        for doc in raw_results:
            src = doc.metadata.get("source", "").lower()
            if char_name.lower() in src:
                matched_chunks.append(doc)
            else:
                other_chunks.append(doc)

        # Ưu tiên chunk trúng tên file trước, thiếu thì bù chunk khác vào
        final_docs = (matched_chunks + other_chunks)[:top_k]
        return final_docs

    # Mắt xích 3 & 4: Ép LLM sinh đáp án kèm guardrail
    async def run(self, user_question: str) -> RAGResult:
        # Bước 1: Cho LLM tự bóc tách entity nhân vật và dịch query chuẩn thuật ngữ
        intent = self.extract_search_intent(user_question)
        print(f"\n[Harness Log] Intent bóc được: {intent}")

        # Bước 2: Bốc doc theo entity (tăng top_k lên 8 để gom đủ stat/nguyên liệu)
        docs = self.retrieve(intent, top_k=8)
        print(f"[Harness Log] Số chunk bốc được: {len(docs)}")

        if not docs:
            return RAGResult(
                answer="Huhu, Paimon đã lục tung hết cả balo tài liệu rồi mà không thấy thông tin này Nhà Lữ Hành ơi! :(",
                sources=[],
                retrieved_chunks=0
            )

        # Gom context và danh sách file nguồn
        context_blocks = []
        sources = []
        for i, d in enumerate(docs):
            src = d.metadata.get("source", "unknown")
            sources.append(src)
            context_blocks.append(f"Source [{src}]:\n{d.page_content}")
            print(f"--> Chunk {i+1} nguồn: {src}")

        context_str = "\n\n---\n\n".join(context_blocks)

        # Bước 3: Prompt Guardrail ép model trả lời bám sát context
        system_instruction = """Mày là Paimon, trợ lý Genshin Impact nhí nhảnh, xưng là Paimon và gọi người chơi là Nhà Lữ Hành.
QUY TẮC CỐT LÕI:
1. Đọc kỹ phần CONTEXT bên dưới để trả lời câu hỏi.
2. Nếu context có thông tin (kể cả tiếng Anh), hãy dịch sang tiếng Việt và trình bày ngắn gọn, dễ hiểu, chuẩn style Paimon.
3. Chỉ trả lời dựa trên những gì CONTEXT cung cấp, tuyệt đối không tự bịa đặt hay đoán mò khi không có dữ liệu."""

        full_prompt = f"""CONTEXT:
{context_str}

CÂU HỎI CỦA NHÀ LỮ HÀNH: {user_question}"""

        # Bước 4: Gọi Gemini sinh câu trả lời (để temp thấp để chống ảo giác)
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.3
            )
        )

        return RAGResult(
            answer=response.text,
            sources=list(set(sources)),
            retrieved_chunks=len(docs)
        )

        