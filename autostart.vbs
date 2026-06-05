
' 対旋律作成ツール — バックグラウンド自動起動
' ポート5000がすでに使用中なら何もしない
Dim oShell, oExec
Set oShell = CreateObject("WScript.Shell")

' netstat でポート確認
Set oExec = oShell.Exec("cmd /c netstat -ano | findstr :5000")
Dim result : result = oExec.StdOut.ReadAll

If InStr(result, ":5000") = 0 Then
    ' サーバーが起動していない場合のみ起動
    oShell.CurrentDirectory = "C:\Users\NEC\music_counterpoint"
    oShell.Run "python app.py", 0, False
End If
