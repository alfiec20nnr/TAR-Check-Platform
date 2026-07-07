' Starts the Adverse Intelligence Platform with the terminal window hidden.
'
' The first ever run stays VISIBLE so you can watch the one-time setup and
' see any error messages. Once set up, this launches silently.
'
' Stopping: just close the platform's browser tab - the server notices and
' shuts itself down shortly afterwards (it always waits for any in-progress
' search to finish first). If something seems wrong, run start.bat directly
' to see the output.

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
projectDir = fso.GetParentFolderName(WScript.ScriptFullName)

alreadySetUp = fso.FileExists(projectDir & "\frontend\dist\index.html") _
    And fso.FileExists(projectDir & "\backend\.venv\Scripts\python.exe")

windowStyle = 0                       ' hidden
If Not alreadySetUp Then windowStyle = 1  ' first run: show the setup window

shell.Run """" & projectDir & "\start.bat""", windowStyle, False
