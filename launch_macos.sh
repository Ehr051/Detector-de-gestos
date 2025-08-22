#!/bin/bash

# Launcher para macOS - Sistema de Control por Gestos
# ===================================================

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/detector_gestos_env"
PYTHON_SCRIPT="detectorGestos.py"
REQUIREMENTS_FILE="requirements.txt"

# Función para mostrar el banner
show_banner() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║           SISTEMA DE CONTROL POR GESTOS v2.0                ║"
    echo "║                      Launcher macOS                         ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# Función para logging
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

warning() {
    echo -e "${YELLOW}[WARNING] $1${NC}"
}

# Verificar si Python está instalado
check_python() {
    log "Verificando instalación de Python..."
    
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
        log "Python3 encontrado: $(python3 --version)"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
        log "Python encontrado: $(python --version)"
    else
        error "Python no está instalado. Por favor instala Python 3.7 o superior."
        error "Descárgalo desde: https://www.python.org/downloads/"
        exit 1
    fi
}

# Verificar versión de Python
check_python_version() {
    log "Verificando versión de Python..."
    
    VERSION=$($PYTHON_CMD -c "import sys; print('.'.join(map(str, sys.version_info[:2])))")
    MAJOR=$(echo $VERSION | cut -d. -f1)
    MINOR=$(echo $VERSION | cut -d. -f2)
    
    if [ "$MAJOR" -lt 3 ] || ([ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 7 ]); then
        error "Se require Python 3.7 o superior. Versión actual: $VERSION"
        exit 1
    fi
    
    log "Versión de Python válida: $VERSION"
}

# Crear entorno virtual
create_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        log "Creando entorno virtual..."
        $PYTHON_CMD -m venv "$VENV_DIR"
        if [ $? -ne 0 ]; then
            error "Error creando entorno virtual"
            exit 1
        fi
        log "Entorno virtual creado exitosamente"
    else
        log "Entorno virtual ya existe"
    fi
}

# Activar entorno virtual
activate_venv() {
    log "Activando entorno virtual..."
    source "$VENV_DIR/bin/activate"
    if [ $? -ne 0 ]; then
        error "Error activando entorno virtual"
        exit 1
    fi
    log "Entorno virtual activado"
}

# Instalar dependencias
install_dependencies() {
    log "Verificando e instalando dependencias..."
    
    if [ -f "$REQUIREMENTS_FILE" ]; then
        log "Instalando dependencias desde $REQUIREMENTS_FILE..."
        pip install --upgrade pip
        pip install -r "$REQUIREMENTS_FILE"
        if [ $? -ne 0 ]; then
            error "Error instalando dependencias"
            exit 1
        fi
        log "Dependencias instaladas exitosamente"
    else
        warning "Archivo $REQUIREMENTS_FILE no encontrado. Instalando dependencias básicas..."
        pip install --upgrade pip
        pip install opencv-python mediapipe numpy pyautogui
    fi
}

# Verificar dependencias del sistema macOS
check_macos_dependencies() {
    log "Verificando dependencias del sistema macOS..."
    
    # Verificar si Homebrew está instalado (opcional pero recomendado)
    if ! command -v brew &> /dev/null; then
        warning "Homebrew no está instalado. Se recomienda para mejor compatibilidad."
        echo "Para instalar Homebrew ejecuta:"
        echo "/bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    else
        log "Homebrew encontrado"
    fi
    
    # Verificar permisos de acceso a la cámara
    log "Nota: Asegúrate de que Terminal tenga permisos para acceder a la cámara"
    log "Ve a: Preferencias del Sistema > Seguridad y privacidad > Cámara"
}

# Verificar permisos de accesibilidad
check_accessibility_permissions() {
    log "Verificando permisos de accesibilidad..."
    log "IMPORTANTE: Para controlar el mouse, la aplicación necesita permisos de accesibilidad"
    log "Ve a: Preferencias del Sistema > Seguridad y privacidad > Accesibilidad"
    log "Agrega Terminal y/o Python a la lista de aplicaciones permitidas"
    
    read -p "¿Has configurado los permisos de accesibilidad? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        warning "Configura los permisos de accesibilidad antes de continuar"
        echo "El control del mouse podría no funcionar sin estos permisos"
    fi
}

# Ejecutar el programa principal
run_program() {
    log "Iniciando Sistema de Control por Gestos..."
    
    if [ ! -f "$PYTHON_SCRIPT" ]; then
        error "Archivo $PYTHON_SCRIPT no encontrado"
        exit 1
    fi
    
    log "Ejecutando: $PYTHON_CMD $PYTHON_SCRIPT"
    log "Presiona Ctrl+C para detener el programa"
    echo
    
    $PYTHON_CMD "$PYTHON_SCRIPT"
}

# Función para limpiar al salir
cleanup() {
    log "Limpiando y saliendo..."
    if [ -n "$VIRTUAL_ENV" ]; then
        deactivate
    fi
    exit 0
}

# Configurar trap para cleanup
trap cleanup SIGINT SIGTERM

# Función principal
main() {
    show_banner
    
    cd "$SCRIPT_DIR"
    
    check_python
    check_python_version
    check_macos_dependencies
    create_venv
    activate_venv
    install_dependencies
    check_accessibility_permissions
    
    echo
    log "Configuración completada. Iniciando programa..."
    echo
    
    run_program
}

# Verificar si el script se ejecuta directamente
if [ "${BASH_SOURCE[0]}" == "${0}" ]; then
    main "$@"
fi
