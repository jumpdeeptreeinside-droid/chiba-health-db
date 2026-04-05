#!/bin/bash
# Claude Watcher launcher - LaunchAgent用
# Full Disk Access が必要: System Settings → Privacy & Security → Full Disk Access → /bin/bash を追加
export PATH="$HOME/.local/bin:$HOME/.npm-global/bin:/usr/local/bin:/opt/homebrew/bin:/opt/homebrew/bin:$PATH"
eval "$(/opt/homebrew/bin/brew shellenv)" 2>/dev/null
exec /usr/bin/python3 "$HOME/bin/claude_watcher.py"
