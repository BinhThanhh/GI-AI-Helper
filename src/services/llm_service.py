import os
from google import genai
from src.services.rag_service import query_rag

def get_client():
    return genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

async def ask_paimon(question: str) -> str:
    client = get_client()
    
    # 1. Bốc data liên quan nhất từ thư mục data/ lên
    context = query_rag(question)
    
    # 2. Bơm context vào prompt cho model đọc
    prompt = f"""Mày là Paimon, trợ lý Genshin Impact nhí nhảnh. Dưới đây là thông tin nội bộ về các bản cập nhật: {context}. Dựa vào thông tin trên, hãy trả lời câu hỏi của Nhà Lữ Hành: {question}"""

    response = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=prompt
    )
    
    return response.text