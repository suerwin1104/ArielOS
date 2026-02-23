"""
ariel_launcher.py — ArielOS 哨兵守護器 v4.0

職責：
  1. [哨兵] 監控 ariel_bridge.py (Bridge) 的存活狀態
  2. [快照] 啟動前自動建立 .tar.gz 備份快照
  3. [回滾] 崩潰時自動解壓最新快照並重啟
  4. [記憶隔離] Shared_Vault/Memory/ 不參與回滾，確保記憶永久延續

用法：
  python ariel_launcher.py          # 哨兵模式 (同時啟動 Bridge + 多代理)
  python ariel_launcher.py --bridge # 只啟動 Bridge
  python ariel_launcher.py --agents # 只啟動 Discord Agents
"""
import asyncio
import json
import logging
import os
import subprocess
import sys
import tarfile
import time
from datetime import datetime
from pathlib import Path

import discord
from dotenv import dotenv_values

BASE_DIR = Path(__file__).resolve().parent
BACKUPS_DIR = BASE_DIR / "backups"
BRIDGE_SCRIPT = BASE_DIR / "Central_Bridge" / "ariel_bridge.py"

# 快照時排除的目錄（記憶不參與回滾）
SNAPSHOT_EXCLUDES = {
    "Shared_Vault/Memory",
    "Shared_Vault/chroma_db",
    "backups",
    "__pycache__",
    ".git",
    ".env",
}

MAX_BACKUPS = 7        # 最多保留幾份快照
MAX_RESTARTS = 5       # Bridge 崩潰最多重試幾次
RESTART_COOLDOWN = 10  # 每次重啟前等待秒數


# ── 快照工具 ──────────────────────────────────────────────────────────────────

def create_snapshot() -> Path | None:
    """建立系統快照（排除記憶目錄）"""
    BACKUPS_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap_path = BACKUPS_DIR / f"snapshot_{ts}.tar.gz"

    print(f"📸 [哨兵] 正在建立快照: {snap_path.name} ...")
    try:
        def _exclude(tarinfo):
            rel = Path(tarinfo.name)
            for exc in SNAPSHOT_EXCLUDES:
                if exc in tarinfo.name.replace("\\", "/"):
                    return None
            return tarinfo

        with tarfile.open(snap_path, "w:gz") as tar:
            tar.add(BASE_DIR, arcname="ArielOS", filter=_exclude)

        size_mb = snap_path.stat().st_size / 1024 / 1024
        print(f"✅ [哨兵] 快照完成: {snap_path.name} ({size_mb:.1f} MB)")

        # 清理舊快照，保留最新 MAX_BACKUPS 份
        existing = sorted(BACKUPS_DIR.glob("snapshot_*.tar.gz"), reverse=True)
        for old in existing[MAX_BACKUPS:]:
            old.unlink()
            print(f"🗑️  [哨兵] 刪除舊快照: {old.name}")

        return snap_path
    except Exception as e:
        print(f"⚠️  [哨兵] 快照失敗: {e}")
        return None


def rollback_latest() -> bool:
    """從 backups/ 解壓最新快照，覆蓋系統檔案（排除記憶目錄）"""
    snapshots = sorted(BACKUPS_DIR.glob("snapshot_*.tar.gz"), reverse=True)
    if not snapshots:
        print("❌ [哨兵] 找不到任何快照，無法回滾。")
        return False

    latest = snapshots[0]
    print(f"🔄 [哨兵] 從快照回滾: {latest.name} ...")

    try:
        # 備份當前記憶目錄
        memory_backup = None
        mem_dir = BASE_DIR / "Shared_Vault" / "Memory"
        if mem_dir.exists():
            memory_backup = mem_dir.rename(mem_dir.parent / "_Memory_tmp")

        with tarfile.open(latest, "r:gz") as tar:
            tar.extractall(path=BASE_DIR.parent)

        # 還原記憶目錄（記憶不因回滾消失）
        if memory_backup:
            if mem_dir.exists():
                import shutil
                shutil.rmtree(mem_dir)
            memory_backup.rename(mem_dir)

        print(f"✅ [哨兵] 回滾成功，記憶目錄已保留。")
        return True
    except Exception as e:
        print(f"❌ [哨兵] 回滾失敗: {e}")
        return False


# ── Bridge 哨兵 ────────────────────────────────────────────────────────────────

def run_bridge_sentinel():
    """以哨兵模式監控 ariel_bridge.py，崩潰時自動回滾重啟"""
    restart_count = 0
    create_snapshot()  # 啟動前先快照

    while True:
        print(f"\n🚀 [哨兵] 啟動 Bridge (第 {restart_count + 1} 次)...")
        proc = subprocess.run(
            [sys.executable, str(BRIDGE_SCRIPT)],
            cwd=str(BRIDGE_SCRIPT.parent)
        )

        exit_code = proc.returncode
        if exit_code == 0:
            print("⛔ [哨兵] Bridge 正常結束 (exit 0)。哨兵退出。")
            break

        restart_count += 1
        print(f"💥 [哨兵] Bridge 崩潰 (exit {exit_code})！重啟次數: {restart_count}/{MAX_RESTARTS}")

        if restart_count >= MAX_RESTARTS:
            print("🔄 [哨兵] 重啟上限達到，嘗試從最新快照回滾...")
            if rollback_latest():
                restart_count = 0
                print(f"✅ [哨兵] 回滾成功，重置重啟計數，繼續守護。")
            else:
                print("❌ [哨兵] 無法回滾，哨兵放棄守護。請手動檢查。")
                break

        print(f"⏳ [哨兵] {RESTART_COOLDOWN} 秒後重啟...")
        time.sleep(RESTART_COOLDOWN)


# ── 多代理人 Discord 啟動器 ────────────────────────────────────────────────────

sys.path.insert(0, str(BASE_DIR / "Ariel_Agent_1"))
from ariel_main import ArielAgentNode


async def run_agent(agent_id: str, agent_dir: Path, token: str):
    """啟動單一 Discord Agent"""
    client = ArielAgentNode(
        intents=discord.Intents.all(),
        agent_dir_override=str(agent_dir)
    )
    try:
        await client.start(token, reconnect=True)
    except Exception as e:
        print(f"🚨 [{agent_id}] 異常終止: {e}")
    finally:
        if not client.is_closed():
            await client.close()


async def run_agents():
    """並行啟動所有 Discord Agents"""
    agents_path = BASE_DIR / "Shared_Vault" / "agents.json"
    if not agents_path.exists():
        print("❌ 找不到 agents.json")
        return

    config: dict = json.loads(agents_path.read_text(encoding="utf-8"))
    tasks = []

    for agent_id, info in config.items():
        agent_dir = BASE_DIR / info.get("dir", "")
        if not agent_dir.is_dir() or "Agent" not in agent_dir.name:
            print(f"⏭️  [{agent_id}] 非 Discord Agent，跳過")
            continue

        env_file = agent_dir / ".env"
        if not env_file.exists():
            continue

        env = dotenv_values(env_file)
        token = env.get("DISCORD_TOKEN", "").strip()
        if not token or token == "your_discord_token_here":
            print(f"⚠️  [{agent_id}] DISCORD_TOKEN 未設定，跳過")
            continue

        name = info.get("name", agent_id)
        print(f"🚀 準備啟動: {name} ({agent_id})")
        tasks.append(run_agent(agent_id, agent_dir, token))

    if not tasks:
        print("❌ 沒有可用的代理人")
        return

    print(f"\n✅ 共啟動 {len(tasks)} 個代理人...\n")
    await asyncio.gather(*tasks)


# ── 主入口 ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    mode = sys.argv[1] if len(sys.argv) > 1 else "--all"

    if mode == "--bridge":
        # 只啟動 Bridge 哨兵
        run_bridge_sentinel()

    elif mode == "--agents":
        # 只啟動 Discord Agents
        try:
            asyncio.run(run_agents())
        except KeyboardInterrupt:
            print("\n⛔ 中斷，代理人已關閉。")

    else:
        # 預設：Bridge 哨兵 + Agents 並行
        import threading
        bridge_thread = threading.Thread(target=run_bridge_sentinel, daemon=True)
        bridge_thread.start()
        print("🛡️  [哨兵] Bridge 哨兵已在背景啟動。")

        try:
            asyncio.run(run_agents())
        except KeyboardInterrupt:
            print("\n⛔ 使用者中斷，所有代理人已關閉。")
