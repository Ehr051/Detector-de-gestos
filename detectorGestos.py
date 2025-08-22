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
        
        # Extraer solo los campos válidos para ConfiguracionSistema
        sistema_config = self.config.get('sistema', {})
        config_valida = {
            'min_detection_confidence': self.config.get('deteccion', {}).get('min_detection_confidence', 0.7),
            'min_tracking_confidence': self.config.get('deteccion', {}).get('min_tracking_confidence', 0.5),
            'max_num_hands': self.config.get('deteccion', {}).get('max_num_hands', 2),
            'distancia_pinza': self.config.get('gestos', {}).get('distancia_pinza', 40),
            'factor_zoom_in': self.config.get('gestos', {}).get('factor_zoom_in', 1.5),
            'factor_zoom_out': self.config.get('gestos', {}).get('factor_zoom_out', 0.7),
            'suavizado_movimiento': self.config.get('gestos', {}).get('suavizado_movimiento', 5),
            'doble_click_ventana': self.config.get('gestos', {}).get('doble_click_ventana', 0.5),
            'tiempo_calibracion': self.config.get('gestos', {}).get('tiempo_calibracion', 3.0),
            'mostrar_por_defecto': self.config.get('interfaz', {}).get('mostrar_por_defecto', True)
        }
        self.configuracion = ConfiguracionSistema(**config_valida)
        
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
        
        # Variable para cambio de cámara
        self.cambiar_camara_solicitado = False
        
        # Cargar calibración existente si está en modo mesa
        if self.modo == ModoOperacion.MESA:
            self._cargar_calibracion()
        
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
    
    def _cambiar_modo(self):
        """Cambia entre modo pantalla y mesa"""
        if self.modo == ModoOperacion.PANTALLA:
            self.modo = ModoOperacion.MESA
            logger.info("Cambiado a modo MESA (proyección)")
        else:
            self.modo = ModoOperacion.PANTALLA
            # Resetear calibración al cambiar a pantalla
            self.puntos_camara = []
            self.puntos_proyeccion = []
            logger.info("Cambiado a modo PANTALLA (control directo)")
    
    def _cambiar_camara(self):
        """Solicita cambio de cámara al sistema principal"""
        # Esta función será manejada por el sistema principal
        logger.info("Solicitado cambio de cámara")
        self.cambiar_camara_solicitado = True
    
    def _iniciar_calibracion(self):
        """Inicia el proceso de calibración para modo mesa"""
        if self.modo == ModoOperacion.MESA:
            self.calibrando = True
            self.puntos_camara = []
            self.puntos_proyeccion = []
            self.esquina_actual = 0
            self.tiempo_en_punto = 0
            self.punto_calibracion_activo = False
            
            # Definir las esquinas de la proyección (orden: TL, TR, BR, BL)
            self.esquinas_proyeccion = [
                (50, 50),    # Top-Left
                (self.ancho_pantalla - 50, 50),    # Top-Right  
                (self.ancho_pantalla - 50, self.alto_pantalla - 50),    # Bottom-Right
                (50, self.alto_pantalla - 50)     # Bottom-Left
            ]
            
            logger.info("Calibración iniciada. Toca las esquinas de la proyección en orden.")
        else:
            logger.warning("La calibración solo está disponible en modo MESA")
    
    def _procesar_calibracion(self, frame: np.ndarray, landmarks):
        """Procesa el estado de calibración cuando está activa"""
        if not self.calibrando or self.esquina_actual >= 4:
            return
        
        altura, ancho = frame.shape[:2]
        
        # Obtener posición del dedo índice
        indice_tip = landmarks.landmark[8]
        x_dedo = int(indice_tip.x * ancho)
        y_dedo = int(indice_tip.y * altura)
        
        # Esquina objetivo actual
        esquina_objetivo = self.esquinas_proyeccion[self.esquina_actual]
        
        # Dibujar indicador de calibración
        self._dibujar_indicador_calibracion(frame, esquina_objetivo, self.esquina_actual)
        
        # Verificar si el dedo está cerca de la esquina objetivo
        distancia = np.sqrt((x_dedo - esquina_objetivo[0])**2 + (y_dedo - esquina_objetivo[1])**2)
        
        if distancia < 50:  # 50 píxeles de tolerancia
            if not self.punto_calibracion_activo:
                self.punto_calibracion_activo = True
                self.tiempo_en_punto = time.time()
            
            # Mostrar progreso
            tiempo_transcurrido = time.time() - self.tiempo_en_punto
            progreso = min(tiempo_transcurrido / self.tiempo_requerido_calibracion, 1.0)
            
            # Dibujar barra de progreso
            self._dibujar_progreso_calibracion(frame, esquina_objetivo, progreso)
            
            # Si se completó el tiempo requerido
            if tiempo_transcurrido >= self.tiempo_requerido_calibracion:
                # Guardar punto
                self.puntos_camara.append((x_dedo, y_dedo))
                self.puntos_proyeccion.append(esquina_objetivo)
                
                logger.info(f"Punto {self.esquina_actual + 1}/4 calibrado")
                
                # Avanzar a la siguiente esquina
                self.esquina_actual += 1
                self.punto_calibracion_activo = False
                
                if self.esquina_actual >= 4:
                    self._finalizar_calibracion()
        else:
            # Reset si se aleja del punto
            if self.punto_calibracion_activo:
                self.punto_calibracion_activo = False
                self.tiempo_en_punto = 0
    
    def _dibujar_indicador_calibracion(self, frame: np.ndarray, esquina: Tuple[int, int], numero: int):
        """Dibuja el indicador visual para la calibración"""
        x, y = esquina
        
        # Círculo grande de objetivo
        cv2.circle(frame, (x, y), 40, (0, 255, 255), 3)
        cv2.circle(frame, (x, y), 30, (0, 255, 255), 2)
        cv2.circle(frame, (x, y), 20, (0, 255, 255), 1)
        
        # Número de esquina
        cv2.putText(frame, f"{numero + 1}", (x - 10, y + 10), cv2.FONT_HERSHEY_SIMPLEX, 
                   1, (0, 255, 255), 3)
        
        # Instrucciones
        nombres_esquinas = ["Superior Izquierda", "Superior Derecha", "Inferior Derecha", "Inferior Izquierda"]
        instruccion = f"Toca esquina {nombres_esquinas[numero]} y mantén 3 segundos"
        cv2.putText(frame, instruccion, (50, frame.shape[0] - 50), cv2.FONT_HERSHEY_SIMPLEX, 
                   0.8, (0, 255, 255), 2)
    
    def _dibujar_progreso_calibracion(self, frame: np.ndarray, esquina: Tuple[int, int], progreso: float):
        """Dibuja la barra de progreso de calibración"""
        x, y = esquina
        
        # Círculo de progreso
        radio = 50
        angulo = int(360 * progreso)
        
        # Dibujar arco de progreso
        if progreso > 0:
            # Crear puntos para el arco
            puntos = []
            for i in range(0, angulo, 5):
                rad = np.radians(i - 90)  # Empezar desde arriba
                px = int(x + radio * np.cos(rad))
                py = int(y + radio * np.sin(rad))
                puntos.append((px, py))
            
            if len(puntos) > 1:
                for i in range(len(puntos) - 1):
                    cv2.line(frame, puntos[i], puntos[i + 1], (0, 255, 0), 5)
        
        # Texto de progreso
        porcentaje = int(progreso * 100)
        cv2.putText(frame, f"{porcentaje}%", (x - 20, y - 60), cv2.FONT_HERSHEY_SIMPLEX, 
                   0.8, (0, 255, 0), 2)
    
    def _finalizar_calibracion(self):
        """Finaliza el proceso de calibración y calcula la matriz de transformación"""
        if len(self.puntos_camara) >= 4 and len(self.puntos_proyeccion) >= 4:
            # Convertir a arrays numpy
            puntos_src = np.array(self.puntos_camara, dtype=np.float32)
            puntos_dst = np.array(self.puntos_proyeccion, dtype=np.float32)
            
            # Calcular matriz de transformación
            self.matriz_transformacion = cv2.getPerspectiveTransform(puntos_src, puntos_dst)
            
            self.calibrando = False
            logger.info("Calibración completada exitosamente")
            
            # Guardar calibración a archivo
            self._guardar_calibracion()
        else:
            logger.error("Error en calibración: puntos insuficientes")
    
    def _guardar_calibracion(self):
        """Guarda la matriz de calibración a un archivo"""
        try:
            np.save('calibracion_matriz.npy', self.matriz_transformacion)
            logger.info("Matriz de calibración guardada")
        except Exception as e:
            logger.error(f"Error guardando calibración: {e}")
    
    def _cargar_calibracion(self):
        """Carga una calibración previamente guardada"""
        try:
            if Path('calibracion_matriz.npy').exists():
                self.matriz_transformacion = np.load('calibracion_matriz.npy')
                logger.info("Calibración cargada desde archivo")
                return True
        except Exception as e:
            logger.error(f"Error cargando calibración: {e}")
        return False
    
    def dibujar_interfaz_principal(self, frame: np.ndarray) -> np.ndarray:
        """Dibuja la interfaz principal del sistema"""
        altura, ancho = frame.shape[:2]
        
        # Siempre dibujar la barra superior con botones
        self._dibujar_barra_superior(frame)
        
        if self.mostrar_interfaz:
            if self.interfaz_compacta:
                self._dibujar_interfaz_compacta(frame)
            else:
                self._dibujar_interfaz_completa(frame)
        
        return frame
    
    def _dibujar_barra_superior(self, frame: np.ndarray):
        """Dibuja la barra superior con botones de control"""
        altura, ancho = frame.shape[:2]
        barra_alto = 50
        
        # Fondo de la barra
        cv2.rectangle(frame, (0, 0), (ancho, barra_alto), (40, 40, 40), -1)
        cv2.rectangle(frame, (0, 0), (ancho, barra_alto), (100, 100, 100), 2)
        
        # Definir botones con más funcionalidades
        botones = [
            {"texto": "SALIR", "x": ancho - 70, "color": (0, 0, 200), "accion": "salir"},
            {"texto": "INTERFAZ", "x": ancho - 140, "color": (0, 150, 0), "accion": "interfaz"},
            {"texto": "CALIBRAR", "x": ancho - 210, "color": (200, 100, 0), "accion": "calibrar"},
            {"texto": "MODO", "x": ancho - 270, "color": (150, 150, 0), "accion": "modo"},
            {"texto": "CAMARA", "x": ancho - 340, "color": (100, 0, 150), "accion": "camara"}
        ]
        
        # Dibujar botones
        for boton in botones:
            x = boton["x"]
            # Fondo del botón
            cv2.rectangle(frame, (x, 5), (x + 65, 40), boton["color"], -1)
            cv2.rectangle(frame, (x, 5), (x + 65, 40), (255, 255, 255), 1)
            # Texto del botón
            cv2.putText(frame, boton["texto"], (x + 5, 28), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.35, (255, 255, 255), 1)
        
        # Información básica en la izquierda
        info_texto = f"Detector v3.0 - {self.modo.value.title()}"
        cv2.putText(frame, info_texto, (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 
                   0.6, (255, 255, 255), 1)
        
        # Información adicional
        if self.modo == ModoOperacion.MESA:
            puntos_cal = len(self.puntos_camara)
            estado_cal = f"Calibracion: {puntos_cal}/4"
            color_cal = (0, 255, 0) if puntos_cal >= 4 else (255, 100, 0)
            cv2.putText(frame, estado_cal, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.5, color_cal, 1)
    
    def manejar_click_boton(self, x: int, y: int, ancho: int) -> bool:
        """Maneja clicks en los botones de la barra superior"""
        if y < 50:  # Click en la barra superior
            if ancho - 70 <= x <= ancho - 5:  # Botón SALIR
                return False
            elif ancho - 140 <= x <= ancho - 75:  # Botón INTERFAZ
                self.alternar_interfaz()
            elif ancho - 210 <= x <= ancho - 145:  # Botón CALIBRAR
                self._iniciar_calibracion()
            elif ancho - 270 <= x <= ancho - 215:  # Botón MODO
                self._cambiar_modo()
            elif ancho - 340 <= x <= ancho - 275:  # Botón CAMARA
                self._cambiar_camara()
        return True
    
    def _dibujar_interfaz_compacta(self, frame: np.ndarray):
        """Dibuja una interfaz compacta para presentaciones"""
        altura, ancho = frame.shape[:2]
        
        # Panel compacto debajo de la barra
        panel_y = 50
        panel_alto = 60
        cv2.rectangle(frame, (0, panel_y), (ancho, panel_y + panel_alto), (20, 20, 20), -1)
        cv2.rectangle(frame, (0, panel_y), (ancho, panel_y + panel_alto), (100, 100, 100), 1)
        
        # Información básica
        gesto_texto = self.ultimo_gesto.value.replace('_', ' ').title()
        info_texto = f"Gesto Actual: {gesto_texto}"
        cv2.putText(frame, info_texto, (10, panel_y + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, 
                   (255, 255, 255), 2)
        
        # Estado de calibración si aplica
        if self.modo == ModoOperacion.MESA:
            puntos_cal = len(self.puntos_camara)
            estado_cal = f"Calibracion: {puntos_cal}/4 puntos"
            cv2.putText(frame, estado_cal, (10, panel_y + 50), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.5, (200, 200, 200), 1)
        
        # Estado de calibración si aplica
        if self.modo == ModoOperacion.MESA:
            estado_cal = "Calibrado" if len(self.puntos_camara) >= 4 else "Sin calibrar"
            cv2.putText(frame, f"Calibracion: {estado_cal}", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.5, self.configuracion.color_secundario, 1)
    
    def _dibujar_interfaz_completa(self, frame: np.ndarray):
        """Dibuja la interfaz completa con información detallada"""
        altura, ancho = frame.shape[:2]
        
        # Panel principal debajo de la barra
        panel_y = 50
        panel_alto = 180
        cv2.rectangle(frame, (0, panel_y), (ancho, panel_y + panel_alto), (30, 30, 30), -1)
        cv2.rectangle(frame, (0, panel_y), (ancho, panel_y + panel_alto), (100, 100, 100), 2)
        
        # Información principal
        y_pos = panel_y + 30
        
        # Gesto actual
        gesto_texto = self.ultimo_gesto.value.replace('_', ' ').title()
        cv2.putText(frame, f"Gesto Actual: {gesto_texto}", (20, y_pos), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        
        y_pos += 35
        # Información del cursor
        cv2.putText(frame, f"Cursor: ({self.cursor_x}, {self.cursor_y})", (20, y_pos), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        
        y_pos += 25
        # Resolución de pantalla
        cv2.putText(frame, f"Pantalla: {self.ancho_pantalla}x{self.alto_pantalla}", (20, y_pos), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        
        # Información de calibración (si es modo mesa)
        if self.modo == ModoOperacion.MESA:
            y_pos += 35
            puntos_cal = len(self.puntos_camara)
            cv2.putText(frame, f"Calibracion: {puntos_cal}/4 puntos completados", (20, y_pos), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 200, 0), 2)
            
            if puntos_cal < 4:
                y_pos += 25
                cv2.putText(frame, "Presiona CALIBRAR para configurar proyeccion", (20, y_pos), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 100, 100), 1)
        
        # Panel lateral con controles
        self._dibujar_panel_controles_simple(frame)
    
    def _dibujar_panel_controles_simple(self, frame: np.ndarray):
        """Dibuja un panel de controles simplificado"""
        altura, ancho = frame.shape[:2]
        panel_ancho = 280
        panel_x = ancho - panel_ancho
        panel_y = 50
        panel_alto = 180
        
        # Fondo del panel
        cv2.rectangle(frame, (panel_x, panel_y), (ancho, panel_y + panel_alto), (30, 30, 30), -1)
        cv2.rectangle(frame, (panel_x, panel_y), (ancho, panel_y + panel_alto), (100, 100, 100), 2)
        
        # Título
        y_pos = panel_y + 30
        cv2.putText(frame, "CONTROLES DE TECLADO:", (panel_x + 15, y_pos), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Lista de controles
        controles = [
            "ESC/Q - Salir del programa",
            "H - Mostrar/Ocultar interfaz", 
            "C - Modo compacto",
            "M - Cambiar modo (Pantalla/Mesa)",
            "N - Cambiar camara",
            "B - Calibrar (solo modo mesa)",
            "R - Reset calibracion/zoom",
            "",
            "GESTOS DISPONIBLES:",
            "Mano abierta - Mover cursor",
            "Pulgar + Indice - Click izquierdo",
            "Doble pinza rapida - Doble click",
            "Pulgar + Medio - Click derecho",
            "Dos manos - Zoom in/out"
        ]
        
        y_pos += 25
        for control in controles:
            if control == "":
                y_pos += 10
                continue
            elif control.startswith("GESTOS"):
                cv2.putText(frame, control, (panel_x + 15, y_pos), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            else:
                cv2.putText(frame, control, (panel_x + 15, y_pos), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
            y_pos += 15
    
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
        
        # Si estamos calibrando, procesar calibración
        if self.calibrando:
            self._procesar_calibracion(frame, landmarks)
            return InfoGesto(gesto=TipoGesto.NINGUNO)
        
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
        if self.modo == ModoOperacion.MESA and len(self.puntos_camara) >= 4:
            # Transformar coordenadas para modo mesa
            posicion = self._transformar_coordenadas(posicion)
        else:
            # Mapear directamente a la pantalla
            # Obtener dimensiones reales del frame
            ancho_frame = 640  # Se puede obtener dinámicamente
            alto_frame = 480
            
            x_pantalla = int(posicion[0] * self.ancho_pantalla / ancho_frame)
            y_pantalla = int(posicion[1] * self.alto_pantalla / alto_frame)
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
        elif tecla == ord('m') or tecla == ord('M'):
            self._cambiar_modo()
        elif tecla == ord('q') or tecla == ord('Q'):
            return False
        elif tecla == ord('n') or tecla == ord('N'):  # Cambiar cámara
            self._cambiar_camara()
        elif tecla == ord('b') or tecla == ord('B'):  # Calibrar
            self._iniciar_calibracion()
        elif tecla == ord('r') or tecla == ord('R'):
            # Reset zoom y calibración
            self.zoom_base = 1.0
            if self.modo == ModoOperacion.MESA:
                self.puntos_camara = []
                self.puntos_proyeccion = []
                self.matriz_transformacion = np.eye(3)
                logger.info("Calibración reseteada")
            logger.info("Sistema reseteado")
        
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
        self.dispositivo_camara_actual = 0
        self.dispositivos_disponibles = self._detectar_camaras()
    
    def _detectar_camaras(self) -> List[int]:
        """Detecta las cámaras disponibles en el sistema"""
        dispositivos = []
        for i in range(5):  # Probar hasta 5 dispositivos
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                dispositivos.append(i)
                cap.release()
        logger.info(f"Cámaras detectadas: {dispositivos}")
        return dispositivos if dispositivos else [0]
    
    def cambiar_camara(self):
        """Cambia a la siguiente cámara disponible"""
        if len(self.dispositivos_disponibles) > 1:
            indice_actual = self.dispositivos_disponibles.index(self.dispositivo_camara_actual)
            siguiente_indice = (indice_actual + 1) % len(self.dispositivos_disponibles)
            nuevo_dispositivo = self.dispositivos_disponibles[siguiente_indice]
            
            # Liberar cámara actual
            if self.cap:
                self.cap.release()
            
            # Inicializar nueva cámara
            if self.inicializar_camara(nuevo_dispositivo):
                self.dispositivo_camara_actual = nuevo_dispositivo
                logger.info(f"Cambiado a cámara {nuevo_dispositivo}")
            else:
                # Si falla, volver a la anterior
                self.inicializar_camara(self.dispositivo_camara_actual)
                logger.error(f"Error cambiando a cámara {nuevo_dispositivo}")
        else:
            logger.info("Solo hay una cámara disponible")
    
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
        if not self.inicializar_camara(self.dispositivo_camara_actual):
            logger.error("No se pudo inicializar la cámara")
            return False
        
        logger.info("Sistema de control por gestos iniciado")
        logger.info("CONTROLES:")
        logger.info("  ESC/Q - Salir")
        logger.info("  H - Alternar interfaz")
        logger.info("  C - Modo compacto")
        logger.info("  M - Cambiar modo (Pantalla/Mesa)")
        logger.info("  N - Cambiar cámara")
        logger.info("  B - Calibrar (modo mesa)")
        logger.info("  R - Reset")
        
        self.ejecutandose = True
        
        try:
            while self.ejecutandose:
                # Verificar si se solicita cambio de cámara
                if self.detector.cambiar_camara_solicitado:
                    self.cambiar_camara()
                    self.detector.cambiar_camara_solicitado = False
                
                ret, frame = self.cap.read()
                if not ret:
                    logger.error("Error capturando frame de la cámara")
                    break
                
                # Voltear horizontalmente para mejor experiencia
                frame = cv2.flip(frame, 1)
                
                # Procesar frame
                frame_procesado, info_gesto = self.detector.procesar_frame(frame)
                
                # Mostrar información de cámara actual
                altura, ancho = frame_procesado.shape[:2]
                info_camara = f"Camara {self.dispositivo_camara_actual} | {len(self.dispositivos_disponibles)} disponibles"
                cv2.putText(frame_procesado, info_camara, (ancho - 300, altura - 20), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                
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
