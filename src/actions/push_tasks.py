import os
import json
import glob
from google.oauth2 import service_account
from googleapiclient.discovery import build

INBOX_DIR = "data/inbox"

def get_latest_inbox_entry():
    # 找最新的 json 檔案
    files = glob.glob(os.path.join(INBOX_DIR, "*.json"))
    if not files: return None
    latest_file = max(files, key=os.path.getctime)
    with open(latest_file, 'r') as f:
        return json.load(f)

def push_to_google_tasks(entry):
    creds_json = os.environ.get('GOOGLE_TASKS_CREDS')
    task_list_id = os.environ.get('TASK_LIST_ID')
    
    if not creds_json or not task_list_id:
        print("Skipping Tasks: No Credentials found.")
        return

    creds_dict = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(creds_dict)
    service = build('tasks', 'v1', credentials=creds)

    # 從 Analysis 解析待辦事項
    # 假設你的 Gemini 解析出的 JSON 結構中有 project_data.open_nodes 或 summary
    analysis = entry.get('analysis', {})
    project_data = analysis.get('project_data', {})
    
    # 萃取 Action Items (這裡依賴 Gemini 的萃取能力)
    # 你可以在 process_inbox.py 的 Prompt 裡強制加一個 "action_items": [] 欄位
    open_nodes = project_data.get('open_nodes', '')
    
    if open_nodes:
        # 簡單處理：如果是一整段文字，直接當作一個大任務，或者嘗試用換行切割
        items = [line.strip() for line in open_nodes.split('\n') if line.strip().startswith('-') or line.strip().startswith('•')]
        if not items: items = [open_nodes] # Fallback
        
        for item in items:
            clean_title = item.replace('-', '').replace('•', '').strip()
            body = {
                'title': f"[LifeOS] {clean_title}",
                'notes': f"From Log: {entry.get('date')}\nContext: {analysis.get('summary')}",
                'due': (datetime.datetime.now() + datetime.timedelta(days=1)).isoformat() + 'Z' # 明天到期
            }
            service.tasks().insert(tasklist=task_list_id, body=body).execute()
            print(f"✅ Google Task Created: {clean_title}")

if __name__ == "__main__":
    try:
        entry = get_latest_inbox_entry()
        if entry:
            push_to_google_tasks(entry)
        else:
            print("No new inbox entry found to sync.")
    except Exception as e:
        print(f"Task Sync Failed: {e}")
