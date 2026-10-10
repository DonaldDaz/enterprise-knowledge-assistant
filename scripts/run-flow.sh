#!/usr/bin/env bash
set -euo pipefail
API_URL="${API_URL:-http://localhost:8000}"
if [[ -f "$(dirname "$0")/../.env" ]]; then
  set -a
  # This file is created locally from .env.example and is never committed.
  source "$(dirname "$0")/../.env"
  set +a
fi
: "${ADMIN_PASSWORD:?Set ADMIN_PASSWORD in .env or the environment}"
: "${EMPLOYEE_PASSWORD:?Set EMPLOYEE_PASSWORD in .env or the environment}"

admin_token=$(curl -fsS -X POST "$API_URL/api/login" -d "username=admin" --data-urlencode "password=$ADMIN_PASSWORD" | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')
employee_token=$(curl -fsS -X POST "$API_URL/api/login" -d "username=employee" --data-urlencode "password=$EMPLOYEE_PASSWORD" | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')
echo "1. Upload a synthetic file as admin"
curl -fsS -X POST "$API_URL/api/documents" -H "Authorization: Bearer $admin_token" -F 'title=Procedura sintetica di supporto' -F 'roles=employee' -F "file=@$(dirname "$0")/../data/travel-policy.md" | python3 -m json.tool
echo "2. Ask as employee"
curl -fsS -X POST "$API_URL/api/ask" -H "Authorization: Bearer $employee_token" -H 'Content-Type: application/json' -d '{"question":"Qual è il limite per un hotel per notte?"}' | python3 -m json.tool
echo "3. Inspect admin statistics"
curl -fsS "$API_URL/api/admin/stats" -H "Authorization: Bearer $admin_token" | python3 -m json.tool
