#!/usr/bin/env bash
# Ubuntu / WSL setup for running PHPJoy Phase-2. Run from the phpjoy_release/ ROOT. Needs sudo.
#   cd phpjoy_release && bash build/env_setup.sh
set -euo pipefail
ROOT="$(pwd)"

echo "[1/5] apt packages (PHP 8, Java 11, Python, git)…"
sudo apt-get update -y
sudo apt-get install -y php-cli php-xml php-mbstring php-curl \
     openjdk-11-jdk python3 python3-venv python3-pip git curl unzip

echo "[2/5] composer + uv…"
if ! command -v composer >/dev/null; then
  curl -sS https://getcomposer.org/installer | php
  sudo mv composer.phar /usr/local/bin/composer
fi
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

echo "[3/5] Neo4j community-4.4.4 into project root…"
if [ ! -d "$ROOT/neo4j-community-4.4.4" ]; then
  curl -L -o /tmp/neo4j.tgz https://dist.neo4j.org/neo4j-community-4.4.4-unix.tar.gz
  tar xzf /tmp/neo4j.tgz -C "$ROOT" && rm /tmp/neo4j.tgz
fi
# allow fetching arbitrary commits is a git thing, not neo4j; note default password must be set
echo "    -> set Neo4j password once: $ROOT/neo4j-community-4.4.4/bin/neo4j-admin set-initial-password 123"

echo "[4/5] php2ast composer deps…"
( cd "$ROOT/phpjoy/php2ast/src" && composer install )

echo "[5/5] python venv + apis deps…"
python3 -m venv "$ROOT/.venv"
# shellcheck disable=SC1091
. "$ROOT/.venv/bin/activate"
pip install -U pip
pip install py2neo networkx
echo "    (QLoRA deps are separate/GPU box: pip install 'transformers>=4.44' peft bitsandbytes datasets accelerate scikit-learn)"

echo
echo "DONE. Versions:"; php -v | head -1; java -version 2>&1 | head -1; python3 --version
echo "Next: verify the toolchain on ONE sample -> follow build/SMOKE_TEST.md, then run: python build/run_phase2.py --limit 1"
