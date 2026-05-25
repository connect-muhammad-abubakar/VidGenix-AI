@echo off
title VidGenix AI Updater
echo Updating VidGenix AI...
curl -o app\config\config.py https://raw.githubusercontent.com/connect-muhammad-abubakar/VidGenix-AI/master/app/config/config.py
curl -o main.py https://raw.githubusercontent.com/connect-muhammad-abubakar/VidGenix-AI/master/main.py
curl -o webui\Main.py https://raw.githubusercontent.com/connect-muhammad-abubakar/VidGenix-AI/master/webui/Main.py
curl -o app\services\task.py https://raw.githubusercontent.com/connect-muhammad-abubakar/VidGenix-AI/master/app\services\task.py
curl -o requirements.txt https://raw.githubusercontent.com/connect-muhammad-abubakar/VidGenix-AI/master/requirements.txt
echo.
echo Update Complete! You can now start VidGenix AI.
pause
