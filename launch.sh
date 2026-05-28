#!/bin/bash

# Move to project directory
cd ~/VidGenixAI

# 1. Start the Backend (Uvicorn)
echo "Starting Backend Server..."
python main.py & 

# Wait for the API to initialize
sleep 5

# 2. Start the Streamlit Web UI
echo "Starting Streamlit UI..."
# Using the correct path discovered via your find command
python -m streamlit run webui/Main.py --server.port 8501 &

# Wait for UI to be ready
sleep 8

# 3. Open the Browser
echo "Opening VidGenix-AI..."
xdg-open http://127.0.0.1:8501 &
