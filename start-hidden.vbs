' Starts the Adverse Intelligence Platform with the terminal window hidden.
'
' The first ever run stays VISIBLE so you can watch the one-time setup and
' see any error messages. Once set up, this launches silently and keeps its
' output in last-run.log instead.
'
' Stopping: just close the platform's browser tab - the server notices and
' shuts itself down shortly afterwards (it always waits for any in-progress
' search to finish first). If a silent start seems wrong, check last-run.log
' or run start.bat directly to watch the output.

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
projectDir = fso.GetParentFolderName(WScript.ScriptFullName)
batPath = projectDir & "\start.bat"

' Guard against running from inside an unextracted ZIP (or a partial copy).
If Not fso.FileExists(batPath) Then
    MsgBox "start.bat was not found next to this script." & vbCrLf & vbCrLf & _
           "If you downloaded a ZIP file, right-click it and choose " & _
           """Extract All"" first, then open the extracted folder and " & _
           "double-click start-hidden.vbs there.", _
           vbExclamation, "Adverse Intelligence Platform"
    WScript.Quit 1
End If

' The Python environment lives in the user profile (see start.bat).
venvPython = shell.ExpandEnvironmentStrings("%USERPROFILE%") & _
    "\.aip\venv\Scripts\python.exe"

alreadySetUp = fso.FileExists(projectDir & "\frontend\dist\index.html") _
    And fso.FileExists(venvPython)

q = Chr(34)
If alreadySetUp Then
    ' Hidden run: no window will ever appear, so tell start.bat not to sit
    ' waiting for a key press on errors, and keep the output in a log file.
    shell.Environment("PROCESS")("AIP_NO_PAUSE") = "1"
    logPath = projectDir & "\last-run.log"
    shell.Run "%ComSpec% /c " & q & q & batPath & q & _
        " > " & q & logPath & q & " 2>&1" & q, 0, False
Else
    ' First run: show the window so setup progress and errors are visible.
    shell.Run q & batPath & q, 1, False
End If
