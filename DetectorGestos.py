import cv2
import mediapipe as mp
import numpy as np
import time
import pyautogui
import sys
import os

# Configurar pyautogui para que sea seguro y funcione correctamente
pyautogui.FAILSAFE = True

# Deshabilitar la función de failsafe basada en posición para permitir movimientos a cualquier parte de la pantalla
pyautogui.FAILSAFE_POINTS = [(0, 0)]  # Solo esquina superior izquierda como punto de seguridad


class ControladorGestos:
    def __init__(self, modo="pantalla"):
        """
        Inicializa el controlador de gestos
        
        Args:
            modo (str): 'pantalla' para controlar el cursor del PC,
                       'mesa' para controlar la mesa de arena con cámara externa
        """
        self.modo = modo
        
        # Inicializar MediaPipe Hands
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,  # Detectamos hasta dos manos para zoom con puños
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.mp_drawing = mp.solutions.drawing_utils
        
        # Obtener tamaño de la pantalla
        self.screen_width, self.screen_height = pyautogui.size()
        
        # Variables de estado para gestos
        self.clicking = False
        self.right_clicking = False
        self.dragging = False
        self.zoom_mode = False
        self.punto_inicial_arrastre = None
        
        # Variables para zoom con dos puños
        self.punos_detectados = []
        self.distancia_punos_inicial = None
        self.haciendo_zoom = False
        
        # Suavizado de movimiento
        self.suavizado = 5
        self.historial_posiciones = []
        
        # Matriz de transformación para mapear coordenadas entre la cámara y proyección
        self.matriz_transformacion = np.eye(3)  # Identidad por defecto
        
        # Variables para calibración
        self.en_calibracion = False
        self.puntos_calibracion_camara = []
        self.calibracion_completada = False
    
    def procesar_frame(self, frame):
        """
        Procesa un fotograma de la cámara y realiza las acciones correspondientes
        
        Args:
            frame: Imagen capturada de la cámara
            
        Returns:
            frame_procesado: Imagen con información visual sobre gestos
            info_gesto: Diccionario con información del gesto detectado
        """
        # Si estamos en modo calibración, procesar la calibración
        if self.en_calibracion and self.modo == "mesa":
            frame_procesado, calibracion_finalizada = self.procesar_calibracion(frame)
            if calibracion_finalizada:
                self.en_calibracion = False
                self.calibracion_completada = True
                print("¡Calibración completada con éxito!")
            
            # Durante la calibración, devolvemos un gesto nulo
            info_gesto = {
                'gesto': 'ninguno',
                'posicion': None,
                'datos_adicionales': {}
            }
            return frame_procesado, info_gesto
        
        # Convertir imagen a RGB (MediaPipe requiere RGB)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        altura, ancho, _ = frame.shape
        
        # Procesar imagen con MediaPipe
        results = self.hands.process(frame_rgb)
        
        # Crear copia del frame para visualización
        frame_visual = frame.copy()
        
        # Información del gesto detectado para devolver
        info_gesto = {
            'gesto': 'ninguno',
            'posicion': None,
            'datos_adicionales': {}
        }
        
        # Si no se detectan manos, devolver el frame original
        if not results.multi_hand_landmarks:
            return frame_visual, info_gesto
        
        # Detectar gestos con dos manos (para zoom)
        if len(results.multi_hand_landmarks) == 2:
            self.detectar_gestos_dos_manos(results, frame_visual, ancho, altura, info_gesto)
            
            # Si se detectó zoom, aplicar la acción y devolver
            if info_gesto['gesto'] in ['zoom_in', 'zoom_out']:
                return frame_visual, info_gesto
        
        # Detectar gestos con una mano
        if len(results.multi_hand_landmarks) > 0:
            hand_landmarks = results.multi_hand_landmarks[0]
            
            # Dibujar los puntos de referencia de la mano
            self.mp_drawing.draw_landmarks(
                frame_visual, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)
            
            # Extraer puntos clave
            puntos = []
            for landmark in hand_landmarks.landmark:
                x, y = int(landmark.x * ancho), int(landmark.y * altura)
                puntos.append((x, y))
            
            # Procesar puntos para detectar gestos específicos
            info_gesto = self.detectar_gestos_una_mano(puntos, frame_visual, ancho, altura)
            
            # Si estamos en modo pantalla, realizar las acciones del mouse
            if self.modo == "pantalla" and info_gesto['posicion'] is not None:
                self.realizar_accion_mouse(info_gesto)
        
        return frame_visual, info_gesto
    
    def detectar_gestos_una_mano(self, puntos, frame, ancho, altura):
        """Detecta gestos realizados con una sola mano"""
        # Dedos clave
        indice_punta = puntos[8]
        indice_base = puntos[5]
        pulgar_punta = puntos[4]
        medio_punta = puntos[12]
        medio_base = puntos[9]
        palma = puntos[0]
        
        # Verificar si dedos están extendidos
        indice_extendido = indice_punta[1] < indice_base[1]
        medio_extendido = medio_punta[1] < medio_base[1]
        
        # Distancias entre dedos
        distancia_pulgar_indice = self._calcular_distancia(pulgar_punta, indice_punta)
        distancia_pulgar_medio = self._calcular_distancia(pulgar_punta, medio_punta)
        
        # Posición para el cursor (sigue el pulgar para mayor precisión)
        if self.modo == "pantalla":
            # Usar pulgar para mejor precisión
            cursor_x, cursor_y = pulgar_punta
            
            # Mapear coordenadas de cámara a pantalla
            screen_x = int(np.interp(cursor_x, [100, ancho-100], [0, self.screen_width]))
            screen_y = int(np.interp(cursor_y, [100, altura-100], [0, self.screen_height]))
            
            # Aplicar suavizado
            self.historial_posiciones.append((screen_x, screen_y))
            if len(self.historial_posiciones) > self.suavizado:
                self.historial_posiciones.pop(0)
            
            suavizado_x = int(sum(p[0] for p in self.historial_posiciones) / len(self.historial_posiciones))
            suavizado_y = int(sum(p[1] for p in self.historial_posiciones) / len(self.historial_posiciones))
            
            posicion_cursor = (suavizado_x, suavizado_y)
            # Mostrar coordenadas en la pantalla
            cv2.putText(frame, f"Pos: {suavizado_x}, {suavizado_y}", 
                      (ancho - 250, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        else:
            # En modo mesa, aplicar transformación de coordenadas si ya está calibrado
            if self.calibracion_completada:
                posicion_cursor = self._transformar_coordenadas(pulgar_punta)
                cv2.putText(frame, f"Transf: {posicion_cursor[0]}, {posicion_cursor[1]}", 
                          (ancho - 250, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            else:
                posicion_cursor = pulgar_punta
        
        # Información del gesto detectado
        info_gesto = {
            'gesto': 'ninguno',
            'posicion': posicion_cursor,
            'datos_adicionales': {'puntos_mano': puntos}
        }
        
        # Mostrar círculo como cursor básico en el pulgar
        cv2.circle(frame, pulgar_punta, 10, (0, 255, 0), -1)
        
        # Click izquierdo: pinza entre índice y pulgar
        if distancia_pulgar_indice < 40:
            info_gesto['gesto'] = 'click'
            # Dibujar indicador visual
            cv2.circle(frame, indice_punta, 15, (255, 0, 0), -1)
            cv2.circle(frame, pulgar_punta, 15, (255, 0, 0), -1)
            cv2.line(frame, indice_punta, pulgar_punta, (255, 0, 0), 2)
            cv2.putText(frame, "Click", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
            
            # Detectar arrastre si se mantiene la pinza y se mueve
            if self.dragging or self.clicking:
                info_gesto['gesto'] = 'arrastrar'
                cv2.putText(frame, "Arrastrando", (50, 90), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
                if self.punto_inicial_arrastre:
                    info_gesto['datos_adicionales']['punto_inicial'] = self.punto_inicial_arrastre
                    # Dibujar línea de arrastre
                    cv2.line(frame, self.punto_inicial_arrastre, posicion_cursor, (255, 0, 0), 2)
            else:
                self.punto_inicial_arrastre = posicion_cursor
        else:
            # Si la pinza se suelta, resetear estado de arrastre
            self.punto_inicial_arrastre = None
        
        # Click derecho: pulgar y dedo medio juntos
        if distancia_pulgar_medio < 40:
            info_gesto['gesto'] = 'menu_contextual'
            # Dibujar indicador visual
            cv2.circle(frame, medio_punta, 15, (0, 0, 255), -1)
            cv2.circle(frame, pulgar_punta, 15, (0, 0, 255), -1)
            cv2.line(frame, medio_punta, pulgar_punta, (0, 0, 255), 2)
            cv2.putText(frame, "Click Derecho", (50, 130), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        
        # Puño cerrado (para click o para zoom)
        if self._es_puño_cerrado(puntos):
            # Si solo hay una mano, se considera como click
            if not self.zoom_mode:
                info_gesto['gesto'] = 'click'
                cv2.circle(frame, palma, 30, (255, 255, 0), 2)
                cv2.putText(frame, "Puño (Click)", (palma[0]-40, palma[1]-20), 
                          cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        
        return info_gesto
    
    def detectar_gestos_dos_manos(self, results, frame, ancho, altura, info_gesto):
        """Detecta gestos realizados con dos manos, principalmente para zoom con puños cerrados"""
        # Limpiar la lista de puños
        self.punos_detectados = []
        
        # Verificar si ambas manos están en puño
        puños_detectados_esta_vez = 0
        
        for hand_idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
            # Dibujar los puntos de referencia de la mano
            self.mp_drawing.draw_landmarks(
                frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)
            
            # Extraer puntos clave
            puntos = []
            for landmark in hand_landmarks.landmark:
                x, y = int(landmark.x * ancho), int(landmark.y * altura)
                puntos.append((x, y))
            
            # Verificar explícitamente si es un puño usando el método mejorado
            if self._es_puño_cerrado(puntos):
                puños_detectados_esta_vez += 1
                centro_palma = puntos[0]  # Base de la palma
                self.punos_detectados.append(centro_palma)
                
                # Dibujar un círculo grande sobre el puño
                cv2.circle(frame, centro_palma, 30, (0, 0, 255), 3)
                cv2.putText(frame, f"Puño {hand_idx+1}", 
                          (centro_palma[0]-20, centro_palma[1]-20), 
                          cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            else:
                # Si no es un puño, mostrar mensaje de depuración
                cv2.putText(frame, "No es puño", 
                          (20, altura - 20 - (30 * hand_idx)), 
                          cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 165, 0), 2)
        
        # Mostrar cuántos puños se detectaron en esta iteración
        cv2.putText(frame, f"Puños detectados: {puños_detectados_esta_vez}", 
                  (20, altura - 80), 
                  cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # Si se detectaron exactamente dos puños, procesar zoom
        if len(self.punos_detectados) == 2:
            self.zoom_mode = True
            distancia_actual = self._calcular_distancia(self.punos_detectados[0], self.punos_detectados[1])
            
            # Inicializar distancia si es el primer frame
            if not self.haciendo_zoom:
                self.distancia_punos_inicial = distancia_actual
                self.haciendo_zoom = True
                # Añadir texto de inicialización de zoom para depuración
                cv2.putText(frame, "¡Zoom inicializado!", (20, altura - 110), 
                          cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            # Punto medio entre los dos puños
            punto_medio = ((self.punos_detectados[0][0] + self.punos_detectados[1][0]) // 2,
                          (self.punos_detectados[0][1] + self.punos_detectados[1][1]) // 2)
            
            # Dibujar línea entre puños
            cv2.line(frame, self.punos_detectados[0], self.punos_detectados[1], (255, 128, 0), 3)
            
            # Solo evaluar cambios significativos en la distancia para evitar falsas detecciones
            if self.distancia_punos_inicial is not None:
                factor_zoom = distancia_actual / self.distancia_punos_inicial
                
                # Mostrar datos actuales para depuración
                cv2.putText(frame, f"Dist. inicial: {self.distancia_punos_inicial:.1f}, Actual: {distancia_actual:.1f}", 
                          (20, altura - 140), 
                          cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                
                # Aplicar umbrales más estrictos para activar el zoom
                if distancia_actual > self.distancia_punos_inicial * 1.5:  # Cambio de 1.2 a 1.5
                    info_gesto['gesto'] = 'zoom_in'
                    info_gesto['posicion'] = punto_medio
                    info_gesto['datos_adicionales']['factor_zoom'] = factor_zoom
                    
                    cv2.putText(frame, f"ZOOM IN {factor_zoom:.2f}x", punto_medio, 
                              cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                elif distancia_actual < self.distancia_punos_inicial * 0.7:  # Cambio de 0.8 a 0.7
                    info_gesto['gesto'] = 'zoom_out'
                    info_gesto['posicion'] = punto_medio
                    info_gesto['datos_adicionales']['factor_zoom'] = factor_zoom
                    
                    cv2.putText(frame, f"ZOOM OUT {factor_zoom:.2f}x", punto_medio, 
                              cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
        else:
            # Resetear detección de zoom si no hay 2 puños
            self.zoom_mode = False
            self.haciendo_zoom = False
            self.distancia_punos_inicial = None
    
    def procesar_calibracion(self, frame):
        """
        Procesa el modo de calibración para mapear la cámara a la proyección/TV
        
        Args:
            frame: Imagen capturada de la cámara
            
        Returns:
            frame_procesado: Imagen con información visual sobre calibración
            calibracion_finalizada: Bool indicando si la calibración está completa
        """
        altura, ancho, _ = frame.shape
        
        # Definir las esquinas de la proyección en coordenadas de pantalla
        puntos_proyeccion = [
            (0, 0),  # Esquina superior izquierda
            (self.screen_width, 0),  # Esquina superior derecha
            (self.screen_width, self.screen_height),  # Esquina inferior derecha
            (0, self.screen_height)  # Esquina inferior izquierda
        ]
        
        # Crear copia del frame para visualización
        frame_visual = frame.copy()
        
        # Dibujar instrucciones en el frame
        cv2.putText(frame_visual, "MODO CALIBRACION", 
                  (ancho//2 - 150, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        cv2.putText(frame_visual, "Toca cada punto con la punta de tu dedo indice", 
                  (ancho//2 - 250, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        
        # Determinar qué punto estamos calibrando ahora
        punto_actual = len(self.puntos_calibracion_camara)
        
        # Dibujar todos los puntos, destacando el actual
        nombres_puntos = ["Superior Izquierda", "Superior Derecha", "Inferior Derecha", "Inferior Izquierda"]
        for i, punto in enumerate(puntos_proyeccion):
            # Convertir coordenadas de proyección a coordenadas relativas del frame
            x = int(punto[0] * ancho / self.screen_width)
            y = int(punto[1] * altura / self.screen_height)
            
            # Hacer ajustes para que los puntos estén dentro del frame visible
            x = max(50, min(x, ancho - 50))
            y = max(50, min(y, altura - 50))
            
            # Dibujar punto
            color = (0, 0, 255) if i == punto_actual else (128, 128, 128)
            cv2.circle(frame_visual, (x, y), 20, color, -1)
            
            # Si es el punto actual, mostrar instrucciones
            if i == punto_actual:
                cv2.putText(frame_visual, f"Toca: {nombres_puntos[i]}", 
                          (x - 100, y - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        
        # Detectar mano y capturar punto si se detecta un gesto específico
        results = self.hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        
        if results.multi_hand_landmarks and punto_actual < 4:
            for hand_landmarks in results.multi_hand_landmarks:
                # Dibujar puntos de referencia de la mano
                self.mp_drawing.draw_landmarks(
                    frame_visual, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)
                
                # Usando la punta del dedo índice como punto de calibración
                indice_x = int(hand_landmarks.landmark[8].x * ancho)
                indice_y = int(hand_landmarks.landmark[8].y * altura)
                
                # Dibujar la posición del dedo
                cv2.circle(frame_visual, (indice_x, indice_y), 5, (0, 255, 0), -1)
                
                # Verificar si el dedo está cerca del punto actual
                x = int(puntos_proyeccion[punto_actual][0] * ancho / self.screen_width)
                y = int(puntos_proyeccion[punto_actual][1] * altura / self.screen_height)
                
                # Ajustar para que estén dentro del frame visible
                x = max(50, min(x, ancho - 50))
                y = max(50, min(y, altura - 50))
                
                distancia = np.sqrt((indice_x - x)**2 + (indice_y - y)**2)
                
                if distancia < 50:  # Si el dedo está lo suficientemente cerca
                    # Mostrar feedback visual de que está en posición
                    cv2.putText(frame_visual, "¡Posición correcta! Espera...", 
                              (50, 120), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                    cv2.circle(frame_visual, (indice_x, indice_y), 30, (0, 255, 0), 2)
                    
                    # Esperar un momento y mostrar cuenta regresiva
                    cv2.imshow('Control por Gestos - Calibración', frame_visual)
                    cv2.waitKey(1)
                    
                    for i in range(3, 0, -1):
                        temp_frame = frame_visual.copy()
                        cv2.putText(temp_frame, f"Capturando en {i}...", 
                                  (50, 160), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                        cv2.imshow('Control por Gestos - Calibración', temp_frame)
                        cv2.waitKey(1000)  # Esperar 1 segundo
                    
                    # Guardar punto
                    self.puntos_calibracion_camara.append((indice_x, indice_y))
                    
                    # Mostrar mensaje de punto capturado
                    temp_frame = frame_visual.copy()
                    cv2.putText(temp_frame, f"¡Punto {punto_actual+1} capturado!", 
                              (50, 160), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                    cv2.imshow('Control por Gestos - Calibración', temp_frame)
                    cv2.waitKey(1000)  # Mostrar mensaje por 1 segundo
                    
                    # Si hemos capturado todos los puntos, calcular la homografía
                    if len(self.puntos_calibracion_camara) == 4:
                        self.calibrar_mesa(self.puntos_calibracion_camara, puntos_proyeccion)
                        
                        # Mostrar mensaje de calibración completa
                        temp_frame = frame_visual.copy()
                        cv2.putText(temp_frame, "¡Calibración completada!", 
                                  (ancho//2 - 150, altura//2), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                        cv2.imshow('Control por Gestos - Calibración', temp_frame)
                        cv2.waitKey(2000)  # Mostrar mensaje por 2 segundos
                        
                        return frame_visual, True  # Calibración completada
        
        # Mostrar progreso de la calibración
        if punto_actual > 0:
            cv2.putText(frame_visual, f"Puntos capturados: {punto_actual}/4", 
                      (ancho - 250, altura - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        
        return frame_visual, False  # Calibración en progreso
    
    def realizar_accion_mouse(self, info_gesto):
        """Ejecuta las acciones del mouse según el gesto detectado"""
        # Si no hay posición, no hacemos nada
        if info_gesto['posicion'] is None:
            return
        
        # Mover el mouse a la posición del cursor incondicionalmente
        # Esto garantiza que el movimiento ocurra independientemente del gesto
        x, y = info_gesto['posicion']
        
        # Restringir x,y a los límites de la pantalla
        x = max(0, min(x, self.screen_width))
        y = max(0, min(y, self.screen_height))
        
        # Siempre mover el mouse a la posición actual para el seguimiento continuo
        pyautogui.moveTo(x, y)
        print(f"Moviendo mouse a: {x}, {y}")
        
        # Realizar acciones según el gesto
        if info_gesto['gesto'] == 'click':
            if not self.clicking:
                print("Click izquierdo presionado")
                pyautogui.mouseDown()
                self.clicking = True
        elif info_gesto['gesto'] == 'arrastrar':
            if not self.dragging:
                print("Arrastrando")
                self.dragging = True
        elif info_gesto['gesto'] == 'menu_contextual':
            if not self.right_clicking:
                print("Click derecho")
                pyautogui.rightClick()
                self.right_clicking = True
        elif info_gesto['gesto'] == 'zoom_in':
            # Simulamos zoom con la rueda del mouse
            print("Zoom in")
            pyautogui.scroll(10)  # Scroll hacia arriba
        elif info_gesto['gesto'] == 'zoom_out':
            # Simulamos zoom con la rueda del mouse
            print("Zoom out")
            pyautogui.scroll(-10)  # Scroll hacia abajo
        else:
            # Si no hay gestos activos, aseguramos que se libere el mouse
            if self.clicking or self.dragging:
                print("Soltando click")
                pyautogui.mouseUp()
                self.clicking = False
                self.dragging = False
            self.right_clicking = False
    
    def cambiar_modo(self, nuevo_modo):
        """Cambia entre modo 'pantalla' y 'mesa'"""
        if nuevo_modo in ["pantalla", "mesa"]:
            self.modo = nuevo_modo
            print(f"Modo cambiado a: {nuevo_modo}")
            
            # Reiniciar estados
            self.clicking = False
            self.right_clicking = False
            self.dragging = False
            self.punto_inicial_arrastre = None
            self.zoom_mode = False
            self.haciendo_zoom = False
            self.historial_posiciones = []
            
            # Si cambiamos a modo mesa y no está calibrado, activar calibración
            if nuevo_modo == "mesa" and not self.calibracion_completada:
                self.iniciar_calibracion()
    
    def iniciar_calibracion(self):
        """Inicia el proceso de calibración"""
        self.en_calibracion = True
        self.puntos_calibracion_camara = []
        print("Iniciando calibración. Toca cada una de las 4 esquinas con tu dedo índice.")
    
    def calibrar_mesa(self, puntos_camara, puntos_proyeccion):
        """
        Calibra la matriz de transformación entre la cámara y la proyección
        
        Args:
            puntos_camara: Lista de 4 puntos [(x1,y1), (x2,y2), ...] desde la vista de la cámara
            puntos_proyeccion: Lista de 4 puntos correspondientes en coordenadas de proyección
        """
        # Convertir listas a arreglos numpy
        puntos_camara_np = np.array(puntos_camara, dtype=np.float32)
        puntos_proyeccion_np = np.array(puntos_proyeccion, dtype=np.float32)
        
        import cv2
import mediapipe as mp
import numpy as np
import time
import pyautogui
import sys
import os

# Configurar pyautogui para que sea seguro y funcione correctamente
pyautogui.FAILSAFE = True

# Deshabilitar la función de failsafe basada en posición para permitir movimientos a cualquier parte de la pantalla
pyautogui.FAILSAFE_POINTS = [(0, 0)]  # Solo esquina superior izquierda como punto de seguridad


class ControladorGestos:
    def __init__(self, modo="pantalla"):
        """
        Inicializa el controlador de gestos
        
        Args:
            modo (str): 'pantalla' para controlar el cursor del PC,
                       'mesa' para controlar la mesa de arena con cámara externa
        """
        self.modo = modo
        
        # Inicializar MediaPipe Hands
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,  # Detectamos hasta dos manos para zoom con puños
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.mp_drawing = mp.solutions.drawing_utils
        
        # Obtener tamaño de la pantalla
        self.screen_width, self.screen_height = pyautogui.size()
        
        # Variables de estado para gestos
        self.clicking = False
        self.right_clicking = False
        self.dragging = False
        self.zoom_mode = False
        self.punto_inicial_arrastre = None
        
        # Variables para zoom con dos puños
        self.punos_detectados = []
        self.distancia_punos_inicial = None
        self.haciendo_zoom = False
        
        # Suavizado de movimiento
        self.suavizado = 5
        self.historial_posiciones = []
        
        # Matriz de transformación para mapear coordenadas entre la cámara y proyección
        self.matriz_transformacion = np.eye(3)  # Identidad por defecto
        
        # Variables para calibración
        self.en_calibracion = False
        self.puntos_calibracion_camara = []
        self.calibracion_completada = False
    
    def procesar_frame(self, frame):
        """
        Procesa un fotograma de la cámara y realiza las acciones correspondientes
        
        Args:
            frame: Imagen capturada de la cámara
            
        Returns:
            frame_procesado: Imagen con información visual sobre gestos
            info_gesto: Diccionario con información del gesto detectado
        """
        # Si estamos en modo calibración, procesar la calibración
        if self.en_calibracion and self.modo == "mesa":
            frame_procesado, calibracion_finalizada = self.procesar_calibracion(frame)
            if calibracion_finalizada:
                self.en_calibracion = False
                self.calibracion_completada = True
                print("¡Calibración completada con éxito!")
            
            # Durante la calibración, devolvemos un gesto nulo
            info_gesto = {
                'gesto': 'ninguno',
                'posicion': None,
                'datos_adicionales': {}
            }
            return frame_procesado, info_gesto
        
        # Convertir imagen a RGB (MediaPipe requiere RGB)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        altura, ancho, _ = frame.shape
        
        # Procesar imagen con MediaPipe
        results = self.hands.process(frame_rgb)
        
        # Crear copia del frame para visualización
        frame_visual = frame.copy()
        
        # Información del gesto detectado para devolver
        info_gesto = {
            'gesto': 'ninguno',
            'posicion': None,
            'datos_adicionales': {}
        }
        
        # Si no se detectan manos, devolver el frame original
        if not results.multi_hand_landmarks:
            return frame_visual, info_gesto
        
        # Detectar gestos con dos manos (para zoom)
        if len(results.multi_hand_landmarks) == 2:
            self.detectar_gestos_dos_manos(results, frame_visual, ancho, altura, info_gesto)
            
            # Si se detectó zoom, aplicar la acción y devolver
            if info_gesto['gesto'] in ['zoom_in', 'zoom_out']:
                return frame_visual, info_gesto
        
        # Detectar gestos con una mano
        if len(results.multi_hand_landmarks) > 0:
            hand_landmarks = results.multi_hand_landmarks[0]
            
            # Dibujar los puntos de referencia de la mano
            self.mp_drawing.draw_landmarks(
                frame_visual, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)
            
            # Extraer puntos clave
            puntos = []
            for landmark in hand_landmarks.landmark:
                x, y = int(landmark.x * ancho), int(landmark.y * altura)
                puntos.append((x, y))
            
            # Procesar puntos para detectar gestos específicos
            info_gesto = self.detectar_gestos_una_mano(puntos, frame_visual, ancho, altura)
            
            # Si estamos en modo pantalla, realizar las acciones del mouse
            if self.modo == "pantalla" and info_gesto['posicion'] is not None:
                self.realizar_accion_mouse(info_gesto)
        
        return frame_visual, info_gesto
    
    def detectar_gestos_una_mano(self, puntos, frame, ancho, altura):
        """Detecta gestos realizados con una sola mano"""
        # Dedos clave
        indice_punta = puntos[8]
        indice_base = puntos[5]
        pulgar_punta = puntos[4]
        medio_punta = puntos[12]
        medio_base = puntos[9]
        palma = puntos[0]
        
        # Verificar si dedos están extendidos
        indice_extendido = indice_punta[1] < indice_base[1]
        medio_extendido = medio_punta[1] < medio_base[1]
        
        # Distancias entre dedos
        distancia_pulgar_indice = self._calcular_distancia(pulgar_punta, indice_punta)
        distancia_pulgar_medio = self._calcular_distancia(pulgar_punta, medio_punta)
        
        # Posición para el cursor (sigue el pulgar para mayor precisión)
        if self.modo == "pantalla":
            # Usar pulgar para mejor precisión
            cursor_x, cursor_y = pulgar_punta
            
            # Mapear coordenadas de cámara a pantalla
            screen_x = int(np.interp(cursor_x, [100, ancho-100], [0, self.screen_width]))
            screen_y = int(np.interp(cursor_y, [100, altura-100], [0, self.screen_height]))
            
            # Aplicar suavizado
            self.historial_posiciones.append((screen_x, screen_y))
            if len(self.historial_posiciones) > self.suavizado:
                self.historial_posiciones.pop(0)
            
            suavizado_x = int(sum(p[0] for p in self.historial_posiciones) / len(self.historial_posiciones))
            suavizado_y = int(sum(p[1] for p in self.historial_posiciones) / len(self.historial_posiciones))
            
            posicion_cursor = (suavizado_x, suavizado_y)
            # Mostrar coordenadas en la pantalla
            cv2.putText(frame, f"Pos: {suavizado_x}, {suavizado_y}", 
                      (ancho - 250, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        else:
            # En modo mesa, aplicar transformación de coordenadas si ya está calibrado
            if self.calibracion_completada:
                posicion_cursor = self._transformar_coordenadas(pulgar_punta)
                cv2.putText(frame, f"Transf: {posicion_cursor[0]}, {posicion_cursor[1]}", 
                          (ancho - 250, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            else:
                posicion_cursor = pulgar_punta
        
        # Información del gesto detectado
        info_gesto = {
            'gesto': 'ninguno',
            'posicion': posicion_cursor,
            'datos_adicionales': {'puntos_mano': puntos}
        }
        
        # Mostrar círculo como cursor básico en el pulgar
        cv2.circle(frame, pulgar_punta, 10, (0, 255, 0), -1)
        
        # Click izquierdo: pinza entre índice y pulgar
        if distancia_pulgar_indice < 40:
            info_gesto['gesto'] = 'click'
            # Dibujar indicador visual
            cv2.circle(frame, indice_punta, 15, (255, 0, 0), -1)
            cv2.circle(frame, pulgar_punta, 15, (255, 0, 0), -1)
            cv2.line(frame, indice_punta, pulgar_punta, (255, 0, 0), 2)
            cv2.putText(frame, "Click", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
            
            # Detectar arrastre si se mantiene la pinza y se mueve
            if self.dragging or self.clicking:
                info_gesto['gesto'] = 'arrastrar'
                cv2.putText(frame, "Arrastrando", (50, 90), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
                if self.punto_inicial_arrastre:
                    info_gesto['datos_adicionales']['punto_inicial'] = self.punto_inicial_arrastre
                    # Dibujar línea de arrastre
                    cv2.line(frame, self.punto_inicial_arrastre, posicion_cursor, (255, 0, 0), 2)
            else:
                self.punto_inicial_arrastre = posicion_cursor
        else:
            # Si la pinza se suelta, resetear estado de arrastre
            self.punto_inicial_arrastre = None
        
        # Click derecho: pulgar y dedo medio juntos
        if distancia_pulgar_medio < 40:
            info_gesto['gesto'] = 'menu_contextual'
            # Dibujar indicador visual
            cv2.circle(frame, medio_punta, 15, (0, 0, 255), -1)
            cv2.circle(frame, pulgar_punta, 15, (0, 0, 255), -1)
            cv2.line(frame, medio_punta, pulgar_punta, (0, 0, 255), 2)
            cv2.putText(frame, "Click Derecho", (50, 130), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        
        # Puño cerrado (para click o para zoom)
        if self._es_puño_cerrado(puntos):
            # Si solo hay una mano, se considera como click
            if not self.zoom_mode:
                info_gesto['gesto'] = 'click'
                cv2.circle(frame, palma, 30, (255, 255, 0), 2)
                cv2.putText(frame, "Puño (Click)", (palma[0]-40, palma[1]-20), 
                          cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        
        return info_gesto
    
    def detectar_gestos_dos_manos(self, results, frame, ancho, altura, info_gesto):
        """Detecta gestos realizados con dos manos, principalmente para zoom con puños cerrados"""
        # Limpiar la lista de puños
        self.punos_detectados = []
        
        # Verificar si ambas manos están en puño
        puños_detectados_esta_vez = 0
        
        for hand_idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
            # Dibujar los puntos de referencia de la mano
            self.mp_drawing.draw_landmarks(
                frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)
            
            # Extraer puntos clave
            puntos = []
            for landmark in hand_landmarks.landmark:
                x, y = int(landmark.x * ancho), int(landmark.y * altura)
                puntos.append((x, y))
            
            # Verificar explícitamente si es un puño usando el método mejorado
            if self._es_puño_cerrado(puntos):
                puños_detectados_esta_vez += 1
                centro_palma = puntos[0]  # Base de la palma
                self.punos_detectados.append(centro_palma)
                
                # Dibujar un círculo grande sobre el puño
                cv2.circle(frame, centro_palma, 30, (0, 0, 255), 3)
                cv2.putText(frame, f"Puño {hand_idx+1}", 
                          (centro_palma[0]-20, centro_palma[1]-20), 
                          cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            else:
                # Si no es un puño, mostrar mensaje de depuración
                cv2.putText(frame, "No es puño", 
                          (20, altura - 20 - (30 * hand_idx)), 
                          cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 165, 0), 2)
        
        # Mostrar cuántos puños se detectaron en esta iteración
        cv2.putText(frame, f"Puños detectados: {puños_detectados_esta_vez}", 
                  (20, altura - 80), 
                  cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # Si se detectaron exactamente dos puños, procesar zoom
        if len(self.punos_detectados) == 2:
            self.zoom_mode = True
            distancia_actual = self._calcular_distancia(self.punos_detectados[0], self.punos_detectados[1])
            
            # Inicializar distancia si es el primer frame
            if not self.haciendo_zoom:
                self.distancia_punos_inicial = distancia_actual
                self.haciendo_zoom = True
                # Añadir texto de inicialización de zoom para depuración
                cv2.putText(frame, "¡Zoom inicializado!", (20, altura - 110), 
                          cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            # Punto medio entre los dos puños
            punto_medio = ((self.punos_detectados[0][0] + self.punos_detectados[1][0]) // 2,
                          (self.punos_detectados[0][1] + self.punos_detectados[1][1]) // 2)
            
            # Dibujar línea entre puños
            cv2.line(frame, self.punos_detectados[0], self.punos_detectados[1], (255, 128, 0), 3)
            
            # Solo evaluar cambios significativos en la distancia para evitar falsas detecciones
            if self.distancia_punos_inicial is not None:
                factor_zoom = distancia_actual / self.distancia_punos_inicial
                
                # Mostrar datos actuales para depuración
                cv2.putText(frame, f"Dist. inicial: {self.distancia_punos_inicial:.1f}, Actual: {distancia_actual:.1f}", 
                          (20, altura - 140), 
                          cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                
                # Aplicar umbrales más estrictos para activar el zoom
                if distancia_actual > self.distancia_punos_inicial * 1.5:  # Cambio de 1.2 a 1.5
                    info_gesto['gesto'] = 'zoom_in'
                    info_gesto['posicion'] = punto_medio
                    info_gesto['datos_adicionales']['factor_zoom'] = factor_zoom
                    
                    cv2.putText(frame, f"ZOOM IN {factor_zoom:.2f}x", punto_medio, 
                              cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                elif distancia_actual < self.distancia_punos_inicial * 0.7:  # Cambio de 0.8 a 0.7
                    info_gesto['gesto'] = 'zoom_out'
                    info_gesto['posicion'] = punto_medio
                    info_gesto['datos_adicionales']['factor_zoom'] = factor_zoom
                    
                    cv2.putText(frame, f"ZOOM OUT {factor_zoom:.2f}x", punto_medio, 
                              cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
        else:
            # Resetear detección de zoom si no hay 2 puños
            self.zoom_mode = False
            self.haciendo_zoom = False
            self.distancia_punos_inicial = None
    
    def procesar_calibracion(self, frame):
        """
        Procesa el modo de calibración para mapear la cámara a la proyección/TV
        
        Args:
            frame: Imagen capturada de la cámara
            
        Returns:
            frame_procesado: Imagen con información visual sobre calibración
            calibracion_finalizada: Bool indicando si la calibración está completa
        """
        altura, ancho, _ = frame.shape
        
        # Definir las esquinas de la proyección en coordenadas de pantalla
        puntos_proyeccion = [
            (0, 0),  # Esquina superior izquierda
            (self.screen_width, 0),  # Esquina superior derecha
            (self.screen_width, self.screen_height),  # Esquina inferior derecha
            (0, self.screen_height)  # Esquina inferior izquierda
        ]
        
        # Crear copia del frame para visualización
        frame_visual = frame.copy()
        
        # Dibujar instrucciones en el frame
        cv2.putText(frame_visual, "MODO CALIBRACION", 
                  (ancho//2 - 150, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        cv2.putText(frame_visual, "Toca cada punto con la punta de tu dedo indice", 
                  (ancho//2 - 250, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        
        # Determinar qué punto estamos calibrando ahora
        punto_actual = len(self.puntos_calibracion_camara)
        
        # Dibujar todos los puntos, destacando el actual
        nombres_puntos = ["Superior Izquierda", "Superior Derecha", "Inferior Derecha", "Inferior Izquierda"]
        for i, punto in enumerate(puntos_proyeccion):
            # Convertir coordenadas de proyección a coordenadas relativas del frame
            x = int(punto[0] * ancho / self.screen_width)
            y = int(punto[1] * altura / self.screen_height)
            
            # Hacer ajustes para que los puntos estén dentro del frame visible
            x = max(50, min(x, ancho - 50))
            y = max(50, min(y, altura - 50))
            
            # Dibujar punto
            color = (0, 0, 255) if i == punto_actual else (128, 128, 128)
            cv2.circle(frame_visual, (x, y), 20, color, -1)
            
            # Si es el punto actual, mostrar instrucciones
            if i == punto_actual:
                cv2.putText(frame_visual, f"Toca: {nombres_puntos[i]}", 
                          (x - 100, y - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        
        # Detectar mano y capturar punto si se detecta un gesto específico
        results = self.hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        
        if results.multi_hand_landmarks and punto_actual < 4:
            for hand_landmarks in results.multi_hand_landmarks:
                # Dibujar puntos de referencia de la mano
                self.mp_drawing.draw_landmarks(
                    frame_visual, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)
                
                # Usando la punta del dedo índice como punto de calibración
                indice_x = int(hand_landmarks.landmark[8].x * ancho)
                indice_y = int(hand_landmarks.landmark[8].y * altura)
                
                # Dibujar la posición del dedo
                cv2.circle(frame_visual, (indice_x, indice_y), 5, (0, 255, 0), -1)
                
                # Verificar si el dedo está cerca del punto actual
                x = int(puntos_proyeccion[punto_actual][0] * ancho / self.screen_width)
                y = int(puntos_proyeccion[punto_actual][1] * altura / self.screen_height)
                
                # Ajustar para que estén dentro del frame visible
                x = max(50, min(x, ancho - 50))
                y = max(50, min(y, altura - 50))
                
                distancia = np.sqrt((indice_x - x)**2 + (indice_y - y)**2)
                
                if distancia < 50:  # Si el dedo está lo suficientemente cerca
                    # Mostrar feedback visual de que está en posición
                    cv2.putText(frame_visual, "¡Posición correcta! Espera...", 
                              (50, 120), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                    cv2.circle(frame_visual, (indice_x, indice_y), 30, (0, 255, 0), 2)
                    
                    # Esperar un momento y mostrar cuenta regresiva
                    cv2.imshow('Control por Gestos - Calibración', frame_visual)
                    cv2.waitKey(1)
                    
                    for i in range(3, 0, -1):
                        temp_frame = frame_visual.copy()
                        cv2.putText(temp_frame, f"Capturando en {i}...", 
                                  (50, 160), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                        cv2.imshow('Control por Gestos - Calibración', temp_frame)
                        cv2.waitKey(1000)  # Esperar 1 segundo
                    
                    # Guardar punto
                    self.puntos_calibracion_camara.append((indice_x, indice_y))
                    
                    # Mostrar mensaje de punto capturado
                    temp_frame = frame_visual.copy()
                    cv2.putText(temp_frame, f"¡Punto {punto_actual+1} capturado!", 
                              (50, 160), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                    cv2.imshow('Control por Gestos - Calibración', temp_frame)
                    cv2.waitKey(1000)  # Mostrar mensaje por 1 segundo
                    
                    # Si hemos capturado todos los puntos, calcular la homografía
                    if len(self.puntos_calibracion_camara) == 4:
                        self.calibrar_mesa(self.puntos_calibracion_camara, puntos_proyeccion)
                        
                        # Mostrar mensaje de calibración completa
                        temp_frame = frame_visual.copy()
                        cv2.putText(temp_frame, "¡Calibración completada!", 
                                  (ancho//2 - 150, altura//2), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                        cv2.imshow('Control por Gestos - Calibración', temp_frame)
                        cv2.waitKey(2000)  # Mostrar mensaje por 2 segundos
                        
                        return frame_visual, True  # Calibración completada
        
        # Mostrar progreso de la calibración
        if punto_actual > 0:
            cv2.putText(frame_visual, f"Puntos capturados: {punto_actual}/4", 
                      (ancho - 250, altura - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        
        return frame_visual, False  # Calibración en progreso
    
    def realizar_accion_mouse(self, info_gesto):
        """Ejecuta las acciones del mouse según el gesto detectado"""
        # Si no hay posición, no hacemos nada
        if info_gesto['posicion'] is None:
            return
        
        # Mover el mouse a la posición del cursor incondicionalmente
        # Esto garantiza que el movimiento ocurra independientemente del gesto
        x, y = info_gesto['posicion']
        
        # Restringir x,y a los límites de la pantalla
        x = max(0, min(x, self.screen_width))
        y = max(0, min(y, self.screen_height))
        
        # Siempre mover el mouse a la posición actual para el seguimiento continuo
        pyautogui.moveTo(x, y)
        print(f"Moviendo mouse a: {x}, {y}")
        
        # Realizar acciones según el gesto
        if info_gesto['gesto'] == 'click':
            if not self.clicking:
                print("Click izquierdo presionado")
                pyautogui.mouseDown()
                self.clicking = True
        elif info_gesto['gesto'] == 'arrastrar':
            if not self.dragging:
                print("Arrastrando")
                self.dragging = True
        elif info_gesto['gesto'] == 'menu_contextual':
            if not self.right_clicking:
                print("Click derecho")
                pyautogui.rightClick()
                self.right_clicking = True
        elif info_gesto['gesto'] == 'zoom_in':
            # Simulamos zoom con la rueda del mouse
            print("Zoom in")
            pyautogui.scroll(10)  # Scroll hacia arriba
        elif info_gesto['gesto'] == 'zoom_out':
            # Simulamos zoom con la rueda del mouse
            print("Zoom out")
            pyautogui.scroll(-10)  # Scroll hacia abajo
        else:
            # Si no hay gestos activos, aseguramos que se libere el mouse
            if self.clicking or self.dragging:
                print("Soltando click")
                pyautogui.mouseUp()
                self.clicking = False
                self.dragging = False
            self.right_clicking = False
    
    def cambiar_modo(self, nuevo_modo):
        """Cambia entre modo 'pantalla' y 'mesa'"""
        if nuevo_modo in ["pantalla", "mesa"]:
            self.modo = nuevo_modo
            print(f"Modo cambiado a: {nuevo_modo}")
            
            # Reiniciar estados
            self.clicking = False
            self.right_clicking = False
            self.dragging = False
            self.punto_inicial_arrastre = None
            self.zoom_mode = False
            self.haciendo_zoom = False
            self.historial_posiciones = []
            
            # Si cambiamos a modo mesa y no está calibrado, activar calibración
            if nuevo_modo == "mesa" and not self.calibracion_completada:
                self.iniciar_calibracion()
    
    def iniciar_calibracion(self):
        """Inicia el proceso de calibración"""
        self.en_calibracion = True
        self.puntos_calibracion_camara = []
        print("Iniciando calibración. Toca cada una de las 4 esquinas con tu dedo índice.")
    
    def calibrar_mesa(self, puntos_camara, puntos_proyeccion):
        """
        Calibra la matriz de transformación entre la cámara y la proyección
        
        Args:
            puntos_camara: Lista de 4 puntos [(x1,y1), (x2,y2), ...] desde la vista de la cámara
            puntos_proyeccion: Lista de 4 puntos correspondientes en coordenadas de proyección
        """
        # Convertir listas a arreglos numpy
        puntos_camara_np = np.array(puntos_camara, dtype=np.float32)
        puntos_proyeccion_np = np.array(puntos_proyeccion, dtype=np.float32)
        
        # Calcular matriz de homografía para transformar entre sistemas de coordenadas
        self.matriz_transformacion, _ = cv2.findHomography(
            puntos_camara_np, 
            puntos_proyeccion_np, 
            cv2.RANSAC, 5.0
        )
        
        print("Matriz de calibración calculada:")
        print(self.matriz_transformacion)
        
        # Guardar la matriz en un archivo para futuro uso
        np.save("calibracion_matriz.npy", self.matriz_transformacion)
        print("Matriz de calibración guardada en 'calibracion_matriz.npy'")
    
    def _transformar_coordenadas(self, punto):
        """Transforma coordenadas de la cámara al espacio de proyección"""
        # Convertir a coordenadas homogéneas
        punto_h = np.array([punto[0], punto[1], 1.0])
        
        # Aplicar transformación
        punto_transformado = np.dot(self.matriz_transformacion, punto_h)
        
        # Normalizar y convertir de vuelta a coordenadas cartesianas
        if punto_transformado[2] != 0:  # Evitar división por cero
            punto_transformado = punto_transformado / punto_transformado[2]
        
        return (int(punto_transformado[0]), int(punto_transformado[1]))
    
    def _calcular_distancia(self, punto1, punto2):
        """Calcula la distancia euclidiana entre dos puntos"""
        return np.sqrt((punto1[0] - punto2[0])**2 + (punto1[1] - punto2[1])**2)
    
    def _es_puño_cerrado(self, puntos):
        """Detecta si la mano forma un puño cerrado de manera más estricta para evitar falsos positivos"""
        # Verificar si las puntas de los dedos están por debajo de sus bases
        # Esto es más estricto y evita confundir muñecas con puños
        punta_dedos = [puntos[8], puntos[12], puntos[16], puntos[20]]
        base_dedos = [puntos[5], puntos[9], puntos[13], puntos[17]]
        
        # Comprobamos que los dedos estén realmente doblados (puntas debajo de sus bases)
        dedos_doblados = 0
        for punta, base in zip(punta_dedos, base_dedos):
            # Si la punta está debajo de la base (en coordenadas y mayores)
            if punta[1] > base[1]:
                dedos_doblados += 1
        
        # Verificar también que la distancia entre puntas de dedos y nudillos sea pequeña
        palma = puntos[0]
        puntas_cerca = 0
        for punta in punta_dedos:
            if self._calcular_distancia(punta, palma) < self._calcular_distancia(base_dedos[0], palma) * 1.3:
                puntas_cerca += 1
        
        # Debe tener al menos 3 dedos doblados Y las puntas deben estar cerca de la palma
        return dedos_doblados >= 3 and puntas_cerca >= 3


def main():
    # Inicializar la cámara
    cap = cv2.VideoCapture(0)
    
    # Verificar si la cámara se abrió correctamente
    if not cap.isOpened():
        print("Error: No se pudo abrir la cámara.")
        return
    
    # Crear controlador de gestos (por defecto en modo 'pantalla')
    controlador = ControladorGestos(modo="pantalla")
    
    # Variables para cambiar entre modos
    modo_actual = "pantalla"
    
    print("\n=== Sistema Unificado de Control por Gestos ===")
    print("Modo actual: Control del cursor de pantalla")
    print("\nGestos disponibles:")
    print("  - Mano abierta: Mover el cursor (el pulgar controla la posición)")
    print("  - Pulgar + Índice juntos: Click izquierdo / Arrastrar")
    print("  - Pulgar + Dedo medio juntos: Click derecho")
    print("  - Dos puños: Zoom (acercar/alejar según la distancia)")
    print("\nControles:")
    print("  - Presiona 'q' para salir")
    print("  - Presiona 'm' para cambiar entre modo 'pantalla' y 'mesa'")
    print("  - Presiona 'c' para iniciar calibración manual")
    print("\nAsegúrate de que la ventana de visualización no está en primer plano")
    print("para que los gestos puedan controlar otras aplicaciones.")
    
    # Establecer la ventana en una posición que no interfiera
    cv2.namedWindow('Control por Gestos')
    cv2.moveWindow('Control por Gestos', 50, 50)
    
    # Ajustar el tamaño de la ventana para que no ocupe toda la pantalla
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cv2.resizeWindow('Control por Gestos', width//2, height//2)
    
    # Configurar pyautogui para que use el movimiento relativo
    # esto puede ayudar en algunos sistemas operativos
    pyautogui.PAUSE = 0.03  # Reducir el tiempo de pausa entre comandos
    
    # Intentar cargar calibración previa si existe
    try:
        matriz_cargada = np.load("calibracion_matriz.npy")
        controlador.matriz_transformacion = matriz_cargada
        controlador.calibracion_completada = True
        print("Calibración cargada desde archivo 'calibracion_matriz.npy'")
    except:
        print("No se encontró archivo de calibración previo.")
    
    # Bucle principal
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            print("Error al capturar el frame.")
            break
        
        # Voltear horizontalmente para una visualización más natural
        frame = cv2.flip(frame, 1)
        
        # Procesar frame
        frame_procesado, info_gesto = controlador.procesar_frame(frame)
        
        # Mostrar el modo actual en la imagen
        modo_texto = "PANTALLA" if modo_actual == "pantalla" else "MESA (PROYECCIÓN/TV)"
        calibracion_texto = " - CALIBRADO" if controlador.calibracion_completada and modo_actual == "mesa" else ""
        cv2.putText(frame_procesado, f"Modo: {modo_texto}{calibracion_texto}", 
                  (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 155, 255), 2)
        
        # Redimensionar el frame para que no ocupe toda la pantalla
        frame_mostrar = cv2.resize(frame_procesado, (width//2, height//2))
        
        # Mostrar frame procesado
        cv2.imshow('Control por Gestos', frame_mostrar)
        
        # Gestionar teclas
        key = cv2.waitKey(1) & 0xFF
        
        # Salir con 'q'
        if key == ord('q'):
            break
        
        # Cambiar modo con 'm'
        elif key == ord('m'):
            if modo_actual == "pantalla":
                modo_actual = "mesa"
                controlador.cambiar_modo("mesa")
                print("Cambiado a modo: Mesa de Arena")
            else:
                modo_actual = "pantalla"
                controlador.cambiar_modo("pantalla")
                print("Cambiado a modo: Control de Pantalla")
        
        # Iniciar calibración manual con 'c'
        elif key == ord('c'):
            if modo_actual == "mesa":
                print("Iniciando calibración manual...")
                controlador.iniciar_calibracion()
    
    # Liberar recursos
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
