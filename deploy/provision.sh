#!/usr/bin/env bash
# provision.sh — EC2 인스턴스 프로비저닝 (SPEC §9.2, AWS CLI).
# 실행은 사람 게이트: 실 AWS 자원(EC2·SG·IAM·EIP)을 생성한다. 실행 전
# docs/DEPLOY.md의 순서와 비용(SPEC §9.5, Budgets $20)을 확인할 것.
set -euo pipefail

REGION="${REGION:-ap-northeast-2}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t3.small}"
ROOT_VOLUME_GB="${ROOT_VOLUME_GB:-30}"
KEY_NAME="${1:?usage: bash deploy/provision.sh <ec2-keypair-name>}"
SG_NAME="repodoc-sg"
ROLE_NAME="repodoc-ec2-role"
PROFILE_NAME="repodoc-ec2-profile"

# --- AMI: Ubuntu 24.04 amd64 (Canonical, ap-northeast-2). 고정하려면 AMI_ID 지정. ---
if [ -z "${AMI_ID:-}" ]; then
  AMI_ID=$(aws ec2 describe-images --region "$REGION" \
    --owners 099720109477 \
    --filters "Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*" \
              "Name=state,Values=available" \
    --query 'sort_by(Images,&CreationDate)[-1].ImageId' --output text)
fi
echo "AMI: $AMI_ID  REGION: $REGION  TYPE: $INSTANCE_TYPE"

# --- 보안그룹: 80/443만 허용. 22 포함 금지(SSH 대신 SSM Session Manager). ---
SG_ID=$(aws ec2 describe-security-groups --region "$REGION" \
  --group-names "$SG_NAME" --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || true)
if [ -z "$SG_ID" ] || [ "$SG_ID" = "None" ]; then
  SG_ID=$(aws ec2 create-security-group --region "$REGION" \
    --group-name "$SG_NAME" --description "repodoc 80/443 only" \
    --query 'GroupId' --output text)
  aws ec2 authorize-security-group-ingress --region "$REGION" --group-id "$SG_ID" \
    --protocol tcp --port 80 --cidr 0.0.0.0/0
  aws ec2 authorize-security-group-ingress --region "$REGION" --group-id "$SG_ID" \
    --protocol tcp --port 443 --cidr 0.0.0.0/0
fi
echo "SG: $SG_ID"

# --- IAM 인스턴스 롤: ECR pull · S3 put · SSM get-parameter · CloudWatch put. ---
if ! aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
  cat > /tmp/repodoc-trust.json <<'JSON'
{ "Version": "2012-10-17",
  "Statement": [ { "Effect": "Allow",
    "Principal": { "Service": "ec2.amazonaws.com" },
    "Action": "sts:AssumeRole" } ] }
JSON
  aws iam create-role --role-name "$ROLE_NAME" \
    --assume-role-policy-document file:///tmp/repodoc-trust.json >/dev/null
fi
aws iam attach-role-policy --role-name "$ROLE_NAME" \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly
cat > /tmp/repodoc-role-policy.json <<'JSON'
{ "Version": "2012-10-17",
  "Statement": [ { "Effect": "Allow",
    "Action": [ "s3:PutObject", "s3:GetObject" ],
    "Resource": "arn:aws:s3:::repodoc-reports/*" },
  { "Effect": "Allow",
    "Action": [ "ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath" ],
    "Resource": "arn:aws:ssm:*:*:parameter/repodoc/*" },
  { "Effect": "Allow",
    "Action": [ "cloudwatch:PutMetricData",
                "logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents",
                "logs:DescribeLogStreams" ],
    "Resource": "*" } ] }
JSON
aws iam put-role-policy --role-name "$ROLE_NAME" \
  --policy-name repodoc-inline --policy-document file:///tmp/repodoc-role-policy.json
aws iam create-instance-profile --instance-profile-name "$PROFILE_NAME" >/dev/null 2>&1 || true
aws iam add-role-to-instance-profile --instance-profile-name "$PROFILE_NAME" \
  --role-name "$ROLE_NAME" 2>/dev/null || true

# --- user-data (SPEC §9.2 verbatim 절차). ---
cat > /tmp/repodoc-userdata.sh <<'USERDATA'
#!/bin/bash
set -eux
systemctl stop unattended-upgrades || true
apt-get -o DPkg::Lock::Timeout=600 update
DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=600 install -y \
  docker.io docker-compose-v2 awscli amazon-cloudwatch-agent curl
# amazon-ssm-agent는 Ubuntu 표준 저장소에 없다(24.04) — snap 설치.
snap install amazon-ssm-agent --classic || apt-get -o DPkg::Lock::Timeout=600 install -y amazon-ssm-agent
systemctl enable --now docker amazon-ssm-agent amazon-cloudwatch-agent
usermod -aG docker ubuntu
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
echo '{"log-driver":"json-file","log-opts":{"max-size":"10m","max-file":"3"}}' > /etc/docker/daemon.json
systemctl restart docker
mkdir -p /opt/repodoc /var/scan
chown -R ubuntu:ubuntu /opt/repodoc /var/scan
echo '*/30 * * * * root find /var/scan -mindepth 1 -mmin +30 -exec rm -rf {} +' \
  > /etc/cron.d/scan-cleanup
touch /var/lib/cloud/instance/repodoc-ready
USERDATA

# --- 인스턴스 기동: 루트 30GB gp3, IAM 프로필 부착. ---
INSTANCE_ID=$(aws ec2 run-instances --region "$REGION" \
  --image-id "$AMI_ID" --instance-type "$INSTANCE_TYPE" \
  --key-name "$KEY_NAME" \
  --security-group-ids "$SG_ID" \
  --iam-instance-profile "Name=$PROFILE_NAME" \
  --block-device-mappings "DeviceName=/dev/sda1,Ebs={VolumeSize=$ROOT_VOLUME_GB,VolumeType=gp3}" \
  --user-data file:///tmp/repodoc-userdata.sh \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=repodoc}]" \
  --count 1 \
  --query 'Instances[0].InstanceId' --output text)
echo "INSTANCE: $INSTANCE_ID — cloud-init 대기는 deploy.sh가 repodoc-ready로 확인한다."

# --- EIP 할당·연결. 할당 후 재할당 금지(도메인 A 레코드 고정 — docs/DEPLOY.md). ---
EIP_ALLOC=$(aws ec2 allocate-address --region "$REGION" \
  --domain vpc --query 'AllocationId' --output text)
aws ec2 associate-address --region "$REGION" --instance-id "$INSTANCE_ID" \
  --allocation-id "$EIP_ALLOC"
EIP=$(aws ec2 describe-addresses --region "$REGION" \
  --allocation-ids "$EIP_ALLOC" --query 'Addresses[0].PublicIp' --output text)
echo "EIP: $EIP — Route 53 A 레코드와 FALLBACK_DOMAIN(<dash-EIP>.sslip.io)에 사용."
