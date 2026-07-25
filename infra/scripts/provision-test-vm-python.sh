#!/usr/bin/env bash
# Provisions a Python venv on vm-rag-test and installs requirements.txt.
# Expects /tmp/requirements.txt to already be present on the VM (written by
# provision-test-vm-python.ps1 before this script runs).
set -euo pipefail

sudo apt-get update
sudo apt-get install -y python3-venv python3-pip

python3 -m venv ~/.venv
source ~/.venv/bin/activate

pip install --upgrade pip
pip install -r /tmp/requirements.txt

python3 -c "import openai, azure.search.documents, azure.identity; print('venv OK')"
