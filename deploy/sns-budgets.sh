#!/usr/bin/env bash
# sns-budgets.sh — SNS 토픽+이메일 구독, Budgets $20 알림 (SPEC §9.5).
# 실행은 사람 게이트.
#   EMAIL=ops@example.com ACCOUNT_ID=123456789012 bash deploy/sns-budgets.sh
# 구독은 AWS가 보낸 확인 메일의 Confirm 링크를 사람이 눌러야 활성화된다.
set -euo pipefail

REGION="${REGION:-ap-northeast-2}"
EMAIL="${EMAIL:?EMAIL 환경변수가 필요하다}"
ACCOUNT_ID="${ACCOUNT_ID:?ACCOUNT_ID 환경변수가 필요하다}"
TOPIC_NAME="repodoc-alerts"

# --- SNS 토픽 + 이메일 구독. ---
TOPIC_ARN=$(aws sns list-topics --region "$REGION" \
  --query "Topics[?ends_with(TopicArn, ':$TOPIC_NAME')].TopicArn | [0]" --output text)
if [ -z "$TOPIC_ARN" ] || [ "$TOPIC_ARN" = "None" ]; then
  TOPIC_ARN=$(aws sns create-topic --region "$REGION" \
    --name "$TOPIC_NAME" --query TopicArn --output text)
  echo "created topic: $TOPIC_ARN"
fi
aws sns subscribe --region "$REGION" \
  --topic-arn "$TOPIC_ARN" --protocol email \
  --notification-endpoint "$EMAIL"
echo "subscribed(pending confirmation): $EMAIL — 확인 메일 승인 필요"

# --- CloudWatch Budgets: 월 $20, 80% 실제 / 100% 예측·실제 알림. ---
cat > /tmp/repodoc-budget.json <<JSON
{
  "BudgetName": "repodoc-monthly-20usd",
  "BudgetLimit": { "Amount": "20", "Unit": "USD" },
  "TimeUnit": "MONTHLY",
  "BudgetType": "COST"
}
JSON
cat > /tmp/repodoc-budget-notifs.json <<JSON
[
  { "Notification": { "NotificationType": "ACTUAL", "ComparisonOperator": "GREATER_THAN",
      "Threshold": 80, "NotificationState": "ALARM" },
    "Subscribers": [ { "SubscriptionType": "SNS", "Address": "$TOPIC_ARN" } ] },
  { "Notification": { "NotificationType": "FORECASTED", "ComparisonOperator": "GREATER_THAN",
      "Threshold": 100, "NotificationState": "ALARM" },
    "Subscribers": [ { "SubscriptionType": "SNS", "Address": "$TOPIC_ARN" } ] }
]
JSON
if aws budgets describe-budget --account-id "$ACCOUNT_ID" \
    --budget-name repodoc-monthly-20usd >/dev/null 2>&1; then
  echo "exists budget: repodoc-monthly-20usd"
else
  aws budgets create-budget --account-id "$ACCOUNT_ID" \
    --budget file:///tmp/repodoc-budget.json \
    --notifications-with-subscribers file:///tmp/repodoc-budget-notifs.json
  echo "created budget: repodoc-monthly-20usd (SNS: $TOPIC_ARN)"
fi

echo "남은 수동 절차: (1) SNS 확인 메일 승인  (2) CloudWatch 알람 2개 적용 —"
echo "  cloudwatch.json의 <ACCOUNT_ID>·<INSTANCE_ID> 치환 후"
echo "  aws cloudwatch put-metric-alarm --cli-input-json file://deploy/cloudwatch.json"
