Option Explicit
Dim fso, sh, scriptDir, psScript, profileName, mode, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
psScript = scriptDir & "\Codex-Multi.ps1"

profileName = "default"
mode = "LaunchDesktop"

If WScript.Arguments.Count >= 1 Then
    profileName = WScript.Arguments(0)
End If
If WScript.Arguments.Count >= 2 Then
    mode = WScript.Arguments(1)
End If

cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & psScript & """ -Action " & mode & " -Name """ & profileName & """"
sh.Run cmd, 0, False
