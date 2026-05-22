# Gestor de historial del portapapeles

Un gestor de historial del portapapeles para NVDA inspirado en Ditto.

Realiza un seguimiento de todo lo que copias — texto, archivos, enlaces y correos electrónicos — con monitorización instantánea del portapapeles basada en eventos.

## Características

* **Monitorización instantánea del portapapeles** usando el listener de portapapeles de Windows (basado en eventos, sin sondeo periódico).
* **Soporte de archivos**: Los archivos copiados en el Explorador aparecen en el historial y se pegan como archivos reales (formato CF_HDROP).
* **Agrupación automática**: Las entradas se clasifican automáticamente como Archivos y carpetas, Enlaces o Correos electrónicos.
* **Búsqueda y filtrado**: Búsqueda de texto completo y filtro por grupo en el diálogo del historial.
* **Fijar entradas importantes** para que nunca se eliminen al alcanzar el límite.
* **Selección múltiple y pegado**: Selecciona múltiples entradas con Ctrl+Espacio y pégalas en el orden de selección.
* **Añadir al portapapeles**: Añade el texto seleccionado al contenido actual del portapapeles.
* **Reordenar entradas**: Mueve las entradas arriba/abajo con Shift+Flechas, o al principio/final mediante el menú contextual.
* **Guardar entradas**: Guarda cualquier entrada como archivo de texto (.txt) o documento Word (.docx) desde el menú contextual.
* **Indicador de pegado**: Las entradas que han sido pegadas se marcan con "Pasted:" en la lista.
* **Pegado combinado**: Cuando se pegan múltiples entradas juntas, el texto combinado también se guarda como nueva entrada.
* **Historial persistente**: El historial se guarda entre sesiones de NVDA (configurable).
* **Grupos personalizados**: Crea y gestiona grupos personalizados para organizar las entradas.
* **Editor de clips**: Crea nuevos clips desde cero o edita entradas existentes con un editor de texto integrado, con advertencia de cambios sin guardar.
* **Seleccionar todo**: Pulsa Ctrl+A en el diálogo del historial para seleccionar todas las entradas.
* **Configurable**: Panel de ajustes en Preferencias de NVDA para el máximo de entradas, persistencia y anuncios.

## Atajos de teclado globales

| Atajo | Acción |
|---|---|
| NVDA+A | Abrir el diálogo del historial del portapapeles |
| NVDA+C | Anunciar el contenido actual del portapapeles |
| NVDA+Shift+A | Añadir texto seleccionado a la última entrada |
| NVDA+Alt+Flecha arriba | Navegar a la entrada anterior |
| NVDA+Alt+Flecha abajo | Navegar a la entrada siguiente |
| NVDA+Alt+V | Pegar la entrada seleccionada actualmente |
| NVDA+Alt+Intro | Copiar la entrada al portapapeles |
| NVDA+Alt+Suprimir | Eliminar la entrada seleccionada actualmente |
| NVDA+Alt+P | Fijar/desfijar la entrada |
| NVDA+Alt+X | Borrar todo el historial |
| NVDA+Shift+C | Abrir editor para escribir un nuevo clip |
| NVDA+Alt+G | Establecer grupo para la entrada |

## Atajos de teclado en el diálogo

Cuando el diálogo del historial está abierto:

| Atajo | Acción |
|---|---|
| Intro | Pegar la(s) entrada(s) seleccionada(s) |
| Ctrl+Espacio | Alternar selección múltiple (respeta el orden) |
| Suprimir | Eliminar la(s) entrada(s) seleccionada(s) |
| Ctrl+A | Seleccionar todas las entradas |
| Ctrl+E | Editar la entrada seleccionada |
| Ctrl+P | Fijar/desfijar |
| Ctrl+G | Establecer grupo |
| Shift+Flecha arriba | Mover entrada hacia arriba |
| Shift+Flecha abajo | Mover entrada hacia abajo |
| Tecla Aplicaciones | Abrir menú contextual |
| Alt+S | Enfocar campo de búsqueda |
| Alt+U | Enfocar filtro de grupo |
| Alt+G | Botón establecer grupo |
| Escape | Cerrar diálogo |

## Opciones del menú contextual

Clic derecho o tecla Aplicaciones en cualquier entrada:

* Pegar
* Copiar al portapapeles
* Editar
* **Guardar como** submenú: Archivo de texto (.txt), Documento Word (.docx)
* **Mover a** submenú: Principio, Final
* Fijar / Desfijar
* Establecer grupo
* Eliminar

## Ajustes

Disponibles en menú NVDA > Preferencias > Opciones > Historial del portapapeles:

* **Número máximo de entradas**: Establece el límite (10–10.000, predeterminado 500). Al superarlo, se elimina la entrada no fijada más antigua.
* **Guardar historial entre sesiones**: Mantener el historial entre reinicios (predeterminado: activado).
* **Anunciar cuando se copia nuevo texto**: Verbalizar una vista previa cuando se detecta nuevo contenido (predeterminado: desactivado).

## Compatibilidad

* Versión mínima de NVDA: 2024.1
* Última versión probada: NVDA 2025.3

## Licencia

Licencia Pública General GNU, versión 2.
