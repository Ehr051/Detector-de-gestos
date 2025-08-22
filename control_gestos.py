#!/usr/bin/env python3
"""
Sistema Unificado de Control por Gestos - Versión Mejorada
===========================================================

Permite controlar el cursor y las acciones del mouse mediante gestos de las manos,
usando una cámara web o externa, para controlar PC o proyecciones/TV.

Características:
- Control de cursor con movimiento de mano
- Click izquierdo/arrastrar con pinza índice-pulgar  
- Click derecho con pinza pulgar-medio
- Zoom con dos puños
- Dos modos: Pantalla y Mesa (con calibración)
- Calibración para mapear área de gestos a proyección

Autor: Sistema de Control por Gestos
Versión: 2.0 Mejorada
"""

import cv2
import mediapipe as mp
import numpy as np
import time
import pyautogui
import sys
import os
import logging
from pathlib import Path

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('detector_gestos.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configurar pyautogui para mayor seguridad y rendimiento
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.01
pyautogui.FAILSAFE_POINTS = [(0, 0)]


class ControladorGestos:
    def __init__(self, modo="pantalla"):
        """
        Inicializa el controlador de gestos
        
        Args:
            modo (str): 'pantalla' para controlar el cursor del PC,
                       'mesa' para controlar la mesa de arena con cámara externa
        """
        self.modo = modo
        
        # Inicializar MediaPipe Hands con configuración optimizada
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.7,  # Aumentado para mayor precisión
            min_tracking_confidence=0.6    # Aumentado para mayor estabilidad
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
        
        # Suavizado de movimiento mejorado
        self.suavizado = 5
        self.historial_posiciones = []
        
        # Matriz de transformación para mapear coordenadas entre la cámara y proyección
        self.matriz_transformacion = np.eye(3)
        
        # Variables para calibración
        self.en_calibracion = False
        self.puntos_calibracion_camara = []
        self.calibracion_completada = False
        
        # Intentar cargar calibración previa
        self._cargar_calibracion_previa()
    
    def _cargar_calibracion_previa(self):
        """Carga calibración previa si existe"""
        try:
            calibration_file = Path("calibracion_matriz.npy")
            if calibration_file.exists():
                self.matriz_transformacion = np.load(calibration_file)
                self.calibracion_completada = True
                logger.info("Calibración previa cargada exitosamente")
        except Exception as e:
            logger.warning(f"No se pudo cargar calibración previa: {e}")
    
    def procesar_frame(self, frame):
        """
        Procesa un fotograma de la cámara y realiza las acciones correspondientes
        
        Args:
            frame: Imagen capturada de la cámara
            
        Returns:
            frame_procesado: Imagen con información visual sobre gestos
            info_gesto: Diccionario con información del gesto detectado
        """
        try:
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
            
        except Exception as e:
            logger.error(f"Error procesando frame: {e}")
            return frame, info_gesto
    
    def detectar_gestos_una_mano(self, puntos, frame, ancho, altura):
        """Detecta gestos realizados con una sola mano"""
        try:
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
                screen_x = int(np.interp(cursor_x, [100, ancho-100], [0, self.screen_width]))
                screen_y = int(np.interp(cursor_y, [100, altura-100], [0, self.screen_height]))
                
                # Aplicar suavizado mejorado
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
                        cv2.line(frame, self.punto_inicial_arrastre, posicion_cursor, (255, 0, 0), 2)
                else:
                    self.punto_inicial_arrastre = posicion_cursor
            else:
                self.punto_inicial_arrastre = None
            
            # Click derecho: pulgar y dedo medio juntos
            if distancia_pulgar_medio < 40:
                info_gesto['gesto'] = 'menu_contextual'
                cv2.circle(frame, medio_punta, 15, (0, 0, 255), -1)
                cv2.circle(frame, pulgar_punta, 15, (0, 0, 255), -1)
                cv2.line(frame, medio_punta, pulgar_punta, (0, 0, 255), 2)
                cv2.putText(frame, "Click Derecho", (50, 130), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            
            # Puño cerrado (para click o para zoom)
            if self._es_puño_cerrado(puntos):
                if not self.zoom_mode:
                    info_gesto['gesto'] = 'click'
                    cv2.circle(frame, palma, 30, (255, 255, 0), 2)
                    cv2.putText(frame, "Puño (Click)", (palma[0]-40, palma[1]-20), 
                              cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
            
            return info_gesto
            
        except Exception as e:
            logger.error(f"Error detectando gestos de una mano: {e}")
            return {
                'gesto': 'ninguno',
                'posicion': None,
                'datos_adicionales': {}
            }
    
    def detectar_gestos_dos_manos(self, results, frame, ancho, altura, info_gesto):
        """Detecta gestos realizados con dos manos, principalmente para zoom con puños cerrados"""
        try:
            self.punos_detectados = []
            puños_detectados_esta_vez = 0
            
            for hand_idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
                self.mp_drawing.draw_landmarks(
                    frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)
                
                puntos = []
                for landmark in hand_landmarks.landmark:
                    x, y = int(landmark.x * ancho), int(landmark.y * altura)
                    puntos.append((x, y))
                
                if self._es_puño_cerrado(puntos):
                    puños_detectados_esta_vez += 1
                    centro_palma = puntos[0]
                    self.punos_detectados.append(centro_palma)
                    
                    cv2.circle(frame, centro_palma, 30, (0, 0, 255), 3)
                    cv2.putText(frame, f"Puño {hand_idx+1}", 
                              (centro_palma[0]-20, centro_palma[1]-20), 
                              cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            cv2.putText(frame, f"Puños detectados: {puños_detectados_esta_vez}", 
                      (20, altura - 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            if len(self.punos_detectados) == 2:
                self._procesar_zoom(frame, altura, info_gesto)
            else:
                self._resetear_zoom()
                
        except Exception as e:
            logger.error(f"Error detectando gestos de dos manos: {e}")
    
    def _procesar_zoom(self, frame, altura, info_gesto):
        """Procesa el gesto de zoom con dos puños"""
        self.zoom_mode = True
        distancia_actual = self._calcular_distancia(self.punos_detectados[0], self.punos_detectados[1])
        
        if not self.haciendo_zoom:
            self.distancia_punos_inicial = distancia_actual
            self.haciendo_zoom = True
            cv2.putText(frame, "¡Zoom inicializado!", (20, altura - 110), 
                      cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        punto_medio = ((self.punos_detectados[0][0] + self.punos_detectados[1][0]) // 2,
                      (self.punos_detectados[0][1] + self.punos_detectados[1][1]) // 2)
        
        cv2.line(frame, self.punos_detectados[0], self.punos_detectados[1], (255, 128, 0), 3)
        
        if self.distancia_punos_inicial:
            factor_zoom = distancia_actual / self.distancia_punos_inicial
            
            cv2.putText(frame, f"Dist. inicial: {self.distancia_punos_inicial:.1f}, Actual: {distancia_actual:.1f}", 
                      (20, altura - 140), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            if distancia_actual > self.distancia_punos_inicial * 1.5:
                info_gesto['gesto'] = 'zoom_in'
                info_gesto['posicion'] = punto_medio
                info_gesto['datos_adicionales']['factor_zoom'] = factor_zoom
                cv2.putText(frame, f"ZOOM IN {factor_zoom:.2f}x", punto_medio, 
                          cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            elif distancia_actual < self.distancia_punos_inicial * 0.7:
                info_gesto['gesto'] = 'zoom_out'
                info_gesto['posicion'] = punto_medio
                info_gesto['datos_adicionales']['factor_zoom'] = factor_zoom
                cv2.putText(frame, f"ZOOM OUT {factor_zoom:.2f}x", punto_medio, 
                          cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
    
    def _resetear_zoom(self):
        """Resetea el estado de zoom"""
        self.zoom_mode = False
        self.haciendo_zoom = False
        self.distancia_punos_inicial = None
    
    def procesar_calibracion(self, frame):
        """Procesa el modo de calibración para mapear la cámara a la proyección/TV"""
        altura, ancho, _ = frame.shape
        
        puntos_proyeccion = [
            (0, 0),
            (self.screen_width, 0),
            (self.screen_width, self.screen_height),
            (0, self.screen_height)
        ]
        
        frame_visual = frame.copy()
        
        cv2.putText(frame_visual, "MODO CALIBRACION", 
                  (ancho//2 - 150, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        cv2.putText(frame_visual, "Toca cada punto con la punta de tu dedo indice", 
                  (ancho//2 - 250, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        
        punto_actual = len(self.puntos_calibracion_camara)
        nombres_puntos = ["Superior Izquierda", "Superior Derecha", "Inferior Derecha", "Inferior Izquierda"]
        
        for i, punto in enumerate(puntos_proyeccion):
            x = int(punto[0] * ancho / self.screen_width)
            y = int(punto[1] * altura / self.screen_height)
            x = max(50, min(x, ancho - 50))
            y = max(50, min(y, altura - 50))
            
            color = (0, 0, 255) if i == punto_actual else (128, 128, 128)
            cv2.circle(frame_visual, (x, y), 20, color, -1)
            
            if i == punto_actual:
                cv2.putText(frame_visual, f"Toca: {nombres_puntos[i]}", 
                          (x - 100, y - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        
        results = self.hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        
        if results.multi_hand_landmarks and punto_actual < 4:
            for hand_landmarks in results.multi_hand_landmarks:
                self.mp_drawing.draw_landmarks(frame_visual, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)
                
                indice_x = int(hand_landmarks.landmark[8].x * ancho)
                indice_y = int(hand_landmarks.landmark[8].y * altura)
                
                cv2.circle(frame_visual, (indice_x, indice_y), 5, (0, 255, 0), -1)
                
                x = int(puntos_proyeccion[punto_actual][0] * ancho / self.screen_width)
                y = int(puntos_proyeccion[punto_actual][1] * altura / self.screen_height)
                x = max(50, min(x, ancho - 50))
                y = max(50, min(y, altura - 50))
                
                distancia = np.sqrt((indice_x - x)**2 + (indice_y - y)**2)
                
                if distancia < 50:
                    cv2.putText(frame_visual, "¡Posición correcta! Espera...", 
                              (50, 120), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                    cv2.circle(frame_visual, (indice_x, indice_y), 30, (0, 255, 0), 2)
                    
                    cv2.imshow('Control por Gestos - Calibración', frame_visual)
                    cv2.waitKey(1)
                    
                    for i in range(3, 0, -1):
                        temp_frame = frame_visual.copy()
                        cv2.putText(temp_frame, f"Capturando en {i}...", 
                                  (50, 160), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                        cv2.imshow('Control por Gestos - Calibración', temp_frame)
                        cv2.waitKey(1000)
                    
                    self.puntos_calibracion_camara.append((indice_x, indice_y))
                    
                    temp_frame = frame_visual.copy()
                    cv2.putText(temp_frame, f"¡Punto {punto_actual+1} capturado!", 
                              (50, 160), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                    cv2.imshow('Control por Gestos - Calibración', temp_frame)
                    cv2.waitKey(1000)
                    
                    if len(self.puntos_calibracion_camara) == 4:
                        self.calibrar_mesa(self.puntos_calibracion_camara, puntos_proyeccion)
                        
                        temp_frame = frame_visual.copy()
                        cv2.putText(temp_frame, "¡Calibración completada!", 
                                  (ancho//2 - 150, altura//2), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                        cv2.imshow('Control por Gestos - Calibración', temp_frame)
                        cv2.waitKey(2000)
                        
                        return frame_visual, True
        
        if punto_actual > 0:
            cv2.putText(frame_visual, f"Puntos capturados: {punto_actual}/4", 
                      (ancho - 250, altura - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        
        return frame_visual, False
    
    def realizar_accion_mouse(self, info_gesto):
        """Ejecuta las acciones del mouse según el gesto detectado"""
        if info_gesto['posicion'] is None:
            return
        
        try:
            x, y = info_gesto['posicion']
            x = max(0, min(x, self.screen_width))
            y = max(0, min(y, self.screen_height))
            
            pyautogui.moveTo(x, y)
            
            if info_gesto['gesto'] == 'click':
                if not self.clicking:
                    logger.debug("Click izquierdo presionado")
                    pyautogui.mouseDown()
                    self.clicking = True
            elif info_gesto['gesto'] == 'arrastrar':
                if not self.dragging:
                    logger.debug("Iniciando arrastre")
                    self.dragging = True
            elif info_gesto['gesto'] == 'menu_contextual':
                if not self.right_clicking:
                    logger.debug("Click derecho")
                    pyautogui.rightClick()
                    self.right_clicking = True
            elif info_gesto['gesto'] == 'zoom_in':
                logger.debug("Zoom in")
                pyautogui.scroll(10)
            elif info_gesto['gesto'] == 'zoom_out':
                logger.debug("Zoom out")
                pyautogui.scroll(-10)
            else:
                if self.clicking or self.dragging:
                    logger.debug("Liberando click")
                    pyautogui.mouseUp()
                    self.clicking = False
                    self.dragging = False
                self.right_clicking = False
                
        except Exception as e:
            logger.error(f"Error en acción de mouse: {e}")
    
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
        logger.info("Iniciando calibración manual")
    
    def calibrar_mesa(self, puntos_camara, puntos_proyeccion):
        """Calibra la matriz de transformación entre la cámara y la proyección"""
        try:
            puntos_camara_np = np.array(puntos_camara, dtype=np.float32)
            puntos_proyeccion_np = np.array(puntos_proyeccion, dtype=np.float32)
            
            self.matriz_transformacion, _ = cv2.findHomography(
                puntos_camara_np, puntos_proyeccion_np, cv2.RANSAC, 5.0)
            
            np.save("calibracion_matriz.npy", self.matriz_transformacion)
            logger.info("Calibración completada y guardada")
            
        except Exception as e:
            logger.error(f"Error en calibración: {e}")
    
    def _transformar_coordenadas(self, punto):
        """Transforma coordenadas de la cámara al espacio de proyección"""
        try:
            punto_h = np.array([punto[0], punto[1], 1.0])
            punto_transformado = np.dot(self.matriz_transformacion, punto_h)
            
            if punto_transformado[2] != 0:
                punto_transformado = punto_transformado / punto_transformado[2]
            
            return (int(punto_transformado[0]), int(punto_transformado[1]))
        except Exception as e:
            logger.error(f"Error en transformación: {e}")
            return punto
    
    def _calcular_distancia(self, punto1, punto2):
        """Calcula la distancia euclidiana entre dos puntos"""
        return np.sqrt((punto1[0] - punto2[0])**2 + (punto1[1] - punto2[1])**2)
    
    def _es_puño_cerrado(self, puntos):
        """Detecta si la mano forma un puño cerrado"""
        try:
            punta_dedos = [puntos[8], puntos[12], puntos[16], puntos[20]]
            base_dedos = [puntos[5], puntos[9], puntos[13], puntos[17]]
            
            dedos_doblados = sum(1 for punta, base in zip(punta_dedos, base_dedos) if punta[1] > base[1])
            
            palma = puntos[0]
            puntas_cerca = sum(1 for punta in punta_dedos 
                             if self._calcular_distancia(punta, palma) < 
                             self._calcular_distancia(base_dedos[0], palma) * 1.3)
            
            return dedos_doblados >= 3 and puntas_cerca >= 3
        except Exception as e:
            logger.error(f"Error detectando puño: {e}")
            return False


def main():
    """Función principal del programa"""
    try:
        # Inicializar la cámara
        cap = cv2.VideoCapture(0)
        
        if not cap.isOpened():
            logger.error("No se pudo abrir la cámara.")
            return
        
        # Crear controlador de gestos
        controlador = ControladorGestos(modo="pantalla")
        modo_actual = "pantalla"
        
        # Mostrar información inicial
        print("\n" + "="*60)
        print("    SISTEMA UNIFICADO DE CONTROL POR GESTOS v2.0")
        print("="*60)
        print(f"Modo actual: {modo_actual.upper()}")
        print("\nGestos disponibles:")
        print("  • Mano abierta: Mover el cursor (el pulgar controla)")
        print("  • Pulgar + Índice: Click izquierdo / Arrastrar")
        print("  • Pulgar + Medio: Click derecho")
        print("  • Dos puños: Zoom (acercar/alejar según distancia)")
        print("\nControles:")
        print("  • 'q' - Salir del programa")
        print("  • 'm' - Cambiar entre modo pantalla/mesa")
        print("  • 'c' - Iniciar calibración manual (modo mesa)")
        print("\nNota: Mantén esta ventana en segundo plano para")
        print("      controlar otras aplicaciones.")
        print("="*60)
        
        # Configurar ventana
        cv2.namedWindow('Control por Gestos')
        cv2.moveWindow('Control por Gestos', 50, 50)
        
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cv2.resizeWindow('Control por Gestos', width//2, height//2)
        
        logger.info("Sistema iniciado correctamente")
        
        # Bucle principal
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                logger.error("Error al capturar el frame.")
                break
            
            # Voltear horizontalmente para una visualización más natural
            frame = cv2.flip(frame, 1)
            
            # Procesar frame
            frame_procesado, info_gesto = controlador.procesar_frame(frame)
            
            # Mostrar información del modo
            modo_texto = "PANTALLA" if modo_actual == "pantalla" else "MESA"
            calibracion_texto = ""
            if modo_actual == "mesa":
                calibracion_texto = " - CALIBRADO" if controlador.calibracion_completada else " - SIN CALIBRAR"
            
            cv2.putText(frame_procesado, f"Modo: {modo_texto}{calibracion_texto}", 
                      (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 155, 255), 2)
            
            # Redimensionar y mostrar
            frame_mostrar = cv2.resize(frame_procesado, (width//2, height//2))
            cv2.imshow('Control por Gestos', frame_mostrar)
            
            # Procesar teclas
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q'):
                logger.info("Saliendo del programa")
                break
            elif key == ord('m'):
                if modo_actual == "pantalla":
                    modo_actual = "mesa"
                    controlador.cambiar_modo("mesa")
                    print("Cambiado a modo: MESA")
                else:
                    modo_actual = "pantalla"
                    controlador.cambiar_modo("pantalla")
                    print("Cambiado a modo: PANTALLA")
            elif key == ord('c'):
                if modo_actual == "mesa":
                    controlador.iniciar_calibracion()
                    print("Iniciando calibración manual...")
        
        # Limpiar recursos
        cap.release()
        cv2.destroyAllWindows()
        logger.info("Programa finalizado correctamente")
        
    except KeyboardInterrupt:
        logger.info("Programa interrumpido por el usuario")
    except Exception as e:
        logger.error(f"Error en función principal: {e}")
    finally:
        # Asegurar limpieza de recursos
        try:
            cap.release()
            cv2.destroyAllWindows()
        except:
            pass


if __name__ == "__main__":
    main()
