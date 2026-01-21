import os
import json
import re
import glob
import datetime
import frontmatter
import requests

# 定義路徑
INBOX_DIR = "data/inbox"
PROJECTS_DIR = "data/projects"
LIFE_DIR = "data/life"

# Webhook
ZAPIER_TASK_WEBHOOK = os.getenv("ZAPIER_TASK_WEBHOOK")

def ensure_dir(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

def append_to_log(filepath, date, content, source_uuid):
    """
    通用寫入函數：將內容 Append 到指定的 Markdown 檔案
    """
    header = f"\n\n### {date} (Ref: {source_uuid})\n"
    
    # 簡單的防重複檢查 (讀取最後 1000 字，看是否已存在相同的 UUID)
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            # 讀取檔尾
            try:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(size - 2000, 0), 0)
                tail = f.read()
                if source_uuid in tail:
                    print(f"Skipping duplicate entry for {filepath}")
                    return
            except:
                pass # 新檔案或讀取錯誤直接寫入

    with open(filepath, 'a+', encoding='utf-8') as f:
        f.write(header)
        f.write(content.strip())
    
    print(f"📝 Appended to {os.path.basename(filepath)}")

def extract_tasks(content):
    """從日記內容中抓取待辦事項"""
    tasks = []
    # 模式 A: Tomorrow's MIT
    mit_match = re.search(r"Tomorrow's MIT.*?(\n(?:[-*].*?|\s*)*)(?=\n#|\n\n|$)", content, re.IGNORECASE | re.DOTALL)
    if mit_match:
        lines = mit_match.group(1).strip().split('\n')
        for line in lines:
            clean_line = re.sub(r"^[-*]\s*", "", line).strip()
            if clean_line: tasks.append(clean_line)

    # 模式 B: Checkbox [ ]
    checkboxes = re.findall(r"-\s*\[\s*\]\s*(.*)", content)
    tasks.extend(checkboxes)
    return list(set(tasks))

def send_to_zapier(tasks, date):
    if not ZAPIER_TASK_WEBHOOK: return
    for task in tasks:
        try:
            requests.post(ZAPIER_TASK_WEBHOOK, json={"title": task, "date": date, "source": "LifeOS"})
        except Exception as e:
            print(f"❌ Failed to send task: {e}")

def process_inbox_files():
    ensure_dir(PROJECTS_DIR)
    ensure_dir(LIFE_DIR)
    
    # 讀取 Inbox 所有 .md
    files = glob.glob(os.path.join(INBOX_DIR, "*.md"))
    if not files:
        print("No files to classify.")
        return

    for filepath in files:
        try:
            # 1. 讀取 Markdown & Frontmatter
            post = frontmatter.load(filepath)
            content = post.content
            metadata = post.metadata
            
            # 取得關鍵元數據
            uuid_str = metadata.get('uuid', 'unknown')
            date_str = metadata.get('date', datetime.datetime.now().strftime('%Y-%m-%d'))
            # 確保 date_str 是字串 (有時 YAML 會解析成 datetime 物件)
            if isinstance(date_str, datetime.date):
                date_str = date_str.strftime('%Y-%m-%d')
            
            # 嘗試讀取 Sidecar JSON 以獲得更精準的 tags
            json_path = filepath.replace('.md', '.json')
            tags = metadata.get('tags', [])
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as jf:
                    sidecar = json.load(jf)
                    if 'analysis' in sidecar and 'tags' in sidecar['analysis']:
                        # 合併 tags
                        ai_tags = sidecar['analysis']['tags']
                        if isinstance(ai_tags, list):
                            tags.extend(ai_tags)
            
            # 去重並正規化 Tags
            tags = list(set([t.lower().replace('#', '') for t in tags if isinstance(t, str)]))

            # --- 路由邏輯 (Routing Logic) ---

            # A. Life Track (全量備份)
            # 按年份歸檔，例如 data/life/2026_log.md
            year = date_str[:4]
            life_file = os.path.join(LIFE_DIR, f"{year}_log.md")
            append_to_log(life_file, date_str, content, uuid_str)

            # B. Project Track (專案分流)
            # 如果 Tag 符合現有專案，或看起來像專案名，則寫入
            # 這裡簡單判定：只要有 Tag，就視為一個 Topic/Project
            for tag in tags:
                # 過濾掉通用 Tags
                if tag in ['journal', 'log', 'daily', 'life']:
                    continue
                
                # 檔名清理 (避免非法字元)
                safe_tag = re.sub(r'[\\/*?:"<>|]', "", tag).title()
                project_file = os.path.join(PROJECTS_DIR, f"{safe_tag}.md")
                
                # 寫入專案日誌
                append_to_log(project_file, date_str, content, uuid_str)

            # C. Task Extraction
            tasks = extract_tasks(content)
            if tasks:
                print(f"Found {len(tasks)} tasks via regex.")
                #send_to_zapier(tasks, date_str)

        except Exception as e:
            print(f"Error classifying {filepath}: {e}")

if __name__ == "__main__":
    process_inbox_files()
