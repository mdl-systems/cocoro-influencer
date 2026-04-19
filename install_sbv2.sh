#!/bin/bash
# Style-Bert-VITS2 依存関係インストールスクリプト
LOG=/tmp/sbv2_install.log
echo "[$(date)] インストール開始" > $LOG

cd /home/Style-Bert-VITS2
source venv/bin/activate

echo "[$(date)] torch 2.4.0 インストール中..." >> $LOG
pip install --no-cache-dir torch==2.4.0 torchaudio==2.4.0 \
    --index-url https://download.pytorch.org/whl/cu124 >> $LOG 2>&1

if [ $? -eq 0 ]; then
    echo "[$(date)] torch インストール成功" >> $LOG
else
    echo "[$(date)] torch インストール失敗" >> $LOG
    exit 1
fi

echo "[$(date)] librosa==0.9.2 インストール中..." >> $LOG
pip install --no-cache-dir librosa==0.9.2 --no-deps >> $LOG 2>&1

if [ $? -eq 0 ]; then
    echo "[$(date)] librosa インストール成功" >> $LOG
else
    echo "[$(date)] librosa インストール失敗" >> $LOG
fi

echo "[$(date)] 完了" >> $LOG
