@echo off
:: Launcher para Windows - Sistema de Control por Gestos
:: =====================================================

setlocal EnableDelayedExpansion

:: Variables
set SCRIPT_DIR=%~dp0
set VENV_DIR=%SCRIPT_DIR%detector_gestos_env
set PYTHON_SCRIPT=detectorGestos.py
set REQUIREMENTS_FILE=requirements.txt

:: Colores para output (si está disponible)
set GREEN=[92m
set RED=[91m
set YELLOW=[93m
set BLUE=[94m
set NC=[0m

:: Función para mostrar el banner
:show_banner
echo %BLUE%
echo ╔══════════════════════════════════════════════════════════════╗
echo ║           SISTEMA DE CONTROL POR GESTOS v2.0                ║
echo ║                     Launcher Windows                        ║
echo ╚══════════════════════════════════════════════════════════════╝
echo %NC%
goto :eof

:: Función para logging
:log
echo %GREEN%[%date% %time%] %~1%NC%
goto :eof

:error
echo %RED%[ERROR] %~1%NC%
goto :eof

:warning
echo %YELLOW%[WARNING] %~1%NC%
goto :eof

:: Verificar si Python está instalado
:check_python
call :log "Verificando instalación de Python..."

python --version >nul 2>&1
if !errorlevel! equ 0 (
    set PYTHON_CMD=python
    for /f "tokens=*" %%a in ('python --version') do call :log "%%a encontrado"
    goto :check_python_version
)

python3 --version >nul 2>&1
if !errorlevel! equ 0 (
    set PYTHON_CMD=python3
    for /f "tokens=*" %%a in ('python3 --version') do call :log "%%a encontrado"
    goto :check_python_version
)

py --version >nul 2>&1
if !errorlevel! equ 0 (
    set PYTHON_CMD=py
    for /f "tokens=*" %%a in ('py --version') do call :log "%%a encontrado"
    goto :check_python_version
)

call :error "Python no está instalado. Por favor instala Python 3.7 o superior."
call :error "Descárgalo desde: https://www.python.org/downloads/"
echo Presiona cualquier tecla para salir...
pause >nul
exit /b 1

:: Verificar versión de Python
:check_python_version
call :log "Verificando versión de Python..."

for /f "tokens=2" %%a in ('%PYTHON_CMD% --version') do set VERSION=%%a
for /f "tokens=1,2 delims=." %%a in ("!VERSION!") do (
    set MAJOR=%%a
    set MINOR=%%b
)

if !MAJOR! lss 3 (
    call :error "Se requiere Python 3.7 o superior. Versión actual: !VERSION!"
    goto :exit_error
)

if !MAJOR! equ 3 if !MINOR! lss 7 (
    call :error "Se requiere Python 3.7 o superior. Versión actual: !VERSION!"
    goto :exit_error
)

call :log "Versión de Python válida: !VERSION!"
goto :eof

:: Crear entorno virtual
:create_venv
if not exist "%VENV_DIR%" (
    call :log "Creando entorno virtual..."
    %PYTHON_CMD% -m venv "%VENV_DIR%"
    if !errorlevel! neq 0 (
        call :error "Error creando entorno virtual"
        goto :exit_error
    )
    call :log "Entorno virtual creado exitosamente"
) else (
    call :log "Entorno virtual ya existe"
)
goto :eof

:: Activar entorno virtual
:activate_venv
call :log "Activando entorno virtual..."
call "%VENV_DIR%\Scripts\activate.bat"
if !errorlevel! neq 0 (
    call :error "Error activando entorno virtual"
    goto :exit_error
)
call :log "Entorno virtual activado"
goto :eof

:: Instalar dependencias
:install_dependencies
call :log "Verificando e instalando dependencias..."

if exist "%REQUIREMENTS_FILE%" (
    call :log "Instalando dependencias desde %REQUIREMENTS_FILE%..."
    python -m pip install --upgrade pip
    pip install -r "%REQUIREMENTS_FILE%"
    if !errorlevel! neq 0 (
        call :error "Error instalando dependencias"
        goto :exit_error
    )
    call :log "Dependencias instaladas exitosamente"
) else (
    call :warning "Archivo %REQUIREMENTS_FILE% no encontrado. Instalando dependencias básicas..."
    python -m pip install --upgrade pip
    pip install opencv-python mediapipe numpy pyautogui
)
goto :eof

:: Verificar dependencias del sistema Windows
:check_windows_dependencies
call :log "Verificando dependencias del sistema Windows..."

:: Verificar Visual C++ Redistributable
call :log "Nota: Asegúrate de tener Microsoft Visual C++ Redistributable instalado"
call :log "Descárgalo desde: https://aka.ms/vs/17/release/vc_redist.x64.exe"

:: Verificar permisos de cámara
call :log "Nota: Asegúrate de que Python tenga permisos para acceder a la cámara"
call :log "Ve a: Configuración > Privacidad > Cámara"
goto :eof

:: Verificar permisos de Windows
:check_windows_permissions
call :log "Verificando configuración de Windows..."
call :log "IMPORTANTE: Para un funcionamiento óptimo:"
call :log "1. Ejecuta como administrador si experimentas problemas"
call :log "2. Configura permisos de cámara en Configuración > Privacidad"
call :log "3. Desactiva temporalmente el antivirus si hay interferencias"

set /p "continue=¿Continuar con la ejecución? (s/n): "
if /i not "!continue!"=="s" (
    call :log "Ejecución cancelada por el usuario"
    goto :exit_normal
)
goto :eof

:: Ejecutar el programa principal
:run_program
call :log "Iniciando Sistema de Control por Gestos..."

if not exist "%PYTHON_SCRIPT%" (
    call :error "Archivo %PYTHON_SCRIPT% no encontrado"
    goto :exit_error
)

call :log "Ejecutando: python %PYTHON_SCRIPT%"
call :log "Presiona Ctrl+C para detener el programa"
echo.

python "%PYTHON_SCRIPT%"
goto :eof

:: Manejo de errores
:exit_error
echo.
call :error "Se produjo un error. Revisa los mensajes anteriores."
echo Presiona cualquier tecla para salir...
pause >nul
exit /b 1

:: Salida normal
:exit_normal
call :log "Programa terminado"
echo Presiona cualquier tecla para salir...
pause >nul
exit /b 0

:: Función principal
:main
call :show_banner

cd /d "%SCRIPT_DIR%"

call :check_python
if !errorlevel! neq 0 goto :exit_error

call :check_python_version
if !errorlevel! neq 0 goto :exit_error

call :check_windows_dependencies

call :create_venv
if !errorlevel! neq 0 goto :exit_error

call :activate_venv
if !errorlevel! neq 0 goto :exit_error

call :install_dependencies
if !errorlevel! neq 0 goto :exit_error

call :check_windows_permissions

echo.
call :log "Configuración completada. Iniciando programa..."
echo.

call :run_program

goto :exit_normal

:: Ejecutar función principal
call :main
