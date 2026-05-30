Set oShell = CreateObject("WScript.Shell")
Set oFSO   = CreateObject("Scripting.FileSystemObject")

' ── 1. Get project directory (folder this .vbs file lives in) ──
' WScript.ScriptFullName gives the full path to this .vbs file.
' GetParentFolderName extracts the folder it lives in.
strPath = oFSO.GetParentFolderName(WScript.ScriptFullName)

' ── 2. Auto-detect Conda activate.bat ─────────────────────────
strUserProf = oShell.ExpandEnvironmentStrings("%USERPROFILE%")
Dim possibleConda(3)
possibleConda(0) = strUserProf & "\miniconda3\Scripts\activate.bat"
possibleConda(1) = strUserProf & "\anaconda3\Scripts\activate.bat"
possibleConda(2) = "C:\ProgramData\miniconda3\Scripts\activate.bat"
possibleConda(3) = "C:\ProgramData\anaconda3\Scripts\activate.bat"

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

    ' Start FastAPI backend (hidden window)
    oShell.Run "cmd /c cd /d """ & strPath & """ && call """ & strConda & """ MoneyPrinterTurbo && python main.py > backend.log 2>&1", 0, False
    WScript.Sleep 6000

    ' Start Streamlit frontend (hidden window)
    oShell.Run "cmd /c cd /d """ & strPath & """ && call """ & strConda & """ MoneyPrinterTurbo && python -m streamlit run webui\Main.py --server.port 8501 --server.address 127.0.0.1 --server.headless true", 0, False
    WScript.Sleep 10000

    ' Open default browser (works regardless of which browser is installed)
    oShell.Run "cmd /c start http://127.0.0.1:8501", 0, False

Else
    MsgBox "Could not find Conda. Please install Miniconda or Anaconda." & vbCrLf & _
           "Checked locations:" & vbCrLf & _
           "%USERPROFILE%\miniconda3" & vbCrLf & _
           "%USERPROFILE%\anaconda3" & vbCrLf & _
           "C:\ProgramData\miniconda3" & vbCrLf & _
           "C:\ProgramData\anaconda3", _
           16, "VidGenix AI — Error"
End If
