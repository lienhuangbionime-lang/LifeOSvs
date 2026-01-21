import os
import json
import uuid
import datetime
from google import genai
import frontmatter
import re

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("FATAL: GEMINI_API_KEY is not set.")

# [MIGRATION] 初始化新版 Client
client = genai.Client(api_key=API_KEY)

def regex_fallback_extract(raw_text):
    """
    如果 AI 失敗，使用強化的正則表達式強制提取 'Tomorrow's MIT' 區塊
    """
    tasks = []
    # (?:##|###) -> 匹配二級或三級標題
    mit_pattern = r"(?:##|###)\s*(?:\d+\.?\s*)?Tomorrow.s\s*MIT.*?(?:\n|$)(.*?)(?=\n#|\Z)"
    
    match = re.search(mit_pattern, raw_text, re.DOTALL | re.IGNORECASE)
    
    if match:
        block_content = match.group(1)
        print(f"🔍 DEBUG: Regex found MIT block content (len={len(block_content)})")
        lines = block_content.split('\n')
        for line in lines:
            line = line.strip()
            # 支援 "- [ ]", "- ", "TODO:"
            if line.startswith('- [ ]') or line.startswith('- ') or line.startswith('TODO'):
                clean_task = re.sub(r"^(-\s*\[\s*\]|-\s*|TODO\s*:?)\s*", "", line)
                if clean_task:
                    tasks.append({
                        "task": clean_task,
                        "priority": "High", 
                        "context": "Fallback Extraction"
                    })
    else:
        print("🔍 DEBUG: Regex could not find 'Tomorrow's MIT' header (Check numbering or spelling).")
        
    return tasks

def analyze_dual_track_entry(raw_text):
    prompt = f"""
    You are the parser for LifeOS. Convert the raw "Dual-Track" journal into structured JSON.
    
    ### Input Text:
    {raw_text}
    
    ### Extraction Logic:
    1. **Project Intelligence**: 'name_candidates', 'signals', 'blind_spots', 'open_nodes'.
    2. **Action Extraction**: 'action_items' from "Tomorrow's MIT".
    3. **Life Telemetry**: 'energy_stability', 'relationship_presence', 'baseline_safety'.
    
    ### Output Format (Strict JSON):
    {{
      "mood": 5.0, "focus": 5.0, "tags": [], "action_items": [],
      "project_data": {{}}, "life_data": {{}}, "summary": "..."
    }}
    """

    try:
        # [MIGRATION] 新版生成調用 (google-genai)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        # 移除 markdown code block 標記
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        analysis = json.loads(clean_text)
    except Exception as e:
        print(f"❌ AI Parse Failed: {e}")
        analysis = {"action_items": [], "summary": "AI Parse Error"}

    # 如果 AI 沒抓到，啟用 Regex Fallback
    if not analysis.get('action_items'):
        print("⚠️ AI found no actions. Engaging Regex Fallback Protocol...")
        fallback_actions = regex_fallback_extract(raw_text)
        if fallback_actions:
            analysis['action_items'] = fallback_actions

    # Embedding
    try:
        # [MIGRATION] 新版 Embedding 調用 (google-genai)
        # 注意：LifeOS 目前僅使用單一文檔 embedding
        embedding_resp = client.models.embed_content(
            model="text-embedding-004",
            contents=raw_text,
            config={'task_type': 'RETRIEVAL_DOCUMENT'}
        )
        # 新版 SDK 回傳結構：embedding_resp.embeddings[0].values
        embedding = embedding_resp.embeddings[0].values
    except Exception as e:
        print(f"⚠️ Embedding Failed: {e}")
        embedding = []
    
    return analysis, embedding

def save_to_inbox(raw_text, analysis, embedding):
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', raw_text)
    if date_match:
        date_str = date_match.group(1)

    entry_id = str(uuid.uuid4())[:8]
    filename_base = f"data/inbox/{date_str}_{entry_id}"
    
    frontend_data = {
        "uuid": entry_id,
        "date": date_str,
        "raw_text": raw_text, 
        "analysis": analysis, 
        "embedding": embedding 
    }

    os.makedirs("data/inbox", exist_ok=True)
    
    json_path = f"{filename_base}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(frontend_data, f, ensure_ascii=False, indent=2)

    md_path = f"{filename_base}.md"
    post = frontmatter.Post(raw_text, **{"uuid": entry_id, "mood": analysis.get("mood")})
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))

    print(f"✅ FILE WRITTEN: {os.path.abspath(json_path)}")

if __name__ == "__main__":
    journal_text = os.getenv("JOURNAL_TEXT")
    if not journal_text:
        print("⚠️ No text provided.")
        exit(1)
    
    analysis_data, vector_data = analyze_dual_track_entry(journal_text)
    save_to_inbox(journal_text, analysis_data, vector_data)
