# Detector-de-gestos

# Sistema Unificado de Control por Gestos

Este proyecto permite controlar el cursor y las acciones del mouse mediante gestos de las manos, usando una cámara web o una cámara externa, sobre la pantalla del PC o una proyección/TV.

## Descripción

Utiliza MediaPipe para la detección de manos y OpenCV para el procesamiento de imágenes, integrando pyautogui para el control del mouse y la simulación de acciones de usuario.

El programa es independiente: ejecútalo y podrás controlar el mouse en cualquier aplicación de tu computadora.

## Características

- **Control de cursor:** Mueve el mouse con la mano abierta (el pulgar controla la posición).
- **Click izquierdo / arrastrar:** Junta el pulgar y el índice.
- **Click derecho:** Junta el pulgar y el dedo medio.
- **Zoom:** Dos puños, acerca/aleja según la distancia entre ellos.
- **Modos:** 
  - *pantalla*: controla el mouse sobre la PC.
  - *mesa*: controla proyección/TV, requiere calibración.
- **Calibración:** Toca las esquinas para mapear el área de gestos a la proyección.

## Instalación

1. **Instala Python 3.7+**
2. **Instala las dependencias:**  
   ```sh
   pip install -r requirements.txt
   ```
3. **Ejecuta el script principal:**  
   ```sh
   python control_gestos.py
   ```

## Uso

- Al iniciar aparecerá la ventana de visualización.
- **Gestos disponibles:**
  - Mano abierta: mueve el cursor.
  - Pulgar + índice juntos: click izquierdo / arrastrar.
  - Pulgar + dedo medio juntos: click derecho.
  - Dos puños: zoom in/out.
- **Teclas:**
  - `q`: salir.
  - `m`: cambiar modo entre “pantalla” y “mesa”.
  - `c`: iniciar calibración manual (solo en modo mesa).
- **Recomendación:** Mantén la ventana de visualización en segundo plano para controlar otras aplicaciones.

## Calibración (modo mesa)

- Se te pedirá tocar las 4 esquinas del área de proyección con el dedo índice.
- El sistema calcula la matriz de transformación y la guarda en `calibracion_matriz.npy`.

## Dependencias

- [OpenCV](https://opencv.org/)
- [MediaPipe](https://google.github.io/mediapipe/)
- [NumPy](https://numpy.org/)
- [PyAutoGUI](https://pyautogui.readthedocs.io/en/latest/)

## Notas

- Para correcto funcionamiento, usa buena iluminación y asegúrate de que la cámara vea bien tus manos.
- Si usas una cámara externa, asegúrate de que el sistema la detecta (puedes cambiar el índice de cámara en el código).
- En algunos sistemas, puede requerir permisos extra para controlar el mouse.

## Licencia

MIT (modifica si prefieres otra)

---

**¡Disfruta tu sistema de control por gestos!**
