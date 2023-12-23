#!/bin/bash
set -e
BRANCH="main"
SCRIPT_DIR=$(cd $(dirname $0); pwd)

cd $SCRIPT_DIR

git pull

python3 scraper.py

if [ -n "$(git status --porcelain)" ]; then
  msg="ISU: automated update"
  git add .
  git commit -m "$msg"
  git push
else
  echo "Data is up to date"
fi
