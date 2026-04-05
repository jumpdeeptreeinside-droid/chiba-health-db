#!/usr/bin/env python3
"""
Claude Watcher
inbox/claude_tasks/ に .md ファイルが追加されると自動でClaude Codeに実行させ、
結果を inbox/claude_results/ に保存する。
"""

import os
import re
import shutil
import sys
import time
import subprocess
import logging
import threading
from datetime import datetime
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

VAULT_DIR = Path.home() / "Documents" / "Obsidian_Integlation"
TASKS_DIR = VAULT_DIR / "inbox" / "claude_tasks"
RESULTS_DIR = VAULT_DIR / "inbox" / "claude_results"
DEFAULT_CWD = str(Path.home() / "chiba_pdf_db")
LOG_FILE = Path("/tmp/claude_watcher.log")

# Claude コマンドの検出: 既知パスを試し、なければ PATH 上の claude を使う
_CLAUDE_CANDIDATES = [
    Path.home() / ".npm-global" / "bin" / "claude",
    Path.home() / ".local" / "bin" / "claude",
]


def _find_claude_cmd() -> str:
    for p in _CLAUDE_CANDIDATES:
        if p.exists():
            return str(p)
    found = shutil.which("claude")
    if found:
        return found
    # 最終フォールバック
    return str(_CLAUDE_CANDIDATES[0])


CLAUDE_CMD = _find_claude_cmd()

SKIP_FILENAMES = {"README.md"}
SKIP_PREFIXES = ("_", "TEMPLATE_")

# 処理中ファイルを追跡して二重処理を防止
_processing_lock = threading.Lock()
_processing_files: set[str] = set()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

GITHUB_REPO = "jumpdeeptreeinside-droid/chiba-health-db"


def _send_completion_notification(task_count):
    """バッチ完了時にGitHub Issueで通知"""
    try:
        title = f"CPL完了: {task_count}件 ({datetime.now().strftime('%Y-%m-%d %H:%M')})"
        body = (
            f"Claude Watcher バッチ処理が完了しました。\n\n"
            f"- 処理件数: {task_count}件\n"
            f"- 完了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"結果は `inbox/claude_results/` を確認してください。"
        )
        result = subprocess.run(
            ["gh", "issue", "create", "--repo", GITHUB_REPO,
             "--title", title, "--body", body, "--label", "cpl-notification"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            log.info(f"GitHub Issue通知: {result.stdout.strip()}")
        else:
            log.warning(f"GitHub Issue作成失敗: {result.stderr}")
    except Exception as e:
        log.warning(f"通知失敗: {e}")


WRAPPER_PROMPT = """\
以下のタスクファイルの内容に従って作業を実行してください。
コードの実行、ファイルの作成・編集、データのダウンロードなど、必要な作業を全て実際に行ってください。
「手順を書く」のではなく「実際に実行する」こと。
結果のサマリーを最後に出力してください。

---
{task_content}
"""


def _extract_cwd(content: str) -> str:
    """タスク内容から作業ディレクトリを抽出する。

    '## 作業ディレクトリ' セクション内のバッククォート囲みパス（例: `~/chiba_pdf_db/`）を探す。
    見つからなければ DEFAULT_CWD を返す。
    """
    in_section = False
    for line in content.splitlines():
        if re.match(r"^##\s*作業ディレクトリ", line):
            in_section = True
            continue
        if in_section:
            # 次の見出しに到達したらセクション終了
            if re.match(r"^##\s", line):
                break
            m = re.search(r"`([^`]+)`", line)
            if m:
                path_str = m.group(1).strip().rstrip("/")
                expanded = os.path.expanduser(path_str)
                if os.path.isdir(expanded):
                    return expanded
                log.warning(f"作業ディレクトリが存在しません: {expanded} — デフォルトを使用")
                break
    return DEFAULT_CWD


def process_task(task_path: Path):
    task_path = Path(task_path)

    # --- 早期スキップ条件 ---
    if not task_path.suffix == ".md":
        return
    if any(task_path.name.startswith(p) for p in SKIP_PREFIXES):
        return
    if task_path.name in SKIP_FILENAMES:
        return
    if not task_path.exists():
        return

    # 二重処理防止
    abs_key = str(task_path.resolve())
    with _processing_lock:
        if abs_key in _processing_files:
            log.debug(f"スキップ（処理中）: {task_path.name}")
            return
        _processing_files.add(abs_key)

    try:
        log.info(f"タスク検出: {task_path.name}")
        content = task_path.read_text(encoding="utf-8")

        cwd = _extract_cwd(content)
        log.info(f"作業ディレクトリ: {cwd}")

        prompt = WRAPPER_PROMPT.format(task_content=content)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = RESULTS_DIR / f"{timestamp}_{task_path.stem}_result.md"

        try:
            result = subprocess.run(
                [CLAUDE_CMD, "--dangerously-skip-permissions", "-p", prompt],
                capture_output=True,
                text=True,
                timeout=1800,
                cwd=cwd,
            )
            output = result.stdout if result.stdout else result.stderr
            status = "✅ 完了" if result.returncode == 0 else "❌ エラー"
        except subprocess.TimeoutExpired:
            output = "タイムアウト（30分）"
            status = "⏱ タイムアウト"
        except Exception as e:
            output = str(e)
            status = "❌ 例外エラー"

        result_content = f"""# {status}：{task_path.stem}
実行日時: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 元タスク
{content}

## 結果
{output}
"""
        result_file.write_text(result_content, encoding="utf-8")
        log.info(f"結果保存: {result_file.name}")

        # 処理済みタスクを _done_ プレフィックスにリネーム
        done_path = task_path.parent / f"_done_{task_path.name}"
        task_path.rename(done_path)
    finally:
        with _processing_lock:
            _processing_files.discard(abs_key)


class TaskHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory:
            time.sleep(1)  # ファイル書き込み完了を待つ
            process_task(event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            return
        dest = Path(event.dest_path)
        # _done_ リネームによる再トリガーをスキップ
        if dest.stem.startswith("_"):
            return
        time.sleep(1)
        process_task(event.dest_path)


if __name__ == "__main__":
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    log.info(f"Claude Watcher 起動")
    log.info(f"監視ディレクトリ: {TASKS_DIR}")
    log.info(f"結果ディレクトリ: {RESULTS_DIR}")
    log.info(f"Claude コマンド: {CLAUDE_CMD}")
    log.info(f"デフォルト作業ディレクトリ: {DEFAULT_CWD}")

    # 起動時に既存の未処理タスクをスキャン
    existing = sorted(TASKS_DIR.glob("*.md"))
    pending = [f for f in existing if not any(f.name.startswith(p) for p in SKIP_PREFIXES)
               and f.name not in SKIP_FILENAMES]
    if pending:
        log.info(f"未処理タスク {len(pending)}件を検出、順次実行します")
        for task_file in pending:
            process_task(task_file)
        # 全バッチ完了時にGitHub Issue通知
        _send_completion_notification(len(pending))

    observer = Observer()
    observer.schedule(TaskHandler(), str(TASKS_DIR), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        observer.stop()
        log.info("Claude Watcher 停止")
    observer.join()
