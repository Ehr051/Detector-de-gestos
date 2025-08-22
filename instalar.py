#!/usr/bin/env python3
"""
Instalador Automático - Sistema de Control por Gestos
====================================================

Script para instalar automáticamente todas las dependencias
y configurar el sistema para su uso.
"""

import sys
import subprocess
import os
import platform
from pathlib import Path

def print_banner():
    """Muestra el banner del instalador"""
    print("=" * 70)
    print("    INSTALADOR AUTOMÁTICO - SISTEMA DE CONTROL POR GESTOS")
    print("=" * 70)
    print()

def run_command(command, description=""):
    """Ejecuta un comando y maneja errores"""
    if description:
        print(f"🔄 {description}...")
    
    try:
        result = subprocess.run(command, shell=True, check=True, 
                              capture_output=True, text=True)
        if description:
            print(f"   ✅ {description} - Completado")
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        if description:
            print(f"   ❌ {description} - Error: {e}")
            print(f"   📋 Salida: {e.stdout}")
            print(f"   📋 Error: {e.stderr}")
        return False, e.stderr

def check_python():
    """Verifica la versión de Python"""
    print("🐍 Verificando Python...")
    
    version = sys.version_info
    if version.major >= 3 and version.minor >= 7:
        print(f"   ✅ Python {version.major}.{version.minor} encontrado")
        return True
    else:
        print(f"   ❌ Python {version.major}.{version.minor} - Se requiere 3.7+")
        return False

def upgrade_pip():
    """Actualiza pip a la última versión"""
    print("📦 Actualizando pip...")
    
    commands = [
        f"{sys.executable} -m pip install --upgrade pip"
    ]
    
    for cmd in commands:
        success, output = run_command(cmd, "Actualizando pip")
        if not success:
            print("   ⚠️  Continuando con la versión actual de pip...")
            
    return True

def install_requirements():
    """Instala las dependencias desde requirements.txt"""
    print("📋 Instalando dependencias desde requirements.txt...")
    
    if not Path("requirements.txt").exists():
        print("   ❌ Archivo requirements.txt no encontrado")
        return install_manual_dependencies()
    
    cmd = f"{sys.executable} -m pip install -r requirements.txt"
    success, output = run_command(cmd, "Instalando dependencias")
    
    if not success:
        print("   ⚠️  Error instalando desde requirements.txt, intentando instalación manual...")
        return install_manual_dependencies()
    
    return True

def install_manual_dependencies():
    """Instala dependencias manualmente"""
    print("🔧 Instalación manual de dependencias...")
    
    packages = [
        "opencv-python>=4.5.0",
        "numpy>=1.21.0", 
        "mediapipe>=0.10.0",
        "pyautogui>=0.9.54"
    ]
    
    for package in packages:
        cmd = f"{sys.executable} -m pip install {package}"
        success, output = run_command(cmd, f"Instalando {package}")
        if not success:
            print(f"   ❌ Error instalando {package}")
            return False
    
    return True

def install_system_dependencies():
    """Instala dependencias específicas del sistema"""
    system = platform.system()
    print(f"🖥️  Configurando dependencias para {system}...")
    
    if system == "Darwin":  # macOS
        print("   ℹ️  macOS detectado")
        print("   📝 Recomendaciones adicionales:")
        print("      • Instalar Homebrew si no está instalado")
        print("      • Configurar permisos de cámara y accesibilidad")
        
    elif system == "Windows":  # Windows
        print("   ℹ️  Windows detectado")
        print("   📝 Instalando dependencias adicionales...")
        
        # Intentar instalar Visual C++ redistributable info
        print("   ℹ️  Si hay errores, instala Visual C++ Redistributable:")
        print("      https://aka.ms/vs/17/release/vc_redist.x64.exe")
        
    elif system == "Linux":  # Linux
        print("   ℹ️  Linux detectado")
        print("   📦 Instalando dependencias del sistema...")
        
        linux_packages = [
            "sudo apt-get update",
            "sudo apt-get install -y python3-opencv",
            "sudo apt-get install -y python3-tk python3-dev"
        ]
        
        for cmd in linux_packages:
            success, output = run_command(cmd, f"Ejecutando {cmd.split()[-1]}")
            if not success:
                print(f"   ⚠️  Error con {cmd}, continuando...")
    
    return True

def create_virtual_environment():
    """Crea un entorno virtual si no existe"""
    venv_path = Path("detector_gestos_env")
    
    if venv_path.exists():
        print("   ℹ️  Entorno virtual ya existe")
        return True
    
    print("🏗️  Creando entorno virtual...")
    
    cmd = f"{sys.executable} -m venv detector_gestos_env"
    success, output = run_command(cmd, "Creando entorno virtual")
    
    return success

def verify_installation():
    """Verifica que la instalación fue exitosa"""
    print("✅ Verificando instalación...")
    
    try:
        # Verificar que se puede importar cada dependencia
        import cv2
        print("   ✅ OpenCV - OK")
        
        import mediapipe
        print("   ✅ MediaPipe - OK")
        
        import numpy
        print("   ✅ NumPy - OK")
        
        import pyautogui
        print("   ✅ PyAutoGUI - OK")
        
        # Verificar acceso básico a la cámara
        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            print("   ✅ Acceso a cámara - OK")
            cap.release()
        else:
            print("   ⚠️  Acceso a cámara - Verificar permisos")
        
        print("\n🎉 ¡Instalación completada exitosamente!")
        return True
        
    except Exception as e:
        print(f"   ❌ Error en verificación: {e}")
        return False

def show_next_steps():
    """Muestra los siguientes pasos después de la instalación"""
    print("\n" + "=" * 70)
    print("    SIGUIENTES PASOS")
    print("=" * 70)
    
    print("\n🚀 Para ejecutar el sistema:")
    print("   python control_gestos.py")
    
    print("\n🔧 O usar los launchers:")
    if platform.system() == "Darwin":
        print("   ./launch_macos.sh")
    elif platform.system() == "Windows":
        print("   launch_windows.bat")
    
    print("\n🔍 Para verificar el sistema:")
    print("   python verificar_sistema.py")
    
    print("\n📖 Para más información:")
    print("   • Consulta README_v2.md")
    print("   • Revisa config.json para configuración avanzada")
    
    print(f"\n🔐 Configuración de permisos ({platform.system()}):")
    if platform.system() == "Darwin":
        print("   • Preferencias del Sistema > Seguridad y privacidad > Cámara")
        print("   • Preferencias del Sistema > Seguridad y privacidad > Accesibilidad")
    elif platform.system() == "Windows":
        print("   • Configuración > Privacidad > Cámara")
        print("   • Ejecutar como administrador si hay problemas")

def main():
    """Función principal del instalador"""
    print_banner()
    
    # Verificar Python
    if not check_python():
        print("❌ Versión de Python incompatible. Instala Python 3.7 o superior.")
        return False
    
    # Actualizar pip
    if not upgrade_pip():
        print("⚠️  Problema actualizando pip, continuando...")
    
    # Instalar dependencias del sistema
    install_system_dependencies()
    
    # Instalar dependencias de Python
    if not install_requirements():
        print("❌ Error instalando dependencias de Python")
        return False
    
    # Verificar instalación
    if not verify_installation():
        print("❌ La verificación falló. Revisa los errores anteriores.")
        return False
    
    # Mostrar siguientes pasos
    show_next_steps()
    
    return True

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Instalación cancelada por el usuario")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        sys.exit(1)
