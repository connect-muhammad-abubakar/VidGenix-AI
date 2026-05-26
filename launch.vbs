Set oShell = CreateObject("WScript.Shell")
strConda = "C:\Users\Usman\anaconda3\Scripts\activate.bat"
strPath = "C:\VidGenixAI"
oShell.Run "cmd /c cd /d " & strPath & " && call " & strConda & " VidGenixAI && python main.py", 0, False
WScript.Sleep 5000
oShell.Run "cmd /c cd /d " & strPath & " && call " & strConda & " VidGenixAI && webui.bat", 0, False
WScript.Sleep 8000
oShell.Run "cmd /c start chrome http://127.0.0.1:8501", 0, False
