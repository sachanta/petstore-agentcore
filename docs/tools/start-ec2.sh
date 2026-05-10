#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# start-ec2.sh  —  Start dev EC2 instances and connect
#
# Machines managed by this script:
#   linux   → mc-dev-instance-1  (i-0cf74c0989bad70cd) — SSH
#   windows → mc-dev-win2022     (i-010af4643144bef75) — RDP
#
# Usage:
#   ./start-ec2.sh linux          # start Linux + SSH in
#   ./start-ec2.sh windows        # start Windows + open RDP
#   ./start-ec2.sh all            # start both machines
#   ./start-ec2.sh linux --no-connect    # start only, no SSH
#   ./start-ec2.sh windows --no-connect  # start only, no RDP
#
# Requirements on your Mac:
#   - AWS CLI installed and configured  (brew install awscli)
#   - SSH key: ~/srikar-amex.pem
#   - Microsoft Remote Desktop app (for Windows RDP)
#     Install: https://apps.apple.com/app/microsoft-remote-desktop/id1295203466
# ─────────────────────────────────────────────────────────────

set -euo pipefail

# ── Config ────────────────────────────────────────────────────
REGION="us-east-1"
KEY_PATH="${HOME}/srikar-amex.pem"

LINUX_INSTANCE_ID="i-0cf74c0989bad70cd"
LINUX_NAME="mc-dev-instance-1"
LINUX_USER="ubuntu"

WINDOWS_INSTANCE_ID="i-010af4643144bef75"
WINDOWS_NAME="mc-dev-win2022 (EC2AMAZ-GKUG6QT)"
WINDOWS_RDP_PORT="3389"
# ─────────────────────────────────────────────────────────────

# ── Helpers ───────────────────────────────────────────────────

usage() {
  echo "Usage: $0 <linux|windows|all> [--no-connect]"
  echo ""
  echo "  linux            Start Linux instance and SSH in"
  echo "  windows          Start Windows instance and open RDP"
  echo "  all              Start both instances"
  echo "  --no-connect     Start only, do not connect"
  exit 1
}

get_state() {
  aws ec2 describe-instances \
    --instance-ids "$1" \
    --region "$REGION" \
    --query "Reservations[0].Instances[0].State.Name" \
    --output text
}

get_public_ip() {
  aws ec2 describe-instances \
    --instance-ids "$1" \
    --region "$REGION" \
    --query "Reservations[0].Instances[0].PublicIpAddress" \
    --output text
}

start_instance() {
  local id="$1"
  local name="$2"
  local state
  state=$(get_state "$id")

  echo "[$name] State: $state"

  case "$state" in
    running)
      echo "[$name] Already running."
      ;;
    stopped)
      echo "[$name] Starting..."
      aws ec2 start-instances --instance-ids "$id" --region "$REGION" > /dev/null
      echo "[$name] Waiting for 'running' state..."
      aws ec2 wait instance-running --instance-ids "$id" --region "$REGION"
      echo "[$name] Running."
      ;;
    stopping)
      echo "[$name] Waiting for stop to complete..."
      aws ec2 wait instance-stopped --instance-ids "$id" --region "$REGION"
      echo "[$name] Starting..."
      aws ec2 start-instances --instance-ids "$id" --region "$REGION" > /dev/null
      aws ec2 wait instance-running --instance-ids "$id" --region "$REGION"
      echo "[$name] Running."
      ;;
    pending)
      echo "[$name] Already starting — waiting..."
      aws ec2 wait instance-running --instance-ids "$id" --region "$REGION"
      echo "[$name] Running."
      ;;
    *)
      echo "[$name] ERROR: Unexpected state '$state'. Check the AWS console."
      exit 1
      ;;
  esac
}

wait_for_ssh() {
  local ip="$1"
  local name="$2"
  echo "[$name] Waiting for SSH..."
  local attempts=0
  until ssh -i "$KEY_PATH" \
        -o StrictHostKeyChecking=no \
        -o ConnectTimeout=3 \
        -o ServerAliveInterval=60 \
        -o ServerAliveCountMax=3 \
        "${LINUX_USER}@${ip}" "exit" 2>/dev/null; do
    attempts=$((attempts + 1))
    if [[ $attempts -ge 30 ]]; then
      echo "[$name] ERROR: SSH not reachable after 30 attempts. Check security group."
      exit 1
    fi
    printf "."
    sleep 3
  done
  echo " ready."
}

connect_linux() {
  local ip="$1"
  echo ""
  echo "Connecting to ${LINUX_USER}@${ip} ..."
  echo "─────────────────────────────────────────"
  exec ssh -i "$KEY_PATH" \
       -o StrictHostKeyChecking=no \
       -o ServerAliveInterval=60 \
       -o ServerAliveCountMax=3 \
       "${LINUX_USER}@${ip}"
}

get_windows_password() {
  local id="$1"
  echo "Fetching Windows password (requires key pair)..."
  local encrypted
  encrypted=$(aws ec2 get-password-data \
    --instance-id "$id" \
    --region "$REGION" \
    --query "PasswordData" \
    --output text)

  if [[ -z "$encrypted" ]]; then
    echo "  Password not yet available — Windows may still be initialising."
    echo "  Try again in ~2 minutes, or get it from the AWS console:"
    echo "  EC2 → Instances → $id → Actions → Get Windows Password"
    return 1
  fi

  echo "$encrypted" | base64 --decode | openssl rsautl -decrypt -inkey "$KEY_PATH" 2>/dev/null || {
    # macOS openssl may need pkeyutl
    echo "$encrypted" | base64 --decode | openssl pkeyutl -decrypt -inkey "$KEY_PATH"
  }
}

connect_windows() {
  local ip="$1"
  local id="$2"
  echo ""
  echo "[$WINDOWS_NAME]"
  echo "  Public IP : $ip"
  echo "  RDP Port  : $WINDOWS_RDP_PORT"
  echo ""

  # Try to get the password
  local password=""
  password=$(get_windows_password "$id") || true

  if [[ -n "$password" ]]; then
    echo "  Username  : Administrator"
    echo "  Password  : $password"
    echo ""
  else
    echo "  Username  : Administrator"
    echo "  Password  : (see above — not yet available)"
    echo ""
  fi

  # Create a .rdp file and open it with Microsoft Remote Desktop
  local rdp_file="/tmp/mc-dev-win2022.rdp"
  cat > "$rdp_file" <<EOF
full address:s:${ip}:${WINDOWS_RDP_PORT}
username:s:Administrator
prompt for credentials:i:0
administrative session:i:1
EOF

  echo "Opening RDP session..."
  open "$rdp_file"
  echo "(Microsoft Remote Desktop should launch — enter the password above when prompted)"
}

# ── Argument parsing ──────────────────────────────────────────
TARGET="${1:-}"
NO_CONNECT=false

if [[ -z "$TARGET" ]]; then usage; fi
shift

for arg in "$@"; do
  case $arg in
    --no-connect) NO_CONNECT=true ;;
    *) echo "Unknown argument: $arg"; usage ;;
  esac
done

[[ "$TARGET" =~ ^(linux|windows|all)$ ]] || usage

# ── Validate key file ─────────────────────────────────────────
if [[ ! -f "$KEY_PATH" ]]; then
  echo "ERROR: SSH key not found at $KEY_PATH"
  echo "       Update KEY_PATH at the top of this script."
  exit 1
fi
chmod 400 "$KEY_PATH" 2>/dev/null || true

# ── Main ──────────────────────────────────────────────────────

echo ""
echo "=== EC2 Startup Script ==="
echo "Region: $REGION"
echo ""

# Linux
if [[ "$TARGET" == "linux" || "$TARGET" == "all" ]]; then
  start_instance "$LINUX_INSTANCE_ID" "$LINUX_NAME"
  LINUX_IP=$(get_public_ip "$LINUX_INSTANCE_ID")
  echo "[$LINUX_NAME] Public IP: $LINUX_IP"
  echo ""
fi

# Windows
if [[ "$TARGET" == "windows" || "$TARGET" == "all" ]]; then
  start_instance "$WINDOWS_INSTANCE_ID" "$WINDOWS_NAME"
  WINDOWS_IP=$(get_public_ip "$WINDOWS_INSTANCE_ID")
  echo "[$WINDOWS_NAME] Public IP: $WINDOWS_IP"
  echo ""
fi

# Connect
if [[ "$NO_CONNECT" == false ]]; then
  if [[ "$TARGET" == "linux" ]]; then
    wait_for_ssh "$LINUX_IP" "$LINUX_NAME"
    connect_linux "$LINUX_IP"

  elif [[ "$TARGET" == "windows" ]]; then
    connect_windows "$WINDOWS_IP" "$WINDOWS_INSTANCE_ID"

  elif [[ "$TARGET" == "all" ]]; then
    # Start both — print connection info, then SSH into Linux
    # (Windows RDP is opened first as a background app)
    connect_windows "$WINDOWS_IP" "$WINDOWS_INSTANCE_ID"
    echo ""
    wait_for_ssh "$LINUX_IP" "$LINUX_NAME"
    connect_linux "$LINUX_IP"
  fi
else
  echo "─────────────────────────────────────────"
  echo "Started (--no-connect). Manual commands:"
  if [[ "$TARGET" == "linux" || "$TARGET" == "all" ]]; then
    echo "  SSH  : ssh -i $KEY_PATH ${LINUX_USER}@${LINUX_IP}"
  fi
  if [[ "$TARGET" == "windows" || "$TARGET" == "all" ]]; then
    echo "  RDP  : open Microsoft Remote Desktop → add PC → ${WINDOWS_IP}"
    echo "  User : Administrator"
    echo "  Pass : aws ec2 get-password-data --instance-id $WINDOWS_INSTANCE_ID --region $REGION"
  fi
fi
