#!/bin/bash
# Despliega el servidor webhook en Railway y actualiza el agente ElevenLabs.
# Ejecutar UNA SOLA VEZ desde la terminal:   bash deploy.sh

set -e

RAILWAY="$HOME/.local/bin/railway"
DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "═══════════════════════════════════════════"
echo "  Despliegue Salón Bot → Railway"
echo "═══════════════════════════════════════════"
echo ""

# 1. Login (abre el navegador)
echo "▶ Paso 1/4  Iniciando sesión en Railway..."
$RAILWAY login
echo ""

# 2. Inicializar proyecto
echo "▶ Paso 2/4  Creando proyecto en Railway..."
cd "$DIR"
$RAILWAY init --name salon-bot 2>/dev/null || true
echo ""

# 3. Configurar variables de entorno
echo "▶ Paso 3/4  Configurando variables de entorno..."

GCREDS=$(python3 -c "import base64; print(base64.b64encode(open('credentials.json','rb').read()).decode())")

$RAILWAY variables set \
  GOOGLE_CREDENTIALS_JSON="$GCREDS" \
  GOOGLE_CALENDAR_ID="$(grep GOOGLE_CALENDAR_ID .env | cut -d= -f2)" \
  SALON_TIMEZONE="$(grep SALON_TIMEZONE .env | cut -d= -f2)" \
  OPEN_HOUR="$(grep '^OPEN_HOUR' .env | cut -d= -f2)" \
  CLOSE_HOUR="$(grep '^CLOSE_HOUR' .env | cut -d= -f2)"

echo ""

# 4. Desplegar
echo "▶ Paso 4/4  Desplegando... (puede tardar ~2 min)"
$RAILWAY up --detach --service salon-bot-webhook 2>/dev/null || $RAILWAY up --detach

# Obtener URL pública
echo ""
echo "Obteniendo URL pública..."
sleep 10
PUBLIC_URL=$($RAILWAY domain 2>/dev/null || echo "")

if [ -z "$PUBLIC_URL" ]; then
  # Generar dominio Railway
  $RAILWAY domain --generate 2>/dev/null || true
  sleep 5
  PUBLIC_URL=$($RAILWAY domain 2>/dev/null || echo "")
fi

if [ -z "$PUBLIC_URL" ]; then
  echo ""
  echo "⚠  No se pudo obtener la URL automáticamente."
  echo "   Ábrela desde: https://railway.app/dashboard"
  echo "   Luego ejecuta: python3 setup_agent.py --webhook https://TU-URL.railway.app"
else
  WEBHOOK_URL="https://$PUBLIC_URL"
  echo ""
  echo "✓ URL pública: $WEBHOOK_URL"
  echo ""
  echo "▶ Actualizando agente ElevenLabs con webhook permanente..."
  python3 setup_agent.py --webhook "$WEBHOOK_URL"
fi

echo ""
echo "═══════════════════════════════════════════"
echo "  ¡Listo! El servidor corre 24/7 en Railway."
echo "  Abre ElevenLabs y prueba el agente."
echo "═══════════════════════════════════════════"
echo ""
