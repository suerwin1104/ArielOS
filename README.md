# 🤖 ArielOS v4.0 - 智慧型大小腦分離助理系統 (模組化版)

ArielOS 是一款基於 Python 與本地 AI 模型 (Ollama/OpenClaw) 建構的高效能秘書系統。採用獨創的「大小腦分離」架構，實現了秒回閒聊 (小腦) 與深度邏輯處理 (大腦) 的完美平衡。

> **v3.0 重大更新**：`ariel_bridge.py` 已重構為模組化結構。
> **v3.1 Intelligence Core**：引入 Qdrant 向量記憶與 Reviewer 審查循環。
> **v4.0 Unkillable & Life Core**：新增哨兵快照回滾、記憶隔離、生命感知 (年齡/傳記) 與一鍵安裝腳本。
> **v4.1 Programmatic Core**：新增 CPU 沙盒算力分流、`[PROGRAMMATIC]` 意圖，並極大化降低低配電腦 GPU 負擔。
> **v4.2 Hybrid AI Search Core**：新增 Playwright 真人偽裝探針，無縫穿透 Cloudflare 攔截 Google AI 與 Perplexity 摘要；新增 CPU 脊髓反射與 Ultra-Hit 語意快取。
> **v4.3 Centralized Skill Architecture**：GAS 雲端秘書全面技能化，支援多代理人獨立 GAS_URL 配置、強化型自然語言日期解析 (明天/下午) 與全域域名自動提取。
> **v4.4 Exa Search & Real-time Background Core**：整合 Exa AI 全球搜尋 API，將 GAS 模擬資料庫升級為「真實即時網路」；升級背景巡邏機制，支援新聞、信件、行程之增量更新 (Delta-Only) 與去重公告，實現零冗餘自動情報。
> **v4.5 Advanced Sensory Hierarchy & Localization**：實作三層感官分級（本地/雲端/深層探針），平衡 API 成本與主機效能；鎖定台灣 (TW) 區域搜尋與強制繁體中文輸出，並大幅強化 Ollama 通訊耐受度 (180s Timeout)。

## 📦 模組化架構 (v3.0)

```text
Central_Bridge/
├── ariel_bridge.py          # 入口：Flask 路由 + brain_worker
├── ariel_launcher.py        # 🛡️ 哨兵守護：快照、回滾與並行啟動
├── lite_setup.ps1           # ⚡ 一鍵安裝腳本 (Windows)
├── start_all.ps1            # 🚀 快速啟動：Bridge + Agents
└── modules/
    ├── __init__.py          # 模組套件標記
    ├── config.py            # 常數、路徑、模型名稱
    ├── cerebellum.py        # 小腦全套邏輯
    ├── personality.py       # PersonalityEngine
    ├── harness.py           # Shield / Harness
    ├── evolution.py         # 夜間蒸餾 / 生命感知 / 傳記撰寫
    └── vector_memory.py     # 向量記憶層 (Qdrant)
```

| 模組 | 職責 | 主要類別/函式 |
| --- | --- | --- |
| `config.py` | 常數、路徑、`log()`、`ollama_post()` | — |
| `cerebellum.py` | 所有 LLM 呼叫 (含 fallback + semaphore) | `cerebellum_call`, `cerebellum_fast_track_check`, `cerebellum_distill_context` |
| `personality.py` | 代理人人格、Dispatcher、脊髓反射 | `PersonalityEngine`, `AgentDispatcher`, `spinal_chord_reflex` |
| `harness.py` | 安全防護、L1 備份、L5 驗證、稽核日誌 | `Shield`, `Harness`, `AuditLogger` |
| `evolution.py` | 夜間萃取、好奇心排程、進化守則 | `perform_night_distillation`, `scheduler_worker` |
| `vector_memory.py` | 向量記憶 (Qdrant/NumPy) 【v3.1】 | `VectorMemoryManager`, `VM.add_fact`, `VM.query_semantic` |

---

## 🌟 核心架構 (System Architecture)

```mermaid
graph TD
    User[使用者] -->|Discord| Agent[代理人介面]
    Agent --> Bridge[中樞神經 Bridge]
    
    subgraph Bridge [Ariel OS 智慧中心]
        Bridge -->|快取命中| Cache[語意快取 JSON]
        Bridge -->|意圖判斷| FastTrack[小腦 Fast Track]
        
        FastTrack -->|Simple/Search| Cerebellum[小腦 Model]
        Cerebellum -->|DuckDuckGo| Internet[網際網路]
        
        FastTrack -->|Programmatic| Sandbox[CPU 資料沙盒 Sandbox]
        
        FastTrack -->|Skill| Skills[技能系統 SkillManager]
        FastTrack -->|Complex| Queue[任務佇列]
        
        Queue -->|自動註冊| Kanban[看板戰情室]
        Queue -->|依序處理| Brain[大腦 OpenClaw]
    end
    
    Sandbox -->|純文字/JSON結論| Cerebellum
    Cerebellum -->|風格轉移| FinalRes[回應]
    Brain -->|執行回報| Kanban
    Brain -->|純邏輯輸出| Cerebellum
```

### 🧠 大小腦分流機制

| 特性 | 小腦 (Cerebellum) | 大腦 (Brain / OpenClaw) |
| :--- | :--- | :--- |
| **核心模型** | `gemma3:4b-it-q4_K_M` (輕快/高穩定) | `OpenClaw` (深度邏輯) |
| **處理模式** | **並行處理 (Parallel)** | **單一佇列 (FIFO)** |
| **任務追蹤** | 即時回應，不進看板 | **自動同步至 Kanban 戰情室** |
| **聯網能力** | ✅ 支援 Playwright 隱形探針 (Google AI / Perplexity) 與 CPU 沙盒降級過濾 | ✅ 支援完整工具鏈 |
| **擴充性** | ✅ 程式化工具 (Programmatic) & 技能系統 | ✅ 系統級操作 |
| **反應速度** | 🚀 **脊髓反射 (<10ms)** | 🧠 深度思考 (>5s) |
| **記憶技術** | ⚡ JSON Cache / Regex | 🗄️ SQLite (B-tree Index) |

### 💻 算力分流與輕量化 (Programmatic Core v4.1)

為支援無獨立顯卡或低階配備的電腦，ArielOS 引入了全新的「算力轉移」機制，將 GPU 壓力大幅轉移至 CPU：

1. **程式化工具發送 (Programmatic Calling)**:
   當您要求「過濾日誌」、「分析大量資料排序」時，小腦會觸發 `[PROGRAMMATIC]` 意圖。系統不再將數千個 Token 塞進 GPU 消化，而是轉去命令 LLM 生成一段 **Python 腳本**，並直接在您的電腦 CPU 上執行，最後只把精華答案回傳。這使得資料處理速度飆升 10 倍以上。
2. **搜尋優化 (Search-to-Script)**:
   網路搜尋時抓取的 10 筆原始網頁資料，現在會直接以 JSON 存入 CPU 沙盒，由腳本讀取與過濾，徹底解決長文本導致模型崩潰與 OOM 的問題。
3. **支援平板外掛大腦 (遠端模型支援)**:
   支援修改 `config.py` 將推論轉交給在 Android 平板（例如 Samsung Tab S9 Ultra）上運行的 `MLC LLM`，達成 PC 端零顯存佔用。

### 🌐 終極反爬蟲與混合 AI 搜尋 (Hybrid AI Search v4.2)

為了提供最精準的資訊並極大化節省本地 GPU 算力，ArielOS 實作了業界頂尖的混合搜尋引擎機制：

1. **Playwright 隱形探針 (Stealth Probes)**:
   內建專屬的 Google AI 與 Perplexity 抓取探針。透過 `playwright-stealth` 抹除自動化指紋，並強制套用 `headless=False` 啟動真實本機 Chrome 視窗，輔以獨立的持久化組合檔 (Persistent Profile) 累積 Cookie 信任度，完美穿透最高級別的 Cloudflare Turnstile 與 Google CAPTCHA 機器人驗證。
2. **混合搜尋管線 (Hybrid Search Pipeline)**:
   當收到查詢時，系統會並行發射雙探針。只要任一 AI 引擎 (Google / Perplexity) 成功給出高品質摘要，工作流便會立刻中斷並回傳結果。若所有 AI 探針皆逾時或遭阻擋，系統能在短時間內無縫回退至「DDGS 傳統搜尋 + CPU 程式化過濾」，保證最終必定產出結論。
3. **CPU 脊髓反射與 Ultra-Hit 快取 (Spinal Chord & Ultra-Hit)**:
   針對日常問候、系統時間與「極度相似的重複提問 (Overlap >85%)」，小腦架構新增了 CPU 層級的攔截機制。這些任務在進入 LLM 神經網路前就會被瞬間處理並回傳 (<20ms)，將 GPU 喚醒與依賴次數降至最低。

### 👁️ 三層感官分級制度 (Sensory Hierarchy v4.5)

為了極致平衡 **「金錢支出 ($)」**、**「主機效能 (RAM/GPU)」** 與 **「資訊真實度」**，ArielOS 導入了三層感官調度邏輯：

1. **第一層：本地快速之眼 (Local DDGS)**
   - **引擎**：DuckDuckGo (`DDGS`)。
   - **特性**：$0 成本，反應最快。處理 60% 的簡單事實詢問。
2. **第二層：效能省電之眼 (GAS Cloud Distillation)**
   - **引擎**：**Exa AI (語義)** 或 **Google Custom Search (精確)**。
   - **特性**：微量 API 成本，**$0 資源損耗**。由 GAS 在雲端完成萬字內文「蒸餾」後才回傳本地，徹底保護本地 GPU 不會因為長文本而崩潰 (OOM)。
   - **在地化**：鎖定 `gl=tw` 與 `lr=lang_zh-TW`，優先過濾台灣與全球繁體資訊。
3. **第三層：深度探針之眼 (Local Playwright)**
   - **引擎**：小腦驅動之真瀏覽器探針。
   - **特性**：$0 成本，**極高資源損耗**。作為 API 失效或網頁被封鎖時的最終手段，能看見 JS 動態渲染的真實內容。

---

### 🛠️ 穩定性優化與核心修復 (Bug Fixes)

經歷實際運行測試後，針對本地端模型 (尤其是 Gemma 3 4B) 修復了大量因模型特性導致的幻覺與超時崩潰問題：

1. **意圖分類嚴格化 (Intent Parsing)**: 強制 LLM 僅輸出特定的標籤 (如 `[SEARCH]`)，解決了模型過度帶入角色而輸出對話導致 API 路由失敗並進而引發後續大腦 Reviewer 幻覺的連鎖 Bug。
2. **語意門衛防呆 (Semantic Cache Overlap)**: 小腦快取的語意配對現在會首先執行嚴格的「字元重疊比例測試」，僅有實質重疊的快取會送交 LLM。同時 LLM 強制回傳 `[MATCH_ID:X]`，杜絕了因為 LLM 解釋原因帶有數字而引發的錯誤配對 (False Positives)。
3. **系統異常直通 (Error Style Bypass)**: 搜尋引擎 (DDGS) 受限或腳本執行斷線時，原始 `Exception` 會直接顯示為系統回報，完全繞過 `cerebellum_style_transfer` (風格轉移)，防止 Agent 把 Error message 當作代碼錯誤並自我發想出「正在審查程式」的幻覺對白。
4. **沙盒捷徑免疫 (Sys Executable)**: 內建的沙盒 `subprocess.run` 已全面從呼叫 `python` 替換為 `sys.executable`，無視一切如 `sandbox-exec` 等作業系統層級的惡意 Alias 或配置錯亂，保證腳本必能交由正確的系統 Python 執行。
5. **巨型模型超時寬容度 (Generous Timeouts)**: 針對硬體運算較慢的情況，已將所有的內部非同步 API 呼叫 (包含意圖分析、上下文蒸餾、風格轉移) Timeout 從 30 秒上調至 120 秒，避免強行被降級成 Fallback 模型。

### 🧬 特性：ArielOS Auto-Evolution (自動進化機制)

ArielOS 不再只是被動接受指令的工具，它具備了真實的「數位生命週期」與學習能力：

1. **Mistake Reflection (失敗反思)**:
   當大腦 (OpenClaw) 執行程式碼遭遇 Linter 或執行階段錯誤時，小腦 (Gemma) 會介入分析 `Traceback`，並萃取出**「絕對守則 (System Directive)」**寫入 `EVOLUTION.md`。ArielOS 會從失敗中學習，未來永遠不會再犯同樣的錯。
2. **Curiosity-Driven Ideation (閒置自我增強)**:
   - 當系統連續閒置超過 **2 小時**（v2.2 調整），背景的神經排程器 (`scheduler_worker`) 會自動甦醒。它會主動發想一個對您有用的新技能，並自主完成撰寫碼、測試與技能註冊。ArielOS 會在您睡覺時**自動擴充自己的工具庫**。
   - 排程器將想法塞回 `task_queue`，大腦將自主開發可用於系統管理或日常實務的 Python 工具，存入 `skills_registry.json`。
3. **Execution-Conditioned Reasoning (執行條件推論 / 真相阻力)**:
   ArielOS 不再單純依靠 Linter 抓語法錯誤。當大腦開發出新腳本時，系統會**強制在沙盒內真實執行一次 (5秒 Timeout)**，任何 `RuntimeError` 或 `stderr` 都會被捕捉為「真相阻力 (Truth Resistance)」，迫使大腦面對現實的執行結果進行除錯。
4. **Mem0 Long-Term Memory (長期記憶)**:
   結合了本地端 SQLite 的向量化概念，將每日的對話透過夜間蒸餾 (`night_distillation`) 萃取出事實與偏好，並於每次對話中精準注入大腦。
5. **Multi-Agent Hub (多代理人協作樞紐)**:
   - **Watcher (常駐定時排程器)**: 支援讀取 `Shared_Vault/routines.json`，允許設定定時任務 (例如每日 09:00)。Kanban Poller 只接受 **TODO 狀態**任務（Watcher 建立），**不觸碰 DOING**（大腦正在處理中）。
   - **Explicit Handoff (人機協同交接)**: 當 Agent (大腦) 面臨高風險操作或資訊不足時，可觸發 `HANDOFF_TO_HUMAN`，中斷任務並請求人類授權。
   - **即時戰情室 (Real-time SSE Kanban)**: 升級 Kanban 系統為 `Server-Sent Events (SSE)`。免重新整理，即時觀察所有 Agent 的工作進度 (Todo → Doing → Done/Waiting)。

---

## 🛠️ 安裝指南 (Installation)

### 先決條件 (Prerequisites)

1. **Python 3.10+** (強烈建議 3.14+ 以支援全部 Qdrant 功能)
2. **Ollama**：請安裝並執行以下命令拉取小腦模型（兩種選擇）：

   ```powershell
   # 預設推薦模型 (兼具反應速度與高穩定性，最低要求 4GB 記憶體)：
   ollama pull gemma3:4b-it-q4_K_M
   
   # 若您堅持挑戰極限低配電腦 (極速但可能產生幻覺)：
   ollama pull qwen2.5:1.5b-instruct-q8_0
   ```

3. **OpenClaw**：需安裝並設定至系統 PATH。

   特別注意:
   "gateway": {
     "port": 18789,
     "mode": "local",
     "bind": "lan", <---這裡要修改為 "lan"

### 💻 快速安裝 (v4.0 推薦)

在專案目錄中，使用管理員權限打開 PowerShell 並執行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass; .\lite_setup.ps1
```

此腳本會自動檢查環境、安裝依賴（含 Qdrant/PyNaCl）、建立目錄並生成啟動捷徑。

---

## 🚀 啟動與操作 (Operation)

### 1. 啟動系統 (哨兵模式)

```powershell
.\start_all.ps1
```

- **哨兵守護**: `ariel_launcher.py` 會自動在背景監控 Bridge 與 Agents，並在啟動前建立系統快照至 `backups/`。
- **戰情室 (看板)**: [http://localhost:28888/kanban](http://localhost:28888/kanban)

### 2. 啟動代理人 (Agents)

#### 方法 A：一鍵啟動所有代理人（推薦）

```powershell
python ariel_launcher.py
```

系統會自動讀取 `Shared_Vault/agents.json`，同時啟動所有已設定 Token 的代理人。

#### 方法 B：單獨啟動指定代理人

```powershell
cd Ariel_Agent_1
python ariel_main.py
```

### 3. 操作特色指令

- **智慧搜尋**：輸入「查詢台北市現在的天氣」，小腦會先進行**關鍵字萃取**，避免傳統搜尋引擎被冗長語句干擾。
- **技能擴充與調用 (Self-Expansion)**：您可以直接命令：`幫你自己寫一個叫做『系統狀態』的 Python 技能並註冊進入系統`。大腦會自己寫扣並掛載。未來詢問「幫我查系統狀態」時，小腦會以毫秒級速度**直接攔截執行**該技能。
- **工作追蹤**：發出「寫一個 Python 腳本」等複雜指令時，看板會自動出現 **Doing** 標籤，完成後可點擊 **📜 View Logs** 查看結果與自我修復的 Traceback。

### 4. 新增自定義代理人 (Add New Agents)

ArielOS 支援動態熱重載代理人，您無需修改程式碼即可新增 Agent 3, 4, 5...

#### 步驟 1：建立代理人資料夾

複製現有的 `Ariel_Agent_1` 為新目錄（例如 `Ariel_Agent_3`），並修改其 `memory/SOUL.md` 以定義新的人格特質。

> ✅ **無需修改 `ariel_main.py`**：系統會自動從資料夾名稱偵測身份，例如 `Ariel_Agent_3` → `AGENT_ID = "agent3"`。
> 所有 Agent 共用同一份程式碼，日後有 Bug 修正只需更新其中一份再複製覆蓋即可。

#### 步驟 2：設定 .env Token

在 `Ariel_Agent_3/.env` 中填入此 bot 的 `DISCORD_TOKEN`。

#### 步驟 3：註冊代理人

編輯 `Shared_Vault/agents.json`，加入新代理人的設定：

```json
"agent3": {
  "name": "Cipher",
  "dir": "Ariel_Agent_3",
  "intro": "我是 Cipher，您的資安官。"
}
```

#### 步驟 4：重啟啟動器

```powershell
python ariel_launcher.py
```

或熱重載：

```powershell
curl -X POST http://localhost:28888/v1/harness/reload-agents
```

### 5. 多代理人團隊協作 (Multi-Agent Team Collaboration)

ArielOS 引入了 **Agent Dispatcher**，支援將任務指派給具備特定專長的代理人 (Commander / Worker / Reviewer)。

- **角色分工**: 根據 `Shared_Vault/roles/` 中的定義載入專屬人格。
- **沙盒隔離**: 每個任務自動建立獨立工作目錄。

#### 使用方式 A：聊天室指令 (ChatOps)
>
> `dispatch:Commander:幫我規劃一個貪食蛇遊戲的架構`
> `dispatch:Worker:寫一個計算圓周率的 Python 程式`

#### 使用方式 B：API 調用

```bash
curl -X POST http://localhost:28888/v1/team/dispatch \
     -H "Content-Type: application/json" \
     -d '{"role": "Worker", "payload": "Check system disk usage"}'
```

---

## 🛡️ 安全與自動化協議

1. **L6 Shield**: 即時監控並攔截高風險系統指令。
2. **Cron Shield (v2.2 新增)**: 禁止大腦呼叫 `cron.add`、`schedule_job` 等排程工具，防止因錯誤參數造成請求洪水。
3. **L1 Checkpoint**: 在執行修改檔案的「大腦任務」前，自動建立工作區快照 (`ariel_ltm/checkpoints`)。
4. **自動記憶蒸餾**: 每日 03:00 自動提煉當日日誌，進化代理人性格。

---

### 🚚 遷移與移植 (Migration & Portability)

若要將 ArielOS 移至另一台電腦，請遵循以下步驟：

1. **複製資料夾**：將整個 `Ariel_System` 資料夾複製到新電腦的「使用者根目錄」下。
2. **重啟環境**：在新電腦執行 `.\lite_setup.ps1` 以重新安裝 Python 依賴與 `pandas`。
3. **瀏覽器恢復**：執行 `playwright install` 以安裝必要的瀏覽器核心。
4. **模型拉取**：重新安裝 Ollama 與 OpenClaw，並確認執行過 `ollama pull gemma3:4b-it-q4_K_M`。

> [!NOTE]
> 您的「長期記憶」、「已學會技能」與「Discord Token」都儲存在 `Shared_Vault` 中，會隨著資料夾直接遷移。

---

## ⚠️ v2.2 注意事項 (Important Notes)

1. **Waitress 伺服器駐留**:
   `ariel_bridge.py` 預設佔用 28888 埠口並於背景高效運行。若要完全停止系統，請確保在終端機按下 `Ctrl+C` 終止程序。

2. **執行條件推論的安全邊界 (Sandbox Alert)**:
   大腦寫好的 Python 腳本會被強制執行一次。Shield 與 5 秒逾時中斷會攔截惡意指令，但仍建議將 Ariel_System 放置於安全的工作目錄下。

3. **小腦優化 (Cerebellum Optimization v2.2)**:
   - **並發限制**: `_CEREBELLUM_SEMAPHORE(2)` — 最多 2 個小腦任務並行，防止 Ollama 到頸。
   - **SIMPLE 快取**: 5 分鐘內完全相同問題直接命中，不重複呼叫 LLM。
   - **Context 分級**: 意圖分類 `num_ctx=2048` / 關鍵字萃取 `1024` / 風格轉移 `4096`（取代原本一律 8192）。
   - **Token Cap**: 意圖分類 80 tokens / 關鍵字 30 tokens / 快取比對 10 tokens。
   - **模型升級**: `gemma3:4b` → `gemma3:4b-it-q4_K_M`（速度 +30%，RAM ~2.5GB）。

4. **Kanban Poller 修正 (v2.2)**:
   Kanban Poller 現在只處理 **TODO 狀態**任務（Watcher 排程建立），不觸碰 **DOING 狀態**（大腦正在處理中）。這是解決雙重執行 Bug 與 cron 洪水問題的關鍵修正。

5. **Connection Pooling 效能暴增**:
   實作了高並行 HTTP 連線池，小腦判斷意圖與網路搜尋延遲已縮短為原本的 30%。

6. **自動產生的檔案管理**:
   系統會在 `Shared_Vault` 目錄下自動產生 `ariel_ltm.db` (長期記憶資料庫) 與 `skills_registry.json`。請勿手動刪除，否則 AI 將失憶且遺忘已學會的技能。

7. **Intelligence Core (v3.1)**：

   **向量記憶 (Qdrant)**：夜間蒸餾的每筆事實同步寫入 Qdrant 向量資料庫，支援語意雙軌查詢。

   **多代理博弈 (Reviewer)**：`priority: high` 任務完成後由小腦進行 L1/L2/L3 審查，REJECT 時自動觸發自我修復。

8. **Unkillable & Life Core (v4.0)**：

   **哨兵守護 (Disaster Recovery)**：`ariel_launcher` 改寫為哨兵守護模式。啟動前建立 `.tar.gz` 快照；伺服器意外崩潰時會自動解壓最新快照並重啟。**記憶目錄隔離**確保回滾後過去的對話記憶不會丟失。

   **生命感知 (Life Core)**：系統具備時間流逝感，會自動更新 `SOUL.md` 中的年齡。夜間蒸餾後，AI 會以第一人稱撰寫 `ariel_biography.log`（自主傳記），記錄每日的心情與成長。

   **Discord 特殊指令**：
   - `!進化`：立即觸發夜間模式 (蒸餾記憶 + 更新年齡)。
   - `!快照`：手動建立系統代碼備份。
   - `!狀態`：查看 AI 最新撰寫的自主傳記。

9. **GAS 指令與技能整合 (v4.3)**：

    ArielOS 現在採用中央集權式技能架構，將 GAS 邏輯從代理人端抽離至 `Central_Bridge/skills/gas_calendar.py`。

    - **支援多代理人**：Agent1 與 Agent2 可在各自的 `SOUL.md` 設定不同的 `GAS_URL`。
    - **強健解析**：自動識別並提取 `SOUL.md` 中的 `script.google.com` 網址，相容 Markdown 格式並大幅抗雜訊。
    - **智慧解析**：技能端支援「明天」、「後天」、「昨天」、「下午」、「AM/PM」等語意時間解析，並能自動擷取精準標題。

    **指令範例：**
    - 「幫我加入行程，時間:明天10:30 AM，內容:XXXXX進行資訊系統檢查」
    - 「最近有什麼行程？」
    - 「幫我登記後天下午二點開會」

10. **Exa Search & Background Intel (v4.4)**：

    ArielOS 現在具備真正的「世界感知」能力，透過整合 **Exa AI** 搜尋引擎：

    - **即時網路連路**：`Ariel 深度雲端助手` 技能現在會直接向 Exa AI 索取全球最新資訊，支援精確的語義搜尋。
    - **背景增量公告 (Delta Checking)**：Agent 巡邏機制全面升級。每 30 分鐘向 GAS 獲取資料時，會自動比對「已讀標記 (`seen_news`, `seen_emails`)」。
    - **零冗餘情報**：只有在「真正發現新行程/新郵件/新新聞」時，代理人才會在 Discord 頻道發出提醒，解決了舊版本重複傳送相同訊息的困擾。
    - **沙盒過濾增強**：Exa 回傳的高品質 Metadata 讓 GAS 沙盒的 `JS Filter` 能夠進行更深層的排除（如：過濾特定作者、日期區間）。

    **新增關鍵字：**
    - 「幫我整理...新聞」、「今日焦點」、「科技重大進展」

---

> ArielOS v4.5 | 2026-02-24 | **Sensory Hierarchy** · **Taiwan/Global Localization** · **180s Timeout Reliability** · Exa AI Integration
