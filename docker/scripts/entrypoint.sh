#!/bin/bash
set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}=== NEXI Service Entrypoint ===${NC}"

# 1. Load .env if exists
if [ -f /app/.env ]; then
    export $(grep -v '^#' /app/.env | xargs)
    echo -e "${GREEN}Loaded .env${NC}"
fi

# 2. Prompt for missing required API keys
prompt_for_key() {
    local var_name=$1
    local description=$2
    local current_value=${!var_name:-}
    
    if [ -z "$current_value" ] || [ "$current_value" = "YOUR_${var_name}_HERE" ]; then
        echo -e "${YELLOW}$description is required but not set.${NC}"
        read -p "Enter $var_name: " value
        export $var_name="$value"
        # Persist to .env for next run
        echo "$var_name=$value" >> /app/.env
    else
        echo -e "${GREEN}$var_name is set${NC}"
    fi
}

# Required keys
prompt_for_key "OPENROUTER_API_KEY" "OpenRouter API Key (for LLM)"
prompt_for_key "GROQ_API_KEY" "Groq API Key (for Audio STT)"
prompt_for_key "PORCUPINE_ACCESS_KEY" "Picovoice Access Key (for wake-word)"

# 3. Download models if needed
if [ "$DOWNLOAD_MODELS" = "true" ]; then
    echo -e "${GREEN}Downloading models...${NC}"
    python /app/scripts/download_models.py || true
fi

# 4. Wait for dependencies
if [ -n "$WAIT_FOR_SERVICES" ]; then
    echo -e "${GREEN}Waiting for dependent services...${NC}"
    /app/scripts/wait-for-services.sh "$WAIT_FOR_SERVICES"
fi

# 5. Execute command
exec "$@"