#!/bin/sh
# Backup diário (banco + imagens + recortes) → deploy/data/backups/. Agende com:  crontab -e
#   0 3 * * * /home/ubuntu/omr-exam-system/deploy/backup.sh >> /home/ubuntu/backup.log 2>&1
cd "$(dirname "$0")" && docker compose exec -T api python -m app.backup
