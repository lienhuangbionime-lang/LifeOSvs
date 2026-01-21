import pandas as pd
import glob
import os
import json
import frontmatter
import shutil
from collections import Counter

# 定義路徑
INBOX_PATH = "data/inbox/"
ARCHIVE_PARQUET_PATH = "data/archive/journal.parquet"
ARCHIVE_JSON_PATH = "data/archive/lifeos_db.json"
SYSTEM_STATE_PATH = "data/archive/system_state.json"

def generate_system_state(df):
    """
    計算專案索引、想法交集與系統降速狀態
    """
    if df.empty:
        return {
            "active_projects": [],
            "idea_seeds": [],
            "system_status": {"mode": "BUILD", "reason": "No Data"}
        }

    # 確保是日期倒序（最新在前），這樣 head(30) 才是最近 30 天
    df_sorted = df.sort_values(by='date', ascending=False)
    recent_df = df_sorted.head(30)
    
    # 1. 自動專案索引 (Gardener Logic)
    # 邏輯：統計過去 30 天 Tags 出現頻率 > 3 次
    all_tags = []
    for _, row in recent_df.iterrows():
        # 優先從 ai_analysis 拿，沒有則從 metadata 拿
        analysis = row.get('ai_analysis') or {}
        tags = analysis.get('tags') or row.get('tags') or []
        
        if isinstance(tags, list):
            all_tags.extend([t.replace('#', '') for t in tags]) # 去除 # 號
    
    tag_counts = Counter(all_tags)
    active_projects = [tag for tag, count in tag_counts.items() if count >= 3]

    # 2. 想法萃取 (Idea Generator)
    # 邏輯：找出同時有 Signal + BlindSpot + OpenNodes 的日記
    ideas = []
    for _, row in recent_df.iterrows():
        analysis = row.get('ai_analysis') or {}
        p_data = analysis.get('project_data', {})
        
        # 檢查是否三個關鍵欄位都有值
        has_signal = bool(p_data.get('signals'))
        has_blind_spot = bool(p_data.get('blind_spots'))
        has_open_node = bool(p_data.get('open_nodes'))

        if has_signal and has_blind_spot and has_open_node:
            # 擷取前 20 個字作為預覽
            signal_txt = str(p_data['signals'])[:20]
            node_txt = str(p_data['open_nodes'])[:20]
            ideas.append({
                "date": row['date'].strftime('%Y-%m-%d') if pd.notnull(row['date']) else "Unknown",
                "core_concept": f"{signal_txt}... + {node_txt}..."
            })

    # 3. 生活降速機制 (The Governor)
    # 邏輯：檢查最後 2 筆 Life Log (因為 df 已倒序，取 head(2) 即可)
    last_2_days = df_sorted.head(2)
    throttle_mode = "BUILD" # 預設模式
    reason = "All Systems Nominal"
    
    for _, row in last_2_days.iterrows():
        analysis = row.get('ai_analysis') or {}
        life = analysis.get('life_data', {})
        
        safety = life.get('baseline_safety')
        energy = life.get('energy_stability')

        if safety == 'Intervene' or energy == 'Low':
            throttle_mode = "MAINTENANCE"
            date_str = row['date'].strftime('%Y-%m-%d') if pd.notnull(row['date']) else "Unknown"
            reason = f"Safety Protocol Triggered on {date_str}"
            break
            
    return {
        "active_projects": active_projects,
        "idea_seeds": ideas,
        "system_status": {
            "mode": throttle_mode,
            "reason": reason
        }
    }

def compaction_process():
    # 1. 檢查是否有新檔案
    md_files = glob.glob(os.path.join(INBOX_PATH, "*.md"))
    if not md_files:
        print("No files to compact.")
        # 即使沒有新檔案，也重新生成 System State (可能上次刪檔後未更新)
        # 但如果連 Parquet 都沒有，就無法生成
        if not os.path.exists(ARCHIVE_PARQUET_PATH):
            return
            
    print(f"Starting compaction for {len(md_files)} entries...")

    # 2. 讀取現有 Parquet (作為基底)
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
            # 讀取 MD
            post = frontmatter.load(md_file)
            entry = post.metadata
            
            # 確保有 date 欄位
            if 'date' not in entry: 
                filename = os.path.basename(md_file)
                if filename[:8].isdigit():
                    entry['date'] = f"{filename[:4]}-{filename[4:6]}-{filename[6:8]}"
                else:
                    entry['date'] = str(post.get('date'))[:10] if post.get('date') else "1970-01-01"
            
            # 將內容放入 content 欄位
            entry['content'] = post.content
            entry['note'] = post.content 
            
            # 讀取 JSON Sidecar
            json_file = md_file.replace(".md", ".json")
            if os.path.exists(json_file):
                with open(json_file, 'r', encoding='utf-8') as f:
                    sidecar = json.load(f)
                    if 'analysis' in sidecar:
                        entry['ai_analysis'] = sidecar['analysis'] 
                        # 嘗試將 AI 分析的 mood/focus 覆蓋回去
                        if 'mood' not in entry and 'mood' in sidecar['analysis']:
                            entry['mood'] = sidecar['analysis']['mood']
                    
                    # Embedding 存入 Parquet
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
            # 確保格式一致
            if 'date' in df_new.columns:
                df_new['date'] = pd.to_datetime(df_new['date'])
            if not df_base.empty and 'date' in df_base.columns:
                df_base['date'] = pd.to_datetime(df_base['date'])

            df_combined = pd.concat([df_base, df_new], ignore_index=True)
        else:
            df_combined = df_base.copy()
        
        # 去重
        if 'uuid' in df_combined.columns:
            df_combined = df_combined.drop_duplicates(subset=['uuid'], keep='last')
        else:
            df_combined = df_combined.drop_duplicates(subset=['date'], keep='last')

        # 排序 (日期舊 -> 新)
        df_combined = df_combined.sort_values(by='date')

        # [NEW] 產出系統狀態檔 (System State)
        try:
            print("Analyzing System State...")
            system_state = generate_system_state(df_combined)
            os.makedirs(os.path.dirname(SYSTEM_STATE_PATH), exist_ok=True)
            with open(SYSTEM_STATE_PATH, "w", encoding="utf-8") as f:
                json.dump(system_state, f, ensure_ascii=False, indent=2)
            print(f"✅ System State Updated: {SYSTEM_STATE_PATH}")
        except Exception as e:
            print(f"❌ System State Generation Failed: {e}")

        # [OUTPUT 1] 寫入 Parquet
        if not df_combined.empty:
            os.makedirs(os.path.dirname(ARCHIVE_PARQUET_PATH), exist_ok=True)
            df_combined.to_parquet(ARCHIVE_PARQUET_PATH, compression='snappy')
            print(f"Compacted to {ARCHIVE_PARQUET_PATH}")

            # [OUTPUT 2] 寫入 JSON (給前端)
            df_export = df_combined.copy()
            if 'embedding' in df_export.columns:
                df_export = df_export.drop(columns=['embedding'])
            if 'date' in df_export.columns:
                df_export['date'] = df_export['date'].dt.strftime('%Y-%m-%d')
            
            df_export.to_json(ARCHIVE_JSON_PATH, orient='records', force_ascii=False, date_format='iso')
            print(f"Exported JSON to {ARCHIVE_JSON_PATH}")

        # 5. 清理 Inbox
        for f in files_to_delete:
            if os.path.exists(f):
                os.remove(f)
        if files_to_delete:
            print("Inbox cleaned.")

if __name__ == "__main__":
    compaction_process()
