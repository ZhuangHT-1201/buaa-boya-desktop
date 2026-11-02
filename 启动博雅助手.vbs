Option Explicit

Dim shell, fso, root, exePath, exePathEn, setupPath, pythonw, appName, appTitle, appTitleEn, setupName
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
appName = ChrW(21338) & ChrW(38597) & ChrW(33258) & ChrW(21160) & ChrW(21161) & ChrW(25163) & ".exe"
appTitle = ChrW(21338) & ChrW(38597) & ChrW(33258) & ChrW(21160) & ChrW(21161) & ChrW(25163)
appTitleEn = "Boya Automation"
setupName = ChrW(19968) & ChrW(38190) & ChrW(23433) & ChrW(35013) & ChrW(24182) & ChrW(21551) & ChrW(21160) & ".cmd"
exePath = fso.BuildPath(fso.BuildPath(root, "release"), appName)
exePathEn = fso.BuildPath(fso.BuildPath(root, "release"), "BoyaAutomation.exe")

If shell.AppActivate(appTitleEn) Then
    WScript.Quit 0
End If
If shell.AppActivate(appTitle) Then
    WScript.Quit 0
End If

If Not fso.FileExists(exePath) And fso.FileExists(exePathEn) Then
    exePath = exePathEn
End If

If fso.FileExists(exePath) Then
    shell.CurrentDirectory = fso.GetParentFolderName(exePath)
    shell.Run Chr(34) & exePath & Chr(34), 1, False
Else
    pythonw = fso.BuildPath(root, ".venv\Scripts\pythonw.exe")
    If fso.FileExists(pythonw) Then
        shell.CurrentDirectory = root
        shell.Run Chr(34) & pythonw & Chr(34) & " -m boya_kit.launcher", 1, False
    Else
        setupPath = fso.BuildPath(root, setupName)
        shell.Run "cmd /c """ & setupPath & """", 1, False
    End If
End If
