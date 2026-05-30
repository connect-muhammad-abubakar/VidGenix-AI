Set oShell = CreateObject("WScript.Shell")
Set oFSO   = CreateObject("Scripting.FileSystemObject")

' ── 1. Get project directory ───────────────────────────────────
strPath = oFSO.GetParentFolderName(WScript.ScriptFullName)

' ── 2. Auto-detect Conda activate.bat ─────────────────────────
strUserProf = oShell.ExpandEnvironmentStrings("%USERPROFILE%")
Dim possibleConda(3)
possibleConda(0) = strUserProf & "\Miniconda3\Scripts\activate.bat"
possibleConda(1) = strUserProf & "\miniconda3\Scripts\activate.bat"
possibleConda(2) = strUserProf & "\anaconda3\Scripts\activate.bat"
possibleConda(3) = "C:\ProgramData\miniconda3\Scripts\activate.bat"

strConda = ""
Dim i
For i = 0 To 3
    If oFSO.FileExists(possibleConda(i)) Then
        strConda = possibleConda(i)
        Exit For
    End If
Next

' ── 3. Launch ──────────────────────────────────────────────────
If strConda <> "" Then

    ' Kill any old processes on ports 8080 and 8501
    oShell.Run "cmd /c for /f ""tokens=5"" %a in ('netstat -aon ^| findstr :8080') do taskkill /f /pid %a", 0, True
    oShell.Run "cmd /c for /f ""tokens=5"" %a in ('netstat -aon ^| findstr :8501') do taskkill /f /pid %a", 0, True
    WScript.Sleep 2000

    ' Start FastAPI backend (hidden window)
    oShell.Run "cmd /c cd /d """ & strPath & """ && call """ & strConda & """ MoneyPrinterTurbo && python main.py > backend.log 2>&1", 0, False
    WScript.Sleep 6000

    ' Start Streamlit frontend (hidden window)
    oShell.Run "cmd /c cd /d """ & strPath & """ && call """ & strConda & """ MoneyPrinterTurbo && python -m streamlit run webui\Main.py --server.port 8501 --server.address 127.0.0.1 --server.headless true", 0, False
    WScript.Sleep 10000

    ' Open default browser
    oShell.Run "cmd /c start http://127.0.0.1:8501", 0, False

Else
    MsgBox "Could not find Conda/Miniconda." & vbCrLf & vbCrLf & _
           "Checked locations:" & vbCrLf & _
           "%USERPROFILE%\Miniconda3" & vbCrLf & _
           "%USERPROFILE%\miniconda3" & vbCrLf & _
           "%USERPROFILE%\anaconda3" & vbCrLf & _
           "C:\ProgramData\miniconda3", _
           16, "VidGenix AI — Error"
End If
