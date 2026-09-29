#!/usr/bin/env bash
# Bootstrap local dev environment.
set -e

echo "Setting up backend..."
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..

echo "Setting up dashboard..."
cd dashboard
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..

echo "Copy .env.example to .env and fill in values:"
echo "  cp .env.example .env"
echo ""
echo "Start infra with: cd docker && docker compose up -d"
