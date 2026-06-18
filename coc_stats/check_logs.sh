#!/bin/bash
# Usage: ./check_logs.sh          -> show all errors/warnings
#        ./check_logs.sh -n 100   -> only last 100 lines per log file
#
# Override the project location (default ~/coc-stats/coc_stats) with:
#   COC_STATS_DIR=/path/to/coc-stats/coc_stats ./check_logs.sh

PROJECT_DIR="${COC_STATS_DIR:-$HOME/coc-stats/coc_stats}"
LOGS_DIR="$PROJECT_DIR/logs"
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

    # Tag each ERROR/WARNING line with its level, and carry that level onto any
    # following lines that aren't a new timestamped log entry (e.g. a traceback
    # attached via exc_info=True) — stops as soon as the next timestamped line appears.
    echo "$content" | awk '
        /^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} - ERROR - /   { level="ERROR";   print level "\t" $0; next }
        /^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} - WARNING - / { level="WARNING"; print level "\t" $0; next }
        /^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} - (INFO|DEBUG|CRITICAL) - / { level=""; next }
        level != "" { print level "\t" $0 }
    ' | while IFS=$'\t' read -r level line; do
        if [ "$level" = "ERROR" ]; then
            echo -e "  ${RED}${line}${RESET}"
        else
            echo -e "  ${YELLOW}${line}${RESET}"
        fi
    done

    echo ""
    total_errors=$((total_errors + errors))
    total_warnings=$((total_warnings + warnings))
done

# Also check systemd journal for the scheduler service
echo -e "${CYAN}${BOLD}systemd (last 50 lines):${RESET}"
echo "──────────────────────────────────────────────────────"
journal_content=$(journalctl -u coc_scheduler.service -n 50 --no-pager 2>/dev/null)
journal_hits=$(echo "$journal_content" | grep -iE "error|warning|traceback|exception")

journal_errors=0
journal_warnings=0
if [ -n "$journal_hits" ]; then
    echo "$journal_hits" | while IFS= read -r line; do
        if echo "$line" | grep -qiE "error|traceback|exception"; then
            echo -e "  ${RED}${line}${RESET}"
        else
            echo -e "  ${YELLOW}${line}${RESET}"
        fi
    done
    # error-class takes priority (matches the coloring above), so a line never counts as both.
    journal_errors=$(echo "$journal_hits" | grep -ciE "error|traceback|exception")
    journal_warnings=$(echo "$journal_hits" | grep -viE "error|traceback|exception" | grep -ci "warning")
else
    echo "  (no issues found)"
fi

echo ""
echo -e "${BOLD}Summary:${RESET} ${RED}${total_errors} errors${RESET}, ${YELLOW}${total_warnings} warnings${RESET} across all logs"
echo -e "${BOLD}Journal${RESET} (loose text match, may include non-app crashes): ${RED}${journal_errors} error-like${RESET}, ${YELLOW}${journal_warnings} warning-like${RESET} lines"
