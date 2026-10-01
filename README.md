# Wave Curses 🌊

Visualizador de onda de audio en terminal (curses) para archivos MP3 y otros formatos. Muestra el envelope (min/max amplitude) del audio en tiempo real, con cursor interactivo para navegar por la pista.

## Características

- Visualización de forma de onda en terminal (curses)
- Cálculo de envelope (min/máx por bin) mediante streaming con ffmpeg
- Cache automática para evitar recálculos (útil para audios largos)
- Navegación con flechas izquierda/derecha
- Mostrar tiempo aproximado en la posición del cursor
- Ajustar sample rate (+/-) para más/menos detalle
- Compatibles con audios muy largos (horas)

## Dependencias

- **Python 3** (3.6+)
- **ffmpeg** (incluye ffprobe)
- **curses** (biblioteca estándar de Python, pero a veces necesita paquete separado en algunos sistemas)

### Instalación en Termux

```bash
# Actualizar y instalar dependencias
pkg update
pkg install -y python ffmpeg
```

### Instalación en otras distribuciones Linux

```bash
# Debian/Ubuntu
sudo apt install python3 ffmpeg

# Arch Linux
sudo pacman -S python ffmpeg

# Fedora
sudo dnf install python3 ffmpeg
```

### Verificación

```bash
# Verificar que ffmpeg y ffprobe estén disponibles
which ffmpeg ffprobe
python3 -c "import curses; print('curses OK')"
``

## Uso

```bash
python3 wave_curses.py /ruta/al/audio.mp3
```

Ejemplo en Termux:
```bash
python3 wave_curses.py /sdcard/Music/mi_audio.mp3
```

## Controles

| Tecla | Acción |
|-------|--------|
| `←` `→` | Mover cursor |
| `Enter` | Mostrar tiempo aproximado en posición actual |
| `+` / `=` | Aumentar sample rate (más detalle, más lento) |
| `-` | Disminuir sample rate (menos detalle, más rápido) |
| `r` | Forzar recálculo (elimina cache) |
| `q` | Salir |

## Cómo funciona

1. Usa `ffprobe` para obtener la duración del audio.
2. Decodifica el audio a PCM mono con `ffmpeg` en streaming.
3. Calcula el valor min/max de amplitud por cada "bin" (segmento de audio).
4. Dibuja el envelope en la terminal usando curses.
5. Guarda un cache `.env_*.json` para no recalcular la próxima vez.

## Notas

- La primera ejecución puede tardar unos segundos (o minutos para audios largos) mientras calcula el envelope.
- Las subsiguientes ejecuciones usan el cache y son casi instantáneas.
- El sample rate por defecto es 8000 Hz (buen equilibrio velocidad/calidad).
- Puedes ajustar el sample rate con +/- durante la ejecución.

## Ejemplo de cache

Al ejecutar sobre `Jardín de rosas - Rojo.mp3`, se crea el archivo:
`.rosas.mp3.env_8000hz_38bins.json`

## Licencia

Este proyecto es de uso personal. No garantiza compatibilidad con todos los formatos de audio.