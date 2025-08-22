#!/usr/bin/env python3
"""
Sistema Unificado de Control por Gestos - Versión Optimizada
============================================================

Permite controlar el cursor y las acciones del mouse mediante gestos de las manos,
usando una cámara web o externa, para controlar PC o proyecciones/TV.

Autor: Sistema de Control por Gestos
Versión: 2.0
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
from pathlib import Path
from typing import Tuple, Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('detector_gestos.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ModoOperacion(Enum):
    """Modos de operación del sistema"""
    PANTALLA = "pantalla"
    MESA = "mesa"

class TipoGesto(Enum):
    """Tipos de gestos reconocidos"""
    NINGUNO = "ninguno"
    CLICK = "click"
    ARRASTRAR = "arrastrar"
    MENU_CONTEXTUAL = "menu_contextual"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"

@dataclass
class ConfiguracionSistema:
    """Configuración del sistema"""
    # Detección
    min_detection_confidence: float = 0.7
    min_tracking_confidence: float = 0.5
    max_num_hands: int = 2
    
    # Gestos
    distancia_pinza: int = 40
    factor_zoom_in: float = 1.5
    factor_zoom_out: float = 0.7
    suavizado_movimiento: int = 5
    
    # Calibración
    distancia_calibracion: int = 50
    tiempo_captura: int = 3
    
    # Ventana
    resize_factor: float = 0.5
    window_pos_x: int = 50
    window_pos_y: int = 50
    
    # PyAutoGUI
    pause_time: float = 0.01
    fail_safe: bool = True

@dataclass
class InfoGesto:
    """Información de un gesto detectado"""
    tipo: TipoGesto
    posicion: Optional[Tuple[int, int]]
    datos_adicionales: Dict[str, Any]

class ControladorGestos:
    """Controlador principal para detección y procesamiento de gestos"""
    
    def __init__(self, modo: ModoOperacion = ModoOperacion.PANTALLA, config: ConfiguracionSistema = None):
        """
        Inicializa el controlador de gestos
        
        Args:
            modo: Modo de operación (PANTALLA o MESA)
            config: Configuración del sistema
        """
        self.modo = modo
        self.config = config or ConfiguracionSistema()
        
        # Configurar PyAutoGUI
        pyautogui.FAILSAFE = self.config.fail_safe
        pyautogui.PAUSE = self.config.pause_time
        pyautogui.FAILSAFE_POINTS = [(0, 0)]
        
        # Inicializar MediaPipe
        self._inicializar_mediapipe()
        
        # Obtener información de pantalla
        self.screen_width, self.screen_height = pyautogui.size()
        logger.info(f"Resolución de pantalla: {self.screen_width}x{self.screen_height}")
        
        # Estados del sistema
        self._inicializar_estados()
        
        # Calibración
        self._inicializar_calibracion()
        
        logger.info(f"Controlador inicializado en modo {modo.value}")
    
    def _inicializar_mediapipe(self):
        """Inicializa MediaPipe Hands"""
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=self.config.max_num_hands,
            min_detection_confidence=self.config.min_detection_confidence,
            min_tracking_confidence=self.config.min_tracking_confidence
        )
        self.mp_drawing = mp.solutions.drawing_utils
    
    def _inicializar_estados(self):
        """Inicializa los estados del sistema"""
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
        self.historial_posiciones = []
    
    def _inicializar_calibracion(self):
        """Inicializa variables de calibración"""
        self.matriz_transformacion = np.eye(3)
        self.en_calibracion = False
        self.puntos_calibracion_camara = []
        self.calibracion_completada = False
        
        # Intentar cargar calibración existente
        self._cargar_calibracion()
    
    def _cargar_calibracion(self):
        """Carga calibración previa si existe"""
        try:
            calibration_file = Path("calibracion_matriz.npy")
            if calibration_file.exists():
                self.matriz_transformacion = np.load(calibration_file)
                self.calibracion_completada = True
                logger.info("Calibración cargada desde archivo")
        except Exception as e:
            logger.warning(f"No se pudo cargar calibración: {e}")
    
    def _guardar_calibracion(self):
        """Guarda la calibración actual"""
        try:
            np.save("calibracion_matriz.npy", self.matriz_transformacion)
            logger.info("Calibración guardada exitosamente")
        except Exception as e:
            logger.error(f"Error al guardar calibración: {e}")
    
    def procesar_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, InfoGesto]:
        """
        Procesa un fotograma y detecta gestos
        
        Args:
            frame: Imagen de la cámara
            
        Returns:
            Tupla con (frame_procesado, info_gesto)
        """
        try:
            # Procesar calibración si está activa
            if self.en_calibracion and self.modo == ModoOperacion.MESA:
                return self._procesar_calibracion(frame)
            
            # Convertir a RGB para MediaPipe
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            altura, ancho = frame.shape[:2]
            
            # Procesar con MediaPipe
            results = self.hands.process(frame_rgb)
            
            # Crear frame visual
            frame_visual = frame.copy()
            
            # Detectar gestos
            info_gesto = self._detectar_gestos(results, frame_visual, ancho, altura)
            
            # Aplicar acciones si es modo pantalla
            if self.modo == ModoOperacion.PANTALLA and info_gesto.posicion:
                self._realizar_accion_mouse(info_gesto)
            
            return frame_visual, info_gesto
            
        except Exception as e:
            logger.error(f"Error procesando frame: {e}")
            return frame, InfoGesto(TipoGesto.NINGUNO, None, {})
    
    def _detectar_gestos(self, results, frame: np.ndarray, ancho: int, altura: int) -> InfoGesto:
        """Detecta gestos en el frame"""
        info_gesto = InfoGesto(TipoGesto.NINGUNO, None, {})
        
        if not results.multi_hand_landmarks:
            return info_gesto
        
        # Detectar gestos con dos manos (zoom)
        if len(results.multi_hand_landmarks) == 2:
            self._detectar_gestos_dos_manos(results, frame, ancho, altura, info_gesto)
            if info_gesto.tipo in [TipoGesto.ZOOM_IN, TipoGesto.ZOOM_OUT]:
                return info_gesto
        
        # Detectar gestos con una mano
        if results.multi_hand_landmarks:
            hand_landmarks = results.multi_hand_landmarks[0]
            
            # Dibujar landmarks
            self.mp_drawing.draw_landmarks(
                frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)
            
            # Extraer puntos
            puntos = self._extraer_puntos(hand_landmarks, ancho, altura)
            
            # Detectar gestos
            info_gesto = self._detectar_gestos_una_mano(puntos, frame, ancho, altura)
        
        return info_gesto
    
    def _extraer_puntos(self, hand_landmarks, ancho: int, altura: int) -> List[Tuple[int, int]]:
        """Extrae puntos de los landmarks de la mano"""
        puntos = []
        for landmark in hand_landmarks.landmark:
            x, y = int(landmark.x * ancho), int(landmark.y * altura)
            puntos.append((x, y))
        return puntos
    
    def _detectar_gestos_una_mano(self, puntos: List[Tuple[int, int]], frame: np.ndarray, 
                                 ancho: int, altura: int) -> InfoGesto:
        """Detecta gestos con una sola mano"""
        # Puntos clave de la mano
        indice_punta = puntos[8]
        pulgar_punta = puntos[4]
        medio_punta = puntos[12]
        palma = puntos[0]
        
        # Calcular distancias
        distancia_pulgar_indice = self._calcular_distancia(pulgar_punta, indice_punta)
        distancia_pulgar_medio = self._calcular_distancia(pulgar_punta, medio_punta)
        
        # Calcular posición del cursor
        posicion_cursor = self._calcular_posicion_cursor(pulgar_punta, ancho, altura)
        
        # Información base del gesto
        info_gesto = InfoGesto(TipoGesto.NINGUNO, posicion_cursor, {'puntos_mano': puntos})
        
        # Dibujar cursor
        cv2.circle(frame, pulgar_punta, 10, (0, 255, 0), -1)
        
        # Detectar tipos de gesto
        if distancia_pulgar_indice < self.config.distancia_pinza:
            info_gesto.tipo = TipoGesto.CLICK
            self._dibujar_pinza(frame, indice_punta, pulgar_punta, "Click", (255, 0, 0))
            
            # Detectar arrastre
            if self.dragging or self.clicking:
                info_gesto.tipo = TipoGesto.ARRASTRAR
                cv2.putText(frame, "Arrastrando", (50, 90), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
                if self.punto_inicial_arrastre:
                    info_gesto.datos_adicionales['punto_inicial'] = self.punto_inicial_arrastre
                    cv2.line(frame, self.punto_inicial_arrastre, posicion_cursor, (255, 0, 0), 2)
            else:
                self.punto_inicial_arrastre = posicion_cursor
        else:
            self.punto_inicial_arrastre = None
        
        if distancia_pulgar_medio < self.config.distancia_pinza:
            info_gesto.tipo = TipoGesto.MENU_CONTEXTUAL
            self._dibujar_pinza(frame, medio_punta, pulgar_punta, "Click Derecho", (0, 0, 255))
        
        # Detectar puño
        if self._es_puño_cerrado(puntos) and not self.zoom_mode:
            info_gesto.tipo = TipoGesto.CLICK
            cv2.circle(frame, palma, 30, (255, 255, 0), 2)
            cv2.putText(frame, "Puño (Click)", (palma[0]-40, palma[1]-20), 
                      cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        
        # Mostrar coordenadas
        self._mostrar_coordenadas(frame, posicion_cursor, ancho)
        
        return info_gesto
    
    def _calcular_posicion_cursor(self, pulgar_punta: Tuple[int, int], ancho: int, altura: int) -> Tuple[int, int]:
        """Calcula la posición del cursor basada en el pulgar"""
        if self.modo == ModoOperacion.PANTALLA:
            cursor_x, cursor_y = pulgar_punta
            
            # Mapear a coordenadas de pantalla
            screen_x = int(np.interp(cursor_x, [100, ancho-100], [0, self.screen_width]))
            screen_y = int(np.interp(cursor_y, [100, altura-100], [0, self.screen_height]))
            
            # Aplicar suavizado
            self.historial_posiciones.append((screen_x, screen_y))
            if len(self.historial_posiciones) > self.config.suavizado_movimiento:
                self.historial_posiciones.pop(0)
            
            suavizado_x = int(sum(p[0] for p in self.historial_posiciones) / len(self.historial_posiciones))
            suavizado_y = int(sum(p[1] for p in self.historial_posiciones) / len(self.historial_posiciones))
            
            return (suavizado_x, suavizado_y)
        else:
            # Modo mesa con transformación si está calibrado
            if self.calibracion_completada:
                return self._transformar_coordenadas(pulgar_punta)
            else:
                return pulgar_punta
    
    def _dibujar_pinza(self, frame: np.ndarray, punto1: Tuple[int, int], punto2: Tuple[int, int], 
                      texto: str, color: Tuple[int, int, int]):
        """Dibuja indicadores visuales para gestos de pinza"""
        cv2.circle(frame, punto1, 15, color, -1)
        cv2.circle(frame, punto2, 15, color, -1)
        cv2.line(frame, punto1, punto2, color, 2)
        cv2.putText(frame, texto, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
    
    def _mostrar_coordenadas(self, frame: np.ndarray, posicion: Tuple[int, int], ancho: int):
        """Muestra las coordenadas en el frame"""
        if self.modo == ModoOperacion.PANTALLA:
            cv2.putText(frame, f"Pos: {posicion[0]}, {posicion[1]}", 
                      (ancho - 250, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        else:
            if self.calibracion_completada:
                cv2.putText(frame, f"Transf: {posicion[0]}, {posicion[1]}", 
                          (ancho - 250, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    
    def _detectar_gestos_dos_manos(self, results, frame: np.ndarray, ancho: int, altura: int, info_gesto: InfoGesto):
        """Detecta gestos con dos manos (principalmente zoom)"""
        self.punos_detectados = []
        puños_detectados_esta_vez = 0
        
        for hand_idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
            self.mp_drawing.draw_landmarks(frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)
            
            puntos = self._extraer_puntos(hand_landmarks, ancho, altura)
            
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
    
    def _procesar_zoom(self, frame: np.ndarray, altura: int, info_gesto: InfoGesto):
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
            
            if distancia_actual > self.distancia_punos_inicial * self.config.factor_zoom_in:
                info_gesto.tipo = TipoGesto.ZOOM_IN
                info_gesto.posicion = punto_medio
                info_gesto.datos_adicionales['factor_zoom'] = factor_zoom
                cv2.putText(frame, f"ZOOM IN {factor_zoom:.2f}x", punto_medio, 
                          cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            elif distancia_actual < self.distancia_punos_inicial * self.config.factor_zoom_out:
                info_gesto.tipo = TipoGesto.ZOOM_OUT
                info_gesto.posicion = punto_medio
                info_gesto.datos_adicionales['factor_zoom'] = factor_zoom
                cv2.putText(frame, f"ZOOM OUT {factor_zoom:.2f}x", punto_medio, 
                          cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
    
    def _resetear_zoom(self):
        """Resetea el estado de zoom"""
        self.zoom_mode = False
        self.haciendo_zoom = False
        self.distancia_punos_inicial = None
    
    def _procesar_calibracion(self, frame: np.ndarray) -> Tuple[np.ndarray, InfoGesto]:
        """Procesa el modo de calibración"""
        altura, ancho = frame.shape[:2]
        
        puntos_proyeccion = [
            (0, 0),
            (self.screen_width, 0),
            (self.screen_width, self.screen_height),
            (0, self.screen_height)
        ]
        
        frame_visual = frame.copy()
        
        # Dibujar instrucciones
        cv2.putText(frame_visual, "MODO CALIBRACION", 
                  (ancho//2 - 150, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        cv2.putText(frame_visual, "Toca cada punto con la punta de tu dedo indice", 
                  (ancho//2 - 250, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        
        punto_actual = len(self.puntos_calibracion_camara)
        nombres_puntos = ["Superior Izquierda", "Superior Derecha", "Inferior Derecha", "Inferior Izquierda"]
        
        # Dibujar puntos de calibración
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
        
        # Detectar punto de calibración
        calibracion_finalizada = self._capturar_punto_calibracion(frame, frame_visual, puntos_proyeccion, punto_actual, ancho, altura)
        
        info_gesto = InfoGesto(TipoGesto.NINGUNO, None, {})
        return frame_visual, info_gesto if not calibracion_finalizada else info_gesto
    
    def _capturar_punto_calibracion(self, frame: np.ndarray, frame_visual: np.ndarray, 
                                   puntos_proyeccion: List[Tuple[int, int]], punto_actual: int, 
                                   ancho: int, altura: int) -> bool:
        """Captura un punto de calibración"""
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
                
                if distancia < self.config.distancia_calibracion:
                    return self._ejecutar_captura_punto(frame_visual, indice_x, indice_y, punto_actual, puntos_proyeccion)
        
        if punto_actual > 0:
            cv2.putText(frame_visual, f"Puntos capturados: {punto_actual}/4", 
                      (ancho - 250, altura - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        
        return False
    
    def _ejecutar_captura_punto(self, frame_visual: np.ndarray, indice_x: int, indice_y: int, 
                               punto_actual: int, puntos_proyeccion: List[Tuple[int, int]]) -> bool:
        """Ejecuta la captura de un punto con cuenta regresiva"""
        cv2.putText(frame_visual, "¡Posición correcta! Espera...", 
                  (50, 120), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.circle(frame_visual, (indice_x, indice_y), 30, (0, 255, 0), 2)
        
        cv2.imshow('Control por Gestos - Calibración', frame_visual)
        cv2.waitKey(1)
        
        for i in range(self.config.tiempo_captura, 0, -1):
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
            self._calibrar_mesa(self.puntos_calibracion_camara, puntos_proyeccion)
            return True
        
        return False
    
    def _realizar_accion_mouse(self, info_gesto: InfoGesto):
        """Ejecuta acciones del mouse según el gesto"""
        if not info_gesto.posicion:
            return
        
        try:
            x, y = info_gesto.posicion
            x = max(0, min(x, self.screen_width))
            y = max(0, min(y, self.screen_height))
            
            pyautogui.moveTo(x, y)
            
            if info_gesto.tipo == TipoGesto.CLICK:
                if not self.clicking:
                    logger.debug("Click izquierdo presionado")
                    pyautogui.mouseDown()
                    self.clicking = True
            elif info_gesto.tipo == TipoGesto.ARRASTRAR:
                if not self.dragging:
                    logger.debug("Iniciando arrastre")
                    self.dragging = True
            elif info_gesto.tipo == TipoGesto.MENU_CONTEXTUAL:
                if not self.right_clicking:
                    logger.debug("Click derecho")
                    pyautogui.rightClick()
                    self.right_clicking = True
            elif info_gesto.tipo == TipoGesto.ZOOM_IN:
                logger.debug("Zoom in")
                pyautogui.scroll(10)
            elif info_gesto.tipo == TipoGesto.ZOOM_OUT:
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
    
    def cambiar_modo(self, nuevo_modo: ModoOperacion):
        """Cambia el modo de operación"""
        if self.modo != nuevo_modo:
            self.modo = nuevo_modo
            self._reiniciar_estados()
            
            if nuevo_modo == ModoOperacion.MESA and not self.calibracion_completada:
                self.iniciar_calibracion()
            
            logger.info(f"Modo cambiado a: {nuevo_modo.value}")
    
    def _reiniciar_estados(self):
        """Reinicia los estados del controlador"""
        self.clicking = False
        self.right_clicking = False
        self.dragging = False
        self.punto_inicial_arrastre = None
        self.zoom_mode = False
        self.haciendo_zoom = False
        self.historial_posiciones = []
    
    def iniciar_calibracion(self):
        """Inicia el proceso de calibración"""
        self.en_calibracion = True
        self.puntos_calibracion_camara = []
        logger.info("Iniciando calibración manual")
    
    def _calibrar_mesa(self, puntos_camara: List[Tuple[int, int]], puntos_proyeccion: List[Tuple[int, int]]):
        """Calibra la mesa calculando la matriz de homografía"""
        try:
            puntos_camara_np = np.array(puntos_camara, dtype=np.float32)
            puntos_proyeccion_np = np.array(puntos_proyeccion, dtype=np.float32)
            
            self.matriz_transformacion, _ = cv2.findHomography(
                puntos_camara_np, puntos_proyeccion_np, cv2.RANSAC, 5.0)
            
            self.calibracion_completada = True
            self._guardar_calibracion()
            
            logger.info("Calibración completada exitosamente")
            
        except Exception as e:
            logger.error(f"Error en calibración: {e}")
    
    def _transformar_coordenadas(self, punto: Tuple[int, int]) -> Tuple[int, int]:
        """Transforma coordenadas usando la matriz de calibración"""
        try:
            punto_h = np.array([punto[0], punto[1], 1.0])
            punto_transformado = np.dot(self.matriz_transformacion, punto_h)
            
            if punto_transformado[2] != 0:
                punto_transformado = punto_transformado / punto_transformado[2]
            
            return (int(punto_transformado[0]), int(punto_transformado[1]))
        except Exception as e:
            logger.error(f"Error en transformación de coordenadas: {e}")
            return punto
    
    def _calcular_distancia(self, punto1: Tuple[int, int], punto2: Tuple[int, int]) -> float:
        """Calcula distancia euclidiana entre dos puntos"""
        return np.sqrt((punto1[0] - punto2[0])**2 + (punto1[1] - punto2[1])**2)
    
    def _es_puño_cerrado(self, puntos: List[Tuple[int, int]]) -> bool:
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


class SistemaControl:
    """Sistema principal de control por gestos"""
    
    def __init__(self, config: ConfiguracionSistema = None):
        """Inicializa el sistema de control"""
        self.config = config or ConfiguracionSistema()
        self.controlador = ControladorGestos(ModoOperacion.PANTALLA, self.config)
        self.cap = None
        self.ejecutando = False
        
        logger.info("Sistema de control inicializado")
    
    def inicializar_camara(self, device_id: int = 0) -> bool:
        """Inicializa la cámara"""
        try:
            self.cap = cv2.VideoCapture(device_id)
            if not self.cap.isOpened():
                logger.error("No se pudo abrir la cámara")
                return False
            
            logger.info(f"Cámara {device_id} inicializada correctamente")
            return True
        except Exception as e:
            logger.error(f"Error inicializando cámara: {e}")
            return False
    
    def configurar_ventana(self):
        """Configura la ventana de visualización"""
        try:
            cv2.namedWindow('Control por Gestos')
            cv2.moveWindow('Control por Gestos', self.config.window_pos_x, self.config.window_pos_y)
            
            if self.cap:
                width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                new_width = int(width * self.config.resize_factor)
                new_height = int(height * self.config.resize_factor)
                cv2.resizeWindow('Control por Gestos', new_width, new_height)
        except Exception as e:
            logger.error(f"Error configurando ventana: {e}")
    
    def mostrar_info_inicial(self):
        """Muestra información inicial del sistema"""
        print("\n" + "="*60)
        print("    SISTEMA UNIFICADO DE CONTROL POR GESTOS v2.0")
        print("="*60)
        print(f"Modo actual: {self.controlador.modo.value.upper()}")
        print("\nGestos disponibles:")
        print("  • Mano abierta: Mover el cursor (el pulgar controla)")
        print("  • Pulgar + Índice: Click izquierdo / Arrastrar")
        print("  • Pulgar + Medio: Click derecho")
        print("  • Dos puños: Zoom (acercar/alejar según distancia)")
        print("\nControles de teclado:")
        print("  • 'q' - Salir del programa")
        print("  • 'm' - Cambiar entre modo pantalla/mesa")
        print("  • 'c' - Iniciar calibración manual (modo mesa)")
        print("\nNota: Mantén esta ventana en segundo plano para")
        print("      controlar otras aplicaciones.")
        print("="*60)
    
    def ejecutar(self):
        """Ejecuta el bucle principal del sistema"""
        if not self.inicializar_camara():
            return
        
        self.configurar_ventana()
        self.mostrar_info_inicial()
        
        self.ejecutando = True
        
        try:
            while self.ejecutando and self.cap.isOpened():
                ret, frame = self.cap.read()
                if not ret:
                    logger.error("Error capturando frame")
                    break
                
                # Voltear horizontalmente para visualización natural
                frame = cv2.flip(frame, 1)
                
                # Procesar frame
                frame_procesado, info_gesto = self.controlador.procesar_frame(frame)
                
                # Añadir información del modo
                self._dibujar_info_sistema(frame_procesado)
                
                # Redimensionar y mostrar
                frame_mostrar = cv2.resize(frame_procesado, 
                                         (int(frame_procesado.shape[1] * self.config.resize_factor),
                                          int(frame_procesado.shape[0] * self.config.resize_factor)))
                
                cv2.imshow('Control por Gestos', frame_mostrar)
                
                # Procesar teclas
                if not self._procesar_teclas():
                    break
                    
        except KeyboardInterrupt:
            logger.info("Interrupción por teclado")
        except Exception as e:
            logger.error(f"Error en bucle principal: {e}")
        finally:
            self.finalizar()
    
    def _dibujar_info_sistema(self, frame: np.ndarray):
        """Dibuja información del sistema en el frame"""
        modo_texto = "PANTALLA" if self.controlador.modo == ModoOperacion.PANTALLA else "MESA"
        calibracion_texto = ""
        
        if self.controlador.modo == ModoOperacion.MESA:
            calibracion_texto = " - CALIBRADO" if self.controlador.calibracion_completada else " - SIN CALIBRAR"
        
        cv2.putText(frame, f"Modo: {modo_texto}{calibracion_texto}", 
                  (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 155, 255), 2)
    
    def _procesar_teclas(self) -> bool:
        """Procesa las teclas presionadas"""
        key = cv2.waitKey(1) & 0xFF
        
        if key == ord('q'):
            logger.info("Saliendo del programa")
            return False
        elif key == ord('m'):
            nuevo_modo = (ModoOperacion.MESA if self.controlador.modo == ModoOperacion.PANTALLA 
                         else ModoOperacion.PANTALLA)
            self.controlador.cambiar_modo(nuevo_modo)
            print(f"Cambiado a modo: {nuevo_modo.value.upper()}")
        elif key == ord('c'):
            if self.controlador.modo == ModoOperacion.MESA:
                self.controlador.iniciar_calibracion()
                print("Iniciando calibración manual...")
        
        return True
    
    def finalizar(self):
        """Finaliza el sistema liberando recursos"""
        self.ejecutando = False
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()
        logger.info("Sistema finalizado correctamente")


def main():
    """Función principal"""
    try:
        # Crear configuración personalizada si es necesario
        config = ConfiguracionSistema()
        
        # Crear y ejecutar sistema
        sistema = SistemaControl(config)
        sistema.ejecutar()
        
    except Exception as e:
        logger.error(f"Error en función principal: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
