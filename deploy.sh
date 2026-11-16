#!/usr/bin/env bash
# 나라장터 대시보드 → GitHub Pages 배포/갱신 스크립트
# 사용: bash deploy.sh
# 전제: 저장소 xcastle2art/g2b-dashboard 가 이미 존재하고 Pickle의 GitHub 연결에 공유되어 있어야 함.
set -uo pipefail

OWNER="xcastle2art"
REPO="g2b-dashboard"
BRANCH="main"
SITE="https://${OWNER}.github.io/${REPO}/"
cd "$(dirname "$0")" || exit 1

echo "== 1) 저장소 확인 =="
if ! gh api "repos/${OWNER}/${REPO}" --jq '.full_name + " (" + .visibility + ")"'; then
  echo "!! 저장소가 없거나 접근 권한이 없습니다. github.com/new 에서 ${REPO} (public) 생성 후"
  echo "   Pickle 앱 > GitHub 연결 설정에서 해당 저장소를 선택해야 합니다."
  exit 2
fi

echo "== 2) 커밋 & 푸시 =="
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { git init -q -b "$BRANCH"; }
git add -A
git diff --cached --quiet || git commit -q -m "대시보드 갱신 $(date '+%Y-%m-%d %H:%M')"
git remote get-url origin >/dev/null 2>&1 || git remote add origin "https://github.com/${OWNER}/${REPO}.git"
git push -u origin "$BRANCH" || { echo "!! push 실패 — GitHub 연결에 이 저장소가 공유됐는지 확인"; exit 3; }

echo "== 3) GitHub Pages 활성화 =="
if gh api "repos/${OWNER}/${REPO}/pages" >/dev/null 2>&1; then
  echo "이미 Pages 활성화됨"
else
  gh api -X POST "repos/${OWNER}/${REPO}/pages" \
    -f "source[branch]=${BRANCH}" -f "source[path]=/" \
    && echo "Pages 활성화 요청 완료" \
    || echo "!! Pages API 권한 없음 — Settings > Pages 에서 main / (root) 한 번 지정 필요"
fi

echo "== 4) 배포 확인 (최대 10분 대기) =="
for i in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$SITE")
  echo "  ${i}: ${SITE} → HTTP ${code}"
  [ "$code" = "200" ] && break
  sleep 10
done

echo "== 5) data.json 확인 =="
curl -s --max-time 20 "${SITE}data.json" | head -c 300; echo
curl -s -o /dev/null -w 'data.json → HTTP %{http_code}\n' --max-time 20 "${SITE}data.json"
echo "접속 URL: ${SITE}"
