"""
ArielOS SkillManager — 小腦技能自動搜尋、安裝與執行模組
混合模式：Python 技能用 import / MCP 技能用常駐 subprocess + JSON-RPC
"""

import json, subprocess, re, os, time, threading, uuid, datetime, requests, logging, sys, shlex, shutil
from pathlib import Path
from ddgs import DDGS

# Ollama API Configuration
OLLAMA_API = "http://127.0.0.1:11434/api/generate"

# 模型配置 (與 ariel_bridge.py 同步)
CEREBELLUM_MODEL = "gemma3:4b-it-q4_K_M"
CEREBELLUM_FALLBACK_MODEL = "gemma3:4b"

def cerebellum_call(prompt: str, temperature: float = 0.3, timeout: int = 120,
                    num_ctx: int = 2048, num_predict: int = 256) -> str:
    """🧠 小腦統一呼叫介面（含自動模型降級）"""
    payload = {
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_ctx": num_ctx,
            "num_predict": num_predict
        }
    }
    # 嘗試主要模型
    try:
        resp = requests.post(OLLAMA_API, json={**payload, "model": CEREBELLUM_MODEL}, timeout=timeout)
        return resp.json().get('response', '').strip()
    except Exception as e:
        _log(f"⚠️ [{CEREBELLUM_MODEL}] 失敗，降級至 {CEREBELLUM_FALLBACK_MODEL}: {e}")
    
    # 降級：使用備用模型
    try:
        resp = requests.post(OLLAMA_API, json={**payload, "model": CEREBELLUM_FALLBACK_MODEL}, timeout=timeout)
        return resp.json().get('response', '').strip()
    except Exception as e:
        _log(f"❌ 小腦呼叫徹底失敗: {e}")
        return ""


def _log(msg):
    t = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{t}] 🔧 [SkillMgr] {msg}")


class MCPConnection:
    """常駐 MCP Server 連線 (stdin/stdout JSON-RPC)"""

    def __init__(self, name, cmd):
        self.name = name
        self.cmd = cmd
        self.process = None
        self.lock = threading.Lock()

    def start(self):
        """啟動 MCP server 為常駐背景進程"""
        if self.process and self.process.poll() is None:
            return True  # 已經在跑
        try:
            # 將指令字串安全解析為 list 避免 shell=True 導致 Windows 管線卡死
            cmd_args = shlex.split(self.cmd)
            if cmd_args and cmd_args[0] in ('npx', 'npx.cmd'):
                npx_path = shutil.which('npx.cmd') if os.name == 'nt' else shutil.which('npx')
                if npx_path:
                    cmd_args[0] = npx_path
                
            # 完全繞過 PowerShell profile 劫持 (例如 sandbox-exec 錯誤)
            env = os.environ.copy()
            # 強制移除所有可能觸發 PowerShell alias 的變數
            env.pop('PSModulePath', None)
            
            self.process = subprocess.Popen(
                cmd_args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                shell=False,
                bufsize=0,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            _log(f"✅ MCP Server [{self.name}] 已啟動 (PID={self.process.pid})")
            return True
        except Exception as e:
            _log(f"❌ MCP Server [{self.name}] 啟動失敗: {e}")
            return False

    def call(self, method, params=None):
        """透過 JSON-RPC 呼叫 MCP server"""
        with self.lock:
            if not self.process or self.process.poll() is not None:
                if not self.start():
                    return None
            try:
                request_obj = {
                    "jsonrpc": "2.0",
                    "id": str(uuid.uuid4()),
                    "method": method,
                    "params": params or {}
                }
                msg = json.dumps(request_obj) + "\n"
                self.process.stdin.write(msg)
                self.process.stdin.flush()

                # 讀取回應 (含超時)
                self.process.stdout.flush()
                line = self.process.stdout.readline()
                if line:
                    return json.loads(line.strip())
                
                # 如果讀不到資料，檢查進程是否已經崩潰
                if self.process.poll() is not None:
                    err_lines = self.process.stderr.readlines()
                    err = "".join(err_lines).strip()
                    _log(f"⚠️ MCP Server 崩潰退出 (Code={self.process.returncode})\nStderr: {err}")
                    return {"error": err or "未知崩潰"}
                
            except Exception as e:
                _log(f"⚠️ MCP 呼叫失敗 [{self.name}]: {e}")
            return None

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            _log(f"🛑 MCP Server [{self.name}] 已停止")


class SkillManager:
    """ArielOS 技能管理器"""

    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.registry_path = self.base_dir / "Shared_Vault" / "skills_registry.json"
        self._mcp_connections = {}  # name -> MCPConnection
        self._ensure_registry()
        _log(f"SkillManager 初始化完成 | Registry: {self.registry_path}")

    # ─── Registry I/O ────────────────────────────────────

    def _ensure_registry(self):
        if not self.registry_path.exists():
            self._save_registry({
                "installed_skills": [],
                "mcp_catalog": []
            })

    def _load_registry(self):
        try:
            with open(self.registry_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"installed_skills": [], "mcp_catalog": []}

    def _save_registry(self, data):
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ─── Public API ──────────────────────────────────────

    def list_installed(self):
        """列出已安裝技能"""
        return self._load_registry().get("installed_skills", [])

    def list_catalog(self):
        """列出 MCP 官方技能目錄"""
        return self._load_registry().get("mcp_catalog", [])

    def find_matching_skill(self, query):
        """
        在已安裝技能 + MCP 目錄中尋找匹配技能。
        使用關鍵字積分比對 (匹配關鍵字總長度最高者勝出)。
        """
        query_lower = query.lower()
        registry = self._load_registry()

        best_skill = None
        best_score = 0

        all_skills = registry.get("installed_skills", []) + registry.get("mcp_catalog", [])
        
        for skill in all_skills:
            score = 0
            for kw in skill.get("keywords", []):
                if kw.lower() in query_lower:
                    score += len(kw) * 10
                    # 如果關鍵字完全等於輸入，給極高分數
                    if kw.lower() == query_lower.strip():
                        score += 1000
            
            if score > best_score:
                best_score = score
                best_skill = skill
            elif score == best_score and score > 0:
                # 遇到平手 (Keyword collision)，交由 LLM 進行精確匹配判斷
                best_skill = None
                
        return best_skill

    def find_skill_by_llm(self, query):
        """
        使用小腦 LLM 分析使用者意圖，萃取關鍵字後比對技能。
        僅在 find_matching_skill 無結果時使用 (約 2-5s)。
        """
        import requests

        all_skills = self.list_catalog() + self.list_installed()
        if not all_skills:
            return None

        skills_desc = "\n".join([
            f"ID:{i} | {s['name']}: {s['description']} (keywords: {', '.join(s.get('keywords', []))})"
            for i, s in enumerate(all_skills)
        ])

        instruction = (
            f"你是 ArielOS 技能匹配引擎。可用技能清單：\n{skills_desc}\n\n"
            f"使用者需求：『{query}』\n"
            "【嚴格規則】\n"
            "1. 若使用者明確要求「執行」某項功能 (例如: 幫我查 CPU、整理檔案)，且清單中有對應技能，回傳其 ID 數字。\n"
            "2. 若使用者只是在「詢問資訊」(例如: 你會什麼？有哪些技能？)，這不是執行技能的意圖，請立刻回傳 NO。\n"
            "3. 若無匹配技能，回傳 NO。\n"
            "僅回傳 ID 或 NO，不要多說。"
        )

        try:
            judgment = cerebellum_call(
                prompt=instruction,
                temperature=0,
                timeout=120,
                num_ctx=2048,
                num_predict=10
            )
            if "NO" not in judgment.upper():
                match = re.search(r'\d+', judgment)
                if match:
                    idx = int(match.group())
                    if 0 <= idx < len(all_skills):
                        _log(f"🎯 LLM 技能命中: {all_skills[idx]['name']}")
                        return all_skills[idx]
        except Exception as e:
            _log(f"⚠️ LLM 技能匹配異常: {e}")

        return None

    def _extract_english_search_terms(self, query):
        """將使用者需求轉換為英文搜尋關鍵字 (針對 PyPI/MCP)"""
        import requests
        instruction = (
            f"Convert this user query into 2-4 English search keywords for finding a software library or tool.\n"
            f"Query: '{query}'\n"
            f"Keywords (space separated, no explanation):"
        )
        try:
            return cerebellum_call(
                prompt=instruction,
                temperature=0,
                timeout=120,
                num_ctx=1024,
                num_predict=30
            ).replace('"', '')
        except: return None

    def search_skill_online(self, query):
        """
        從 GitHub / MCP 倉庫 / 網路搜尋可用技能。
        回傳候選技能清單。
        """
        candidates = []
        
        # 0. 關鍵字優化：若含中文，轉為英文關鍵字以利搜尋
        search_terms = query
        if any(u'\u4e00' <= c <= u'\u9fff' for c in query):
            translated = self._extract_english_search_terms(query)
            if translated:
                search_terms = translated
                _log(f"🔤 關鍵字轉換: '{query}' → '{search_terms}'")

        # 1. 先在內建 MCP 目錄中搜尋 (使用原始 query 與 英文 terms)
        catalog = self.list_catalog()
        for skill in catalog:
            for kw in skill.get("keywords", []):
                if kw.lower() in query.lower() or kw.lower() in search_terms.lower():
                    candidates.append(skill)
                    break

        if candidates:
            _log(f"📦 MCP 目錄命中 {len(candidates)} 個技能")
            return candidates

        # 2. DuckDuckGo 搜尋 MCP servers (3-5s)
        _log(f"🌐 線上搜尋技能: {search_terms}")
        try:
            search_query = f"MCP server {search_terms} github modelcontextprotocol"
            results = DDGS().text(search_query, max_results=5)

            for r in results:
                title = r.get('title', '')
                body = r.get('body', '')
                href = r.get('href', '')

                # 解析 GitHub 上的 MCP server
                if 'github.com' in href and any(k in title.lower() for k in ['mcp', 'server', 'tool']):
                    # 優先檢查是否為官方 monorepo 的子套件 (如 @modelcontextprotocol/server-weather)
                    sub_pkg_match = re.search(r'(@modelcontextprotocol/server-[a-z-]+)', body + " " + title)
                    if sub_pkg_match:
                        pkg_name = sub_pkg_match.group(1)
                        _log(f"✨ 偵測到官方 MCP 套件: {pkg_name}")
                    else:
                        pkg_match = re.search(r'github\.com/([^/]+/[^/]+)', href)
                        repo_name = pkg_match.group(1) if pkg_match else title
                        pkg_name = f"github:{repo_name}" if "github.com" in href else title

                    candidates.append({
                        "name": title[:50],
                        "description": body[:100],
                        "keywords": query.lower().split(),
                        "type": "mcp",
                        "package": pkg_name,
                        "source_url": href,
                        "run_cmd": f"npx -y {pkg_name}"
                    })

            if candidates:
                _log(f"🌐 線上找到 {len(candidates)} 個候選技能")
        except Exception as e:
            _log(f"⚠️ 線上搜尋失敗: {e}")

        # 3. 搜尋 pip/Python 套件
        if not candidates:
            try:
                search_query = f"python {search_terms} library pip"
                results = DDGS().text(search_query, max_results=3)
                for r in results:
                    if 'pypi.org' in r.get('href', ''):
                        pkg_match = re.search(r'pypi\.org/project/([^/]+)', r['href'])
                        if pkg_match:
                            pkg_name = pkg_match.group(1)
                            candidates.append({
                                "name": pkg_name,
                                "description": r.get('body', '')[:100],
                                "keywords": query.lower().split(),
                                "type": "pip",
                                "package": pkg_name,
                                "source_url": r['href'],
                                "run_cmd": f"python -c \"import {pkg_name}\""
                            })
            except Exception as e:
                _log(f"⚠️ PyPI 搜尋失敗: {e}")

        return candidates

    def install_skill(self, skill_info):
        """
        自動安裝技能 (不詢問)。
        pip → pip install / npm/mcp → npx -y (自動下載)
        """
        skill_type = skill_info.get("type", "mcp")
        package = skill_info.get("package", "")
        name = skill_info.get("name", "unknown")

        _log(f"📦 正在安裝技能: {name} ({skill_type}: {package})")

        try:
            if skill_type == "pip":
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", package],
                    capture_output=True, text=True, encoding='utf-8', timeout=120
                )
                if result.returncode != 0:
                    _log(f"❌ pip 安裝失敗: {result.stderr[:200]}")
                    return False

            elif skill_type in ("mcp", "npm"):
                # 解決 Windows 上 subprocess 搭配 shell=True 與 timeout 導致管線卡死的 Bug
                npm_bin = 'npm.cmd' if os.name == 'nt' else 'npm'
                npm_path = shutil.which(npm_bin) or npm_bin
                
                # 完全繞過 PowerShell profile 劫持
                env = os.environ.copy()
                env.pop('PSModulePath', None)

                # 🤖 強化版驗證：改用 npm view 並加上 --json 來確保輸出的純粹，避免互動式提示
                test_cmd = [npm_path, "view", package, "version", "--json"]
                _log(f"🔍 執行驗證指令: {' '.join(test_cmd)}")
                
                start_t = time.time()
                try:
                    result = subprocess.run(
                        test_cmd,
                        capture_output=True, text=True, encoding='utf-8', timeout=30, # 縮短至 30s，驗證不該太久
                        env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    )
                    elapsed = time.time() - start_t
                    _log(f"⏱️ 驗證耗時: {elapsed:.2f}s | ReturnCode: {result.returncode}")
                except subprocess.TimeoutExpired:
                    _log(f"⚠️ 驗證逾時 (30s)，但考量網路環境，我們仍嘗試繼續安裝程序...")
                    return True # 逾時也放行，交給 npx 執行時下載就好，避免卡死用戶
                
                if result.returncode != 0:
                    # 有些公司內部網路抓不到外部套件，這裡給予警告但不要完全卡死
                    _log(f"⚠️ npm view 驗證失敗 (可能網路受限): {result.stderr[:100]}")
                    # 決定放行，讓 npx 執行時自己去處理下載與重試
                    return True 
                
                _log(f"✅ npm 套件驗證完畢: {package}")

            # 記錄到 registry
            registry = self._load_registry()
            # 避免重複安裝
            existing_names = [s['name'] for s in registry['installed_skills']]
            if name not in existing_names:
                skill_record = {
                    "name": name,
                    "description": skill_info.get("description", ""),
                    "keywords": skill_info.get("keywords", []),
                    "type": skill_type,
                    "package": package,
                    "run_cmd": skill_info.get("run_cmd", ""),
                    "installed_at": datetime.datetime.now().isoformat(),
                    "status": "active"
                }
                registry["installed_skills"].append(skill_record)
                self._save_registry(registry)

            _log(f"✅ 技能安裝成功: {name}")
            return True

        except subprocess.TimeoutExpired:
            _log(f"⏱️ 安裝逾時: {name}")
            return False
        except Exception as e:
            _log(f"❌ 安裝異常: {e}")
            return False

    def execute_skill(self, skill_info, query, **kwargs):
        """
        執行技能。
        - pip 技能: 直接 Python import + 呼叫
        - MCP 技能: 常駐 subprocess JSON-RPC 或一次性呼叫
        若有額外參數 (如 gas_url) 將以全大寫的環境變數注入。
        """
        skill_type = skill_info.get("type", "mcp")
        name = skill_info.get("name", "unknown")
        run_cmd = skill_info.get("run_cmd", "")

        _log(f"⚡ 執行技能: {name} | 類型: {skill_type}")

        try:
            if skill_type == "pip":
                return self._execute_pip_skill(skill_info, query, **kwargs)
            elif skill_type in ("mcp", "npm"):
                return self._execute_mcp_skill(skill_info, query, **kwargs)
        except Exception as e:
            _log(f"❌ 技能執行失敗 [{name}]: {e}")

        return None

    def _execute_pip_skill(self, skill_info, query, **kwargs):
        """直接 import Python 模組執行或執行註冊的本機腳本"""
        package = skill_info.get("package", "")
        name = skill_info.get("name", "")
        run_cmd = skill_info.get("run_cmd", "")

        # 完全繞過 PowerShell profile 劫持
        env = os.environ.copy()
        env.pop('PSModulePath', None)
        
        # 注入動態來源參數 (例如 Agent 傳進來的 gas_url -> GAS_URL)
        for k, v in kwargs.items():
            if v:
                env[k.upper()] = str(v)

        # 1. 若有指定本機腳本 (例如自製的 free_weather.py)，優先直接執行
        if run_cmd and run_cmd.startswith("python "):
            script_path = run_cmd.replace("python ", "").strip()
            if os.path.exists(script_path):
                _log(f"🚀 直接執行本機 Python 技能腳本: {script_path}")
                result = subprocess.run(
                    [sys.executable, script_path, query],
                    capture_output=True, text=True, encoding='utf-8', timeout=120,
                    env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                stdout = result.stdout or ""
                stderr = result.stderr or ""
                output = (stdout + "\n" + stderr).strip()
                if output:
                    return f"[技能: {name}]\n{output}"
                else:
                    return f"[技能: {name}] 無輸出結果 (Script Executed)"

        # 2. 若沒有腳本，使用小腦生成執行程式碼
        import requests
        instruction = (
            f"你是 Python 程式碼生成器。使用者需要用 `{package}` 套件完成：『{query}』\n"
            f"請生成一段極簡的 Python 程式碼來完成此任務。\n"
            "僅回傳可直接執行的程式碼 (不含 markdown 標記)，用 print() 輸出結果。"
        )

        code = cerebellum_call(
            prompt=instruction,
            temperature=0.2,
            timeout=120,
            num_ctx=2048,
            num_predict=512
        )
        # 清理 markdown code block
        code = re.sub(r'^```\w*\n?', '', code)
        code = re.sub(r'\n?```$', '', code)

        # 完全繞過 PowerShell profile 劫持
        env = os.environ.copy()
        env.pop('PSModulePath', None)

        # 在隔離進程中執行
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, encoding='utf-8', timeout=120,
            env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )

        output = result.stdout.strip()
        if not output:
            output = result.stderr.strip()

        if output:
            _log(f"✅ pip 技能完成: {name} | 輸出長度: {len(output)}")
            return f"[技能: {name}]\n{output}"

        return None

    def _execute_mcp_skill(self, skill_info, query, **kwargs):
        """
        MCP 技能執行：使用常駐連線 (效能模式) 或一次性呼叫 (備用)。
        """
        name = skill_info.get("name", "")
        run_cmd = skill_info.get("run_cmd", "")

        # 嘗試常駐連線模式
        if name not in self._mcp_connections:
            self._mcp_connections[name] = MCPConnection(name, run_cmd)

        conn = self._mcp_connections[name]

        # 嘗試 JSON-RPC 呼叫
        response = conn.call("tools/list")
        
        # 若發生啟動崩潰，直接中斷幻覺備援模式，顯示真實錯誤
        if response and "error" in response:
            return f"[技能執行錯誤]\n啟動 MCP 伺服器失敗，可能缺少 API Key 變數或有設定錯誤：\n{response['error']}"
            
        if response and "result" in response:
            tools = response["result"].get("tools", [])
            if tools:
                # 用小腦選擇合適的 tool 並生成參數
                tool_result = self._mcp_select_and_call(conn, tools, query, name)
                if tool_result:
                    return tool_result

        # 備用方案：一次性 subprocess 呼叫
        _log(f"🔄 [{name}] 降級至一次性呼叫模式")
        return self._execute_mcp_oneshot(skill_info, query, **kwargs)

    def _mcp_select_and_call(self, conn, tools, query, skill_name):
        """用小腦選擇 MCP tool 並呼叫"""
        import requests

        tools_desc = "\n".join([
            f"ID:{i} | {t['name']}: {t.get('description', '')}"
            for i, t in enumerate(tools)
        ])

        instruction = (
            f"MCP Server [{skill_name}] 可用工具：\n{tools_desc}\n\n"
            f"使用者需求：『{query}』\n"
            "選擇最合適的工具並回傳 JSON：{\"tool_id\": 數字, \"arguments\": {{...}}}\n"
            "僅回傳 JSON。"
        )

        try:
            raw = cerebellum_call(
                prompt=instruction,
                temperature=0.1,
                timeout=120,
                num_ctx=2048,
                num_predict=256
            )
            json_str = re.search(r'\{.*\}', raw, re.DOTALL).group(0)
            selection = json.loads(json_str)

            tool_idx = selection.get("tool_id", 0)
            arguments = selection.get("arguments", {})

            if 0 <= tool_idx < len(tools):
                chosen = tools[tool_idx]
                result = conn.call("tools/call", {
                    "name": chosen["name"],
                    "arguments": arguments
                })
                if result and "result" in result:
                    content = result["result"]
                    if isinstance(content, dict):
                        text_parts = []
                        for item in content.get("content", []):
                            if item.get("type") == "text":
                                text_parts.append(item["text"])
                        return f"[技能: {skill_name}/{chosen['name']}]\n" + "\n".join(text_parts)
                    return f"[技能: {skill_name}]\n{json.dumps(content, ensure_ascii=False)}"
        except Exception as e:
            _log(f"⚠️ MCP tool 選擇/呼叫失敗: {e}")

        return None

    def _execute_mcp_oneshot(self, skill_info, query, **kwargs):
        """一次性呼叫 MCP server (備用模式)"""
        import requests

        name = skill_info.get("name", "")
        description = skill_info.get("description", "")

        # 用小腦結合技能資訊回答
        instruction = (
            f"你有一個工具叫做 [{name}]，功能是：{description}。\n"
            f"使用者問：『{query}』\n"
            f"請運用此工具的概念簡潔地回答使用者的問題。"
        )

        _log(f"🧠 正在引導本地模型運用此技能 (依硬體效能可能需時 1~2 分鐘，請耐心等候)...")

        try:
            answer = cerebellum_call(
                prompt=instruction,
                temperature=0.3,
                timeout=180,
                num_ctx=2048,
                num_predict=256
            )
            if answer:
                return f"[技能: {name} (概念資訊)]\n我目前無法直接執行此工具的操作，但我理解它的功能：\n{answer}"
        except Exception as e:
            _log(f"⚠️ MCP oneshot 失敗: {e}")

        return None

    def remove_skill(self, name):
        """移除已安裝技能"""
        registry = self._load_registry()
        original_len = len(registry["installed_skills"])
        registry["installed_skills"] = [
            s for s in registry["installed_skills"] if s["name"] != name
        ]
        if len(registry["installed_skills"]) < original_len:
            self._save_registry(registry)
            # 停止常駐連線
            if name in self._mcp_connections:
                self._mcp_connections[name].stop()
                del self._mcp_connections[name]
            _log(f"🗑️ 技能已移除: {name}")
            return True
        return False

    def shutdown(self):
        """停止所有常駐 MCP 連線"""
        for name, conn in self._mcp_connections.items():
            conn.stop()
        self._mcp_connections.clear()
        _log("🛑 所有 MCP 連線已關閉")
