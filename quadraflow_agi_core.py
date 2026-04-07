import os
import json
import time
import uuid
from datetime import datetime
import urllib.request
import urllib.error

# PrimeQUADRAFLOW: AGI Master Orchestrator
# モデル: Gemma 4 (26B A4B Local)
# 目的: アナリティクスデータの解析と、12体のOpenClawエージェントへの全自動タスク投下

OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "gemma4:26b"
OPENCLAW_MESSAGES_DIR = os.path.expanduser(r"~/.openclaw/shared/messages")

def call_local_gemma(prompt: str) -> str:
    """ローカルのGemma 4を呼び出し、意思決定を行わせる"""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_ctx": 16384 # 高度な推論用にコンテキストを拡大
        }
    }
    
    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(
        OLLAMA_API_URL, 
        data=json.dumps(payload).encode('utf-8'), 
        headers=headers
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get("response", "")
    except urllib.error.URLError as e:
        print(f"[-] ローカルOllamaへの接続に失敗しました: {e}")
        return "ERROR: Gemma 4 unreachable."

def get_latest_sales_data() -> str:
    """（モック）直近24時間の売上・エンゲージメントデータを取得"""
    # 実際はStripe APIやXのAnalyticsスクレイピング結果などを統合する
    return """
    日時: 2026-04-07
    [エンゲージメント分析]
    - テーマ「Claude Codeの全自動化」のX投稿がインプレッション 15,200 (+400%)
    - テーマ「初心者の副業」のX投稿がインプレッション 800 (-20%)
    
    [販売分析]
    - note「AIエージェント完全自動化マニュアル」: 3件販売 (利益: 2,940円)
    - Gumroad「MCPテンプレ」: 1件販売 (利益: 1,500円)
    """

def strategize_with_agi(sales_data: str) -> dict:
    """売上データに基づきGemma4が「次に作るべき商品とプロモーション」を決定する"""
    prompt = f"""
あなたは PrimeQUADRAFLOW のCEO（最高意思決定AGI）です。
目的は「システムの完全自動収益化（最大化）」です。

以下の直近24時間のエンゲージメント・販売データに基づき、
今日（これから24時間）で作成・販売すべき「デジタル商品」のテーマと、
それに紐づく「SNS集客用」のテーマを決定してください。

必ず以下のJSONフォーマットのみ（Markdown修飾なし）で返答してください。

[データ]
{sales_data}

[出力フォーマット]
{{
  "product_title": "作成すべき有料記事や商品のタイトル",
  "product_type": "note または gumroad",
  "marketing_angle": "XやMoltbookでどうやってバズを作って販売リンクに誘導するかの方針（100文字）",
  "target_agent": "指示を出す主要エージェント名 (例: content-creator, tech-writer)"
}}
"""
    response_text = call_local_gemma(prompt)
    
    # 簡単なJSONパース処理
    try:
        # Markdownのコードブロックを除去
        text = response_text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
            
        strategy = json.loads(text.strip())
        return strategy
    except Exception as e:
        print(f"[-] AGI推論のJSONパースに失敗しました: {e}")
        print(f"生の出力: {response_text}")
        # フォールバック
        return {
            "product_title": "AIコーディングの極意",
            "product_type": "note",
            "marketing_angle": "開発効率10倍をアピールしてnoteへ誘導",
            "target_agent": "tech-writer"
        }

def dispatch_task_to_agent(target_agent: str, strategy: dict):
    """OpenClawエージェントに自律タスクを投下する"""
    agent_inbox = os.path.join(OPENCLAW_MESSAGES_DIR, target_agent, "inbox")
    os.makedirs(agent_inbox, exist_ok=True)
    
    task_id = str(uuid.uuid4())
    task_payload = {
        "id": task_id,
        "timestamp": datetime.now().isoformat(),
        "from": "prime-agi-orchestrator",
        "priority": "high",
        "task_type": "monetization_cycle",
        "data": strategy
    }
    
    file_path = os.path.join(agent_inbox, f"task_{task_id}.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(task_payload, f, ensure_ascii=False, indent=2)
        
    print(f"[+] Task {task_id} を [{target_agent}] のInboxに投下しました。")
    print(f"    -> ミッション: {strategy.get('product_title')}")

def run_agi_cycle():
    print("=" * 50)
    print("🤖 PrimeQUADRAFLOW: AGI Monetization Cycle Triggered")
    print("=" * 50)
    
    print("[1] データ収集（アナリティクスエンジン連携）...")
    data = get_latest_sales_data()
    time.sleep(1)
    
    print("[2] Gemma 4 推論（戦略策定中）...")
    strategy = strategize_with_agi(data)
    print(f"    -> 決定事項: {strategy}")
    
    print("[3] 各エージェントへのタスクディスパッチ...")
    # プロダクト作成エージェントへ指示
    dispatch_task_to_agent(strategy.get("target_agent", "content-creator"), strategy)
    
    # SNSプロモーション（m.blue / x-longform）へ集客指示
    promotional_task = strategy.copy()
    promotional_task["task_type"] = "viral_hook_generation"
    dispatch_task_to_agent("mblue", promotional_task)
    dispatch_task_to_agent("x-longform-writer", promotional_task)
    
    print("[+] サイクル完了。各エージェントがバックグラウンドで稼働を開始します。")

if __name__ == "__main__":
    run_agi_cycle()
