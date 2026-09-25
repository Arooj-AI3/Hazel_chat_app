Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")

projectDir = files.GetParentFolderName(WScript.ScriptFullName)
pythonwPath = files.BuildPath(projectDir, ".venv\Scripts\pythonw.exe")
mainPath = files.BuildPath(projectDir, "main.py")

If Not files.FileExists(pythonwPath) Then
    MsgBox "The project virtual environment was not found. Run setup before launching the app.", vbCritical, "Groq Chat"
    WScript.Quit 1
End If

shell.CurrentDirectory = projectDir
command = Chr(34) & pythonwPath & Chr(34) & " " & Chr(34) & mainPath & Chr(34)
shell.Run command, 1, False