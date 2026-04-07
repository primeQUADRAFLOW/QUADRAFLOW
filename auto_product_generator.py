import os
import json
from datetime import datetime

# AGIからの指示を受け取り、デジタル商品（note / Gumroad用）を全自動で生成・格納するモジュール
# OpenClawエージェント（tech-writer等）が叩く内部ツールとしても機能する

PRODUCTS_DIR = r"F:\PrimeQUADRAFLOW_Universe\20_Content_Strategy\Articles\published\monetization_products"

def generate_digital_product(title: str, product_type: str, content: str):
    """
    AGIによって決定されたデジタル生成物をファイルシステムに保存し、販売準備を整える。
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    safe_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c==' ']).rstrip().replace(" ", "_").lower()
    
    target_dir = os.path.join(PRODUCTS_DIR, product_type, date_str)
    os.makedirs(target_dir, exist_ok=True)
    
    file_path = os.path.join(target_dir, f"{safe_title}.md")
    
    # note / Gumroad 用の販売メタデータを付与して保存
    product_md = f"""---
title: "{title}"
type: "paid_{product_type}"
price: 980
status: "ready_to_publish"
created_at: "{datetime.now().isoformat()}"
---

# {title}

{content}

---
*この商品は PrimeQUADRAFLOW AGI によって自己生成されました。*
"""

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(product_md)
        
    print(f"[Product Generator] 商品パッケージが完成しました:")
    print(f" -> {file_path}")
    return file_path

if __name__ == "__main__":
    # テスト実行用
    generate_digital_product(
        title="Gemma 4 で作る完全自動化セールスファネル",
        product_type="note",
        content="（ここにAIが生成した有料記事本文となる詳細プロンプト・コード・ノウハウが展開されます）\n\n1. ローカルLLMを使った戦略\n2. OpenClawのフック実装..."
    )
