#!/bin/bash

# 1. Setup Conda path
CONDA_PATH="$HOME/miniconda3/etc/profile.d/conda.sh"
if [ ! -f "$CONDA_PATH" ]; then
    CONDA_PATH="$HOME/anaconda3/etc/profile.d/conda.sh"
fi

# 2. Move to project directory
cd ~/VidGenixAI

# --- NEW: CLEANUP OLD PROCESSES ---
echo "Cleaning up old sessions..."
fuser -k 8080/tcp 2>/dev/null
fuser -k 8501/tcp 2>/dev/null
sleep 2
# ----------------------------------

# 3. Source Conda and activate
if [ -f "$CONDA_PATH" ]; then
    source "$CONDA_PATH"
    conda activate VidGenixAI
else
    echo "Error: Conda not found."
    exit 1
fi

# 4. Dependency Guard
echo "Verifying project dependencies..."
python -c "import fastapi, pydantic, streamlit, uvicorn, openai, bs4" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Missing libraries. Installing now..."
    pip install fastapi pydantic uvicorn streamlit moviepy loguru pillow openai edge-tts beautifulsoup4 requests
fi

# 5. Start the Backend
echo "Starting Backend Server..."
python main.py > backend.log 2>&1 & 

sleep 5

# 6. Start the Streamlit Web UI
echo "Starting Streamlit UI..."
python -m streamlit run webui/Main.py --server.port 8501 --server.address 127.0.0.1 &

sleep 8

# 7. Open the Browser
echo "Opening VidGenix-AI..."
xdg-open http://127.0.0.1:8501 &
