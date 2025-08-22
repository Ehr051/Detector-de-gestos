#!/usr/bin/env python3
"""
Sistema Unificado de Control por Gestos - Versión Definitiva
===========================================================

Combina la arquitectura moderna de DetectorGestosOptimizado.py 
con todas las características avanzadas de control_gestos.py

Características principales:
- Arquitectura moderna con dataclasses y enums
- Control de cursor completo con gestos de manos
- Doble click automático
- Interfaz compacta y configurable
- Calibración automática mejorada  
- Dos modos: pantalla y mesa (con calibración)
- Logging avanzado y configuración optimizada

Autor: Sistema de Control por Gestos
Versión: 3.0 (Definitiva)
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

# Configurar pyautogui para que sea seguro y funcione correctamente
pyautogui.PAUSE = 0.01
pyautogui.FAILSAFE_POINTS = [(0, 0)]  # Solo esquina superior izquierda como punto de seguridad

# ================================
# CLASES Y TIPOS DE DATOS
# ================================

class ModoOperacion(Enum):
    """Modos de operación del sistema"""
    PANTALLA = "pantalla"
    MESA = "mesa"

class TipoGesto(Enum):
    """Tipos de gestos reconocidos"""
    CURSOR = "cursor"
    CLICK_IZQUIERDO = "click_izquierdo"
    DOBLE_CLICK = "doble_click"
    CLICK_DERECHO = "click_derecho"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    NINGUNO = "ninguno"

@dataclass
class ConfiguracionSistema:
    """Configuración del sistema con valores por defecto"""
    # Detección
    min_detection_confidence: float = 0.7
    min_tracking_confidence: float = 0.5
    max_num_hands: int = 2
    
    # Gestos
    distancia_pinza: int = 40
    factor_zoom_in: float = 1.5
    factor_zoom_out: float = 0.7
    suavizado_movimiento: int = 5
    doble_click_ventana: float = 0.5
    tiempo_calibracion: float = 3.0
    
    # Interfaz
    mostrar_por_defecto: bool = True
    color_primario: Tuple[int, int, int] = (0, 255, 0)
    color_secundario: Tuple[int, int, int] = (255, 255, 0)
    color_error: Tuple[int, int, int] = (0, 0, 255)

@dataclass
class InfoGesto:
    """Información sobre un gesto detectado"""
    gesto: TipoGesto
    posicion: Optional[Tuple[int, int]] = None
    confianza: float = 0.0
    metadatos: Dict[str, Any] = None

class DetectorGestos:
    """
    Detector de gestos principal que combina lo mejor de ambas versiones
    """
    
    def __init__(self, modo: str = "pantalla"):
        """
        Inicializa el detector de gestos
        
        Args:
            modo: 'pantalla' para control directo de PC, 'mesa' para proyecciones
        """
        self.modo = ModoOperacion(modo)
        
        # Cargar configuración
        self.config = self._cargar_configuracion()
        self.configuracion = ConfiguracionSistema(**self.config.get('sistema', {}))
        
        # Inicializar MediaPipe Hands
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=self.configuracion.max_num_hands,
            min_detection_confidence=self.configuracion.min_detection_confidence,
            min_tracking_confidence=self.configuracion.min_tracking_confidence
        )
        self.mp_drawing = mp.solutions.drawing_utils
        
        # Obtener tamaño de la pantalla
        self.ancho_pantalla, self.alto_pantalla = pyautogui.size()
        logger.info(f"Resolución de pantalla: {self.ancho_pantalla}x{self.alto_pantalla}")
        
        # Variables de estado para gestos
        self.cursor_x, self.cursor_y = 0, 0
        self.arrastrando = False
        self.ultimo_click_tiempo = 0
        self.click_count = 0
        self.gesto_anterior = TipoGesto.NINGUNO
        self.tiempo_gesto_anterior = time.time()
        
        # Variables para zoom con dos puños
        self.zoom_activo = False
        self.distancia_puños_anterior = 0
        self.zoom_base = 1.0
        self.cooldown_zoom = 0
        
        # Suavizado de movimiento
        self.historial_x = []
        self.historial_y = []
        self.suavizado = self.configuracion.suavizado_movimiento
        
        # Matriz de transformación para mapear coordenadas entre la cámara y proyección
        self.matriz_transformacion = np.eye(3)  # Identidad por defecto
        
        # Variables para calibración mejorada
        self.calibrando = False
        self.puntos_camara = []
        self.puntos_proyeccion = []
        self.esquina_actual = 0
        self.tiempo_en_punto = 0
        self.tiempo_requerido_calibracion = self.configuracion.tiempo_calibracion
        self.punto_calibracion_activo = False
        
        # Variables para la interfaz
        self.ultimo_gesto = TipoGesto.NINGUNO
        self.tiempo_gesto = time.time()
        self.mostrar_interfaz = self.configuracion.mostrar_por_defecto
        self.interfaz_compacta = False  # Modo compacto
        
        # Variables para doble click
        self.doble_click_ventana = self.configuracion.doble_click_ventana
        
        logger.info(f"Detector de gestos inicializado en modo: {modo}")
    
    def _cargar_configuracion(self) -> Dict[str, Any]:
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
                    "suavizado_movimiento": 5,
                    "doble_click_ventana": 0.5,
                    "tiempo_calibracion": 3.0
                },
                "interfaz": {
                    "mostrar_por_defecto": True
                },
                "sistema": {}
            }
    
    def alternar_interfaz(self):
        """Alterna entre mostrar y ocultar la interfaz"""
        self.mostrar_interfaz = not self.mostrar_interfaz
        estado = "visible" if self.mostrar_interfaz else "oculta"
        logger.info(f"Interfaz {estado}")
    
    def alternar_modo_compacto(self):
        """Alterna entre modo interfaz normal y compacta"""
        self.interfaz_compacta = not self.interfaz_compacta
        modo = "compacta" if self.interfaz_compacta else "completa"
        logger.info(f"Interfaz {modo}")
    
    def dibujar_interfaz_principal(self, frame: np.ndarray) -> np.ndarray:
        """Dibuja la interfaz principal del sistema"""
        if not self.mostrar_interfaz:
            return frame
            
        altura, ancho = frame.shape[:2]
        
        # Botón para mostrar/ocultar interfaz (siempre visible)
        boton_x, boton_y = ancho - 80, 10
        boton_ancho, boton_alto = 70, 30
        
        # Dibujar botón
        cv2.rectangle(frame, (boton_x, boton_y), (boton_x + boton_ancho, boton_y + boton_alto), 
                     self.configuracion.color_secundario, -1)
        cv2.rectangle(frame, (boton_x, boton_y), (boton_x + boton_ancho, boton_y + boton_alto), 
                     (0, 0, 0), 2)
        
        texto_boton = "OCULTAR" if self.mostrar_interfaz else "MOSTRAR"
        cv2.putText(frame, texto_boton, (boton_x + 5, boton_y + 20), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
        
        if self.interfaz_compacta:
            self._dibujar_interfaz_compacta(frame)
        else:
            self._dibujar_interfaz_completa(frame)
        
        return frame
    
    def _dibujar_interfaz_compacta(self, frame: np.ndarray):
        """Dibuja una interfaz compacta para presentaciones"""
        altura, ancho = frame.shape[:2]
        
        # Panel compacto en la parte superior
        panel_alto = 60
        cv2.rectangle(frame, (0, 0), (ancho, panel_alto), (0, 0, 0), -1)
        cv2.rectangle(frame, (0, 0), (ancho, panel_alto), self.configuracion.color_primario, 2)
        
        # Información básica
        info_texto = f"Modo: {self.modo.value.title()} | Gesto: {self.ultimo_gesto.value.replace('_', ' ').title()}"
        cv2.putText(frame, info_texto, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, 
                   self.configuracion.color_secundario, 2)
        
        # Estado de calibración si aplica
        if self.modo == ModoOperacion.MESA:
            estado_cal = "Calibrado" if len(self.puntos_camara) >= 4 else "Sin calibrar"
            cv2.putText(frame, f"Calibracion: {estado_cal}", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.5, self.configuracion.color_secundario, 1)
    
    def _dibujar_interfaz_completa(self, frame: np.ndarray):
        """Dibuja la interfaz completa con todos los controles"""
        altura, ancho = frame.shape[:2]
        
        # Panel superior - Información del sistema
        panel_alto = 120
        cv2.rectangle(frame, (0, 0), (ancho, panel_alto), (0, 0, 0), -1)
        cv2.rectangle(frame, (0, 0), (ancho, panel_alto), self.configuracion.color_primario, 2)
        
        # Título principal
        cv2.putText(frame, "DETECTOR DE GESTOS v3.0", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 
                   1, self.configuracion.color_secundario, 2)
        
        # Modo actual
        cv2.putText(frame, f"Modo: {self.modo.value.upper()}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 
                   0.7, self.configuracion.color_secundario, 2)
        
        # Gesto actual
        gesto_texto = self.ultimo_gesto.value.replace('_', ' ').title()
        cv2.putText(frame, f"Gesto: {gesto_texto}", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 
                   0.7, self.configuracion.color_secundario, 2)
        
        # Panel lateral derecho con controles
        self._dibujar_panel_controles(frame)
        
        # Panel inferior con información de gestos
        self._dibujar_panel_gestos(frame)
    
    def _dibujar_panel_controles(self, frame: np.ndarray):
        """Dibuja el panel de controles lateral"""
        altura, ancho = frame.shape[:2]
        panel_ancho = 300
        panel_x = ancho - panel_ancho
        
        # Fondo del panel
        cv2.rectangle(frame, (panel_x, 0), (ancho, altura), (0, 0, 0), -1)
        cv2.rectangle(frame, (panel_x, 0), (ancho, altura), self.configuracion.color_primario, 2)
        
        # Información del sistema
        y_pos = 30
        cv2.putText(frame, "CONTROLES", (panel_x + 10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 
                   0.7, self.configuracion.color_secundario, 2)
        
        y_pos += 40
        cv2.putText(frame, "H - Alternar interfaz", (panel_x + 10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 
                   0.5, (255, 255, 255), 1)
        
        y_pos += 25
        cv2.putText(frame, "C - Modo compacto", (panel_x + 10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 
                   0.5, (255, 255, 255), 1)
        
        y_pos += 25
        cv2.putText(frame, "ESC - Salir", (panel_x + 10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 
                   0.5, (255, 255, 255), 1)
        
        # Información de calibración
        if self.modo == ModoOperacion.MESA:
            y_pos += 50
            cv2.putText(frame, "CALIBRACION", (panel_x + 10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.7, self.configuracion.color_secundario, 2)
            
            y_pos += 30
            puntos_cal = len(self.puntos_camara)
            cv2.putText(frame, f"Puntos: {puntos_cal}/4", (panel_x + 10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.5, (255, 255, 255), 1)
            
            if puntos_cal < 4:
                y_pos += 25
                cv2.putText(frame, "Toca las esquinas", (panel_x + 10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 
                           0.5, self.configuracion.color_error, 1)
    
    def _dibujar_panel_gestos(self, frame: np.ndarray):
        """Dibuja el panel de información de gestos"""
        altura, ancho = frame.shape[:2]
        panel_alto = 100
        panel_y = altura - panel_alto
        
        # Fondo del panel
        cv2.rectangle(frame, (0, panel_y), (ancho - 300, altura), (0, 0, 0), -1)
        cv2.rectangle(frame, (0, panel_y), (ancho - 300, altura), self.configuracion.color_primario, 2)
        
        # Información de gestos
        y_pos = panel_y + 30
        cv2.putText(frame, "GESTOS DISPONIBLES", (10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 
                   0.7, self.configuracion.color_secundario, 2)
        
        y_pos += 30
        cv2.putText(frame, "✋ Mano abierta: Cursor | 👌 Pulgar+Indice: Click/Arrastrar | 🤏 Pulgar+Medio: Click derecho", 
                   (10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        y_pos += 25
        cv2.putText(frame, f"👊 Dos puños: Zoom | Doble click: {self.doble_click_ventana}s", 
                   (10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    
    def procesar_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, InfoGesto]:
        """
        Procesa un frame y detecta gestos
        
        Args:
            frame: Frame de la cámara
            
        Returns:
            Tuple con frame procesado e información del gesto
        """
        # Convertir de BGR a RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Detectar manos
        resultados = self.hands.process(rgb_frame)
        
        # Información del gesto por defecto
        info_gesto = InfoGesto(gesto=TipoGesto.NINGUNO)
        
        if resultados.multi_hand_landmarks:
            if len(resultados.multi_hand_landmarks) == 1:
                # Una mano detectada
                info_gesto = self._detectar_gestos_una_mano(
                    resultados.multi_hand_landmarks[0], frame
                )
            elif len(resultados.multi_hand_landmarks) == 2:
                # Dos manos detectadas - posible zoom
                info_gesto = self._detectar_gestos_dos_manos(
                    resultados.multi_hand_landmarks, frame
                )
            
            # Dibujar landmarks
            for hand_landmarks in resultados.multi_hand_landmarks:
                self.mp_drawing.draw_landmarks(
                    frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS
                )
        
        # Ejecutar acción según el gesto
        self._ejecutar_accion(info_gesto)
        
        # Actualizar estado
        self.ultimo_gesto = info_gesto.gesto
        self.tiempo_gesto = time.time()
        
        # Dibujar interfaz
        frame = self.dibujar_interfaz_principal(frame)
        
        # Dibujar indicadores de gesto
        self._dibujar_indicadores_gestos(frame, info_gesto)
        
        return frame, info_gesto
    
    def _detectar_gestos_una_mano(self, landmarks, frame: np.ndarray) -> InfoGesto:
        """Detecta gestos con una sola mano"""
        altura, ancho = frame.shape[:2]
        
        # Convertir landmarks a coordenadas de píxeles
        puntos = []
        for landmark in landmarks.landmark:
            x = int(landmark.x * ancho)
            y = int(landmark.y * altura)
            puntos.append((x, y))
        
        # Obtener puntos clave
        pulgar_tip = puntos[4]
        indice_tip = puntos[8]
        medio_tip = puntos[12]
        
        # Calcular distancias
        distancia_pulgar_indice = np.sqrt((pulgar_tip[0] - indice_tip[0])**2 + 
                                         (pulgar_tip[1] - indice_tip[1])**2)
        distancia_pulgar_medio = np.sqrt((pulgar_tip[0] - medio_tip[0])**2 + 
                                        (pulgar_tip[1] - medio_tip[1])**2)
        
        # Determinar gesto
        tiempo_actual = time.time()
        
        if distancia_pulgar_indice < self.configuracion.distancia_pinza:
            # Click izquierdo o arrastrar
            if self.arrastrando or tiempo_actual - self.ultimo_click_tiempo < self.doble_click_ventana:
                # Verificar doble click
                if tiempo_actual - self.ultimo_click_tiempo < self.doble_click_ventana:
                    return InfoGesto(
                        gesto=TipoGesto.DOBLE_CLICK,
                        posicion=pulgar_tip,
                        confianza=0.9
                    )
                else:
                    return InfoGesto(
                        gesto=TipoGesto.CLICK_IZQUIERDO,
                        posicion=pulgar_tip,
                        confianza=0.9
                    )
            else:
                # Click simple
                if tiempo_actual - self.ultimo_click_tiempo < self.doble_click_ventana:
                    return InfoGesto(
                        gesto=TipoGesto.DOBLE_CLICK,
                        posicion=pulgar_tip,
                        confianza=0.9
                    )
                else:
                    return InfoGesto(
                        gesto=TipoGesto.CLICK_IZQUIERDO,
                        posicion=pulgar_tip,
                        confianza=0.9
                    )
        
        elif distancia_pulgar_medio < self.configuracion.distancia_pinza:
            # Click derecho
            return InfoGesto(
                gesto=TipoGesto.CLICK_DERECHO,
                posicion=pulgar_tip,
                confianza=0.9
            )
        
        else:
            # Cursor (mano abierta)
            # Usar el pulgar como punto de control del cursor
            posicion_suavizada = self._suavizar_movimiento(pulgar_tip[0], pulgar_tip[1])
            return InfoGesto(
                gesto=TipoGesto.CURSOR,
                posicion=posicion_suavizada,
                confianza=0.8
            )
    
    def _detectar_gestos_dos_manos(self, landmarks_list, frame: np.ndarray) -> InfoGesto:
        """Detecta gestos con dos manos (zoom)"""
        altura, ancho = frame.shape[:2]
        
        # Obtener posiciones de las muñecas de ambas manos
        mano1 = landmarks_list[0].landmark[0]  # Muñeca mano 1
        mano2 = landmarks_list[1].landmark[0]  # Muñeca mano 2
        
        pos1 = (int(mano1.x * ancho), int(mano1.y * altura))
        pos2 = (int(mano2.x * ancho), int(mano2.y * altura))
        
        # Calcular distancia entre manos
        distancia_actual = np.sqrt((pos1[0] - pos2[0])**2 + (pos1[1] - pos2[1])**2)
        
        if self.zoom_activo:
            # Determinar dirección del zoom
            if distancia_actual > self.distancia_puños_anterior * 1.1:
                return InfoGesto(
                    gesto=TipoGesto.ZOOM_IN,
                    posicion=((pos1[0] + pos2[0]) // 2, (pos1[1] + pos2[1]) // 2),
                    confianza=0.8
                )
            elif distancia_actual < self.distancia_puños_anterior * 0.9:
                return InfoGesto(
                    gesto=TipoGesto.ZOOM_OUT,
                    posicion=((pos1[0] + pos2[0]) // 2, (pos1[1] + pos2[1]) // 2),
                    confianza=0.8
                )
        
        # Actualizar estado de zoom
        self.zoom_activo = True
        self.distancia_puños_anterior = distancia_actual
        
        return InfoGesto(gesto=TipoGesto.NINGUNO)
    
    def _suavizar_movimiento(self, x: int, y: int) -> Tuple[int, int]:
        """Aplica suavizado al movimiento del cursor"""
        self.historial_x.append(x)
        self.historial_y.append(y)
        
        if len(self.historial_x) > self.suavizado:
            self.historial_x.pop(0)
        if len(self.historial_y) > self.suavizado:
            self.historial_y.pop(0)
        
        x_suavizado = int(np.mean(self.historial_x))
        y_suavizado = int(np.mean(self.historial_y))
        
        return (x_suavizado, y_suavizado)
    
    def _ejecutar_accion(self, info_gesto: InfoGesto):
        """Ejecuta la acción correspondiente al gesto detectado"""
        if info_gesto.gesto == TipoGesto.CURSOR and info_gesto.posicion:
            self._mover_cursor(info_gesto.posicion)
        
        elif info_gesto.gesto == TipoGesto.CLICK_IZQUIERDO:
            self._realizar_click_izquierdo()
        
        elif info_gesto.gesto == TipoGesto.DOBLE_CLICK:
            self._realizar_doble_click()
        
        elif info_gesto.gesto == TipoGesto.CLICK_DERECHO:
            self._realizar_click_derecho()
        
        elif info_gesto.gesto == TipoGesto.ZOOM_IN:
            self._realizar_zoom(self.configuracion.factor_zoom_in)
        
        elif info_gesto.gesto == TipoGesto.ZOOM_OUT:
            self._realizar_zoom(self.configuracion.factor_zoom_out)
    
    def _mover_cursor(self, posicion: Tuple[int, int]):
        """Mueve el cursor a la posición especificada"""
        if self.modo == ModoOperacion.MESA:
            # Transformar coordenadas para modo mesa
            posicion = self._transformar_coordenadas(posicion)
        else:
            # Mapear directamente a la pantalla
            x_pantalla = int(posicion[0] * self.ancho_pantalla / 640)  # Asumiendo 640px de ancho de cámara
            y_pantalla = int(posicion[1] * self.alto_pantalla / 480)   # Asumiendo 480px de alto de cámara
            posicion = (x_pantalla, y_pantalla)
        
        try:
            pyautogui.moveTo(posicion[0], posicion[1], duration=0.01)
            self.cursor_x, self.cursor_y = posicion
        except pyautogui.FailSafeException:
            logger.warning("FailSafe activado - movimiento cancelado")
    
    def _realizar_click_izquierdo(self):
        """Realiza un click izquierdo"""
        try:
            pyautogui.click()
            self.ultimo_click_tiempo = time.time()
            self.arrastrando = True
            logger.info("Click izquierdo ejecutado")
        except pyautogui.FailSafeException:
            logger.warning("FailSafe activado - click cancelado")
    
    def _realizar_doble_click(self):
        """Realiza un doble click"""
        try:
            pyautogui.doubleClick()
            logger.info("Doble click ejecutado")
        except pyautogui.FailSafeException:
            logger.warning("FailSafe activado - doble click cancelado")
    
    def _realizar_click_derecho(self):
        """Realiza un click derecho"""
        try:
            pyautogui.rightClick()
            logger.info("Click derecho ejecutado")
        except pyautogui.FailSafeException:
            logger.warning("FailSafe activado - click derecho cancelado")
    
    def _realizar_zoom(self, factor: float):
        """Realiza zoom in/out"""
        if time.time() - self.cooldown_zoom > 0.1:  # Cooldown de 100ms
            try:
                if factor > 1.0:
                    pyautogui.scroll(3)  # Zoom in
                    logger.info("Zoom in ejecutado")
                else:
                    pyautogui.scroll(-3)  # Zoom out
                    logger.info("Zoom out ejecutado")
                self.cooldown_zoom = time.time()
            except pyautogui.FailSafeException:
                logger.warning("FailSafe activado - zoom cancelado")
    
    def _transformar_coordenadas(self, punto: Tuple[int, int]) -> Tuple[int, int]:
        """Transforma coordenadas de la cámara al espacio de proyección"""
        punto_h = np.array([punto[0], punto[1], 1.0])
        punto_transformado = np.dot(self.matriz_transformacion, punto_h)
        
        if punto_transformado[2] != 0:
            punto_transformado = punto_transformado / punto_transformado[2]
        
        return (int(punto_transformado[0]), int(punto_transformado[1]))
    
    def _dibujar_indicadores_gestos(self, frame: np.ndarray, info_gesto: InfoGesto):
        """Dibuja indicadores visuales de los gestos detectados"""
        if not info_gesto.posicion:
            return
        
        x, y = info_gesto.posicion
        
        # Color según el tipo de gesto
        if info_gesto.gesto == TipoGesto.CURSOR:
            color = self.configuracion.color_primario
            texto = "CURSOR"
        elif info_gesto.gesto == TipoGesto.CLICK_IZQUIERDO:
            color = (255, 0, 0)
            texto = "CLICK"
        elif info_gesto.gesto == TipoGesto.DOBLE_CLICK:
            color = (255, 100, 0)
            texto = "DOBLE CLICK"
        elif info_gesto.gesto == TipoGesto.CLICK_DERECHO:
            color = (0, 0, 255)
            texto = "CLICK DER"
        elif info_gesto.gesto in [TipoGesto.ZOOM_IN, TipoGesto.ZOOM_OUT]:
            color = (255, 255, 0)
            texto = "ZOOM"
        else:
            return
        
        # Dibujar círculo en la posición
        cv2.circle(frame, (x, y), 20, color, 3)
        cv2.circle(frame, (x, y), 5, color, -1)
        
        # Dibujar texto del gesto
        cv2.putText(frame, texto, (x - 40, y - 30), cv2.FONT_HERSHEY_SIMPLEX, 
                   0.7, color, 2)
    
    def manejar_teclas(self, tecla: int) -> bool:
        """
        Maneja las teclas presionadas
        
        Args:
            tecla: Código de la tecla presionada
            
        Returns:
            True si debe continuar, False si debe salir
        """
        if tecla == 27:  # ESC
            return False
        elif tecla == ord('h') or tecla == ord('H'):
            self.alternar_interfaz()
        elif tecla == ord('c') or tecla == ord('C'):
            self.alternar_modo_compacto()
        elif tecla == ord('r') or tecla == ord('R'):
            # Reset zoom
            self.zoom_base = 1.0
            logger.info("Zoom reseteado")
        
        return True
    
    def finalizar(self):
        """Limpia recursos y finaliza el detector"""
        self.hands.close()
        logger.info("Detector de gestos finalizado")


# ================================
# SISTEMA PRINCIPAL
# ================================

class SistemaControlGestos:
    """Sistema principal que coordina la detección y control"""
    
    def __init__(self, modo: str = "pantalla"):
        self.detector = DetectorGestos(modo)
        self.cap = None
        self.ejecutandose = False
    
    def inicializar_camara(self, dispositivo: int = 0) -> bool:
        """Inicializa la cámara"""
        try:
            self.cap = cv2.VideoCapture(dispositivo)
            if not self.cap.isOpened():
                logger.error(f"No se pudo abrir la cámara {dispositivo}")
                return False
            
            # Configurar propiedades de la cámara
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.cap.set(cv2.CAP_PROP_FPS, 30)
            
            logger.info(f"Cámara {dispositivo} inicializada correctamente")
            return True
            
        except Exception as e:
            logger.error(f"Error inicializando cámara: {e}")
            return False
    
    def ejecutar(self):
        """Ejecuta el bucle principal del sistema"""
        if not self.inicializar_camara():
            logger.error("No se pudo inicializar la cámara")
            return False
        
        logger.info("Sistema de control por gestos iniciado")
        logger.info("Presiona H para alternar interfaz, C para modo compacto, ESC para salir")
        
        self.ejecutandose = True
        
        try:
            while self.ejecutandose:
                ret, frame = self.cap.read()
                if not ret:
                    logger.error("Error capturando frame de la cámara")
                    break
                
                # Voltear horizontalmente para mejor experiencia
                frame = cv2.flip(frame, 1)
                
                # Procesar frame
                frame_procesado, info_gesto = self.detector.procesar_frame(frame)
                
                # Mostrar resultado
                cv2.imshow('Detector de Gestos v3.0', frame_procesado)
                
                # Manejar teclas
                tecla = cv2.waitKey(1) & 0xFF
                if not self.detector.manejar_teclas(tecla):
                    break
                    
        except KeyboardInterrupt:
            logger.info("Sistema interrumpido por el usuario")
        except Exception as e:
            logger.error(f"Error en el bucle principal: {e}")
        finally:
            self.finalizar()
        
        return True
    
    def finalizar(self):
        """Finaliza el sistema y libera recursos"""
        self.ejecutandose = False
        
        if self.cap:
            self.cap.release()
        
        cv2.destroyAllWindows()
        self.detector.finalizar()
        
        logger.info("Sistema finalizado correctamente")


def main():
    """Función principal"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Sistema de Control por Gestos v3.0')
    parser.add_argument('--modo', choices=['pantalla', 'mesa'], default='pantalla',
                       help='Modo de operación: pantalla (control directo) o mesa (proyección)')
    parser.add_argument('--camara', type=int, default=0,
                       help='Índice del dispositivo de cámara (default: 0)')
    parser.add_argument('--debug', action='store_true',
                       help='Activar modo debug con logging detallado')
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    print("=" * 60)
    print("    SISTEMA DE CONTROL POR GESTOS v3.0")
    print("=" * 60)
    print(f"Modo: {args.modo}")
    print(f"Cámara: {args.camara}")
    print("Iniciando...")
    print()
    
    try:
        sistema = SistemaControlGestos(modo=args.modo)
        exito = sistema.ejecutar()
        
        if exito:
            print("\n¡Sistema ejecutado exitosamente!")
        else:
            print("\nError ejecutando el sistema")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Error crítico: {e}")
        print(f"\nError crítico: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
