; AllForOne - instalador de Windows (Inno Setup 6). Lo compila tools\package.ps1:
;   ISCC.exe /DAppVersion=0.3.0 /DSourceDir=<carpeta del programa> /DOutputDir=<release> installer\AllForOne.iss
;
; - Por usuario, sin permisos de administrador: por defecto en %LOCALAPPDATA%\Programs\AllForOne. Se
;   puede elegir otra carpeta (por ejemplo otro disco con sitio para los modelos de IA).
; - Los modelos de IA NO van en el instalador: se descargan desde la propia app («Modelos de IA») a
;   la carpeta modelos\ del programa. Tus datos (canciones, ajustes, registros) van en datos\.
; - Actualizar instalando encima conserva modelos\ y datos\. Al desinstalar se pregunta si borrarlos.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #error Falta /DSourceDir=<carpeta con AllForOne.exe>
#endif
#ifndef OutputDir
  #define OutputDir "."
#endif

[Setup]
AppId={{6F1C2A57-3E8B-4C1D-9A2F-AF0A11F0E001}
AppName=AllForOne
AppVersion={#AppVersion}
AppVerName=AllForOne {#AppVersion}
AppPublisher=AllForOne
VersionInfoVersion={#AppVersion}.0
VersionInfoDescription=Instalador de AllForOne
PrivilegesRequired=lowest
DefaultDirName={userpf}\AllForOne
DefaultGroupName=AllForOne
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=AllForOne-{#AppVersion}-Setup
SetupIconFile={#SourceDir}\allforone\qml\assets\icon.ico
UninstallDisplayIcon={app}\AllForOne.exe
UninstallDisplayName=AllForOne
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Messages]
es.WelcomeLabel2=Se instalará [name/ver] en tu equipo.%n%nLos modelos de IA no vienen en el instalador: se descargan después, desde la propia aplicación, en «Modelos de IA».

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[InstallDelete]
; Restos de la versión anterior del programa (nunca modelos\, datos\ ni tus temas)
Type: filesandordirs; Name: "{app}\allforone"
Type: filesandordirs; Name: "{app}\motores"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "datos\*,modelos\*"

[Icons]
Name: "{autoprograms}\AllForOne"; Filename: "{app}\AllForOne.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\AllForOne"; Filename: "{app}\AllForOne.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\AllForOne.exe"; Description: "Abrir AllForOne"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[Code]
var
  KeepUserData: Boolean;

function InitializeUninstall(): Boolean;
begin
  KeepUserData := True;
  if (not UninstallSilent) and
     (DirExists(ExpandConstant('{app}\modelos')) or DirExists(ExpandConstant('{app}\datos'))) then
    KeepUserData := MsgBox('¿Borrar también tus modelos de IA descargados y tus datos (canciones, ajustes y registros)?' + #13#10#13#10 +
                           'Elige «No» para conservarlos: los usará AllForOne si lo vuelves a instalar en la misma carpeta.',
                           mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDNO;
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and (not KeepUserData) then
  begin
    DelTree(ExpandConstant('{app}\modelos'), True, True, True);
    DelTree(ExpandConstant('{app}\datos'), True, True, True);
    RemoveDir(ExpandConstant('{app}'));
  end;
end;
