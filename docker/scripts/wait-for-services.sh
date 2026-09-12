#!/bin/bash
# Wait for dependent services to be healthy

set -euo pipefail

SERVICES="${1:-}"
if [ -z "$SERVICES" ]; then
    echo "Usage: $0 <service1,service2,...>"
    exit 1
fi

IFS=',' read -ra SERVICE_LIST <<< "$SERVICES"

for SERVICE in "${SERVICE_LIST[@]}"; do
    echo "Waiting for $SERVICE..."
    
    case $SERVICE in
        central)
            URL="https://central:8000/health"
            ;;
        vision)
            URL="https://vision:8001/health"
            ;;
        audio)
            URL="https://audio:8002/health"
            ;;
        tts)
            URL="https://tts:8003/health"
            ;;
        teachme)
            URL="https://teachme:8004/health"
            ;;
        enrollment)
            URL="https://enrollment:8005/health"
            ;;
        llm)
            URL="https://llm:8006/api/v1/health"
            ;;
        *)
            echo "Unknown service: $SERVICE"
            exit 1
            ;;
    esac
    
    for i in {1..30}; do
        if curl -sf --cacert "${NEXI_TLS_CA_FILE:?TLS CA path required}" "$URL" > /dev/null 2>&1; then
            echo "✓ $SERVICE is ready"
            break
        fi
        if [ $i -eq 30 ]; then
            echo "✗ $SERVICE failed to become ready"
            exit 1
        fi
        sleep 2
    done
done

echo "All services ready!"
