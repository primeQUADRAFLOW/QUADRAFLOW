"""
ツールレジストリ
エージェントが使用できるツールの実装
"""

import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Any, Callable, Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class ToolResult:
    """ツール実行結果"""

    def __init__(self, success: bool, output: str, error: Optional[str] = None):
        self.success = success
        self.output = output
        self.error = error

    def __str__(self) -> str:
        if self.success:
            return self.output
        return f"エラー: {self.error}\n{self.output}"


class ToolRegistry:
    """ツールを登録・管理するレジストリ"""

    def __init__(self, workspace: str = "./workspace", message_bus=None, agent_id: str = ""):
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.message_bus = message_bus
        self.agent_id = agent_id
        self._tools: dict[str, Callable] = {}
        self._register_builtin_tools()

    def _register_builtin_tools(self):
        """組み込みツールを登録する"""
        self._tools["shell"] = self._tool_shell
        self._tools["file_read"] = self._tool_file_read
        self._tools["file_write"] = self._tool_file_write
        self._tools["web_fetch"] = self._tool_web_fetch
        self._tools["web_search"] = self._tool_web_search
        self._tools["send_message"] = self._tool_send_message

    def register(self, name: str, func: Callable):
        """カスタムツールを登録する"""
        self._tools[name] = func

    def get_available(self, allowed_tools: list[str]) -> dict[str, Callable]:
        """エージェントが使用可能なツール一覧を返す"""
        return {name: func for name, func in self._tools.items() if name in allowed_tools}

    def get_tool_descriptions(self, allowed_tools: list[str]) -> str:
        """システムプロンプト用のツール説明文を生成する"""
        descriptions = {
            "shell": "shell(command: str) -> コマンドを実行して結果を返す。タイムアウト30秒。",
            "file_read": "file_read(path: str) -> ファイルを読み込んで内容を返す。",
            "file_write": "file_write(path: str, content: str) -> ファイルに内容を書き込む。ディレクトリは自動作成。",
            "web_fetch": "web_fetch(url: str) -> URLのページ内容をテキストとして取得する。",
            "web_search": "web_search(query: str) -> Google検索を実行して結果リストを返す。",
            "send_message": "send_message(to: str, content: str) -> 指定エージェントにメッセージを送信する。",
        }
        lines = []
        for tool in allowed_tools:
            if tool in descriptions:
                lines.append(f"- {descriptions[tool]}")
        return "\n".join(lines)

    async def execute(self, tool_name: str, params: dict, allowed_tools: list[str]) -> ToolResult:
        """ツールを実行する"""
        if tool_name not in allowed_tools:
            return ToolResult(False, "", f"ツール '{tool_name}' は許可されていません")

        if tool_name not in self._tools:
            return ToolResult(False, "", f"ツール '{tool_name}' は存在しません")

        try:
            func = self._tools[tool_name]
            result = await func(**params)
            return result
        except TypeError as e:
            return ToolResult(False, "", f"パラメータエラー: {e}")
        except Exception as e:
            logger.exception(f"ツール実行エラー ({tool_name}): {e}")
            return ToolResult(False, "", f"実行エラー: {e}")

    # ---- 組み込みツール実装 ----

    async def _tool_shell(self, command: str) -> ToolResult:
        """シェルコマンドを実行する"""
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.workspace),
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            except asyncio.TimeoutError:
                proc.kill()
                return ToolResult(False, "", "コマンドがタイムアウトしました（30秒）")

            output = stdout.decode("utf-8", errors="replace")
            err = stderr.decode("utf-8", errors="replace")

            if proc.returncode == 0:
                return ToolResult(True, output)
            else:
                return ToolResult(False, output, err)
        except Exception as e:
            return ToolResult(False, "", str(e))

    async def _tool_file_read(self, path: str) -> ToolResult:
        """ファイルを読み込む"""
        try:
            p = Path(path)
            if not p.is_absolute():
                p = self.workspace / path
            if not p.exists():
                return ToolResult(False, "", f"ファイルが存在しません: {path}")
            content = p.read_text(encoding="utf-8", errors="replace")
            # 最大50000文字に制限
            if len(content) > 50000:
                content = content[:50000] + "\n...(以下省略)..."
            return ToolResult(True, content)
        except Exception as e:
            return ToolResult(False, "", str(e))

    async def _tool_file_write(self, path: str, content: str) -> ToolResult:
        """ファイルに書き込む"""
        try:
            p = Path(path)
            if not p.is_absolute():
                p = self.workspace / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return ToolResult(True, f"ファイルを書き込みました: {p}")
        except Exception as e:
            return ToolResult(False, "", str(e))

    async def _tool_web_fetch(self, url: str) -> ToolResult:
        """URLのコンテンツを取得してテキスト抽出する"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            # スクリプト・スタイルを除去
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()

            text = soup.get_text(separator="\n", strip=True)
            # 連続する空行を削除
            lines = [line for line in text.splitlines() if line.strip()]
            clean_text = "\n".join(lines)

            if len(clean_text) > 10000:
                clean_text = clean_text[:10000] + "\n...(以下省略)..."

            return ToolResult(True, clean_text)
        except Exception as e:
            return ToolResult(False, "", str(e))

    async def _tool_web_search(self, query: str) -> ToolResult:
        """Google検索を実行して結果を返す"""
        try:
            url = f"https://www.google.com/search?q={httpx.URL('').copy_with(params={'q': query}).params}"
            # URLエンコードを手動で
            import urllib.parse
            encoded_query = urllib.parse.quote(query)
            search_url = f"https://www.google.com/search?q={encoded_query}&hl=ja"

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "ja,en;q=0.9",
            }

            async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
                response = await client.get(search_url, headers=headers)

            soup = BeautifulSoup(response.text, "html.parser")
            results = []

            # 検索結果のタイトルとURLを抽出
            for g in soup.find_all("div", class_="g")[:8]:
                title_el = g.find("h3")
                link_el = g.find("a")
                snippet_el = g.find("div", class_=["VwiC3b", "yXK7lf"])

                if title_el and link_el:
                    title = title_el.get_text(strip=True)
                    href = link_el.get("href", "")
                    snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                    if href.startswith("/url?"):
                        # Googleのリダイレクト URL をパース
                        import urllib.parse
                        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                        href = parsed.get("q", [href])[0]
                    results.append(f"- {title}\n  URL: {href}\n  {snippet}")

            if not results:
                # フォールバック: テキスト全体から情報を抽出
                text = soup.get_text(separator="\n", strip=True)[:3000]
                return ToolResult(True, f"検索結果:\n{text}")

            output = f"「{query}」の検索結果:\n\n" + "\n\n".join(results)
            return ToolResult(True, output)

        except Exception as e:
            return ToolResult(False, "", f"検索エラー: {e}")

    async def _tool_send_message(self, to: str, content: str) -> ToolResult:
        """別エージェントにメッセージを送信する"""
        if not self.message_bus:
            return ToolResult(False, "", "メッセージバスが設定されていません")

        from quadraflow.core.messaging import Message
        msg = Message(
            from_agent=self.agent_id,
            to_agent=to,
            content=content,
        )
        await self.message_bus.send(msg)
        return ToolResult(True, f"エージェント '{to}' にメッセージを送信しました")
