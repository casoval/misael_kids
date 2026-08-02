# inscripciones/pdf_generator.py
# =====================================================
# GENERADOR DE PDF DE RECIBOS — JARDÍN INFANTIL MISAEL KIDS
# Adaptado desde el generador oficial del Centro de Neurodesarrollo
# Infantil Misael (facturacion/pdf_generator.py) para el sistema de
# inscripciones/cobros de Misael Kids.
#
# Cambios respecto al original:
# 1. Paleta de colores "Jardín mágico" — la misma que ya usa el panel
#    (turquesa/coral/amarillo/verde/violeta), en vez de la paleta azul
#    profesional del centro de terapias. Barra superior arcoíris y
#    confeti decorativo en el header para diferenciarlo claramente.
# 2. Datos del centro/sucursal dinámicos (se leen de la Sucursal real
#    de la inscripción), no hardcodeados.
# 3. Sin "sesiones"/"proyectos"/pagos por lote: nuestro sistema siempre
#    tiene un único concepto por recibo (una mensualidad, un día, o un
#    cobro extra), así que se quitó toda la lógica de página adicional
#    por desborde de tabla — nunca aplica aquí.
# 4. Datos tomados de los modelos reales: Pago/Devolucion → Cobro →
#    Inscripcion → Nino/Tutor/Sucursal (antes: Cliente de otro sistema).
# =====================================================

import os
import logging
from io import BytesIO
from types import SimpleNamespace
from decimal import Decimal
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics import renderPDF
from django.conf import settings
import hashlib

logger = logging.getLogger(__name__)

# =====================================================
# 1. PALETA "JARDÍN MÁGICO" — la misma que usa el panel (variables.css)
# =====================================================
COLOR_TURQUESA        = colors.HexColor('#2DD4BF')
COLOR_TURQUESA_OSCURO = colors.HexColor('#0D9488')
COLOR_TURQUESA_CLARO  = colors.HexColor('#CCFBF1')

COLOR_CORAL        = colors.HexColor('#FF6B6B')   # devoluciones / acentos de alerta
COLOR_CORAL_OSCURO = colors.HexColor('#E85555')
COLOR_CORAL_CLARO  = colors.HexColor('#FFE4E4')

COLOR_AMARILLO        = colors.HexColor('#FFD93D')
COLOR_AMARILLO_OSCURO = colors.HexColor('#F0C000')
COLOR_AMARILLO_CLARO  = colors.HexColor('#FFF8D6')

COLOR_VERDE        = colors.HexColor('#6BCB77')
COLOR_VERDE_OSCURO = colors.HexColor('#4CAF59')
COLOR_VERDE_CLARO  = colors.HexColor('#DCFCE7')

COLOR_VIOLETA        = colors.HexColor('#A78BFA')
COLOR_VIOLETA_OSCURO = colors.HexColor('#7C3AED')
COLOR_VIOLETA_CLARO  = colors.HexColor('#EDE9FE')

COLOR_NARANJA       = colors.HexColor('#FB923C')
COLOR_NARANJA_CLARO = colors.HexColor('#FED7AA')

# Colores de fondo y texto (más oscuros que el CSS del panel para que
# se lean bien impresos, igual criterio que traía el original)
COLOR_FONDO_PAGINA     = colors.HexColor('#F8FAFC')
COLOR_FONDO_TARJETA    = colors.white
COLOR_TEXTO_PRINCIPAL  = colors.HexColor('#1E293B')
COLOR_TEXTO_SECUNDARIO = colors.HexColor('#3D3D3D')
COLOR_GRIS_CLARO       = colors.HexColor('#EEEEEE')
COLOR_GRIS_MEDIO       = colors.HexColor('#888888')
COLOR_GRIS_BORDE       = colors.HexColor('#BBBBBB')

COLOR_FILA_PAR   = colors.HexColor('#FAFAFA')
COLOR_FILA_IMPAR = colors.white

NOMBRE_CENTRO = "Jardín Infantil Misael Kids"
LEMA_CENTRO = "Crece, juega, aprende y sueña con amor"

# Configuración de página (2 copias lado a lado, igual que el original)
PAGE_WIDTH, PAGE_HEIGHT = landscape(letter)
MARGIN = 0.5 * cm
GAP_CENTRAL = 1.0 * cm
ANCHO_RECIBO = (PAGE_WIDTH - (2 * MARGIN) - GAP_CENTRAL) / 2
ALTO_RECIBO = PAGE_HEIGHT - (2 * MARGIN)

MESES_ES = [
    '', 'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
    'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
]

# =====================================================
# 2. FUNCIONES DE UTILIDAD PARA DISEÑO
# =====================================================

def dibujar_gradiente_horizontal(c, x, y, ancho, alto, color1, color2, steps=30):
    """Dibuja un gradiente horizontal suave entre dos colores"""
    c.saveState()
    step_width = ancho / steps
    for i in range(steps):
        ratio = i / steps
        r = color1.red + (color2.red - color1.red) * ratio
        g = color1.green + (color2.green - color1.green) * ratio
        b = color1.blue + (color2.blue - color1.blue) * ratio
        c.setFillColor(colors.Color(r, g, b))
        c.rect(x + i * step_width, y, step_width + 1, alto, fill=1, stroke=0)
    c.restoreState()


def dibujar_gradiente_redondeado(c, x, y, ancho, alto, color1, color2, radio=8, steps=30):
    """Dibuja un gradiente horizontal con bordes redondeados usando clipPath"""
    c.saveState()
    path = c.beginPath()
    path.roundRect(x, y, ancho, alto, radio)
    c.clipPath(path, stroke=0)
    step_width = ancho / steps
    for i in range(steps):
        ratio = i / steps
        r = color1.red + (color2.red - color1.red) * ratio
        g = color1.green + (color2.green - color1.green) * ratio
        b = color1.blue + (color2.blue - color1.blue) * ratio
        c.setFillColor(colors.Color(r, g, b))
        c.rect(x + i * step_width, y, step_width + 1, alto, fill=1, stroke=0)
    c.restoreState()


def dibujar_sombra_suave(c, x, y, ancho, alto, radio=10, offset=2):
    """Dibuja una sombra suave y sutil"""
    c.saveState()
    c.setFillColor(colors.HexColor('#00000015'))
    c.roundRect(x + offset, y - offset, ancho, alto, radio, fill=1, stroke=0)
    c.restoreState()


def generar_hash_verificacion(numero_recibo, fecha, monto):
    """Genera un hash único para validación del recibo"""
    texto = f"{numero_recibo}{fecha}{monto}"
    return hashlib.md5(texto.encode()).hexdigest()[:8].upper()


def crear_qr_code(c, x, y, data, size=1.5 * cm):
    """Crea y dibuja un código QR"""
    try:
        qr_code = QrCodeWidget(data)
        bounds = qr_code.getBounds()
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        d = Drawing(size, size, transform=[size / width, 0, 0, size / height, 0, 0])
        d.add(qr_code)
        renderPDF.draw(d, c, x, y)
    except Exception as e:
        logger.error(f"Error generando QR: {e}")


# =====================================================
# 3. ENTRADAS PRINCIPALES
# =====================================================

def _tutor_principal(nino):
    rel = nino.tutores.filter(es_principal=True).select_related('tutor').first() \
        or nino.tutores.select_related('tutor').first()
    return rel.tutor if rel else None


def _concepto_cobro(cobro):
    if cobro.tipo == cobro.TIPO_MENSUALIDAD and cobro.periodo_inicio:
        return f"Mensualidad de {MESES_ES[cobro.periodo_inicio.month]} {cobro.periodo_inicio.year}".capitalize()
    if cobro.tipo == cobro.TIPO_DIARIO:
        return f"Cobro por día — {cobro.fecha_vencimiento.strftime('%d/%m/%Y')}"
    return cobro.periodo or 'Cobro extra'


def _construir_contexto(obj, es_devolucion):
    """
    Normaliza un Pago o una Devolucion (que tienen campos distintos) a un
    único formato interno que usan todas las funciones de dibujo, para no
    andar adivinando con getattr/hasattr por todos lados.
    """
    cobro = obj.cobro
    inscripcion = cobro.inscripcion
    nino = inscripcion.nino
    tutor = _tutor_principal(nino)
    sucursal = inscripcion.sucursal

    fecha = getattr(obj, 'fecha_pago', None) or getattr(obj, 'fecha', None)
    nota = getattr(obj, 'observacion', '') or getattr(obj, 'motivo', '')
    registrado_por = obj.registrado_por.nombre_completo if obj.registrado_por else None

    return SimpleNamespace(
        es_devolucion=es_devolucion,
        numero_recibo=obj.numero_recibo,
        monto=safe_decimal(obj.monto),
        fecha=fecha,
        metodo_pago_display=obj.get_metodo_pago_display(),
        nota=nota,
        registrado_por=registrado_por,
        nino_nombre=nino.nombre_completo,
        tutor_nombre=f"{tutor.nombres} {tutor.apellidos}" if tutor else "—",
        concepto=_concepto_cobro(cobro),
        tipo_display=cobro.get_tipo_display(),
        sucursal_nombre=sucursal.nombre,
        sucursal_direccion=sucursal.direccion,
        sucursal_telefono=sucursal.telefono,
        sucursal_ciudad=sucursal.ciudad,
    )


def generar_recibo_pdf(pago):
    contexto = _construir_contexto(pago, es_devolucion=False)
    return generar_pdf_maestro(contexto)


def generar_devolucion_pdf(devolucion):
    contexto = _construir_contexto(devolucion, es_devolucion=True)
    return generar_pdf_maestro(contexto)


# =====================================================
# 4. GENERADOR MAESTRO
# =====================================================

def generar_pdf_maestro(ctx):
    buffer = BytesIO()
    c = pdf_canvas.Canvas(buffer, pagesize=landscape(letter))
    c.setTitle(f"{'Devolucion' if ctx.es_devolucion else 'Recibo'}_{ctx.numero_recibo}")

    c.setFillColor(COLOR_FONDO_PAGINA)
    c.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)

    # Recibo izquierdo (cliente) y derecho (administración) — idéntico
    # contenido, solo cambia la etiqueta de la copia.
    dibujar_recibo_optimizado(c, MARGIN, MARGIN, ctx, "COPIA: FAMILIA")
    dibujar_linea_corte(c)
    dibujar_recibo_optimizado(c, MARGIN + ANCHO_RECIBO + GAP_CENTRAL, MARGIN, ctx, "COPIA: ADMINISTRACIÓN")

    c.save()
    pdf_data = buffer.getvalue()
    buffer.close()
    return pdf_data


# =====================================================
# 5. FUNCIÓN PRINCIPAL DE DIBUJO
# =====================================================

def dibujar_recibo_optimizado(c, x, y, ctx, texto_copia):
    """Dibuja un recibo completo con diseño optimizado"""
    top = y + ALTO_RECIBO

    # --- A. TARJETA BASE CON SOMBRA SUTIL ---
    dibujar_sombra_suave(c, x, y, ANCHO_RECIBO, ALTO_RECIBO, radio=14, offset=3)

    c.saveState()
    c.setFillColor(COLOR_FONDO_TARJETA)
    c.setStrokeColor(COLOR_GRIS_BORDE)
    c.setLineWidth(0.5)
    c.roundRect(x, y, ANCHO_RECIBO, ALTO_RECIBO, 14, fill=1, stroke=1)
    c.restoreState()

    # --- B. BARRA SUPERIOR ---
    y_barra = top - 0.6 * cm
    alto_barra = 0.5 * cm

    if ctx.es_devolucion:
        dibujar_gradiente_horizontal(
            c, x + 0.2 * cm, y_barra, ANCHO_RECIBO - 0.4 * cm, alto_barra,
            COLOR_CORAL_CLARO, COLOR_CORAL,
        )
    else:
        # Barra arcoíris "Jardín mágico" — 5 franjas en vez de un gradiente
        # sobrio de 2 colores: esto es justo lo que lo diferencia de un
        # recibo de oficina cualquiera.
        franjas = [COLOR_TURQUESA, COLOR_VERDE, COLOR_AMARILLO, COLOR_NARANJA, COLOR_CORAL]
        ancho_franja = (ANCHO_RECIBO - 0.4 * cm) / len(franjas)
        for i, color in enumerate(franjas):
            c.saveState()
            c.setFillColor(color)
            c.rect(x + 0.2 * cm + i * ancho_franja, y_barra, ancho_franja + 1, alto_barra, fill=1, stroke=0)
            c.restoreState()

    c.saveState()
    c.setStrokeColor(colors.white)
    c.setLineWidth(1.5)
    c.roundRect(x + 0.2 * cm, y_barra, ANCHO_RECIBO - 0.4 * cm, alto_barra, 6, fill=0, stroke=1)
    c.restoreState()

    # --- C. HEADER ---
    y_header = y_barra - 0.3 * cm
    dibujar_header_optimizado(c, x, y_header, ctx)

    # --- D. INFO DEL NIÑO ---
    y_nino = y_header - 3.5 * cm
    dibujar_info_nino_optimizada(c, x, y_nino, ctx)

    # --- E. TABLA DE DETALLE (siempre una sola fila: un concepto) ---
    y_tabla = y_nino - 1.90 * cm
    altura_tabla = dibujar_tabla_detalles_optimizada(c, x, y_tabla, ctx)

    # --- F. OBSERVACIÓN/MOTIVO (si existe) ---
    y_nota = y_tabla - altura_tabla - 0.3 * cm
    altura_nota = dibujar_nota_si_existe(c, x, y_nota, ctx)

    # --- G. TOTAL ---
    y_totales = y_nota - altura_nota - 0.3 * cm
    dibujar_seccion_totales_optimizada(c, x, y_totales, ctx)

    # --- H. QR ---
    dibujar_qr_optimizado(c, x, y, ctx)

    # --- I. FOOTER ---
    dibujar_footer_optimizado(c, x, y, texto_copia, ctx)

    # --- J. FIRMAS ---
    dibujar_seccion_firmas_optimizada(c, x, y, ctx)

    # --- K. IMAGEN DECORATIVA (en el espacio vacío del medio, lejos del texto) ---
    dibujar_imagen_ninos(c, x, y, ctx)

    # --- L. MARCA DE AGUA ---
    dibujar_marca_agua_optimizada(c, x, y, texto_copia)


# =====================================================
# 6. SECCIONES
# =====================================================

def convertir_imagen_a_escala_grises(logo_path):
    """Convierte a escala de grises y reduce la resolución: la marca de
    agua se dibuja a ~3cm repetida muchas veces, así que usar el logo a su
    resolución original (821x881px) infla el PDF sin necesidad."""
    try:
        from PIL import Image
        img = Image.open(logo_path)
        img.thumbnail((300, 300), Image.LANCZOS)
        return img.convert('LA')
    except Exception as e:
        logger.error(f"Error convirtiendo imagen a escala de grises: {e}")
        return None


def dibujar_marca_agua_optimizada(c, x, y, texto_copia):
    """Marca de agua en patrón repetido, en escala de grises con opacidad suave."""
    logo_path = encontrar_logo_misael_kids()
    if not logo_path:
        return
    try:
        img_gray = convertir_imagen_a_escala_grises(logo_path)
        if not img_gray:
            return
        buffer = BytesIO()
        img_gray.save(buffer, format='PNG')
        buffer.seek(0)
        img_reader = ImageReader(buffer)
        iw, ih = img_reader.getSize()
        aspect = ih / float(iw)

        logo_size = 3.2 * cm
        logo_height = logo_size * aspect
        spacing_x = 6.5 * cm
        spacing_y = 5.0 * cm
        rotation = -25

        num_cols = int(ANCHO_RECIBO / spacing_x) + 1
        num_rows = int(ALTO_RECIBO / spacing_y) + 1

        for row in range(num_rows):
            for col in range(num_cols):
                c.saveState()
                offset_x = (spacing_x / 2) if row % 2 == 1 else 0
                logo_x = x + (col * spacing_x) + offset_x - (spacing_x * 0.3)
                logo_y = y + (row * spacing_y) - (spacing_y * 0.3)
                c.setFillAlpha(0.10)
                c.translate(logo_x + logo_size / 2, logo_y + logo_height / 2)
                c.rotate(rotation)
                c.translate(-(logo_x + logo_size / 2), -(logo_y + logo_height / 2))
                c.drawImage(img_reader, logo_x, logo_y, width=logo_size, height=logo_height,
                            mask='auto', preserveAspectRatio=True)
                c.restoreState()
    except Exception as e:
        logger.error(f"Error en marca de agua: {e}")


def dibujar_texto_ajustado(c, x, y, texto, fuente, tam_max, ancho_max, tam_min=5.5):
    """
    Dibuja texto reduciendo el tamaño de fuente hasta que quepa en
    ancho_max; si ni al tamaño mínimo cabe, lo corta con "...". Así una
    dirección larga (o una sucursal nueva con datos distintos) nunca se
    sale del recibo, sin tener que adivinar límites de caracteres a mano.
    """
    tam = tam_max
    while c.stringWidth(texto, fuente, tam) > ancho_max and tam > tam_min:
        tam -= 0.25
    if c.stringWidth(texto, fuente, tam) > ancho_max:
        while texto and c.stringWidth(texto + '...', fuente, tam) > ancho_max:
            texto = texto[:-1]
        texto += '...'
    c.setFont(fuente, tam)
    c.drawString(x, y, texto)


def dibujar_header_optimizado(c, x, y_base, ctx):
    """Header con logo, nombre del jardín y caja de número de recibo."""
    logo_path = encontrar_logo_misael_kids()

    if logo_path:
        try:
            logo_x = x + 0.4 * cm
            logo_y_base = y_base - 3.3 * cm
            img = ImageReader(logo_path)
            iw, ih = img.getSize()
            aspect = ih / float(iw)
            logo_w = 3.2 * cm
            logo_h = logo_w * aspect
            c.drawImage(logo_path, logo_x, logo_y_base, width=logo_w, height=logo_h, mask='auto')
        except Exception as e:
            logger.error(f"Error dibujando logo: {e}")

    text_x = x + 4.0 * cm
    y_text = y_base - 0.5 * cm

    TEXTO_ANTES = "Jardín Infantil "
    TEXTO_KIDS = "Misael Kids"
    c.setFillColor(COLOR_TEXTO_PRINCIPAL)
    c.setFont("Helvetica-Bold", 13.5)
    ancho_antes = c.stringWidth(TEXTO_ANTES, "Helvetica-Bold", 13.5)
    c.drawString(text_x, y_text, TEXTO_ANTES)
    c.setFillColor(COLOR_TURQUESA_OSCURO)
    c.setFont("Helvetica-Bold", 17)
    c.drawString(text_x + ancho_antes, y_text - 1, TEXTO_KIDS)

    c.setFont("Helvetica-Oblique", 7.5)
    c.setFillColor(COLOR_VIOLETA_OSCURO)
    c.drawString(text_x, y_text - 0.42 * cm, LEMA_CENTRO)

    ancho_disponible = ANCHO_RECIBO - (text_x - x) - 0.3 * cm
    c.setFillColor(COLOR_TEXTO_SECUNDARIO)
    dibujar_texto_ajustado(c, text_x, y_text - 0.84 * cm, ctx.sucursal_nombre, "Helvetica", 7.5, ancho_disponible)
    dibujar_texto_ajustado(c, text_x, y_text - 1.21 * cm, ctx.sucursal_direccion, "Helvetica", 7.5, ancho_disponible)
    linea_tel = f"{ctx.sucursal_ciudad}" + (f" · Tel: {ctx.sucursal_telefono}" if ctx.sucursal_telefono else "")
    dibujar_texto_ajustado(c, text_x, y_text - 1.58 * cm, linea_tel, "Helvetica", 7.5, ancho_disponible)

    # Caja de número de recibo
    titulo = "DEVOLUCIÓN" if ctx.es_devolucion else "RECIBO DE PAGO"
    num = safe_str(ctx.numero_recibo).zfill(6)

    box_w = 4.2 * cm
    box_h = 1.7 * cm
    box_x = x + ANCHO_RECIBO - box_w - 0.5 * cm
    box_y = y_base - 3.00 * cm

    color_inicio = COLOR_CORAL_CLARO if ctx.es_devolucion else COLOR_TURQUESA_CLARO
    color_fin = COLOR_CORAL if ctx.es_devolucion else COLOR_TURQUESA

    dibujar_sombra_suave(c, box_x, box_y, box_w, box_h, radio=10, offset=2)
    dibujar_gradiente_redondeado(c, box_x, box_y, box_w, box_h, color_inicio, color_fin, radio=10, steps=20)

    c.saveState()
    c.setStrokeColor(colors.white)
    c.setLineWidth(1.5)
    c.roundRect(box_x, box_y, box_w, box_h, 10, fill=0, stroke=1)
    c.restoreState()

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(box_x + box_w / 2, box_y + 1.15 * cm, titulo)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(box_x + box_w / 2, box_y + 0.4 * cm, f"N° {num}")


def dibujar_info_nino_optimizada(c, x, y_base, ctx):
    """Panel con los datos del niño y su tutor."""
    alto_panel = 1.5 * cm

    c.saveState()
    c.setFillColor(COLOR_TURQUESA_CLARO)
    c.setFillAlpha(0.5)
    c.roundRect(x + 0.4 * cm, y_base - alto_panel, ANCHO_RECIBO - 0.8 * cm, alto_panel, 8, fill=1, stroke=0)
    c.restoreState()

    c.saveState()
    c.setStrokeColor(COLOR_TURQUESA)
    c.setLineWidth(0.75)
    c.roundRect(x + 0.4 * cm, y_base - alto_panel, ANCHO_RECIBO - 0.8 * cm, alto_panel, 8, fill=0, stroke=1)
    c.restoreState()

    fecha_str = ctx.fecha.strftime("%d/%m/%Y") if ctx.fecha else "—"

    y_datos = y_base - 0.60 * cm
    x_datos = x + 0.7 * cm

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(COLOR_TURQUESA_OSCURO)
    c.drawString(x_datos, y_datos, "NIÑO/A:")
    c.setFont("Helvetica", 10)
    c.setFillColor(COLOR_TEXTO_PRINCIPAL)
    c.drawString(x_datos + 1.7 * cm, y_datos, ctx.nino_nombre)

    y_datos -= 0.55 * cm
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(COLOR_TURQUESA_OSCURO)
    c.drawString(x_datos, y_datos, "TUTOR:")
    c.setFont("Helvetica", 10)
    c.setFillColor(COLOR_TEXTO_PRINCIPAL)
    c.drawString(x_datos + 1.7 * cm, y_datos, ctx.tutor_nombre)

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(COLOR_TURQUESA_OSCURO)
    c.drawRightString(x + ANCHO_RECIBO - 0.8 * cm, y_base - 0.60 * cm, "FECHA:")
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(COLOR_TEXTO_PRINCIPAL)
    c.drawRightString(x + ANCHO_RECIBO - 0.8 * cm, y_base - 1.15 * cm, fecha_str)


def dibujar_tabla_detalles_optimizada(c, x, y_base, ctx):
    """Tabla con 3 columnas: #, CONCEPTO, MONTO — siempre una sola fila."""
    headers = [["#", "CONCEPTO", "MONTO (Bs.)"]]
    fila = [["1", f"{ctx.concepto} ({ctx.tipo_display})", f"{ctx.monto:,.2f}"]]
    tabla_data = headers + fila

    ancho_tabla = ANCHO_RECIBO - 0.8 * cm
    col_widths = [ancho_tabla * 0.07, ancho_tabla * 0.75, ancho_tabla * 0.18]

    tabla = Table(tabla_data, colWidths=col_widths, repeatRows=1)
    color_header = COLOR_CORAL if ctx.es_devolucion else COLOR_TURQUESA

    estilos_tabla = [
        ('BACKGROUND', (0, 0), (-1, 0), color_header),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (0, 0), 'CENTER'),
        ('ALIGN', (1, 0), (1, 0), 'LEFT'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),
        ('ALIGN', (2, 1), (2, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 1, COLOR_GRIS_MEDIO),
        ('LINEBELOW', (0, 0), (-1, 0), 1.5, colors.white),
        ('INNERGRID', (0, 1), (-1, -1), 0.5, COLOR_GRIS_CLARO),
        ('BACKGROUND', (0, 1), (-1, 1), COLOR_FILA_IMPAR),
    ]
    tabla.setStyle(TableStyle(estilos_tabla))

    w_t, h_t = tabla.wrapOn(c, ancho_tabla, ALTO_RECIBO)
    tabla.drawOn(c, x + 0.4 * cm, y_base - h_t)
    return h_t


def dibujar_nota_si_existe(c, x, y_base, ctx):
    """Observación (pago) o motivo (devolución), si existen."""
    if not ctx.nota or not ctx.nota.strip():
        return 0

    ancho_panel = ANCHO_RECIBO - 0.8 * cm
    padding = 0.3 * cm

    estilo = ParagraphStyle(
        'nota', fontName='Helvetica', fontSize=8,
        textColor=COLOR_TEXTO_PRINCIPAL, leading=10,
    )
    p = Paragraph(ctx.nota, estilo)
    ancho_texto = ancho_panel - (2 * padding)
    w, h = p.wrap(ancho_texto, ALTO_RECIBO)
    altura_panel = h + (2 * padding) + 0.4 * cm

    color_fondo = COLOR_CORAL_CLARO if ctx.es_devolucion else COLOR_AMARILLO_CLARO
    color_borde = COLOR_CORAL if ctx.es_devolucion else COLOR_AMARILLO_OSCURO
    color_titulo = COLOR_CORAL_OSCURO if ctx.es_devolucion else COLOR_AMARILLO_OSCURO

    c.saveState()
    c.setFillColor(color_fondo)
    c.roundRect(x + 0.4 * cm, y_base - altura_panel, ancho_panel, altura_panel, 8, fill=1, stroke=0)
    c.restoreState()
    c.saveState()
    c.setStrokeColor(color_borde)
    c.setLineWidth(0.75)
    c.roundRect(x + 0.4 * cm, y_base - altura_panel, ancho_panel, altura_panel, 8, fill=0, stroke=1)
    c.restoreState()

    titulo = "MOTIVO DE LA DEVOLUCIÓN:" if ctx.es_devolucion else "OBSERVACIÓN:"
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(color_titulo)
    c.drawString(x + 0.4 * cm + padding, y_base - 0.5 * cm, titulo)

    p.drawOn(c, x + 0.4 * cm + padding, y_base - altura_panel + padding)
    return altura_panel


def dibujar_seccion_totales_optimizada(c, x, y_base, ctx):
    """Caja de total + método de pago + quién lo registró."""
    box_w = 5.5 * cm
    box_h = 1.5 * cm
    box_x = x + ANCHO_RECIBO - box_w - 0.5 * cm
    box_y = y_base - box_h

    dibujar_sombra_suave(c, box_x, box_y, box_w, box_h, radio=10, offset=2)
    color_inicio = COLOR_CORAL_CLARO if ctx.es_devolucion else COLOR_AMARILLO_CLARO
    color_fin = COLOR_CORAL if ctx.es_devolucion else COLOR_AMARILLO
    dibujar_gradiente_redondeado(c, box_x, box_y, box_w, box_h, color_inicio, color_fin, radio=10, steps=20)

    c.saveState()
    c.setStrokeColor(COLOR_CORAL if ctx.es_devolucion else COLOR_AMARILLO_OSCURO)
    c.setLineWidth(1.5)
    c.roundRect(box_x, box_y, box_w, box_h, 10, fill=0, stroke=1)
    c.restoreState()

    etiqueta = "TOTAL DEVUELTO" if ctx.es_devolucion else "TOTAL PAGADO"
    c.setFillColor(COLOR_TEXTO_PRINCIPAL)
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(box_x + box_w - 0.4 * cm, box_y + 1.0 * cm, etiqueta)
    c.setFont("Helvetica-Bold", 18)
    c.drawRightString(box_x + box_w - 0.4 * cm, box_y + 0.25 * cm, f"Bs. {ctx.monto:,.2f}")

    monto_literal = monto_a_letras(ctx.monto)
    c.setFillColor(COLOR_TEXTO_SECUNDARIO)
    c.setFont("Helvetica-BoldOblique", 7)
    c.drawRightString(x + ANCHO_RECIBO - 0.5 * cm, y_base - box_h - 0.45 * cm, f"SON: {monto_literal}")

    y_info = y_base - 0.4 * cm
    x_info = x + 0.6 * cm

    c.setFont("Helvetica", 7)
    c.setFillColor(COLOR_VIOLETA_OSCURO)
    c.drawString(x_info, y_info, "MÉTODO DE PAGO:")
    c.setFont("Helvetica", 8)
    c.setFillColor(COLOR_TEXTO_PRINCIPAL)
    c.drawString(x_info, y_info - 0.35 * cm, ctx.metodo_pago_display)

    y_info -= 0.75 * cm
    c.setFont("Helvetica", 7)
    c.setFillColor(COLOR_VIOLETA_OSCURO)
    c.drawString(x_info, y_info, "REGISTRADO POR:")
    c.setFont("Helvetica", 8)
    c.setFillColor(COLOR_TEXTO_PRINCIPAL)
    c.drawString(x_info, y_info - 0.35 * cm, ctx.registrado_por or "—")


def dibujar_qr_optimizado(c, x, y, ctx):
    """QR de verificación (2 cm)."""
    numero = safe_str(ctx.numero_recibo)
    fecha_str = ctx.fecha.strftime("%Y%m%d") if ctx.fecha else "00000000"
    hash_verificacion = generar_hash_verificacion(numero, fecha_str, str(ctx.monto))
    tipo_recibo = 'devolucion' if ctx.es_devolucion else 'pago'
    url_validacion = f"https://kids.neuromisael.com/validar/{tipo_recibo}/{numero}/{hash_verificacion}"

    qr_size = 2.0 * cm
    qr_x = x + ANCHO_RECIBO - qr_size - 0.5 * cm
    qr_y = y + 2.5 * cm

    c.saveState()
    c.setFillColor(colors.white)
    c.setStrokeColor(COLOR_GRIS_MEDIO)
    c.setLineWidth(0.5)
    c.roundRect(qr_x - 0.1 * cm, qr_y - 0.1 * cm, qr_size + 0.2 * cm, qr_size + 0.2 * cm, 4, fill=1, stroke=1)
    c.restoreState()

    crear_qr_code(c, qr_x, qr_y, url_validacion, qr_size)

    c.setFont("Helvetica", 6)
    c.setFillColor(COLOR_TEXTO_SECUNDARIO)
    c.drawCentredString(qr_x + qr_size / 2, qr_y - 0.35 * cm, "Escanea para validar")
    c.setFont("Helvetica-Bold", 6)
    c.setFillColor(COLOR_TEXTO_PRINCIPAL)
    c.drawCentredString(qr_x + qr_size / 2, qr_y - 0.65 * cm, f"#{hash_verificacion}")


def dibujar_footer_optimizado(c, x, y, texto_copia, ctx):
    y_footer = y + 0.35 * cm

    if "FAMILIA" in texto_copia:
        bg_color = COLOR_TURQUESA
        fg_color = colors.white
    else:
        bg_color = COLOR_GRIS_CLARO
        fg_color = COLOR_TEXTO_PRINCIPAL

    badge_w = 6.5 * cm
    badge_h = 0.6 * cm
    badge_x = x + ANCHO_RECIBO / 2 - badge_w / 2

    dibujar_sombra_suave(c, badge_x, y_footer, badge_w, badge_h, radio=8, offset=1)
    c.setFillColor(bg_color)
    c.roundRect(badge_x, y_footer, badge_w, badge_h, 8, fill=1, stroke=0)
    c.setFillColor(fg_color)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(x + ANCHO_RECIBO / 2, y_footer + 0.18 * cm, texto_copia)


def dibujar_seccion_firmas_optimizada(c, x, y, ctx):
    y_firmas = y + 1.6 * cm

    c.saveState()
    c.setStrokeColor(COLOR_GRIS_MEDIO)
    c.setLineWidth(0.5)
    c.setDash([2, 2])

    label_izq = "FIRMA: ENTREGUÉ CONFORME" if ctx.es_devolucion else "FIRMA AUTORIZADA JARDÍN"
    label_der = "FIRMA: RECIBÍ CONFORME" if ctx.es_devolucion else "FIRMA TUTOR/RESPONSABLE"

    c.line(x + 0.8 * cm, y_firmas, x + 4.5 * cm, y_firmas)
    c.setFont("Helvetica", 7)
    c.setFillColor(COLOR_TEXTO_SECUNDARIO)
    c.drawCentredString(x + 2.65 * cm, y_firmas - 0.3 * cm, label_izq)

    c.line(x + ANCHO_RECIBO - 6.5 * cm, y_firmas, x + ANCHO_RECIBO - 2.8 * cm, y_firmas)
    c.drawCentredString(x + ANCHO_RECIBO - 4.65 * cm, y_firmas - 0.3 * cm, label_der)

    c.setDash([])
    c.restoreState()


def dibujar_linea_corte(c):
    x = PAGE_WIDTH / 2
    c.saveState()
    c.setStrokeColor(COLOR_GRIS_MEDIO)
    c.setLineWidth(0.5)
    c.setDash([4, 4])
    c.line(x, MARGIN + 0.5 * cm, x, PAGE_HEIGHT - MARGIN - 0.5 * cm)
    c.setDash([])
    c.restoreState()

    # Tijeritas al centro — otro detalle "para niños" en vez de una
    # línea de corte pelada.
    c.saveState()
    c.setFont("Helvetica", 11)
    c.setFillColor(COLOR_GRIS_MEDIO)
    c.drawCentredString(x, PAGE_HEIGHT / 2, "✂")
    c.restoreState()


# =====================================================
# 7. FUNCIONES AUXILIARES
# =====================================================

def monto_a_letras(monto):
    try:
        monto = Decimal(monto).quantize(Decimal('0.01'))
        entero = int(monto)
        decimal = int(round((monto - entero) * 100))
        letras = numero_a_letras(entero)
        return f"{letras} {decimal:02d}/100 BOLIVIANOS".upper()
    except Exception:
        return "MONTO NO VÁLIDO"


def numero_a_letras(num):
    if num == 0:
        return "CERO"
    unidades = ["", "UN", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE"]
    decenas = ["", "DIEZ", "VEINTE", "TREINTA", "CUARENTA", "CINCUENTA", "SESENTA", "SETENTA", "OCHENTA", "NOVENTA"]
    diez_veinte = ["DIEZ", "ONCE", "DOCE", "TRECE", "CATORCE", "QUINCE", "DIECISEIS", "DIECISIETE", "DIECIOCHO", "DIECINUEVE"]
    veinte_treinta = ["VEINTE", "VEINTIUNO", "VEINTIDOS", "VEINTITRES", "VEINTICUATRO", "VEINTICINCO", "VEINTISEIS", "VEINTISIETE", "VEINTIOCHO", "VEINTINUEVE"]
    centenas = ["", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS", "QUINIENTOS", "SEISCIENTOS", "SETECIENTOS", "OCHOCIENTOS", "NOVECIENTOS"]

    if num < 10:
        return unidades[num]
    if num < 20:
        return diez_veinte[num - 10]
    if num < 30:
        return veinte_treinta[num - 20]
    if num < 100:
        u = num % 10
        return decenas[num // 10] + (" Y " + unidades[u] if u > 0 else "")
    if num == 100:
        return "CIEN"
    if num < 1000:
        return centenas[num // 100] + (" " + numero_a_letras(num % 100) if num % 100 > 0 else "")
    if num < 1000000:
        miles = num // 1000
        resto = num % 1000
        texto_miles = "MIL" if miles == 1 else numero_a_letras(miles) + " MIL"
        return texto_miles + (" " + numero_a_letras(resto) if resto > 0 else "")
    if num < 1000000000:
        millones = num // 1000000
        resto = num % 1000000
        texto_millones = "UN MILLON" if millones == 1 else numero_a_letras(millones) + " MILLONES"
        return texto_millones + (" " + numero_a_letras(resto) if resto > 0 else "")
    return str(num)


def safe_str(val):
    return "" if val is None else str(val)


def safe_decimal(val):
    if val is None:
        return Decimal(0)
    try:
        return Decimal(val)
    except Exception:
        return Decimal(0)


def dibujar_imagen_ninos(c, x, y, ctx):
    """
    Imagen decorativa (siluetas de niños jugando) en la franja que queda
    vacía entre la sección de total y el QR/firmas. Se ancla desde abajo
    (y = base del recibo) para no depender de cuánto ocupe el contenido de
    arriba (que varía si hay observación/motivo) — así nunca choca con
    texto ni con el QR.
    """
    imagen_path = encontrar_imagen_ninos()
    if not imagen_path:
        return
    try:
        img = ImageReader(imagen_path)
        iw, ih = img.getSize()
        aspect = ih / float(iw)
        img_w = 6.0 * cm
        img_h = img_w * aspect
        img_x = x + (ANCHO_RECIBO - img_w) / 2
        img_y = y + 5.2 * cm
        c.saveState()
        c.setFillAlpha(0.92)
        c.drawImage(imagen_path, img_x, img_y, width=img_w, height=img_h,
                    mask='auto', preserveAspectRatio=True)
        c.restoreState()
    except Exception as e:
        logger.error(f"Error dibujando imagen decorativa: {e}")


def encontrar_imagen_ninos():
    base_dir = settings.BASE_DIR
    rutas = [
        base_dir / 'frontend' / 'img' / 'ninos_decoracion.png',
        base_dir / 'staticfiles' / 'img' / 'ninos_decoracion.png',
        base_dir / 'static' / 'img' / 'ninos_decoracion.png',
    ]
    for ruta in rutas:
        if os.path.exists(ruta):
            return str(ruta)
    return None


def encontrar_logo_misael_kids():
    """Busca el logo en las ubicaciones típicas del proyecto Misael Kids."""
    base_dir = settings.BASE_DIR
    rutas = [
        base_dir / 'frontend' / 'img' / 'logo_recibo.jpg',
        base_dir / 'staticfiles' / 'img' / 'logo_recibo.jpg',
        base_dir / 'static' / 'img' / 'logo_recibo.jpg',
    ]
    for ruta in rutas:
        if os.path.exists(ruta):
            return str(ruta)
    return None
