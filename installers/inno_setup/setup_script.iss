; 媒小宝 (WeMediaBaby) Inno Setup 脚本 template
; 用于"迭代期"快速生成安装包
; 文档: docs/软件打包实施方案.md

#ifndef BuildDir
#define BuildDir "..\..\dist\fast\WeMediaBaby"
#endif

#ifndef OutputPrefix
#define OutputPrefix "Fast"
#endif

; 破坏性升级开关（默认 0 = 允许就地覆盖安装，与日常 Secure 小版本一致）
; 大版本或存储/配置格式不兼容时：在本行改为 1，或用 ISCC 编译加 /DRequireCleanInstall=1
#ifndef RequireCleanInstall
#define RequireCleanInstall 0
#endif

#define MyAppName "WeMediaBaby"
; 快捷方式及安装完成"运行"按钮显示的中文名称
#define MyAppShortcutName "媒小宝"
#ifndef MyAppVersion
  #define MyAppVersion "1.4.4"
#endif
#define MyAppPublisher "MediaBaby Team"
#define MyAppURL "https://github.com/your-repo/wemedia-baby"
#define MyAppExeName "WeMediaBaby.exe"
; 与 [Setup] 中 AppId 的 GUID 一致（去掉花括号），供检测已安装版本；若修改 AppId 必须同步改此处
#define MyAppUninstallRegSubKey "Software\Microsoft\Windows\CurrentVersion\Uninstall\E6F78A12-3456-7890-ABCD-EF1234567890_is1"

; 动态判断快捷方式外部图标路径：PyInstaller(Fast)使用 _internal 内部环境层，Nuitka(Secure)使用根目录
#if Copy(OutputPrefix, 1, 4) == "Fast"
  #define IconFallbackPath "{app}\_internal\resources\icons\app.ico"
#else
  #define IconFallbackPath "{app}\resources\icons\app.ico"
#endif

[Setup]
; NOTE: The value of AppId uniquely identifies this application. Do not use the same AppId value in installers for other applications.
; (To generate a new GUID, click Tools | Generate GUID inside the IDE.)
AppId={{E6F78A12-3456-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\{#MyAppName}\app
DisableProgramGroupPage=yes
; 使用非管理员安装模式（安装到当前用户目录，无需管理员权限）
PrivilegesRequired=lowest
OutputDir=..\..\dist\installers
OutputBaseFilename=WeMediaBaby_Setup_{#OutputPrefix}_v{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
SetupIconFile=..\..\resources\icons\app.ico
WizardStyle=modern

[Languages]
; 安装界面仅保留简体中文（使用项目内 Language 文件，不依赖 Inno 安装目录）
Name: "chinesesimplified"; MessagesFile: "Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; 动态获取 Source
Source: "{#BuildDir}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; NOTE: Don't use "Flags: ignoreversion" on any shared system files

[Icons]
; 用户级别的快捷方式（非管理员安装），显示名称使用中文"媒小宝"
; WorkingDir 必须设为 {app}，否则双击时当前目录可能是桌面等，导致 Qt/依赖找不到插件或资源而静默退出
Name: "{userprograms}\{#MyAppShortcutName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{#IconFallbackPath}"
Name: "{userdesktop}\{#MyAppShortcutName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; WorkingDir: "{app}"; IconFilename: "{#IconFallbackPath}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppShortcutName}}"; Flags: nowait postinstall skipifsilent; WorkingDir: "{app}"

[Code]
procedure SplitUninstallString(const S: string; var ExePath, Params: string);
var
  T: string;
  I: Integer;
begin
  T := Trim(S);
  ExePath := T;
  Params := '';
  if T = '' then
    Exit;
  if T[1] = '"' then
  begin
    I := 2;
    while (I <= Length(T)) and (T[I] <> '"') do
      I := I + 1;
    if I <= Length(T) then
    begin
      ExePath := Copy(T, 2, I - 2);
      Params := Trim(Copy(T, I + 1, Length(T)));
    end;
  end
  else
  begin
    I := Pos(' ', T);
    if I > 0 then
    begin
      ExePath := Copy(T, 1, I - 1);
      Params := Trim(Copy(T, I + 1, Length(T)));
    end;
  end;
end;

function QueryInstalledUninstallString(var UninstallCmd: string): Boolean;
begin
  UninstallCmd := '';
  { 当前脚本为 per-user 安装，卸载项在 HKCU；若曾用管理员安装可能落在 HKLM，一并探测 }
  if RegQueryStringValue(HKCU, '{#MyAppUninstallRegSubKey}', 'UninstallString', UninstallCmd) then
  begin
    Result := True;
    Exit;
  end;
  if RegQueryStringValue(HKLM64, '{#MyAppUninstallRegSubKey}', 'UninstallString', UninstallCmd) then
  begin
    Result := True;
    Exit;
  end;
  if RegQueryStringValue(HKLM32, '{#MyAppUninstallRegSubKey}', 'UninstallString', UninstallCmd) then
  begin
    Result := True;
    Exit;
  end;
  Result := False;
end;

function InitializeSetup(): Boolean;
#if RequireCleanInstall == 1
var
  UninstallCmd: string;
  ExePath: string;
  Params: string;
  ErrCode: Integer;
#endif
begin
  Result := True;
  { 静默安装：不弹窗 }
  if WizardSilent then
    Exit;

#if RequireCleanInstall == 1
  { 破坏性升级：检测到已安装则要求先卸载，并结束本次安装向导 }
  if not QueryInstalledUninstallString(UninstallCmd) then
    Exit;

  if MsgBox(
    '本安装包为「需干净安装」版本（例如大版本升级或存储格式已变更）。' + #13#10 + #13#10 +
    '检测到本机已安装「{#MyAppShortcutName}」。请先卸载旧版本，再运行本安装包，以免程序目录残留导致异常。' + #13#10 + #13#10 +
    '• 点击「是」：打开卸载程序，完成后请重新双击本安装包。' + #13#10 +
    '• 点击「否」：退出安装。',
    mbConfirmation,
    MB_YESNO) = IDYES then
  begin
    SplitUninstallString(UninstallCmd, ExePath, Params);
    if ExePath <> '' then
      ShellExec('', ExePath, Params, '', SW_SHOW, ewNoWait, ErrCode);
  end;

  Result := False;
#endif
end;

{ ============================================================
  卸载前检测软件是否正在运行，若是则提示用户并强制退出后再卸载
  ============================================================ }

const
  WM_CLOSE = $0010;

function FindWindow(lpClassName, lpWindowName: String): THandle;
  external 'FindWindowW@user32.dll stdcall';

function PostMessage(hWnd: THandle; Msg: Integer; wParam, lParam: Integer): BOOL;
  external 'PostMessageW@user32.dll stdcall';

procedure Sleep(dwMilliseconds: Integer);
  external 'Sleep@kernel32.dll stdcall';

{ 通过 tasklist 检查目标进程是否正在运行 }
function IsAppRunning(const ExeName: String): Boolean;
var
  TmpFile:    String;
  ResultCode: Integer;
  Lines:      TArrayOfString;
  i:          Integer;
begin
  Result := False;
  TmpFile := ExpandConstant('{tmp}\wemb_proc_check.txt');
  if Exec(ExpandConstant('{sys}\cmd.exe'),
      '/C tasklist /FI "IMAGENAME eq ' + ExeName + '" /NH /FO CSV > "' + TmpFile + '"',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    if LoadStringsFromFile(TmpFile, Lines) then
    begin
      for i := 0 to GetArrayLength(Lines) - 1 do
      begin
        if Pos(LowerCase(ExeName), LowerCase(Lines[i])) > 0 then
        begin
          Result := True;
          Break;
        end;
      end;
    end;
  end;
end;

{ 先发 WM_CLOSE 尝试优雅退出，等待最多 WaitSec 秒后仍未退出则强制终止 }
procedure KillApp(const ExeName: String; WaitSec: Integer);
var
  hWnd:       THandle;
  ResultCode: Integer;
  i:          Integer;
begin
  { 向主窗口发送 WM_CLOSE，让软件走正常退出流程（含托盘图标清理） }
  hWnd := FindWindow('', '{#MyAppShortcutName}');
  if hWnd <> 0 then
    PostMessage(hWnd, WM_CLOSE, 0, 0);

  { 每 500ms 轮询一次，等待进程自然退出 }
  for i := 1 to WaitSec * 2 do
  begin
    Sleep(500);
    if not IsAppRunning(ExeName) then
      Exit;
  end;

  { 超时仍未退出：强制终止 }
  Exec(ExpandConstant('{sys}\taskkill.exe'),
    '/F /IM ' + ExeName,
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

{ 卸载初始化钩子：若软件正在运行则询问用户是否先退出再卸载 }
function InitializeUninstall(): Boolean;
begin
  Result := True;
  if not IsAppRunning('{#MyAppExeName}') then
    Exit;

  if MsgBox(
    '检测到「{#MyAppShortcutName}」正在运行（包括最小化到系统托盘的情况）。' + #13#10 + #13#10 +
    '继续卸载前需要先关闭软件，否则可能导致卸载不干净。' + #13#10 + #13#10 +
    '• 点击「是」：自动关闭软件并继续卸载。' + #13#10 +
    '• 点击「否」：取消卸载，请手动关闭软件后再重试。',
    mbConfirmation,
    MB_YESNO) = IDNO then
  begin
    Result := False;
    Exit;
  end;

  { 用户确认：先优雅关闭，最多等 6 秒，超时强制终止 }
  KillApp('{#MyAppExeName}', 6);

  { 再次确认进程是否退出；若仍在运行则提示但不阻止卸载继续 }
  if IsAppRunning('{#MyAppExeName}') then
    MsgBox(
      '软件进程未能完全退出，卸载将继续，但建议卸载完成后重启电脑以清理残留。',
      mbInformation,
      MB_OK);
end;
