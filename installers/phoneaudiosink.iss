; PhoneAudioSink Windows 安装脚本（Inno Setup 6）
; 编译：ISCC.exe phoneaudiosink.iss

#define MyAppName "PhoneAudioSink"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "PhoneAudioSink contributors"
#define MyAppURL "https://bobo0925-a.github.io/PhoneAudioSink/"
#define MyAppExeName "PhoneAudioSink.exe"

[Setup]
; 固定 AppId，保证升级/卸载识别为同一程序
AppId={{9F0E0567-F3D1-4C0A-9639-E234DE6B3E57}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
; 按当前用户安装，不需要管理员权限；程序目录可写，配置/日志可落在旁边
DefaultDirName={localappdata}\Programs\PhoneAudioSink
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=Output
OutputBaseFilename=PhoneAudioSink-setup-v1.0.0
SetupIconFile=..\pc\assets\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableWelcomePage=no
; 按系统语言自动选中安装界面语言，用户仍可在向导中切换
ShowLanguageDialog=auto

[Languages]
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
chinesesimplified.CreatingShortcuts=正在创建快捷方式…
english.CreatingShortcuts=Creating shortcuts...

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\PhoneAudioSink.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
