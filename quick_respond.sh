#!/bin/bash
# Quick shell-based responder
# Usage: ./quick_respond.sh req_id answer

PROTOCOL_DIR="${AGENT_PROTOCOL_DIR:-.}"

if [ $# -lt 2 ]; then
    echo "Usage: $0 <request_id> <answer>"
    echo ""
    echo "Pending requests:"
    python3 protocol.py pending
    exit 1
fi

REQ_ID="$1"
ANSWER="$2"

echo "{\"id\":\"$REQ_ID\",\"answer\":\"$ANSWER\",\"timestamp\":\"$(date -Iseconds)\"}" >> "$PROTOCOL_DIR/responses.jsonl"

echo "Responded to $REQ_ID with: $ANSWER"
