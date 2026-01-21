import os
import json
import glob
import requests
import time

ZAPIER_TASK_WEBHOOK = os.getenv("ZAPIER_TASK_WEBHOOK")

def sync_tasks_to_cloud():
    # 強制檢查目錄，確認資料來源
    print(f"📂 Current Working Directory: {os.getcwd()}")
    if os.path.exists("data/inbox"):
        files = os.listdir('data/inbox')
        print(f"📂 Listing data/inbox ({len(files)} files): {files}")
    else:
        print("❌ ERROR: data/inbox directory does not exist!")
        return

    inbox_files = glob.glob("data/inbox/*.json")
    tasks_to_sync = []
    
    print(f"🔍 Found {len(inbox_files)} JSON files to scan.")

    for filepath in inbox_files:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 讀取 AI 分析結果
            analysis = data.get('analysis', {})
            ai_actions = analysis.get('action_items', [])
            
            if ai_actions:
                print(f"✅ [{filepath}] Extracted {len(ai_actions)} tasks.")
                for item in ai_actions:
                    # 相容性處理
                    task_obj = item if isinstance(item, dict) else {"task": item}
                    
                    tasks_to_sync.append({
                        "title": f"[LifeOS] {task_obj.get('task', 'Untitled')}",
                        "notes": f"Context: {task_obj.get('context', 'General')}\nPriority: {task_obj.get('priority', 'Med')}",
                        "due": "tomorrow"
                    })
            else:
                print(f"⚠️ [{filepath}] No 'action_items' found in AI analysis.")
                
        except Exception as e:
            print(f"❌ Error processing {filepath}: {e}")
            
    # [核心修正] 迴圈單條發送 (Loop Send)
    if tasks_to_sync and ZAPIER_TASK_WEBHOOK:
        print(f"🚀 Sending {len(tasks_to_sync)} tasks to Zapier...")
        for i, task in enumerate(tasks_to_sync):
            try:
                # [修正點] 發送單一物件，而非 {"tasks": []}
                requests.post(ZAPIER_TASK_WEBHOOK, json=task)
                print(f"📨 Sent ({i+1}/{len(tasks_to_sync)}): {task['title']}")
                time.sleep(1) # 避免過快被擋
            except Exception as e:
                print(f"❌ Send Failed: {e}")
    elif not tasks_to_sync:
        print("💡 No actionable tasks found in any file.")
    else:
        print("⚠️ Tasks found but Webhook URL is missing.")

if __name__ == "__main__":
    sync_tasks_to_cloud()
