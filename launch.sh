#!/bin/bash
# ─────────────────────────────────────────────
# VidGenix AI — Linux Launcher (launch.sh)
# ─────────────────────────────────────────────

set -e

PROJECT_DIR="$HOME/VidGenixAI"
ENV_NAME="MoneyPrinterTurbo"
BACKEND_PORT=8080
FRONTEND_PORT=8501
BACKEND_LOG="$PROJECT_DIR/backend.log"

# ── 1. Find Conda ─────────────────────────────
CONDA_PATH=""
for p in \
    "$HOME/miniconda3/etc/profile.d/conda.sh" \
    "$HOME/anaconda3/etc/profile.d/conda.sh" \
    "/opt/conda/etc/profile.d/conda.sh"; do
    if [ -f "$p" ]; then
        CONDA_PATH="$p"
        break
    fi
done

if [ -z "$CONDA_PATH" ]; then
    echo "[ERROR] Conda not found. Please install Miniconda or Anaconda."
    exit 1
fi

source "$CONDA_PATH"
conda activate "$ENV_NAME"

# ── 2. Move to project dir ────────────────────
cd "$PROJECT_DIR"

# ── 3. Kill any old processes on our ports ────
echo "[INFO] Cleaning up old sessions..."
fuser -k ${BACKEND_PORT}/tcp 2>/dev/null || true
fuser -k ${FRONTEND_PORT}/tcp 2>/dev/null || true
sleep 2

# ── 4. Verify key dependencies ────────────────
echo "[INFO] Verifying dependencies..."
python -c "import fastapi, pydantic, streamlit, uvicorn, openai, bs4, moviepy, loguru, edge_tts" 2>/dev/null || {
    echo "[INFO] Missing libraries — installing..."
    pip install fastapi pydantic uvicorn streamlit moviepy loguru pillow \
        openai edge-tts beautifulsoup4 requests google-generativeai pydub
}

# ── 5. Start FastAPI backend ──────────────────
echo "[INFO] Starting backend server (port $BACKEND_PORT)..."
python main.py > "$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!
echo "[INFO] Backend PID: $BACKEND_PID"

# Wait until backend is actually ready
echo -n "[INFO] Waiting for backend"
for i in $(seq 1 15); do
    sleep 1
    if curl -s http://127.0.0.1:${BACKEND_PORT}/docs > /dev/null 2>&1; then
        echo " ready!"
        break
    fi
    echo -n "."
done
echo ""

# ── 6. Start Streamlit frontend ───────────────
echo "[INFO] Starting Streamlit UI (port $FRONTEND_PORT)..."
python -m streamlit run webui/Main.py \
    --server.port $FRONTEND_PORT \
    --server.address 127.0.0.1 \
    --server.headless true &
FRONTEND_PID=$!
echo "[INFO] Frontend PID: $FRONTEND_PID"

sleep 5

# ── 7. Open browser ───────────────────────────
echo "[INFO] Opening browser..."
xdg-open http://127.0.0.1:${FRONTEND_PORT} 2>/dev/null || \
    echo "[INFO] Open your browser at: http://127.0.0.1:${FRONTEND_PORT}"

echo ""
echo "════════════════════════════════════════"
echo "  VidGenix AI is running!"
echo "  UI  → http://127.0.0.1:${FRONTEND_PORT}"
echo "  API → http://127.0.0.1:${BACKEND_PORT}/docs"
echo "  Backend log → $BACKEND_LOG"
echo "  Press Ctrl+C to stop."
echo "════════════════════════════════════════"

# Keep script alive and handle clean shutdown
trap "echo '[INFO] Shutting down...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" SIGINT SIGTERM
wait
