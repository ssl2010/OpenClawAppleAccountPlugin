#!/bin/sh
set -eu

failures=0

check_command() {
  label=$1
  command_path=$2
  if [ -x "$command_path" ]; then
    printf 'ok\t%s\t%s\n' "$label" "$command_path"
  else
    printf 'fail\t%s\tmissing: %s\n' "$label" "$command_path"
    failures=$((failures + 1))
  fi
}

printf 'host\t%s\n' "$(hostname)"
printf 'macos\t%s\n' "$(sw_vers -productVersion)"
printf 'arch\t%s\n' "$(uname -m)"

check_command swiftc /usr/bin/swiftc
check_command ssh /usr/bin/ssh
check_command launchctl /bin/launchctl
check_command python-homebrew /usr/local/bin/python3

if launchctl print "gui/$(id -u)" >/dev/null 2>&1; then
  printf 'ok\tgui-session\tavailable\n'
else
  printf 'fail\tgui-session\tunavailable\n'
  failures=$((failures + 1))
fi

if [ -f "$HOME/.ssh/id_ed25519_openclaw_apple_bridge" ]; then
  mode=$(stat -f '%Lp' "$HOME/.ssh/id_ed25519_openclaw_apple_bridge")
  if [ "$mode" = 600 ]; then
    printf 'ok\tbridge-key-mode\t600\n'
  else
    printf 'fail\tbridge-key-mode\t%s\n' "$mode"
    failures=$((failures + 1))
  fi
else
  printf 'fail\tbridge-key\tmissing\n'
  failures=$((failures + 1))
fi

if launchctl list | grep -Eq 'com\.calendar|com\.shileisun\.statustool'; then
  printf 'fail\tlegacy-jobs\tstill loaded\n'
  failures=$((failures + 1))
else
  printf 'ok\tlegacy-jobs\tnot loaded\n'
fi

exit "$failures"
