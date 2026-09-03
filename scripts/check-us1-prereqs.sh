#!/bin/sh
set -eu

failures=0

check_version() {
  label=$1
  command_path=$2
  if [ -x "$command_path" ]; then
    printf 'ok\t%s\t' "$label"
    "$command_path" --version 2>&1 | head -1
  else
    printf 'fail\t%s\tmissing: %s\n' "$label" "$command_path"
    failures=$((failures + 1))
  fi
}

printf 'host\t%s\n' "$(hostname)"
check_version node "$HOME/.openclaw/tools/node-v24.19.0/bin/node"
check_version python /usr/bin/python3
check_version openclaw "$HOME/.openclaw/bin/openclaw"

for path in \
  "$HOME/.config/openclaw-apple-account" \
  "$HOME/.local/state/openclaw-apple-account" \
  "$HOME/work/OpenClawAppleAccountPlugin"; do
  if [ -e "$path" ]; then
    printf 'ok\tpath\t%s\n' "$path"
  else
    printf 'fail\tpath\tmissing: %s\n' "$path"
    failures=$((failures + 1))
  fi
done

if systemctl --user is-active openclaw-gateway.service >/dev/null 2>&1; then
  printf 'ok\tgateway\tactive\n'
else
  printf 'fail\tgateway\tinactive\n'
  failures=$((failures + 1))
fi

exit "$failures"
