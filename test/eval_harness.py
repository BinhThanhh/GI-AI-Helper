import json
import asyncio
from src.services.rag_service import query_rag
from src.services.llm_service import ask_paimon, get_client

async def run_harness():
    with open("eval_dataset.json", "r", encoding="utf-8") as f:
        tests = json.load(f)

    client = get_client()
    passed = 0
    total = len(tests)

    print("🚀 Đang chạy Test Harness cho Genshin RAG...\n")

    for idx, item in enumerate(tests, 1):
        q = item["question"]
        gt = item["ground_truth"]

        # 1. Chạy flow thực tế
        context = query_rag(q)
        answer = await ask_paimon(q)

        # 2. Dùng LLM làm quan tòa chấm điểm (LLM-as-a-judge)
        judge_prompt = f"""
        So sánh câu trả lời thực tế với đáp án chuẩn.
        Câu hỏi: {q}
        Đáp án chuẩn: {gt}
        Câu bot trả lời: {answer}

        Nếu câu bot trả lời chứa đúng và đủ ý chính của đáp án chuẩn, chỉ ghi 'PASS'.
        Nếu sai lệch hoặc bịa đặt thông tin, chỉ ghi 'FAIL'.
        """
        verdict = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=judge_prompt
        ).text.strip()

        is_pass = "PASS" in verdict
        if is_pass:
            passed += 1

        print(f"Test #{idx}: {q}")
        print(f"-> Kết quả: {'✅ PASS' if is_pass else '❌ FAIL'}")
        if not is_pass:
            print(f"   [Thực tế]: {answer}")
            print(f"   [Mong đợi]: {gt}")
        print("-" * 50)

    print(f"\n📊 Tỉ lệ chính xác: {passed}/{total} ({passed/total * 100:.1f}%)")

if __name__ == "__main__":
    asyncio.run(run_harness())