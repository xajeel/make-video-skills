#!/bin/sh
# Opens Google Flow in Chrome on gflow's signed-in profile, controllable over CDP port 9333.
# Usage: launch_flow_chrome.sh [URL]   (default https://flow.google.com/)
# Close this window before using the gflow MCP again (both use the same profile).
PROFILE="$HOME/.local/share/gflow-cli/profile_sajeel135"
URL="${1:-https://flow.google.com/}"
if ! pgrep -f "user-data-dir=$PROFILE" >/dev/null; then
  rm -f "$PROFILE"/SingletonLock "$PROFILE"/SingletonCookie "$PROFILE"/SingletonSocket   # stale locks from crashed runs
fi
# VS Code (snap) leaks GTK/GIO vars that crash Chrome on launch - strip them.
unset GSETTINGS_SCHEMA_DIR GTK_PATH GTK_EXE_PREFIX GTK_IM_MODULE_FILE GIO_MODULE_DIR LOCPATH GDK_PIXBUF_MODULE_FILE GDK_PIXBUF_MODULEDIR
export XDG_DATA_DIRS="${XDG_DATA_DIRS_VSCODE_SNAP_ORIG:-/usr/local/share:/usr/share}"
nohup /opt/google/chrome/chrome --user-data-dir="$PROFILE" --remote-debugging-port=9333 \
  --remote-allow-origins=http://127.0.0.1 --no-first-run --window-size=1440,900 "$URL" >/dev/null 2>&1 &
sleep 6; curl -s http://127.0.0.1:9333/json/version | grep -q Browser && echo "Flow Chrome ready on :9333"
