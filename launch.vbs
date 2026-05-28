Set oShell = CreateObject("WScript.Shell")
Set oFSO = CreateObject("Scripting.FileSystemObject")

' --- 1. AUTO-DETECT CONDA PATH ---
' This checks the most common installation spots for Anaconda/Miniconda
strUserProf = oShell.ExpandEnvironmentStrings("%USERPROFILE%")
possibleConda(0) = strUserProf & "\anaconda3\Scripts\activate.bat"
possibleConda(1) = strUserProf & "\miniconda3\Scripts\activate.bat"
possibleConda(2) = "C:\ProgramData\anaconda3\Scripts\activate.bat"

strConda = ""
For Each path In possibleConda
    If oFSO.FileExists(path) Then
        strConda = path
        Exit For
    End If
Next

' --- 2. GET CURRENT DIRECTORY ---
' This makes the script run from wherever you placed the folder
strPath = oFSO.GetParentFolderName(WScript.ScriptPosition)

' --- 3. EXECUTION ---
If strConda <> "" Then
    ' Run Backend (main.py)
    oShell.Run "cmd /c cd /d " & strPath & " && call """ & strConda & """ VidGenixAI && python main.py", 0, False
    WScript.Sleep 5000

    ' Run Frontend (webui.bat)
    oShell.Run "cmd /c cd /d " & strPath & " && call """ & strConda & """ VidGenixAI && webui.bat", 0, False
    WScript.Sleep 8000

    ' Launch Browser
    oShell.Run "cmd /c start chrome http://127.0.0.1:8501", 1, False
Else
    MsgBox "Could not find Anaconda/Miniconda. Please ensure it is installed in the default location.", 16, "Error"
End If
