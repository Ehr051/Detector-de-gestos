# Sistema Unificado de Control por Gestos v2.0

[![Python](https://img.shields.io/badge/Python-3.7+-blue.svg)](https://python.org)
[![OpenCV](https://img.shields.io/badge/OpenCV-4.5+-green.svg)](https://opencv.org)
[![MediaPipe](https://img.shields.io/badge/MediaPipe-0.10+-orange.svg)](https://mediapipe.dev)

Este proyecto permite controlar el cursor y las acciones del mouse mediante gestos de las manos, usando una cámara web o una cámara externa, sobre la pantalla del PC o una proyección/TV.

## 🚀 Características Principales

- **Control de cursor:** Mueve el mouse con la mano abierta (el pulgar controla la posición)
- **Click izquierdo / arrastrar:** Junta el pulgar y el índice
- **Click derecho:** Junta el pulgar y el dedo medio
- **Zoom:** Dos puños, acerca/aleja según la distancia entre ellos
- **Dos modos:** 
  - *Pantalla*: controla el mouse sobre la PC
  - *Mesa*: controla proyección/TV, requiere calibración
- **Calibración automática:** Toca las esquinas para mapear el área de gestos a la proyección
- **Logging avanzado:** Sistema de registro de eventos y errores
- **Configuración optimizada:** Parámetros ajustables para mejor rendimiento

## 🛠 Instalación Rápida

### Para macOS:
```bash
# Clonar el repositorio
git clone https://github.com/Ehr051/Detector-de-gestos.git
cd Detector-de-gestos

# Ejecutar el launcher (automáticamente configura todo)
./launch_macos.sh
```

### Para Windows:
```batch
REM Clonar el repositorio
git clone https://github.com/Ehr051/Detector-de-gestos.git
cd Detector-de-gestos

REM Ejecutar el launcher (automáticamente configura todo)
launch_windows.bat
```

## 📋 Instalación Manual

### Requisitos del Sistema

**Python 3.7 o superior** es requerido.

### 1. Instalar Python
- **macOS:** `brew install python3` o descargar desde [python.org](https://python.org)
- **Windows:** Descargar desde [python.org](https://python.org)

### 2. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 3. Ejecutar el programa
```bash
python control_gestos.py
```

## 🎮 Uso del Sistema

### Gestos Disponibles

| Gesto | Acción | Descripción |
|-------|--------|-------------|
| ✋ Mano abierta | Mover cursor | El pulgar controla la posición del cursor |
| 👌 Pulgar + Índice | Click izquierdo | Junta el pulgar y el índice para hacer click |
| 🤟 Pulgar + Medio | Click derecho | Junta el pulgar y el dedo medio |
| ✊ Puño | Click alternativo | Puño cerrado para hacer click |
| ✊✊ Dos puños | Zoom | Acerca/aleja según la distancia entre puños |

### Controles de Teclado

| Tecla | Función |
|-------|---------|
| `q` | Salir del programa |
| `m` | Cambiar entre modo "pantalla" y "mesa" |
| `c` | Iniciar calibración manual (solo en modo mesa) |

### Modos de Operación

#### Modo Pantalla
- Control directo del cursor del PC
- Funcionamiento inmediato sin calibración
- Ideal para presentaciones y uso general

#### Modo Mesa
- Control de proyecciones o pantallas externas
- Requiere calibración inicial
- Mapea el área de la cámara al área de proyección
- Ideal para mesas interactivas y instalaciones

## 🔧 Calibración (Modo Mesa)

1. Cambia a modo mesa presionando `m`
2. Presiona `c` para iniciar calibración
3. Toca cada esquina indicada con tu dedo índice:
   - Superior izquierda
   - Superior derecha  
   - Inferior derecha
   - Inferior izquierda
4. Espera la cuenta regresiva en cada punto
5. ¡Calibración completada!

La calibración se guarda automáticamente y se carga en futuras sesiones.

## ⚙️ Configuración Avanzada

El archivo `config.json` permite ajustar parámetros:

```json
{
    "deteccion": {
        "min_detection_confidence": 0.7,
        "min_tracking_confidence": 0.5
    },
    "gestos": {
        "distancia_pinza": 40,
        "factor_zoom_in": 1.5,
        "factor_zoom_out": 0.7
    }
}
```

## 🔍 Solución de Problemas

### Problemas Comunes

#### macOS
- **Permisos de cámara:** Ve a Preferencias del Sistema > Seguridad y privacidad > Cámara
- **Permisos de accesibilidad:** Agrega Terminal/Python en Preferencias del Sistema > Seguridad y privacidad > Accesibilidad

#### Windows
- **Cámara no detectada:** Verifica permisos en Configuración > Privacidad > Cámara
- **PyAutoGUI no funciona:** Ejecuta como administrador
- **Error de importación:** Instala Visual C++ Redistributable

#### General
- **Gestos no responden:** Asegúrate de tener buena iluminación
- **Cursor errático:** Ajusta `suavizado_movimiento` en configuración
- **Detección lenta:** Reduce `min_detection_confidence`

### Logs del Sistema

El sistema genera logs automáticamente en `detector_gestos.log`:

```bash
# Ver logs en tiempo real (macOS/Linux)
tail -f detector_gestos.log

# Ver logs (Windows)
type detector_gestos.log
```

## 🏗 Arquitectura del Sistema

```
├── control_gestos.py          # Programa principal optimizado
├── DetectorGestosOptimizado.py # Versión avanzada con clases
├── DetectorGestos.py          # Versión original (mantenida por compatibilidad)
├── config.json               # Configuración del sistema
├── requirements.txt          # Dependencias Python
├── launch_macos.sh          # Launcher para macOS
├── launch_windows.bat       # Launcher para Windows
├── instalar.py              # Instalador automático
├── verificar_sistema.py     # Verificador de dependencias
├── demo.py                  # Demo rápido del sistema
├── calibracion_matriz.npy   # Datos de calibración (generado automáticamente)
└── detector_gestos.log      # Archivo de logs (generado automáticamente)
```

## 🔄 Mejoras en v2.0

### Optimizaciones
- ✅ Código refactorizado y modularizado
- ✅ Sistema de logging profesional
- ✅ Manejo de errores robusto
- ✅ Configuración externa en JSON
- ✅ Launchers automáticos para Windows y macOS
- ✅ Documentación mejorada
- ✅ Parámetros de detección optimizados

### Nuevas Características
- ✅ Suavizado de movimiento mejorado
- ✅ Detección de gestos más precisa
- ✅ Calibración con cuenta regresiva visual
- ✅ Guardado/carga automático de calibración
- ✅ Información en pantalla mejorada
- ✅ Mejor compatibilidad entre plataformas

## 🚀 Uso Rápido

### Verificar Sistema
```bash
python verificar_sistema.py
```

### Demo Rápido
```bash
python demo.py
```

### Instalación Automática
```bash
python instalar.py
```

## 🤝 Contribuir

1. Fork el proyecto
2. Crear una rama para tu feature (`git checkout -b feature/nueva-caracteristica`)
3. Commit tus cambios (`git commit -am 'Agregar nueva característica'`)
4. Push a la rama (`git push origin feature/nueva-caracteristica`)
5. Crear un Pull Request

## 📝 Licencia

Este proyecto está bajo la Licencia MIT - ver el archivo [LICENSE](LICENSE) para detalles.

## 🙏 Reconocimientos

- [MediaPipe](https://mediapipe.dev) por la detección de manos
- [OpenCV](https://opencv.org) por el procesamiento de imágenes
- [PyAutoGUI](https://pyautogui.readthedocs.io) por el control del mouse

## 📞 Soporte

Si tienes problemas o preguntas:

1. Revisa la sección de [Solución de Problemas](#-solución-de-problemas)
2. Consulta los logs en `detector_gestos.log`
3. Abre un [Issue](https://github.com/Ehr051/Detector-de-gestos/issues) en GitHub

---

**¡Disfruta controlando tu computadora con gestos!** 👋
