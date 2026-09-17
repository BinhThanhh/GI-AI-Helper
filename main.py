# pyrefly: ignore [missing-import]
from fastapi import FastAPI
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

# 1. BẮT BUỘC gọi load_dotenv() TRƯỚC TIÊN để nạp API key vào bộ nhớ
load_dotenv()

# 2. Sau đó mới import và khởi tạo harness
from src.core.harness import GenshinRAGHarness

app = FastAPI(title="Genshin AI Companion")

# Bật CORS để mở index.html gọi sang ko bị chặn
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

harness = GenshinRAGHarness()

class ChatRequest(BaseModel):
    message: str

@app.get("/")
async def root():
    return {"status": "OK", "message": "Paimon is ready!"}

@app.post("/chat")
async def chat(req: ChatRequest):
    result = await harness.run(req.message)
    return {
        "reply": result.answer,
        "sources": result.sources,
        "chunks_used": result.retrieved_chunks
    }

if __name__ == "__main__":
    # pyrefly: ignore [missing-import]
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)