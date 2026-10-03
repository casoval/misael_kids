# reportes/pdf_reportes.py
# =====================================================
# PDF DE REPORTES — JARDÍN INFANTIL MISAEL KIDS
# Mismo estilo "Jardín mágico" que los recibos (barra arcoíris, logo,
# paleta turquesa/coral/amarillo/verde/violeta), pero pensado para LEER:
# resumen arriba con cifras grandes, tablas con filas alternadas y los
# filtros usados siempre visibles en la primera página.
#
# Cada generador recibe (filtros, usuario) y devuelve
# (bytes_del_pdf, nombre_de_archivo, cantidad_de_filas).
# =====================================================
import logging
from datetime import date
from io import BytesIO

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

from asistencia.models import Asistencia
from core.models import Sala, Sucursal
from accounts.models import Usuario
from inscripciones.models import Cobro
from inscripciones.pdf_generator import (
    COLOR_AMARILLO, COLOR_AMARILLO_CLARO, COLOR_CORAL, COLOR_CORAL_CLARO, COLOR_CORAL_OSCURO,
    COLOR_FILA_PAR, COLOR_GRIS_BORDE, COLOR_GRIS_CLARO, COLOR_GRIS_MEDIO, COLOR_NARANJA,
    COLOR_TEXTO_PRINCIPAL, COLOR_TEXTO_SECUNDARIO, COLOR_TURQUESA, COLOR_TURQUESA_CLARO,
    COLOR_TURQUESA_OSCURO, COLOR_VERDE, COLOR_VERDE_CLARO, COLOR_VERDE_OSCURO, COLOR_VIOLETA,
    COLOR_VIOLETA_CLARO, COLOR_VIOLETA_OSCURO, LEMA_CENTRO, encontrar_logo_misael_kids,
)
from . import services
from .services import CERO, METODOS

logger = logging.getLogger(__name__)

MARGEN = 1.3 * cm
MAX_FILAS_DETALLE = 3000           # tope de seguridad para que un PDF no crezca sin límite

# ── Estilos de texto ──────────────────────────────────────────────
def _estilo(nombre, **kw):
    base = dict(fontName='Helvetica', fontSize=8.5, leading=10.5, textColor=COLOR_TEXTO_PRINCIPAL)
    base.update(kw)
    return ParagraphStyle(nombre, **base)


ST_CELDA = _estilo('celda')
ST_CELDA_DER = _estilo('celda_der', alignment=2)
ST_CELDA_CEN = _estilo('celda_cen', alignment=1)
ST_CABECERA = _estilo('cabecera', fontName='Helvetica-Bold', fontSize=8, textColor=colors.white, leading=10)
ST_CABECERA_DER = _estilo('cabecera_der', fontName='Helvetica-Bold', fontSize=8, textColor=colors.white,
                          leading=10, alignment=2)
ST_NOTA = _estilo('nota', fontSize=7.5, leading=9.5, textColor=COLOR_GRIS_MEDIO)
ST_VACIO = _estilo('vacio', fontSize=9, textColor=COLOR_GRIS_MEDIO, alignment=1)


def bs(valor):
    return f'Bs. {valor or CERO:,.2f}'


def num(valor):
    return f'{valor or CERO:,.2f}'


def pct(valor):
    if valor is None:
        return '—'
    return f'{valor:g}%'


def _esc(texto):
    return (str(texto if texto is not None else '')
            .replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


# ── Lienzo con numeración "Página x de y" y barra arcoíris ─────────
class _Lienzo(pdf_canvas.Canvas):
    titulo_pie = ''
    pie_generado = ''

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._paginas = []

    def showPage(self):
        self._paginas.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._paginas)
        for estado in self._paginas:
            self.__dict__.update(estado)
            self._decorar(total)
            super().showPage()
        super().save()

    def _decorar(self, total):
        ancho, alto = self._pagesize
        franjas = [COLOR_TURQUESA, COLOR_VERDE, COLOR_AMARILLO, COLOR_NARANJA, COLOR_CORAL]
        w = ancho / len(franjas)
        for i, color in enumerate(franjas):
            self.setFillColor(color)
            self.rect(i * w, alto - 0.38 * cm, w + 1, 0.38 * cm, fill=1, stroke=0)
        self.setStrokeColor(COLOR_GRIS_BORDE)
        self.setLineWidth(0.4)
        self.line(MARGEN, 1.05 * cm, ancho - MARGEN, 1.05 * cm)
        self.setFont('Helvetica', 7)
        self.setFillColor(COLOR_GRIS_MEDIO)
        self.drawString(MARGEN, 0.72 * cm, f'Jardín Infantil Misael Kids · {self.titulo_pie}')
        self.drawString(MARGEN, 0.40 * cm, self.pie_generado)
        self.drawRightString(ancho - MARGEN, 0.72 * cm, f'Página {self._pageNumber} de {total}')


# ── Piezas reutilizables ──────────────────────────────────────────
class Informe:
    """Arma un PDF por partes: encabezado, filtros, cifras, secciones y tablas."""

    def __init__(self, titulo, subtitulo, color, color_claro, usuario, horizontal=False, nombre_sucursal=''):
        self.titulo, self.subtitulo = titulo, subtitulo
        self.color, self.color_claro = color, color_claro
        self.pagesize = landscape(letter) if horizontal else letter
        self.ancho = self.pagesize[0] - 2 * MARGEN
        self.historia = []
        self.usuario = usuario
        self.nombre_sucursal = nombre_sucursal
        self._encabezado()

    # -- encabezado: logo + nombre del jardín + caja con el título del informe
    def _encabezado(self):
        logo = encontrar_logo_misael_kids()
        celda_logo = ''
        if logo:
            try:
                iw, ih = ImageReader(logo).getSize()
                from reportlab.platypus import Image
                celda_logo = Image(logo, width=2.6 * cm, height=2.6 * cm * ih / float(iw))
            except Exception as e:                      # el logo es decorativo: nunca debe romper el reporte
                logger.error('Error cargando logo del reporte: %s', e)
        nombre = Paragraph(
            '<font size="12.5" color="#1E293B"><b>Jardín Infantil </b></font>'
            '<font size="16" color="#0D9488"><b>Misael Kids</b></font><br/>'
            f'<font size="7.5" color="#7C3AED"><i>{_esc(LEMA_CENTRO)}</i></font><br/>'
            f'<font size="7.5" color="#3D3D3D">{_esc(self.nombre_sucursal)}</font>',
            _estilo('enc_nombre', leading=15))
        caja = Table([[Paragraph(f'<font color="white" size="7.5"><b>INFORME</b></font>',
                                 _estilo('enc_chico', alignment=1, leading=9))],
                      [Paragraph(f'<font color="white" size="13"><b>{_esc(self.titulo)}</b></font>',
                                 _estilo('enc_titulo', alignment=1, leading=15))]],
                     colWidths=[6.2 * cm])
        caja.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), self.color), ('ROUNDEDCORNERS', [8, 8, 8, 8]),
            ('TOPPADDING', (0, 0), (-1, 0), 6), ('BOTTOMPADDING', (0, 1), (-1, 1), 7),
            ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        t = Table([[celda_logo, nombre, caja]], colWidths=[3.2 * cm, self.ancho - 3.2 * cm - 6.4 * cm, 6.4 * cm])
        t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                               ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
        self.historia += [t, Spacer(1, 0.25 * cm)]

    def filtros(self, pares):
        """Caja con los filtros usados: [('Período', 'Octubre 2026'), ('Sucursal', 'Todas'), …]."""
        texto = '  ·  '.join(f'<b>{_esc(k)}:</b> {_esc(v)}' for k, v in pares if v)
        t = Table([[Paragraph(texto, _estilo('filtros', fontSize=8.5, leading=11))]], colWidths=[self.ancho])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), self.color_claro), ('BOX', (0, 0), (-1, -1), 0.6, self.color),
            ('ROUNDEDCORNERS', [6, 6, 6, 6]), ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5), ('LEFTPADDING', (0, 0), (-1, -1), 8)]))
        self.historia += [t, Spacer(1, 0.3 * cm)]

    def cifras(self, items, por_fila=4):
        """Tarjetas con cifras grandes. items: [(etiqueta, valor, nota, color, color_claro)]."""
        filas = [items[i:i + por_fila] for i in range(0, len(items), por_fila)]
        for fila in filas:
            ancho_col = self.ancho / por_fila
            celdas = []
            for etq, valor, nota, color, claro in fila:
                celdas.append(Table(
                    [[Paragraph(f'<font size="7.5" color="#3D3D3D"><b>{_esc(etq)}</b></font>', _estilo('k1', leading=9))],
                     [Paragraph(f'<font size="15" color="{color.hexval().replace("0x", "#")}"><b>{_esc(valor)}</b></font>',
                                _estilo('k2', leading=18))],
                     [Paragraph(f'<font size="7" color="#888888">{_esc(nota)}</font>', _estilo('k3', leading=8.5))]],
                    colWidths=[ancho_col - 0.3 * cm],
                    style=TableStyle([('BACKGROUND', (0, 0), (-1, -1), claro), ('BOX', (0, 0), (-1, -1), 0.8, color),
                                      ('ROUNDEDCORNERS', [7, 7, 7, 7]), ('TOPPADDING', (0, 0), (-1, -1), 2),
                                      ('BOTTOMPADDING', (0, 0), (-1, -1), 2), ('LEFTPADDING', (0, 0), (-1, -1), 7)])))
            while len(celdas) < por_fila:
                celdas.append('')
            t = Table([celdas], colWidths=[ancho_col] * por_fila)
            t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                                   ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
            self.historia += [t, Spacer(1, 0.2 * cm)]

    def seccion(self, titulo, nota=None):
        barra = Table([[Paragraph(f'<b>{_esc(titulo)}</b>', _estilo('sec', fontSize=11, leading=13)), '']],
                      colWidths=[self.ancho, 0])
        barra.setStyle(TableStyle([('LINEBEFORE', (0, 0), (0, 0), 4, self.color), ('LEFTPADDING', (0, 0), (0, 0), 7),
                                   ('TOPPADDING', (0, 0), (-1, -1), 1), ('BOTTOMPADDING', (0, 0), (-1, -1), 1)]))
        bloque = [Spacer(1, 0.2 * cm), barra]
        if nota:
            bloque.append(Paragraph(_esc(nota), ST_NOTA))
        bloque.append(Spacer(1, 0.12 * cm))
        self.historia += bloque

    def tabla(self, cabecera, filas, anchos, derecha=(), centro=(), total=None, vacio='Sin registros en este período.',
              resaltar=None):
        """
        cabecera: textos; filas: listas de valores (str/Paragraph); anchos: fracciones que suman ~1;
        derecha/centro: índices de columnas alineadas; total: fila final en negrita;
        resaltar: función(fila_idx, fila) → color de fondo o None.
        """
        if not filas:
            self.historia += [Paragraph(_esc(vacio), ST_VACIO), Spacer(1, 0.2 * cm)]
            return
        suma = sum(anchos)
        col = [self.ancho * a / suma for a in anchos]

        def celda(v, i, cab=False):
            if not isinstance(v, str):
                v = '' if v is None else str(v)
            est = (ST_CABECERA_DER if i in derecha else ST_CABECERA) if cab else (
                ST_CELDA_DER if i in derecha else ST_CELDA_CEN if i in centro else ST_CELDA)
            return Paragraph(_esc(v), est)

        data = [[celda(c, i, True) for i, c in enumerate(cabecera)]]
        data += [[celda(v, i) for i, v in enumerate(f)] for f in filas]
        if total:
            en_negrita = lambda v, i: Paragraph(f'<b>{_esc(v)}</b>', ST_CELDA_DER if i in derecha else ST_CELDA)
            data.append([en_negrita(v, i) for i, v in enumerate(total)])
        t = Table(data, colWidths=col, repeatRows=1)
        estilo = [
            ('BACKGROUND', (0, 0), (-1, 0), self.color),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3.2), ('BOTTOMPADDING', (0, 0), (-1, -1), 3.2),
            ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('LINEBELOW', (0, 0), (-1, -1), 0.25, COLOR_GRIS_CLARO),
            ('BOX', (0, 0), (-1, -1), 0.5, COLOR_GRIS_BORDE),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1 - (1 if total else 0)), [colors.white, COLOR_FILA_PAR]),
        ]
        if total:
            estilo += [('BACKGROUND', (0, -1), (-1, -1), self.color_claro), ('LINEABOVE', (0, -1), (-1, -1), 0.8, self.color)]
        if resaltar:
            for idx, f in enumerate(filas, start=1):
                fondo = resaltar(idx - 1, f)
                if fondo is not None:
                    estilo.append(('BACKGROUND', (0, idx), (-1, idx), fondo))
        t.setStyle(TableStyle(estilo))
        self.historia += [t, Spacer(1, 0.25 * cm)]

    def nota(self, texto):
        self.historia += [Paragraph(_esc(texto), ST_NOTA), Spacer(1, 0.1 * cm)]

    def firmas(self, etiquetas):
        ancho = self.ancho / len(etiquetas)
        celdas = [[Paragraph(f'<para alignment="center">_______________________________<br/>{_esc(e)}</para>',
                             _estilo('firma', fontSize=8, leading=11)) for e in etiquetas]]
        t = Table(celdas, colWidths=[ancho] * len(etiquetas))
        t.setStyle(TableStyle([('TOPPADDING', (0, 0), (-1, -1), 26)]))
        self.historia.append(KeepTogether([Spacer(1, 0.5 * cm), t]))

    def construir(self, titulo_pie):
        buffer = BytesIO()
        doc = BaseDocTemplate(buffer, pagesize=self.pagesize, leftMargin=MARGEN, rightMargin=MARGEN,
                              topMargin=0.9 * cm, bottomMargin=1.5 * cm, title=f'{self.titulo} — {titulo_pie}',
                              author='Jardín Infantil Misael Kids')
        marco = Frame(MARGEN, 1.5 * cm, self.ancho, self.pagesize[1] - 0.9 * cm - 1.5 * cm, id='cuerpo',
                      leftPadding=0, rightPadding=0, topPadding=0.2 * cm, bottomPadding=0)
        doc.addPageTemplates([PageTemplate(id='base', frames=[marco])])
        quien = self.usuario.nombre_completo if self.usuario else ''

        class Lienzo(_Lienzo):
            pass
        Lienzo.titulo_pie = titulo_pie
        Lienzo.pie_generado = f'Generado el {timezone.localtime():%d/%m/%Y %H:%M}' + (f' por {quien}' if quien else '')
        doc.build(self.historia, canvasmaker=Lienzo)
        return buffer.getvalue()


# ── Textos de filtros ─────────────────────────────────────────────
def _nombre(modelo, pk, campo='nombre'):
    if not pk:
        return None
    obj = modelo.objects.filter(pk=pk).first()
    return getattr(obj, campo, None) if obj else None


def _sucursal(f):
    return _nombre(Sucursal, f.sucursal) or 'Todas las sucursales'


def _filtros_base(f, con_sala=False, con_periodo=True):
    pares = []
    if con_periodo:
        pares.append(('Período', f.etiqueta))
    pares.append(('Sucursal', _sucursal(f)))
    if con_sala and f.sala:
        pares.append(('Sala', _nombre(Sala, f.sala) or '—'))
    return pares


def _fecha_hora(dt):
    return timezone.localtime(dt).strftime('%d/%m %H:%M') if dt else ''


# ══════════════════════════════════════════════════════════════════
#  1. INFORME ECONÓMICO
# ══════════════════════════════════════════════════════════════════
def informe_economico(f, usuario):
    cobros = services.resumen_cobros_del_periodo(f.desde, f.hasta, f.sucursal)
    from inscripciones.services import resumen_financiero_rango
    caja = resumen_financiero_rango(f.desde, f.hasta, f.sucursal)
    cierre = services.cierre_caja(f.desde, f.hasta, f.sucursal)
    deudas = services.listar_deudas(f.sucursal)
    cm = caja['caja_mes']

    r = Informe('Económico', '', COLOR_VERDE_OSCURO, COLOR_VERDE_CLARO, usuario, nombre_sucursal=_sucursal(f))
    r.filtros(_filtros_base(f))
    r.cifras([
        ('Dinero que entró (neto)', bs(cm['neto']), f"{cm['cantidad_pagos']} cobro(s) · {cm['cantidad_devoluciones']} devolución(es)",
         COLOR_VERDE_OSCURO, COLOR_VERDE_CLARO),
        ('Cobros emitidos', bs(cobros['emitido']), f"{cobros['cantidad']} cobro(s) en el período", COLOR_TURQUESA_OSCURO, COLOR_TURQUESA_CLARO),
        ('Falta cobrar de lo emitido', bs(cobros['saldo']), f"{pct(cobros['porcentaje_cobrado'])} ya cobrado", COLOR_NARANJA, COLOR_AMARILLO_CLARO),
        ('Niños con deuda hoy', bs(deudas['monto']), f"{deudas['cantidad']} niño(s) no están al día", COLOR_CORAL_OSCURO, COLOR_CORAL_CLARO),
    ])

    r.seccion('Dinero recibido por método de pago',
              'Lo que realmente entró y salió de caja en el período. Los abonos aplicados a días y los traspasos entre cuentas no se cuentan dos veces.')
    filas = [[m['etiqueta'], f"{m['cantidad_ingresos']}", num(m['ingresos']), f"{m['cantidad_devoluciones']}",
              num(m['devoluciones']), num(m['neto'])] for m in cierre['metodos']]
    t = cierre['total']
    r.tabla(['Método', 'Cobros', 'Recibido (Bs.)', 'Devol.', 'Devuelto (Bs.)', 'Neto (Bs.)'], filas,
            [3, 1.2, 2.2, 1.2, 2.2, 2.2], derecha={1, 2, 3, 4, 5},
            total=['TOTAL', f"{t['cantidad_ingresos']}", num(t['ingresos']), f"{t['cantidad_devoluciones']}",
                   num(t['devoluciones']), num(t['neto'])])

    if (f.hasta - f.desde).days <= 62 and len(cierre['por_dia']) > 1:
        r.seccion('Ingresos día por día')
        filas = [[date.fromisoformat(d['fecha']).strftime('%d/%m/%Y'),
                  *[num(d['metodos'].get(k)) for k, _ in METODOS], num(d['total']['neto'])] for d in cierre['por_dia']]
        r.tabla(['Fecha', *[e for _, e in METODOS], 'Total (Bs.)'], filas, [2.4, 2, 2, 2, 2], derecha={1, 2, 3, 4},
                total=['TOTAL', *[num(next((m['neto'] for m in cierre['metodos'] if m['metodo'] == k), CERO)) for k, _ in METODOS],
                       num(t['neto'])])

    r.seccion('Cobros emitidos en el período', 'Emitido = cobrado + condonado + falta cobrar. No incluye cobros anulados.')
    nombres_est = dict(Cobro.ESTADOS)
    filas = [[nombres_est[e], str(v['cantidad']), num(v['monto'])] for e, v in cobros['por_estado'].items() if v['cantidad']]
    r.tabla(['Estado', 'Cantidad', 'Monto (Bs.)'], filas, [4, 1.5, 2.5], derecha={1, 2})
    nombres_tipo = dict(Cobro.TIPOS)
    filas = [[nombres_tipo[k], str(v['cantidad']), num(v['emitido'])] for k, v in cobros['por_tipo'].items() if v['cantidad']]
    if filas:
        r.tabla(['Tipo de cobro', 'Cantidad', 'Emitido (Bs.)'], filas, [4, 1.5, 2.5], derecha={1, 2})
    filas = [['Emitido', num(cobros['emitido'])], ['Cobrado (neto de devoluciones)', num(cobros['cobrado'])],
             ['Condonado', num(cobros['condonado'])], ['Falta cobrar', num(cobros['saldo'])]]
    r.tabla(['Resumen', 'Bs.'], filas, [5, 2], derecha={1})

    r.seccion('Cartera de hoy', 'Foto del día de hoy, de todos los meses (no depende del período elegido).')
    filas = [['Cobros abiertos por cobrar', str(caja['pendiente']['cantidad']), num(caja['pendiente']['monto'])],
             ['De ese total, ya vencidos', str(caja['vencido']['cantidad']), num(caja['vencido']['monto'])],
             ['Niños que no están al día (por adelantado)', str(deudas['cantidad']), num(deudas['monto'])]]
    r.tabla(['Concepto', 'Cantidad', 'Bs.'], filas, [5, 1.5, 2], derecha={1, 2})

    if deudas['filas']:
        r.seccion('Mayores deudas', 'Los 10 niños que más deben. El listado completo está en el informe "Deudas".')
        filas = [[x['nino'], x['sala'], x['modalidad'], x['tutor'] or '—', x['telefono'] or '—', num(x['debe'])]
                 for x in deudas['filas'][:10]]
        r.tabla(['Niño', 'Sala', 'Modalidad', 'Tutor', 'Teléfono', 'Debe (Bs.)'], filas, [3, 2, 1.8, 2.6, 1.6, 1.6], derecha={5})
    return r.construir(f'Informe económico · {f.etiqueta}'), f'informe_economico_{f.sufijo}.pdf', cobros['cantidad']


# ══════════════════════════════════════════════════════════════════
#  2. CIERRE DE CAJA
# ══════════════════════════════════════════════════════════════════
def cierre_de_caja(f, usuario):
    c = services.cierre_caja(f.desde, f.hasta, f.sucursal, f.usuario, f.metodo, con_detalle=True)
    por = {m['metodo']: m for m in c['metodos']}
    colores = {'efectivo': (COLOR_VERDE_OSCURO, COLOR_VERDE_CLARO, 'Efectivo en caja'),
               'transferencia': (COLOR_TURQUESA_OSCURO, COLOR_TURQUESA_CLARO, 'Transferencias a verificar en el banco'),
               'qr': (COLOR_VIOLETA_OSCURO, COLOR_VIOLETA_CLARO, 'Pagos QR a verificar en el banco')}

    r = Informe('Cierre de caja', '', COLOR_VIOLETA_OSCURO, COLOR_VIOLETA_CLARO, usuario, horizontal=True,
                nombre_sucursal=_sucursal(f))
    pares = _filtros_base(f)
    if f.usuario:
        pares.append(('Registrado por', _nombre(Usuario, f.usuario, 'nombre_completo') or '—'))
    if f.metodo:
        pares.append(('Método', dict(METODOS).get(f.metodo, f.metodo)))
    r.filtros(pares)

    items = []
    for k, etq in METODOS:
        m = por[k]
        col, claro, nota = colores[k]
        items.append((f'DEBE DEJAR EN {etq.upper()}', bs(m['neto']),
                      f"Recibido {num(m['ingresos'])} - devuelto {num(m['devoluciones'])}", col, claro))
    items.append(('TOTAL DEL PERÍODO', bs(c['total']['neto']),
                  f"{c['total']['cantidad_ingresos']} cobro(s) · {c['total']['cantidad_devoluciones']} devolución(es)",
                  COLOR_TEXTO_PRINCIPAL, COLOR_GRIS_CLARO))
    r.cifras(items)
    r.nota('Efectivo: es el dinero que debe estar físicamente en la caja. Transferencia y QR: no están en la caja, '
           'se comprueban contra el extracto del banco. Una devolución en efectivo resta del efectivo. '
           'No se cuentan los abonos ya aplicados a días ni los traspasos entre cuentas de un mismo niño.')

    if len(c['por_dia']) > 1:
        r.seccion('Movimiento día por día')
        filas = [[date.fromisoformat(d['fecha']).strftime('%d/%m/%Y'), str(d['total']['cantidad_ingresos'] + d['total']['cantidad_devoluciones']),
                  *[num(d['metodos'].get(k)) for k, _ in METODOS], num(d['total']['neto'])] for d in c['por_dia']]
        r.tabla(['Fecha', 'Mov.', *[f'{e} (Bs.)' for _, e in METODOS], 'Total (Bs.)'], filas, [2.2, 1, 2, 2, 2, 2],
                derecha={1, 2, 3, 4, 5},
                total=['TOTAL', str(c['total']['cantidad_ingresos'] + c['total']['cantidad_devoluciones']),
                       *[num(por[k]['neto']) for k, _ in METODOS], num(c['total']['neto'])])

    if len(c['por_usuario']) > 1 or (c['por_usuario'] and not f.usuario):
        r.seccion('Por persona que registró el dinero', 'Para saber quién debe entregar cuánto.')
        filas = [[u['usuario'], *[num(u['metodos'].get(k)) for k, _ in METODOS], num(u['total']['neto'])] for u in c['por_usuario']]
        r.tabla(['Registró', *[f'{e} (Bs.)' for _, e in METODOS], 'Total (Bs.)'], filas, [3.2, 2, 2, 2, 2], derecha={1, 2, 3, 4})

    r.seccion('Detalle de cada movimiento')
    movs = c['movimientos'][:MAX_FILAS_DETALLE]
    nombres = dict(METODOS)
    filas = [[f"{m['fecha']:%d/%m/%Y} {_fecha_hora(m['creado'])[6:]}", m['tipo_display'], f"{m['recibo']:06d}" if m['recibo'] else '—',
              m['nino'], m['concepto'], nombres.get(m['metodo'], m['metodo']),
              num(m['monto']) if m['signo'] > 0 else '', num(m['monto']) if m['signo'] < 0 else '', m['usuario']] for m in movs]
    r.tabla(['Fecha y hora', 'Tipo', 'Recibo', 'Niño', 'Concepto', 'Método', 'Ingreso', 'Devol.', 'Registró'], filas,
            [1.7, 1.1, 0.9, 2.5, 3, 1.3, 1.1, 1.1, 1.7], derecha={6, 7}, centro={2},
            total=['', '', '', '', '', 'TOTALES', num(c['total']['ingresos']), num(c['total']['devoluciones']), ''],
            resaltar=lambda i, fila: COLOR_CORAL_CLARO if fila[1] == 'Devolución' else None,
            vacio='No hubo movimientos de dinero en este período.')
    if len(c['movimientos']) > MAX_FILAS_DETALLE:
        r.nota(f'Se muestran los primeros {MAX_FILAS_DETALLE} movimientos; los totales de arriba sí incluyen todos.')

    r.seccion('Conteo y firmas')
    contado = Table([[Paragraph('<b>Efectivo contado (Bs.):</b> ______________', ST_CELDA),
                      Paragraph('<b>Diferencia (Bs.):</b> ______________', ST_CELDA),
                      Paragraph('<b>Observaciones:</b> ______________________________', ST_CELDA)]],
                    colWidths=[r.ancho * .3, r.ancho * .25, r.ancho * .45])
    r.historia.append(contado)
    r.firmas(['Entrega (recepción)', 'Recibe (administración)'])
    return r.construir(f'Cierre de caja · {f.etiqueta}'), f'cierre_caja_{f.sufijo}.pdf', len(c['movimientos'])


# ══════════════════════════════════════════════════════════════════
#  3. ASISTENCIA
# ══════════════════════════════════════════════════════════════════
def informe_asistencia(f, usuario):
    res = services.resumen_asistencia(f.desde, f.hasta, f.sucursal, f.sala)
    f_sin_estado = services.Filtros(**{**f.__dict__, 'estado': None})
    por_nino = {}
    for a in services.consulta_asistencia(f_sin_estado):
        i = a.inscripcion
        x = por_nino.setdefault(i.id, {'nino': i.nino.nombre_completo, 'sala': i.sala.nombre, 'turno': i.turno.nombre,
                                       'presente': 0, 'ausente': 0, 'justificado': 0})
        x['presente' if a.estado == Asistencia.ESTADO_PRESENTE else
          'justificado' if a.estado == Asistencia.ESTADO_AUSENTE_JUSTIFICADO else 'ausente'] += 1
    ninos = sorted(por_nino.values(), key=lambda x: (x['sala'], x['nino']))

    r = Informe('Asistencia', '', COLOR_TURQUESA_OSCURO, COLOR_TURQUESA_CLARO, usuario, horizontal=True,
                nombre_sucursal=_sucursal(f))
    pares = _filtros_base(f, con_sala=True)
    if f.estado:
        pares.append(('Detalle de', dict(Asistencia.ESTADOS).get(f.estado, f.estado)))
    r.filtros(pares)
    r.cifras([
        ('Asistencia', pct(res['porcentaje']), f"{res['presentes']} presentes de {res['total']} registros", COLOR_TURQUESA_OSCURO, COLOR_TURQUESA_CLARO),
        ('Presentes', str(res['presentes']), 'registros', COLOR_VERDE_OSCURO, COLOR_VERDE_CLARO),
        ('Ausentes justificados', str(res['justificados']), 'avisaron con permiso', COLOR_NARANJA, COLOR_AMARILLO_CLARO),
        ('Ausentes sin justificar', str(res['ausentes']), 'faltas', COLOR_CORAL_OSCURO, COLOR_CORAL_CLARO),
    ])
    r.seccion('Asistencia por sala')
    filas = [[s['sala_nombre'], str(s['presentes']), str(s['justificados']), str(s['ausentes']), str(s['total']), pct(s['porcentaje'])]
             for s in res['por_sala']]
    r.tabla(['Sala', 'Presentes', 'Justificados', 'Ausentes', 'Total', '% asistencia'], filas, [4, 1.4, 1.4, 1.4, 1.2, 1.5],
            derecha={1, 2, 3, 4, 5},
            total=['TOTAL', str(res['presentes']), str(res['justificados']), str(res['ausentes']), str(res['total']), pct(res['porcentaje'])],
            vacio='Sin registros de asistencia en este período.')

    r.seccion('Asistencia de cada niño', 'Las filas en rojo claro son niños con asistencia menor al 60%.')
    def porcentaje(x):
        t = x['presente'] + x['ausente'] + x['justificado']
        return round(x['presente'] * 100 / t, 1) if t else None
    filas = [[x['nino'], x['sala'], x['turno'], str(x['presente']), str(x['justificado']), str(x['ausente']),
              str(x['presente'] + x['ausente'] + x['justificado']), pct(porcentaje(x))] for x in ninos]
    r.tabla(['Niño', 'Sala', 'Turno', 'Presente', 'Justif.', 'Ausente', 'Total', '%'], filas,
            [3.6, 2.2, 1.8, 1.1, 1.1, 1.1, 1, 1], derecha={3, 4, 5, 6, 7},
            resaltar=lambda i, fila: COLOR_CORAL_CLARO if (porcentaje(ninos[i]) or 100) < 60 else None,
            vacio='Sin registros de asistencia en este período.')

    if f.estado:
        qs = list(services.consulta_asistencia(f)[:MAX_FILAS_DETALLE + 1])
        r.seccion(f"Detalle: {dict(Asistencia.ESTADOS).get(f.estado, f.estado)}")
        filas = [[a.fecha.strftime('%d/%m/%Y'), a.inscripcion.nino.nombre_completo, a.inscripcion.sala.nombre,
                  a.inscripcion.turno.nombre, services._hora(a.hora_entrada) or '—', services._hora(a.hora_salida) or '—',
                  a.motivo_ausencia or ''] for a in qs[:MAX_FILAS_DETALLE]]
        r.tabla(['Fecha', 'Niño', 'Sala', 'Turno', 'Entrada', 'Salida', 'Motivo de ausencia'], filas,
                [1.4, 3, 2, 1.8, 1, 1, 3.2], centro={4, 5}, vacio='Ningún registro con ese estado.')
        if len(qs) > MAX_FILAS_DETALLE:
            r.nota(f'Se muestran los primeros {MAX_FILAS_DETALLE} registros.')
    return r.construir(f'Asistencia · {f.etiqueta}'), f'asistencia_{f.sufijo}.pdf', len(ninos)


# ══════════════════════════════════════════════════════════════════
#  4. COBROS
# ══════════════════════════════════════════════════════════════════
def informe_cobros(f, usuario):
    cobros = list(services.consulta_cobros(f)[:MAX_FILAS_DETALLE + 1])
    recortado = len(cobros) > MAX_FILAS_DETALLE
    cobros = cobros[:MAX_FILAS_DETALLE]
    filas, emitido = [], CERO
    pagado_t = saldo_t = CERO
    for c in cobros:
        pagado, saldo = services.pagado_y_saldo(c)
        if c.estado != Cobro.ESTADO_ANULADO:
            emitido += c.monto_final
            pagado_t += pagado
            saldo_t += saldo
        i = c.inscripcion
        filas.append([c.fecha_emision.strftime('%d/%m/%Y'), i.nino.nombre_completo, i.sala.nombre, c.get_tipo_display(),
                      c.periodo if c.tipo != Cobro.TIPO_MENSUALIDAD else f'{c.periodo_inicio:%d/%m/%Y}' if c.periodo_inicio else c.periodo,
                      num(c.monto_final), num(pagado), num(saldo), c.get_estado_display()])

    r = Informe('Cobros', '', COLOR_NARANJA, COLOR_AMARILLO_CLARO, usuario,
                horizontal=True, nombre_sucursal=_sucursal(f))
    pares = _filtros_base(f, con_sala=True)
    if f.estado:
        pares.append(('Estado', dict(Cobro.ESTADOS).get(f.estado, f.estado)))
    if f.tipo:
        pares.append(('Tipo', dict(Cobro.TIPOS).get(f.tipo, f.tipo)))
    pares.append(('Fecha usada', 'fecha de emisión del cobro'))
    r.filtros(pares)
    r.cifras([
        ('Cobros', str(len(cobros)), 'en la lista', COLOR_TEXTO_PRINCIPAL, COLOR_GRIS_CLARO),
        ('Emitido', bs(emitido), 'sin anulados', COLOR_TURQUESA_OSCURO, COLOR_TURQUESA_CLARO),
        ('Cobrado', bs(pagado_t), 'neto de devoluciones', COLOR_VERDE_OSCURO, COLOR_VERDE_CLARO),
        ('Falta cobrar', bs(saldo_t), 'saldo pendiente', COLOR_CORAL_OSCURO, COLOR_CORAL_CLARO),
    ])
    r.seccion('Lista de cobros')
    def fondo(i, fila):
        return COLOR_CORAL_CLARO if fila[8] == 'Vencido' else None
    r.tabla(['Emisión', 'Niño', 'Sala', 'Tipo', 'Período', 'Monto', 'Pagado', 'Saldo', 'Estado'], filas,
            [1.3, 3, 2, 1.4, 1.8, 1.1, 1.1, 1.1, 1.3], derecha={5, 6, 7}, resaltar=fondo,
            total=['', '', '', '', 'TOTALES', num(emitido), num(pagado_t), num(saldo_t), ''],
            vacio='No hay cobros con esos filtros.')
    if recortado:
        r.nota(f'Se muestran los primeros {MAX_FILAS_DETALLE} cobros; para ver todos acorta el período.')
    return r.construir(f'Cobros · {f.etiqueta}'), f'cobros_{f.sufijo}.pdf', len(cobros)


# ══════════════════════════════════════════════════════════════════
#  5. DEUDAS
# ══════════════════════════════════════════════════════════════════
def informe_deudas(f, usuario):
    d = services.listar_deudas(f.sucursal, f.sala)
    r = Informe('Deudas', '', COLOR_CORAL_OSCURO, COLOR_CORAL_CLARO, usuario, horizontal=True, nombre_sucursal=_sucursal(f))
    r.filtros([('Situación', f'al {date.today():%d/%m/%Y}'), *_filtros_base(f, con_sala=True, con_periodo=False)])
    r.cifras([
        ('Niños con deuda', str(d['cantidad']), 'no están al día', COLOR_CORAL_OSCURO, COLOR_CORAL_CLARO),
        ('Total que deben', bs(d['monto']), 'suma de todas las deudas', COLOR_NARANJA, COLOR_AMARILLO_CLARO),
    ], por_fila=4)
    r.nota('Se cobra por adelantado: en "por día" cuentan los días acordados o asistidos sin pagar; en "mensual", las '
           'mensualidades ya iniciadas sin pagar. También suma lo que quedó debiendo en una inscripción anterior. '
           'Mientras haya deuda no se puede cambiar de modalidad.')
    r.seccion('Niños con deuda, de mayor a menor')
    filas = [[x['nino'], x['sala'], x['turno'], x['modalidad'], x['tutor'] or '—', x['telefono'] or '—',
              num(x['propia']), num(x['anterior']), num(x['debe'])] for x in d['filas']]
    r.tabla(['Niño', 'Sala', 'Turno', 'Modalidad', 'Tutor', 'Teléfono', 'Actual', 'Anterior', 'Debe (Bs.)'], filas,
            [3, 2, 1.7, 1.5, 2.6, 1.4, 1, 1, 1.2], derecha={6, 7, 8},
            total=['', '', '', '', '', 'TOTAL', '', '', num(d['monto'])],
            vacio='Todos los niños están al día.')
    return r.construir(f'Deudas · {date.today():%d/%m/%Y}'), f'deudas_{date.today():%Y-%m-%d}.pdf', d['cantidad']


# ══════════════════════════════════════════════════════════════════
#  6. NIÑOS INSCRITOS
# ══════════════════════════════════════════════════════════════════
def informe_ninos(f, usuario):
    insc = list(services.consulta_ninos(f))
    r = Informe('Niños inscritos', '', COLOR_CORAL_OSCURO, COLOR_CORAL_CLARO, usuario, horizontal=True,
                nombre_sucursal=_sucursal(f))
    r.filtros([('Situación', f'al {date.today():%d/%m/%Y}'), *_filtros_base(f, con_sala=True, con_periodo=False)])
    con_alergia = sum(1 for i in insc if (i.nino.alergias or '').strip())
    r.cifras([('Niños inscritos', str(len(insc)), 'inscripciones activas', COLOR_CORAL_OSCURO, COLOR_CORAL_CLARO),
              ('Con alergias', str(con_alergia), 'revisar antes de las comidas', COLOR_NARANJA, COLOR_AMARILLO_CLARO)])
    r.seccion('Listado')
    filas = []
    for i in insc:
        n = i.nino
        tutores = sorted(n.tutores.all(), key=lambda x: not x.es_principal)
        t = tutores[0].tutor if tutores else None
        filas.append([n.nombre_completo, services._edad_anios(n.edad_en_meses), i.sala.nombre, i.turno.nombre, i.get_modalidad_pago_display(),
                      n.alergias or '—', f'{t.nombres} {t.apellidos}' if t else '—', t.telefono if t else '—'])
    r.tabla(['Niño', 'Edad', 'Sala', 'Turno', 'Modalidad', 'Alergias', 'Tutor', 'Teléfono'], filas,
            [3, 1.6, 1.8, 1.6, 1.3, 1.8, 2.4, 1.3],
            resaltar=lambda i, fila: COLOR_AMARILLO_CLARO if fila[5] != '—' else None,
            vacio='No hay niños inscritos con esos filtros.')
    return r.construir(f'Niños inscritos · {date.today():%d/%m/%Y}'), f'ninos_{date.today():%Y-%m-%d}.pdf', len(insc)


# ══════════════════════════════════════════════════════════════════
#  7. INVENTARIO
# ══════════════════════════════════════════════════════════════════
def informe_inventario(f, usuario):
    items = list(services.consulta_inventario(f))
    bajos = [i for i in items if i.alerta_stock_bajo]
    r = Informe('Inventario', '', COLOR_VIOLETA_OSCURO, COLOR_VIOLETA_CLARO, usuario, nombre_sucursal=_sucursal(f))
    r.filtros([('Situación', f'al {date.today():%d/%m/%Y}'), ('Sucursal', _sucursal(f))])
    r.cifras([('Ítems', str(len(items)), 'activos', COLOR_VIOLETA_OSCURO, COLOR_VIOLETA_CLARO),
              ('Con stock bajo', str(len(bajos)), 'igual o menor al mínimo', COLOR_CORAL_OSCURO, COLOR_CORAL_CLARO)])
    r.seccion('Stock actual', 'En rojo claro: ítems por reponer.')
    filas = [[i.sucursal.nombre, i.nombre, i.get_categoria_display(), i.unidad, str(i.stock_actual), str(i.stock_minimo),
              'Reponer' if i.alerta_stock_bajo else 'Ok'] for i in items]
    r.tabla(['Sucursal', 'Ítem', 'Categoría', 'Unidad', 'Stock', 'Mínimo', 'Estado'], filas, [2.2, 3.2, 2, 1.6, 1, 1, 1.1],
            derecha={4, 5}, centro={6}, resaltar=lambda i, fila: COLOR_CORAL_CLARO if fila[6] == 'Reponer' else None,
            vacio='No hay ítems de inventario.')
    return r.construir(f'Inventario · {date.today():%d/%m/%Y}'), f'inventario_{date.today():%Y-%m-%d}.pdf', len(items)


GENERADORES = {
    'informe-economico': informe_economico,
    'cierre-caja': cierre_de_caja,
    'asistencia': informe_asistencia,
    'cobros': informe_cobros,
    'deudas': informe_deudas,
    'ninos': informe_ninos,
    'inventario': informe_inventario,
}
