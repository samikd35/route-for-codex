[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  UserPath, BinDir, Updated: string;
begin
  if CurStep <> ssPostInstall then Exit;
  BinDir := ExpandConstant('{app}\bin');
  RegQueryStringValue(HKCU, 'Environment', 'Path', UserPath);
  if Pos(';' + Lowercase(BinDir) + ';', ';' + Lowercase(UserPath) + ';') > 0 then Exit;
  Updated := UserPath;
  if (Updated <> '') and (Copy(Updated, Length(Updated), 1) <> ';') then
    Updated := Updated + ';';
  if RegWriteExpandStringValue(HKCU, 'Environment', 'Path', Updated + BinDir) then
    RegWriteStringValue(HKCU, 'Software\RouteForCodex', 'AddedPath', BinDir);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  UserPath, BinDir, Updated: string;
  Start: Integer;
begin
  if CurUninstallStep <> usPostUninstall then Exit;
  if not RegQueryStringValue(HKCU, 'Software\RouteForCodex', 'AddedPath', BinDir) then Exit;
  if RegQueryStringValue(HKCU, 'Environment', 'Path', UserPath) then begin
    Updated := ';' + UserPath + ';';
    Start := Pos(';' + Lowercase(BinDir) + ';', Lowercase(Updated));
    if Start > 0 then begin
      Delete(Updated, Start, Length(BinDir) + 1);
      Updated := Copy(Updated, 2, Length(Updated) - 2);
      RegWriteExpandStringValue(HKCU, 'Environment', 'Path', Updated);
    end;
  end;
  RegDeleteValue(HKCU, 'Software\RouteForCodex', 'AddedPath');
  RegDeleteKeyIfEmpty(HKCU, 'Software\RouteForCodex');
end;
