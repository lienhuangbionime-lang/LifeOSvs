import pandas as pd
import glob
import os
import json
import frontmatter
import sys

# [Path Fix] 確保可以從 src.utils 導入模組
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from src.utils.analytics import generate_system_state

# 定義路徑
INBOX_PATH = "data/inbox/"
ARCHIVE_PARQUET_PATH = "data/archive/journal.parquet"
ARCHIVE_JSON_PATH = "data/archive/lifeos_db.json"
SYSTEM_STATE_PATH = "data/archive/system_state.json"

def compaction_process():
    # 1. 檢查是否有新檔案
    md_files = glob.glob(os.path.join(INBOX_PATH, "*.md"))
    if not md_files:
        print("No files to compact.")
        if not os.path.exists(ARCHIVE_PARQUET_PATH):
            return
            
    print(f"Starting compaction for {len(md_files)} entries...")

    # 2. 讀取現有 Parquet
    if os.path.exists(ARCHIVE_PARQUET_PATH):
        try:
            df_base = pd.read_parquet(ARCHIVE_PARQUET_PATH)
        except Exception as e:
            print(f"Warning: Could not read parquet, starting fresh. {e}")
            df_base = pd.DataFrame()
    else:
        df_base = pd.DataFrame()

    # 3. 解析 Inbox 資料
    new_data = []
    files_to_delete = []

    for md_file in md_files:
        try:
            post = frontmatter.load(md_file)
            entry = post.metadata
            
            if 'date' not in entry: 
                filename = os.path.basename(md_file)
                if filename[:8].isdigit():
                    entry['date'] = f"{filename[:4]}-{filename[4:6]}-{filename[6:8]}"
                else:
                    entry['date'] = str(post.get('date'))[:10] if post.get('date') else "1970-01-01"
            
            entry['content'] = post.content
            entry['note'] = post.content 
            
            json_file = md_file.replace(".md", ".json")
            if os.path.exists(json_file):
                with open(json_file, 'r', encoding='utf-8') as f:
                    sidecar = json.load(f)
                    if 'analysis' in sidecar:
                        entry['ai_analysis'] = sidecar['analysis'] 
                        if 'mood' not in entry and 'mood' in sidecar['analysis']:
                            entry['mood'] = sidecar['analysis']['mood']
                    entry['embedding'] = sidecar.get('embedding') 
                files_to_delete.append(json_file)
            
            files_to_delete.append(md_file)
            new_data.append(entry)
            
        except Exception as e:
            print(f"Error compacting {md_file}: {e}")

    # 4. 合併與寫入
    if new_data or not df_base.empty:
        if new_data:
            df_new = pd.DataFrame(new_data)
            if 'date' in df_new.columns:
                df_new['date'] = pd.to_datetime(df_new['date'])
            if not df_base.empty and 'date' in df_base.columns:
                df_base['date'] = pd.to_datetime(df_base['date'])
            df_combined = pd.concat([df_base, df_new], ignore_index=True)
        else:
            df_combined = df_base.copy()
        
        if 'uuid' in df_combined.columns:
            df_combined = df_combined.drop_duplicates(subset=['uuid'], keep='last')
        else:
            df_combined = df_combined.drop_duplicates(subset=['date'], keep='last')

        df_combined = df_combined.sort_values(by='date')

        # 生成 System State (使用共用模組)
        try:
            print("Analyzing System State...")
            system_state = generate_system_state(df_combined)
            os.makedirs(os.path.dirname(SYSTEM_STATE_PATH), exist_ok=True)
            with open(SYSTEM_STATE_PATH, "w", encoding="utf-8") as f:
                json.dump(system_state, f, ensure_ascii=False, indent=2)
            print(f"✅ System State Updated: {SYSTEM_STATE_PATH}")
        except Exception as e:
            print(f"❌ System State Generation Failed: {e}")

        if not df_combined.empty:
            os.makedirs(os.path.dirname(ARCHIVE_PARQUET_PATH), exist_ok=True)
            df_combined.to_parquet(ARCHIVE_PARQUET_PATH, compression='snappy')
            print(f"Compacted to {ARCHIVE_PARQUET_PATH}")

            df_export = df_combined.copy()
            if 'embedding' in df_export.columns:
                df_export = df_export.drop(columns=['embedding'])
            if 'date' in df_export.columns:
                df_export['date'] = df_export['date'].dt.strftime('%Y-%m-%d')
            
            df_export.to_json(ARCHIVE_JSON_PATH, orient='records', force_ascii=False, date_format='iso')
            print(f"Exported JSON to {ARCHIVE_JSON_PATH}")

        for f in files_to_delete:
            if os.path.exists(f):
                os.remove(f)
        if files_to_delete:
            print("Inbox cleaned.")

if __name__ == "__main__":
    compaction_process()
