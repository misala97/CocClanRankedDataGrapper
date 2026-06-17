#!/bin/bash
# Usage: ./check_logs.sh          -> show all errors/warnings
#        ./check_logs.sh -n 100   -> only last 100 lines per log file

LOGS_DIR="$(dirname "$0")/logs"
TAIL_LINES=${2:-0}  # 0 = whole file

RED='\033[0;31m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

total_errors=0
total_warnings=0

for log_file in "$LOGS_DIR"/*.log; do
    [ -f "$log_file" ] || continue

    if [ "$TAIL_LINES" -gt 0 ]; then
        content=$(tail -n "$TAIL_LINES" "$log_file")
    else
        content=$(cat "$log_file")
    fi

    errors=$(echo "$content"   | grep -c " - ERROR - "   || true)
    warnings=$(echo "$content" | grep -c " - WARNING - " || true)

    [ "$errors" -eq 0 ] && [ "$warnings" -eq 0 ] && continue

    echo -e "${CYAN}${BOLD}$(basename "$log_file")${RESET}  (${RED}${errors} errors${RESET}, ${YELLOW}${warnings} warnings${RESET})"
    echo "──────────────────────────────────────────────────────"

    echo "$content" | grep -E " - (ERROR|WARNING) - " | while IFS= read -r line; do
        if echo "$line" | grep -q " - ERROR - "; then
            echo -e "  ${RED}${line}${RESET}"
        else
            echo -e "  ${YELLOW}${line}${RESET}"
        fi
    done

    echo ""
    total_errors=$((total_errors + errors))
    total_warnings=$((total_warnings + warnings))
done

echo -e "${BOLD}Summary:${RESET} ${RED}${total_errors} errors${RESET}, ${YELLOW}${total_warnings} warnings${RESET} across all logs"

# Also check systemd journal for the scheduler service
echo ""
echo -e "${CYAN}${BOLD}systemd (last 50 lines):${RESET}"
echo "──────────────────────────────────────────────────────"
journalctl -u coc_scheduler.service -n 50 --no-pager 2>/dev/null \
    | grep -iE "error|warning|traceback|exception" \
    | while IFS= read -r line; do
        echo -e "  ${RED}${line}${RESET}"
    done || echo "  (no issues found)"
