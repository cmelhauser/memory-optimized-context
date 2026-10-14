#!/bin/bash
# Schedule tools/nightly_catchup.sh every night.
#
#   tools/install_nightly.sh [--hour 3] [--calls 60]   install (macOS: a launchd agent; elsewhere: prints a cron line)
#   tools/install_nightly.sh --dry-run ...             show what would be written, change nothing
#   tools/install_nightly.sh --uninstall               remove the launchd agent
#
# Nothing here is committed with a path in it: the agent's file is written from this checkout's location and
# $HOME when you run it.
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
label="local.memory-optimized-context.nightly-catchup"
plist="$HOME/Library/LaunchAgents/$label.plist"
state="$HOME/.local/share/memory-optimized-context"
hour=3; calls=60; dry=0; uninstall=0
usage () { echo "usage: $0 [--hour 0-23] [--calls 1-999999] [--dry-run] [--uninstall]" >&2; exit 2; }
while [ $# -gt 0 ]; do
  case "$1" in
    --hour|--calls) [ $# -ge 2 ] || usage; if [ "$1" = --hour ]; then hour="$2"; else calls="$2"; fi; shift 2 ;;
    --dry-run) dry=1; shift ;;
    --uninstall) uninstall=1; shift ;;
    *) usage ;;
  esac
done
case "$hour" in ''|*[!0-9]*) echo "--hour must be a number from 0 to 23" >&2; exit 2 ;; esac
case "$calls" in ''|*[!0-9]*|0) echo "--calls must be a positive number" >&2; exit 2 ;; esac
[ "${#hour}" -le 2 ] && [ "$((10#$hour))" -le 23 ] || { echo "--hour must be a number from 0 to 23" >&2; exit 2; }
[ "${#calls}" -le 6 ] || { echo "--calls must be at most 999999" >&2; exit 2; }
hour=$((10#$hour)); calls=$((10#$calls))
[ "$calls" -ge 1 ] || { echo "--calls must be a positive number" >&2; exit 2; }
xml () { printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'; }   # a path is text in an XML file

if [ "$uninstall" = 1 ]; then
  if [ "$(uname -s)" != "Darwin" ]; then echo "not macOS: no launchd agent to remove; delete the cron line yourself"; exit 0; fi
  if [ "$dry" = 1 ]; then echo "would unload and remove $plist"; exit 0; fi
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  rm -f "$plist"
  echo "removed $label"
  exit 0
fi

if [ "$(uname -s)" != "Darwin" ]; then
  script="$(printf '%q' "$repo/tools/nightly_catchup.sh")"
  echo "Not macOS: add this line with \`crontab -e\`:"
  echo "0 $hour * * * CALLS=$calls /bin/bash ${script//%/\\%}"
  exit 0
fi

body="<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\">
<dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$(xml "$repo")/tools/nightly_catchup.sh</string></array>
  <key>EnvironmentVariables</key><dict><key>CALLS</key><string>$calls</string></dict>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>$hour</integer><key>Minute</key><integer>0</integer></dict>
  <key>RunAtLoad</key><false/>
  <key>StandardOutPath</key><string>$(xml "$state")/nightly-catchup.launchd.log</string>
  <key>StandardErrorPath</key><string>$(xml "$state")/nightly-catchup.launchd.log</string>
</dict>
</plist>"

if [ "$dry" = 1 ]; then
  echo "would write $plist:"; echo "$body"
  exit 0
fi
mkdir -p "$state" "$(dirname "$plist")"
new="$plist.new"
printf '%s\n' "$body" > "$new"
if command -v plutil >/dev/null 2>&1 && ! plutil -lint "$new" >/dev/null; then
  rm -f "$new"; echo "the agent's file is not valid; nothing was installed" >&2; exit 1
fi
mv "$new" "$plist"
launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
for _ in 1 2 3 4 5 6 7 8 9 10; do                       # bootout returns before the old job is gone, and a bootstrap then fails
  launchctl print "gui/$(id -u)/$label" >/dev/null 2>&1 || break
  sleep 0.5
done
launchctl bootstrap "gui/$(id -u)" "$plist" || { sleep 2; launchctl bootstrap "gui/$(id -u)" "$plist"; }
echo "scheduled $label at $hour:00, $calls calls a night; its log is $state/backfill.log"
