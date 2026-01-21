import os
import json
import glob
import requests
import time

ZAPIER_TASK_WEBHOOK = os.getenv("ZAPIER_TASK_WEBHOOK")

def sync_tasks_to_cloud():
    print(f"📂 Current Working Directory: {os.getcwd()}")
    
    # 確保目錄存在
    if not os.path.exists("data/inbox"):
        print("❌ ERROR: data/inbox directory does not exist!")
        return

    inbox_files = glob.glob("data/inbox/*.json")
    tasks_to_sync = []
    
    print(f"🔍 Found {len(inbox_files)} JSON files to scan.")

    for filepath in inbox_files:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            analysis = data.get('analysis', {})
            # 相容性：有些舊格式可能是直接 list，有些是 dict
            ai_actions = analysis.get('action_items', [])
            
            if ai_actions:
                print(f"✅ [{filepath}] Extracted {len(ai_actions)} tasks.")
                for item in ai_actions:
                    task_obj = item if isinstance(item, dict) else {"task": item}
                    
                    # [VISUAL CLEANUP] 視覺淨化處理
                    # 1. 移除 [LifeOS] 前綴，直接顯示任務
                    # 2. Context 改用 Hashtag 格式，較為現代且不佔版面
                    # 3. Priority 若為 High 才標示 emoji，否則隱藏
                    
                    raw_task = task_obj.get('task', 'Untitled')
                    context = task_obj.get('context', 'General').replace(" ", "")
                    priority = task_obj.get('priority', 'Med')
                    
                    # 只有高優先級才加紅點，保持清爽
                    priority_mark = "🔴 " if priority.lower() == 'high' else ""
                    
                    tasks_to_sync.append({
                        "title": f"{priority_mark}{raw_task}",
                        "notes": f"#{context}", # 極簡化備註
                        "due": "today" # 或是 tomorrow，視您的習慣
                    })
            else:
                pass # 靜默處理無任務的檔案
                
        except Exception as e:
            print(f"❌ Error processing {filepath}: {e}")
            
    if tasks_to_sync and ZAPIER_TASK_WEBHOOK:
        print(f"🚀 Sending {len(tasks_to_sync)} tasks to Zapier...")
        for i, task in enumerate(tasks_to_sync):
            try:
                requests.post(ZAPIER_TASK_WEBHOOK, json=task)
                print(f"📨 Sent ({i+1}/{len(tasks_to_sync)}): {task['title']}")
                time.sleep(0.5)
            except Exception as e:
                print(f"❌ Send Failed: {e}")
    elif not tasks_to_sync:
        print("💡 No actionable tasks found.")
    else:
        print("⚠️ Tasks found but Webhook URL is missing.")

if __name__ == "__main__":
    sync_tasks_to_cloud()
