#!/usr/bin/env python3
"""
Sistema Unificado de Control por Gestos v2.0 - Con Interfaz Mejorada
Combina tu código original con mejoras visuales profesionales

Características principales:
- Interfaz de usuario completa y visual
- Panel de información en tiempo real
- Indicadores visuales de gestos
- Guías para el usuario
- Control del cursor mediante gestos de manos
- Dos modos: pantalla y mesa (con calibración)
- Logging avanzado
"""

import cv2
import mediapipe as mp
import numpy as np
import time
import pyautogui
import sys
import os
import json
import logging
from datetime import datetime

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('detector_gestos.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configurar pyautogui para que sea seguro y funcione correctamente
pyautogui.FAILSAFE = True
pyautogui.FAILSAFE_POINTS = [(0, 0)]  # Solo esquina superior izquierda como punto de seguridad


class ControladorGestos:
    def __init__(self, modo="pantalla"):
        """
        Inicializa el controlador de gestos con interfaz mejorada
        
        Args:
            modo (str): 'pantalla' para controlar el cursor del PC,
                       'mesa' para controlar la mesa de arena con cámara externa
        """
        self.modo = modo
        
        # Cargar configuración
        self.config = self.cargar_configuracion()
        
        # Inicializar MediaPipe Hands
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,  # Detectamos hasta dos manos para zoom con puños
            min_detection_confidence=self.config['deteccion']['min_detection_confidence'],
            min_tracking_confidence=self.config['deteccion']['min_tracking_confidence']
        )
        self.mp_drawing = mp.solutions.drawing_utils
        
        # Obtener tamaño de la pantalla
        self.screen_width, self.screen_height = pyautogui.size()
        logger.info(f"Resolución de pantalla detectada: {self.screen_width}x{self.screen_height}")
        
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
        self.suavizado = self.config['gestos']['suavizado_movimiento']
        self.historial_posiciones = []
        
        # Matriz de transformación para mapear coordenadas entre la cámara y proyección
        self.matriz_transformacion = np.eye(3)  # Identidad por defecto
        
        # Variables para calibración
        self.en_calibracion = False
        self.puntos_calibracion_camara = []
        self.calibracion_completada = False
        
        # Variables para la interfaz
        self.ultimo_gesto = "ninguno"
        self.tiempo_gesto = time.time()
        
        logger.info(f"Controlador de gestos inicializado en modo: {modo}")
    
    def cargar_configuracion(self):
        """Carga la configuración desde el archivo config.json"""
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
            logger.info("Configuración cargada exitosamente")
            return config
        except FileNotFoundError:
            logger.warning("Archivo config.json no encontrado, usando configuración por defecto")
            return {
                "deteccion": {
                    "min_detection_confidence": 0.7,
                    "min_tracking_confidence": 0.5
                },
                "gestos": {
                    "distancia_pinza": 40,
                    "factor_zoom_in": 1.5,
                    "factor_zoom_out": 0.7,
                    "suavizado_movimiento": 5
                }
            }
    
    def dibujar_interfaz_principal(self, frame):
        """Dibuja la interfaz principal con información del sistema"""
        altura, ancho, _ = frame.shape
        
        # Panel superior - Información del sistema
        overlay = frame.copy()
        cv2.rectangle(overlay, (10, 10), (ancho-10, 120), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.8, frame, 0.2, 0, frame)
        
        # Título principal
        cv2.putText(frame, "SISTEMA DE CONTROL POR GESTOS v2.0", 
                  (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        
        # Modo actual
        modo_color = (0, 255, 0) if self.modo == "pantalla" else (255, 100, 0)
        modo_texto = "PANTALLA (Control PC)" if self.modo == "pantalla" else "MESA (Proyección/TV)"
        cv2.putText(frame, f"Modo: {modo_texto}", 
                  (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.7, modo_color, 2)
        
        # Estado de calibración
        if self.modo == "mesa":
            if self.calibracion_completada:
                cv2.putText(frame, "Estado: CALIBRADO ✓", 
                          (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            elif self.en_calibracion:
                cv2.putText(frame, "Estado: CALIBRANDO...", 
                          (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            else:
                cv2.putText(frame, "Estado: SIN CALIBRAR - Presiona 'C'", 
                          (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        else:
            cv2.putText(frame, "Estado: LISTO", 
                      (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        return frame
    
    def dibujar_panel_controles(self, frame):
        """Dibuja el panel de controles disponibles"""
        altura, ancho, _ = frame.shape
        
        # Panel de controles
        overlay = frame.copy()
        cv2.rectangle(overlay, (10, 130), (ancho-10, 200), (20, 20, 20), -1)
        cv2.addWeighted(overlay, 0.9, frame, 0.1, 0, frame)
        
        # Título de controles
        cv2.putText(frame, "CONTROLES DISPONIBLES:", 
                  (20, 155), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Controles de teclado
        cv2.putText(frame, "Q = Salir  |  M = Cambiar Modo  |  C = Calibrar  |  + = Más Suavizado  |  - = Menos Suavizado", 
                  (20, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 2)
        
        return frame
    
    def dibujar_panel_gestos(self, frame):
        """Dibuja el panel con información sobre gestos"""
        altura, ancho, _ = frame.shape
        
        # Panel de gestos
        overlay = frame.copy()
        cv2.rectangle(overlay, (10, 210), (ancho-10, 280), (0, 20, 40), -1)
        cv2.addWeighted(overlay, 0.9, frame, 0.1, 0, frame)
        
        # Título de gestos
        cv2.putText(frame, "GESTOS DISPONIBLES:", 
                  (20, 235), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Lista de gestos
        cv2.putText(frame, "✋ Mano Abierta = Mover Cursor  |  👌 Pinza (Pulgar+Índice) = Click Izquierdo", 
                  (20, 255), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 2)
        cv2.putText(frame, "🤟 Pulgar+Medio = Click Derecho  |  ✊ Puño = Click Alternativo  |  ✊✊ Dos Puños = Zoom", 
                  (20, 270), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 2)
        
        return frame
    
    def dibujar_informacion_lateral(self, frame):
        """Dibuja información del sistema en el lado derecho"""
        altura, ancho, _ = frame.shape
        info_x = ancho - 320
        
        # Panel lateral
        overlay = frame.copy()
        cv2.rectangle(overlay, (info_x, 10), (ancho-10, 200), (40, 20, 0), -1)
        cv2.addWeighted(overlay, 0.9, frame, 0.1, 0, frame)
        
        # Título
        cv2.putText(frame, "INFORMACIÓN DEL SISTEMA", 
                  (info_x + 10, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        
        # Información técnica
        cv2.putText(frame, f"Resolución: {self.screen_width}x{self.screen_height}", 
                  (info_x + 10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        cv2.putText(frame, f"Suavizado: {self.suavizado}", 
                  (info_x + 10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        cv2.putText(frame, f"Confianza: {self.config['deteccion']['min_detection_confidence']}", 
                  (info_x + 10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        cv2.putText(frame, f"Detección: MediaPipe", 
                  (info_x + 10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # Tiempo actual
        tiempo_actual = datetime.now().strftime("%H:%M:%S")
        cv2.putText(frame, f"Hora: {tiempo_actual}", 
                  (info_x + 10, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # Estado de manos detectadas
        cv2.putText(frame, "Detección: MediaPipe ON", 
                  (info_x + 10, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        
        return frame
    
    def dibujar_indicadores_gestos(self, frame, info_gesto):
        """Dibuja indicadores en tiempo real de los gestos detectados"""
        altura, ancho, _ = frame.shape
        
        # Panel inferior para gestos activos
        overlay = frame.copy()
        cv2.rectangle(overlay, (10, altura-120), (ancho-10, altura-10), (0, 40, 0), -1)
        cv2.addWeighted(overlay, 0.9, frame, 0.1, 0, frame)
        
        # Título
        cv2.putText(frame, "ESTADO ACTUAL:", 
                  (20, altura-95), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Gesto detectado
        gesto_texto = "Sin gesto detectado"
        gesto_color = (128, 128, 128)
        
        if info_gesto['gesto'] == 'click':
            gesto_texto = "🖱️ CLICK IZQUIERDO ACTIVO"
            gesto_color = (255, 0, 0)
        elif info_gesto['gesto'] == 'arrastrar':
            gesto_texto = "↔️ ARRASTRANDO OBJETO"
            gesto_color = (255, 100, 0)
        elif info_gesto['gesto'] == 'menu_contextual':
            gesto_texto = "📋 CLICK DERECHO ACTIVO"
            gesto_color = (0, 0, 255)
        elif info_gesto['gesto'] == 'zoom_in':
            gesto_texto = "🔍 ZOOM IN (Acercando)"
            gesto_color = (0, 255, 0)
        elif info_gesto['gesto'] == 'zoom_out':
            gesto_texto = "🔍 ZOOM OUT (Alejando)"
            gesto_color = (255, 0, 255)
        elif info_gesto['gesto'] == 'ninguno':
            if info_gesto['posicion'] is not None:
                gesto_texto = "👋 Moviendo cursor"
                gesto_color = (0, 255, 255)
        
        cv2.putText(frame, f"Gesto: {gesto_texto}", 
                  (20, altura-70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, gesto_color, 2)
        
        # Posición del cursor
        if info_gesto['posicion'] is not None:
            x, y = info_gesto['posicion']
            cv2.putText(frame, f"Posición del cursor: ({x}, {y})", 
                      (20, altura-40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        else:
            cv2.putText(frame, "Posición del cursor: No detectada", 
                      (20, altura-40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (128, 128, 128), 2)
        
        return frame
    
    def procesar_frame(self, frame):
        """
        Procesa un fotograma de la cámara y realiza las acciones correspondientes
        """
        # Si estamos en modo calibración, procesar la calibración
        if self.en_calibracion and self.modo == "mesa":
            frame_procesado, calibracion_finalizada = self.procesar_calibracion(frame)
            if calibracion_finalizada:
                self.en_calibracion = False
                self.calibracion_completada = True
                logger.info("¡Calibración completada con éxito!")
            
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
        
        # Detectar gestos si hay manos
        if results.multi_hand_landmarks:
            # Detectar gestos con dos manos (para zoom)
            if len(results.multi_hand_landmarks) == 2:
                self.detectar_gestos_dos_manos(results, frame_visual, ancho, altura, info_gesto)
                
                # Si se detectó zoom, aplicar la acción
                if info_gesto['gesto'] in ['zoom_in', 'zoom_out']:
                    pass  # Los indicadores se dibujan al final
            
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
                if not info_gesto['gesto'] in ['zoom_in', 'zoom_out']:  # Solo si no hay zoom activo
                    info_gesto = self.detectar_gestos_una_mano(puntos, frame_visual, ancho, altura)
                
                # Si estamos en modo pantalla, realizar las acciones del mouse
                if self.modo == "pantalla" and info_gesto['posicion'] is not None:
                    self.realizar_accion_mouse(info_gesto)
        
        # Dibujar toda la interfaz
        frame_visual = self.dibujar_interfaz_principal(frame_visual)
        frame_visual = self.dibujar_panel_controles(frame_visual)
        frame_visual = self.dibujar_panel_gestos(frame_visual)
        frame_visual = self.dibujar_informacion_lateral(frame_visual)
        frame_visual = self.dibujar_indicadores_gestos(frame_visual, info_gesto)
        
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
        
        # Distancias entre dedos
        distancia_pulgar_indice = self._calcular_distancia(pulgar_punta, indice_punta)
        distancia_pulgar_medio = self._calcular_distancia(pulgar_punta, medio_punta)
        
        # Posición para el cursor (sigue el pulgar para mayor precisión)
        if self.modo == "pantalla":
            cursor_x, cursor_y = pulgar_punta
            
            # Mapear coordenadas de cámara a pantalla con márgenes
            margen_x, margen_y = 100, 100
            screen_x = int(np.interp(cursor_x, [margen_x, ancho-margen_x], [0, self.screen_width]))
            screen_y = int(np.interp(cursor_y, [margen_y, altura-margen_y], [0, self.screen_height]))
            
            # Aplicar suavizado
            self.historial_posiciones.append((screen_x, screen_y))
            if len(self.historial_posiciones) > self.suavizado:
                self.historial_posiciones.pop(0)
            
            suavizado_x = int(sum(p[0] for p in self.historial_posiciones) / len(self.historial_posiciones))
            suavizado_y = int(sum(p[1] for p in self.historial_posiciones) / len(self.historial_posiciones))
            
            posicion_cursor = (suavizado_x, suavizado_y)
        else:
            # En modo mesa, aplicar transformación de coordenadas si ya está calibrado
            if self.calibracion_completada:
                posicion_cursor = self._transformar_coordenadas(pulgar_punta)
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
        if distancia_pulgar_indice < self.config['gestos']['distancia_pinza']:
            info_gesto['gesto'] = 'click'
            # Dibujar indicador visual
            cv2.circle(frame, indice_punta, 15, (255, 0, 0), -1)
            cv2.circle(frame, pulgar_punta, 15, (255, 0, 0), -1)
            cv2.line(frame, indice_punta, pulgar_punta, (255, 0, 0), 2)
            
            # Detectar arrastre si se mantiene la pinza y se mueve
            if self.dragging or self.clicking:
                info_gesto['gesto'] = 'arrastrar'
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
        if distancia_pulgar_medio < self.config['gestos']['distancia_pinza']:
            info_gesto['gesto'] = 'menu_contextual'
            # Dibujar indicador visual
            cv2.circle(frame, medio_punta, 15, (0, 0, 255), -1)
            cv2.circle(frame, pulgar_punta, 15, (0, 0, 255), -1)
            cv2.line(frame, medio_punta, pulgar_punta, (0, 0, 255), 2)
        
        # Puño cerrado (para click alternativo)
        if self._es_puño_cerrado(puntos):
            if not self.zoom_mode:
                info_gesto['gesto'] = 'click'
                cv2.circle(frame, palma, 30, (255, 255, 0), 2)
        
        return info_gesto
    
    def detectar_gestos_dos_manos(self, results, frame, ancho, altura, info_gesto):
        """Detecta gestos realizados con dos manos, principalmente para zoom con puños cerrados"""
        self.punos_detectados = []
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
            
            # Verificar si es un puño cerrado
            if self._es_puño_cerrado(puntos):
                puños_detectados_esta_vez += 1
                centro_palma = puntos[0]
                self.punos_detectados.append(centro_palma)
                
                # Dibujar indicador visual
                cv2.circle(frame, centro_palma, 30, (0, 0, 255), 3)
                cv2.putText(frame, f"Puño {hand_idx+1}", 
                          (centro_palma[0]-20, centro_palma[1]-20), 
                          cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        
        # Si se detectaron exactamente dos puños, procesar zoom
        if len(self.punos_detectados) == 2:
            self.zoom_mode = True
            distancia_actual = self._calcular_distancia(self.punos_detectados[0], self.punos_detectados[1])
            
            # Inicializar distancia si es el primer frame
            if not self.haciendo_zoom:
                self.distancia_punos_inicial = distancia_actual
                self.haciendo_zoom = True
            
            # Punto medio entre los dos puños
            punto_medio = ((self.punos_detectados[0][0] + self.punos_detectados[1][0]) // 2,
                          (self.punos_detectados[0][1] + self.punos_detectados[1][1]) // 2)
            
            # Dibujar línea entre puños
            cv2.line(frame, self.punos_detectados[0], self.punos_detectados[1], (255, 128, 0), 3)
            
            # Evaluar cambios en la distancia para zoom
            if self.distancia_punos_inicial is not None:
                factor_zoom = distancia_actual / self.distancia_punos_inicial
                
                if distancia_actual > self.distancia_punos_inicial * self.config['gestos']['factor_zoom_in']:
                    info_gesto['gesto'] = 'zoom_in'
                    info_gesto['posicion'] = punto_medio
                    info_gesto['datos_adicionales']['factor_zoom'] = factor_zoom
                elif distancia_actual < self.distancia_punos_inicial * self.config['gestos']['factor_zoom_out']:
                    info_gesto['gesto'] = 'zoom_out'
                    info_gesto['posicion'] = punto_medio
                    info_gesto['datos_adicionales']['factor_zoom'] = factor_zoom
        else:
            # Resetear detección de zoom si no hay 2 puños
            self.zoom_mode = False
            self.haciendo_zoom = False
            self.distancia_punos_inicial = None
    
    def procesar_calibracion(self, frame):
        """Procesa el modo de calibración para mapear la cámara a la proyección/TV"""
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
        
        # Dibujar fondo para calibración
        overlay = frame_visual.copy()
        cv2.rectangle(overlay, (0, 0), (ancho, altura), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, frame_visual, 0.3, 0, frame_visual)
        
        # Instrucciones principales
        cv2.putText(frame_visual, "MODO CALIBRACIÓN", 
                  (ancho//2 - 150, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
        cv2.putText(frame_visual, "Toca cada punto con la punta de tu dedo índice", 
                  (ancho//2 - 300, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        
        # Punto actual
        punto_actual = len(self.puntos_calibracion_camara)
        nombres_puntos = ["Superior Izquierda", "Superior Derecha", "Inferior Derecha", "Inferior Izquierda"]
        
        if punto_actual < 4:
            cv2.putText(frame_visual, f"Punto {punto_actual + 1}/4: {nombres_puntos[punto_actual]}", 
                      (ancho//2 - 200, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
        
        # Dibujar puntos de calibración
        for i, punto in enumerate(puntos_proyeccion):
            # Convertir coordenadas de proyección a coordenadas del frame
            x = int(punto[0] * ancho / self.screen_width)
            y = int(punto[1] * altura / self.screen_height)
            
            x = max(50, min(x, ancho - 50))
            y = max(50, min(y, altura - 50))
            
            color = (0, 255, 0) if i == punto_actual else (128, 128, 128)
            tamano = 25 if i == punto_actual else 15
            
            cv2.circle(frame_visual, (x, y), tamano, color, -1)
            cv2.putText(frame_visual, str(i+1), (x-10, y+5), 
                      cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        
        # Detectar mano y capturar punto
        results = self.hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        
        if results.multi_hand_landmarks and punto_actual < 4:
            for hand_landmarks in results.multi_hand_landmarks:
                # Dibujar puntos de referencia
                self.mp_drawing.draw_landmarks(
                    frame_visual, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)
                
                # Posición del dedo índice
                indice_x = int(hand_landmarks.landmark[8].x * ancho)
                indice_y = int(hand_landmarks.landmark[8].y * altura)
                
                cv2.circle(frame_visual, (indice_x, indice_y), 8, (0, 255, 0), -1)
                
                # Verificar proximidad al punto objetivo
                target_x = int(puntos_proyeccion[punto_actual][0] * ancho / self.screen_width)
                target_y = int(puntos_proyeccion[punto_actual][1] * altura / self.screen_height)
                target_x = max(50, min(target_x, ancho - 50))
                target_y = max(50, min(target_y, altura - 50))
                
                distancia = np.sqrt((indice_x - target_x)**2 + (indice_y - target_y)**2)
                
                if distancia < 60:
                    cv2.putText(frame_visual, "¡Posición correcta! Mantén...", 
                              (ancho//2 - 150, altura - 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                    
                    # Cuenta regresiva visual
                    for i in range(3, 0, -1):
                        temp_frame = frame_visual.copy()
                        cv2.putText(temp_frame, f"Capturando en {i}...", 
                                  (ancho//2 - 100, altura - 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                        cv2.imshow('Control por Gestos - Calibración', temp_frame)
                        cv2.waitKey(1000)
                    
                    # Guardar punto
                    self.puntos_calibracion_camara.append((indice_x, indice_y))
                    
                    # Si completamos todos los puntos
                    if len(self.puntos_calibracion_camara) == 4:
                        self.calibrar_mesa(self.puntos_calibracion_camara, puntos_proyeccion)
                        return frame_visual, True
        
        return frame_visual, False
    
    def realizar_accion_mouse(self, info_gesto):
        """Ejecuta las acciones del mouse según el gesto detectado"""
        if info_gesto['posicion'] is None:
            return
        
        x, y = info_gesto['posicion']
        x = max(0, min(x, self.screen_width))
        y = max(0, min(y, self.screen_height))
        
        # Mover el mouse
        pyautogui.moveTo(x, y)
        
        # Realizar acciones según el gesto
        if info_gesto['gesto'] == 'click':
            if not self.clicking:
                pyautogui.mouseDown()
                self.clicking = True
        elif info_gesto['gesto'] == 'arrastrar':
            if not self.dragging:
                self.dragging = True
        elif info_gesto['gesto'] == 'menu_contextual':
            if not self.right_clicking:
                pyautogui.rightClick()
                self.right_clicking = True
        elif info_gesto['gesto'] == 'zoom_in':
            pyautogui.scroll(10)
        elif info_gesto['gesto'] == 'zoom_out':
            pyautogui.scroll(-10)
        else:
            if self.clicking or self.dragging:
                pyautogui.mouseUp()
                self.clicking = False
                self.dragging = False
            self.right_clicking = False
    
    def cambiar_modo(self, nuevo_modo):
        """Cambia entre modo 'pantalla' y 'mesa'"""
        if nuevo_modo in ["pantalla", "mesa"]:
            self.modo = nuevo_modo
            logger.info(f"Modo cambiado a: {nuevo_modo}")
            
            # Reiniciar estados
            self.clicking = False
            self.right_clicking = False
            self.dragging = False
            self.punto_inicial_arrastre = None
            self.zoom_mode = False
            self.haciendo_zoom = False
            self.historial_posiciones = []
            
            if nuevo_modo == "mesa" and not self.calibracion_completada:
                self.iniciar_calibracion()
    
    def iniciar_calibracion(self):
        """Inicia el proceso de calibración"""
        self.en_calibracion = True
        self.puntos_calibracion_camara = []
        logger.info("Iniciando calibración...")
    
    def calibrar_mesa(self, puntos_camara, puntos_proyeccion):
        """Calibra la matriz de transformación"""
        puntos_camara_np = np.array(puntos_camara, dtype=np.float32)
        puntos_proyeccion_np = np.array(puntos_proyeccion, dtype=np.float32)
        
        self.matriz_transformacion, _ = cv2.findHomography(
            puntos_camara_np, puntos_proyeccion_np, cv2.RANSAC, 5.0)
        
        np.save("calibracion_matriz.npy", self.matriz_transformacion)
        logger.info("Matriz de calibración guardada")
    
    def ajustar_suavizado(self, incremento):
        """Ajusta el suavizado de movimiento"""
        self.suavizado = max(1, min(10, self.suavizado + incremento))
        logger.info(f"Suavizado ajustado a: {self.suavizado}")
    
    def _transformar_coordenadas(self, punto):
        """Transforma coordenadas de la cámara al espacio de proyección"""
        punto_h = np.array([punto[0], punto[1], 1.0])
        punto_transformado = np.dot(self.matriz_transformacion, punto_h)
        
        if punto_transformado[2] != 0:
            punto_transformado = punto_transformado / punto_transformado[2]
        
        return (int(punto_transformado[0]), int(punto_transformado[1]))
    
    def _calcular_distancia(self, punto1, punto2):
        """Calcula la distancia euclidiana entre dos puntos"""
        return np.sqrt((punto1[0] - punto2[0])**2 + (punto1[1] - punto2[1])**2)
    
    def _es_puño_cerrado(self, puntos):
        """Detecta si la mano forma un puño cerrado"""
        punta_dedos = [puntos[8], puntos[12], puntos[16], puntos[20]]
        base_dedos = [puntos[5], puntos[9], puntos[13], puntos[17]]
        
        dedos_doblados = 0
        for punta, base in zip(punta_dedos, base_dedos):
            if punta[1] > base[1]:
                dedos_doblados += 1
        
        palma = puntos[0]
        puntas_cerca = 0
        for punta in punta_dedos:
            if self._calcular_distancia(punta, palma) < self._calcular_distancia(base_dedos[0], palma) * 1.3:
                puntas_cerca += 1
        
        return dedos_doblados >= 3 and puntas_cerca >= 3


def main():
    """Función principal del programa"""
    # Inicializar la cámara
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("Error: No se pudo abrir la cámara.")
        return
    
    # Crear controlador de gestos
    controlador = ControladorGestos(modo="pantalla")
    modo_actual = "pantalla"
    
    # Mensaje de bienvenida
    print("\n" + "="*60)
    print("🎮 SISTEMA UNIFICADO DE CONTROL POR GESTOS v2.0")
    print("="*60)
    print("🖱️  Modo actual: Control del cursor de pantalla")
    print("\n📖 GUÍA RÁPIDA:")
    print("   ✋ Mano abierta → Mover cursor")
    print("   👌 Pulgar + Índice → Click izquierdo")
    print("   🤟 Pulgar + Medio → Click derecho")
    print("   ✊✊ Dos puños → Zoom")
    print("\n⌨️  CONTROLES:")
    print("   Q = Salir")
    print("   M = Cambiar modo (Pantalla ↔ Mesa)")
    print("   C = Calibrar (solo modo mesa)")
    print("   + = Más suavizado")
    print("   - = Menos suavizado")
    print("\n🔧 INTERFAZ:")
    print("   • Panel superior: Estado del sistema")
    print("   • Panel lateral: Información técnica")
    print("   • Panel inferior: Gestos en tiempo real")
    print("="*60)
    
    # Configurar ventana
    cv2.namedWindow('Control por Gestos v2.0')
    cv2.moveWindow('Control por Gestos v2.0', 50, 50)
    
    # Configurar pyautogui
    pyautogui.PAUSE = 0.02
    
    # Intentar cargar calibración previa
    try:
        matriz_cargada = np.load("calibracion_matriz.npy")
        controlador.matriz_transformacion = matriz_cargada
        controlador.calibracion_completada = True
        logger.info("Calibración cargada desde archivo")
    except:
        logger.info("No se encontró archivo de calibración previo")
    
    # Bucle principal
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            print("Error al capturar el frame.")
            break
        
        # Voltear horizontalmente para visualización natural
        frame = cv2.flip(frame, 1)
        
        # Procesar frame
        frame_procesado, info_gesto = controlador.procesar_frame(frame)
        
        # Mostrar frame
        cv2.imshow('Control por Gestos v2.0', frame_procesado)
        
        # Gestionar teclas
        key = cv2.waitKey(1) & 0xFF
        
        if key == ord('q'):
            break
        elif key == ord('m'):
            if modo_actual == "pantalla":
                modo_actual = "mesa"
                controlador.cambiar_modo("mesa")
                print("🏠 Cambiado a modo: Mesa/Proyección")
            else:
                modo_actual = "pantalla"
                controlador.cambiar_modo("pantalla")
                print("🖥️  Cambiado a modo: Pantalla")
        elif key == ord('c'):
            if modo_actual == "mesa":
                print("🎯 Iniciando calibración manual...")
                controlador.iniciar_calibracion()
        elif key == ord('+') or key == ord('='):
            controlador.ajustar_suavizado(1)
        elif key == ord('-'):
            controlador.ajustar_suavizado(-1)
    
    # Liberar recursos
    cap.release()
    cv2.destroyAllWindows()
    logger.info("Programa terminado")


if __name__ == "__main__":
    main()
