import os
import json
import uuid
import datetime
import google.generativeai as genai
import frontmatter
import re

# 1. 配置 Gemini
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("FATAL: GEMINI_API_KEY is not set.")
genai.configure(api_key=API_KEY)

def analyze_dual_track_entry(raw_text):
    """
    專門解析 Dual-Track (Project/Life) 格式的日記
    """
    model = genai.GenerativeModel('gemini-1.5-flash')

    # [修正重點]：此變數必須縮排在函式內
    prompt = f"""
    You are the parser for LifeOS. Convert the raw "Dual-Track" journal into structured JSON.
    
    ### Input Text:
    {raw_text}
    
    ### Extraction Logic:
    1. **Project Intelligence**:
       - 'name_candidates': Extract potential project names from repeated nouns.
       - 'signals': Content from 'Signals Detected' (Observations).
       - 'blind_spots': Content from 'Blind Spot Question'.
       - 'open_nodes': Content from 'Open Nodes' (Abstract ideas, questions, loose thoughts).
    
    2. **Action Extraction Protocol (CRITICAL)**:
       - 'action_items': Extract specific, actionable tasks.
         - RULE 1: Must extract items from "Tomorrow's MIT" section.
         - RULE 2: Must extract lines starting with "- [ ]" or "TODO".
         - RULE 3: Infer implicit high-priority tasks from the narrative.
         - Format: List of objects {{ "task": "...", "priority": "High/Med/Low", "context": "..." }}.
    
    3. **Life Telemetry**:
       - 'energy_stability': Extract from metrics or infer (High/Med/Low).
       - 'relationship_presence': Boolean.
       - 'baseline_safety': (Stable/Warning/Intervene).
    
    ### Output Format (Strict JSON):
    {{
      "mood": float,
      "focus": float,
      "tags": ["tag1"],
      "action_items": [
         {{ "task": "Fix the sync bug", "priority": "High", "context": "Project A" }}
      ],
      "project_data": {{
          "candidates": ["name1"],
          "signals": "string",
          "blind_spots": "string",
          "open_nodes": "string",
          "confidence": {{ "structure": "Med", "verification": "Low" }}
      }},
      "life_data": {{
          "energy_stability": "Low",
          "relationship_presence": true,
          "baseline_safety": "Stable"
      }},
      "summary": "..."
    }}
    """

    try:
        response = model.generate_content(prompt)
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        analysis = json.loads(clean_text)
    except Exception as e:
        print(f"AI Parse Failed: {e}")
        analysis = {
            "mood": 5, "focus": 5, "energy": 5, 
            "tags": [], "summary": "AI Parse Error", 
            "sections": {},
            "action_items": [] 
        }

    try:
        embedding_result = genai.embed_content(
            model="models/embedding-001",
            content=raw_text,
            task_type="RETRIEVAL_DOCUMENT"
        )
        embedding = embedding_result['embedding']
    except Exception as e:
        print(f"Embedding Failed: {e}")
        embedding = []
    
    return analysis, embedding

def save_to_inbox(raw_text, analysis, embedding):
    # 嘗試抓取日期
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', raw_text)
    if date_match:
        date_str = date_match.group(1)

    entry_id = str(uuid.uuid4())[:8]
    filename_base = f"data/inbox/{date_str}_{entry_id}"
    
    # 建構前端資料
    frontend_data = {
        "uuid": entry_id,
        "date": date_str,
        "raw_text": raw_text, 
        "analysis": {
            "date": date_str,
            "mood": analysis.get("mood", 5),
            "focus": analysis.get("focus", 5),
            "energy": analysis.get("energy", 5),
            "tags": analysis.get("tags", []),
            "summary": analysis.get("summary", ""),
            "sections": analysis.get("sections", {}),
            # [修正重點]：確保寫入 Action Items
            "action_items": analysis.get("action_items", []) 
        },
        "embedding": embedding 
    }

    os.makedirs("data/inbox", exist_ok=True)
    with open(f"{filename_base}.json", "w", encoding="utf-8") as f:
        json.dump(frontend_data, f, ensure_ascii=False, indent=2)

    post = frontmatter.Post(raw_text, **{
        "uuid": entry_id,
        "mood": analysis.get("mood"),
        "tags": analysis.get("tags")
    })
    with open(f"{filename_base}.md", "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))

    print(f"✅ Created Inbox Entry: {filename_base}.json")

if __name__ == "__main__":
    journal_text = os.getenv("JOURNAL_TEXT")
    if not journal_text:
        print("⚠️ No text provided.")
        exit(1)
    
    analysis_data, vector_data = analyze_dual_track_entry(journal_text)
    save_to_inbox(journal_text, analysis_data, vector_data)
