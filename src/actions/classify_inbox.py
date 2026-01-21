import os
import json
import re
import glob
import datetime

# 定義路徑
INBOX_DIR = "data/inbox"
PROJECTS_DIR = "data/projects"
LIFE_DIR = "data/life"
STATUS_FILE = "data/status/latest_actions.json" # [NEW] Nudge 用的資料來源

def parse_dual_track(raw_text):
    """
    手術刀：將日記文本拆解為 Project 與 Life 兩部分，並提取 Next Steps
    """
    # 1. 切割 A. Project Log
    project_match = re.search(r'## A\. Project Log.*?([\s\S]*?)(?=## B\. Life Log|$)', raw_text, re.IGNORECASE)
    project_content = project_match.group(1).strip() if project_match else ""

    # 2. 切割 B. Life Log
    life_match = re.search(r'## B\. Life Log.*?([\s\S]*?)(?=## Graph Seeds|$)', raw_text, re.IGNORECASE)
    life_content = life_match.group(1).strip() if life_match else ""

    # 3. 提取 Project Tags
    tags = re.findall(r'#([\w\u4e00-\u9fa5]+)', project_content)
    valid_project_tags = [t for t in tags if t not in ['LifeOS', 'DualMemory'] or t == 'LifeOS'] 
    primary_project = valid_project_tags[0] if valid_project_tags else "Uncategorized"

    # [NEW] 4. 提取 Tomorrow's MIT (下一步行動)
    # 尋找 "Tomorrow's MIT" 或 "Next Steps" 區塊
    mit_match = re.search(r"(?:Tomorrow’s MIT|Next Steps).*?[:：]?\s*\n([\s\S]*?)(?=\n###|\n##|$)", project_content, re.IGNORECASE)
    next_actions = []
    if mit_match:
        # 抓取 bullet points
        lines = mit_match.group(1).strip().split('\n')
        next_actions = [line.strip().replace('- ', '').replace('* ', '') for line in lines if line.strip().startswith(('- ', '* '))]

    return {
        "project": {
            "name": primary_project,
            "content": project_content,
            "next_actions": next_actions
        },
        "life": {
            "content": life_content
        }
    }

def process_inbox_files():
    os.makedirs(PROJECTS_DIR, exist_ok=True)
    os.makedirs(LIFE_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)

    files = glob.glob(os.path.join(INBOX_DIR, "*.json"))
    
    actions_report = {} # 用來收集所有日記的下一步

    for filepath in files:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # 兼容欄位讀取
        raw_text = data.get('raw_text', '') or data.get('note', '') 
        # 從 analysis.date 或 raw data 取得日期
        date = data.get('analysis', {}).get('date') or data.get('date') or datetime.datetime.now().strftime('%Y-%m-%d')
        
        if not raw_text:
            continue
            
        parsed = parse_dual_track(raw_text)
        
        # --- 路由 1: 專案日誌 ---
        project_name = parsed['project']['name']
        project_file = os.path.join(PROJECTS_DIR, f"{project_name}.md")
        
        with open(project_file, 'a', encoding='utf-8') as pf:
            entry_block = f"\n\n### {date} Log\n{parsed['project']['content']}\n\n---"
            pf.write(entry_block)
            
        print(f"✅ Routed Project Log to: {project_file}")

        # --- 路由 2: 生活訊號 ---
        life_file = os.path.join(LIFE_DIR, f"life_log_{date[:7]}.md") 
        with open(life_file, 'a', encoding='utf-8') as lf:
            entry_block = f"\n\n### {date}\n{parsed['life']['content']}\n\n---"
            lf.write(entry_block)

        # --- [NEW] 收集下一步行動 ---
        if parsed['project']['next_actions']:
            actions_report[project_name] = {
                "date": date,
                "actions": parsed['project']['next_actions']
            }

    # [NEW] 產出 Nudge 用的狀態檔
    if actions_report:
        with open(STATUS_FILE, 'w', encoding='utf-8') as f:
            json.dump(actions_report, f, ensure_ascii=False, indent=2)
        print(f"🚀 Generated Status File: {STATUS_FILE}")

if __name__ == "__main__":
    process_inbox_files()
