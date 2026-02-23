# DOJ Epstein Data Set 1 — Visor de PDFs

Aplicación web para explorar y visualizar los ~3,150 documentos PDF del Data Set 1 publicados por el Departamento de Justicia de EE.UU. en la Epstein Library.

## Requisitos

- Python 3.8+
- pip

## Instalación

```bash
pip install flask requests beautifulsoup4
```

## Uso

```bash
python app.py
```

Luego abre tu navegador en: **http://localhost:5050**

## Funcionalidades

- **Indexación automática**: Al arrancar, el backend raspa las 63 páginas del índice de `justice.gov` en segundo plano.
- **Barra de progreso**: Muestra el avance del indexado en tiempo real.
- **Lista paginada**: 50 documentos por página, con navegación numérica.
- **Búsqueda**: Filtra documentos por nombre en tiempo real.
- **Vista lista / cuadrícula**: Alterna entre dos modos de visualización.
- **Visor embebido**: Abre el PDF directamente en el panel derecho (proxied a través de Flask para evitar CORS).
- **Navegación**: Flechas para ir al documento anterior/siguiente sin salir del visor.
- **Abrir en nueva pestaña**: Enlace directo al PDF en `justice.gov`.
- **Descargar**: Descarga el PDF actual directamente.

## Estructura

```
epstein-viewer/
├── app.py              # Backend Flask
└── templates/
    └── index.html      # Frontend HTML/CSS/JS
```

## Notas

- La fuente de datos es 100% pública: https://www.justice.gov/epstein/doj-disclosures/data-set-1-files
- Los PDFs se sirven a través del endpoint `/api/proxy` para evitar restricciones CORS del navegador.
- El índice completo tarda ~1-2 minutos en cargarse (63 páginas × ~0.3s delay).