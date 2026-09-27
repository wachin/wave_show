#!/usr/bin/env python3
import curses
import os
import sys
import json
import math
import time
import subprocess
from array import array

# Envelope cache to avoid recomputing every run (very helpful for 6h audio)
def cache_path(audio_path, sr, bins):
    base = os.path.basename(audio_path)
    safe = "".join(c for c in base if c.isalnum() or c in "._-")
    return os.path.join(os.path.dirname(audio_path), f".{safe}.env_{sr}hz_{bins}bins.json")

def ffprobe_duration_seconds(path):
    # Returns duration as float seconds (or None if unknown)
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1",
        path
    ]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode("utf-8").strip()
        return float(out) if out else None
    except Exception:
        return None

def compute_envelope_streaming(audio_path, sr, bins, status_cb=None):
    """
    Compute min/max amplitude per bin over the whole file.
    Uses ffmpeg to decode to signed 16-bit little-endian mono at given sample rate.
    Returns (mins, maxs) arrays in [-1.0, 1.0].
    """
    dur = ffprobe_duration_seconds(audio_path)
    if dur is None or dur <= 0:
        raise RuntimeError("No pude obtener la duración con ffprobe.")

    total_samples = int(dur * sr)
    if total_samples <= 0:
        raise RuntimeError("Duración inválida.")

    # Samples per bin (at least 1)
    spb = max(1, total_samples // bins)

    mins = [1.0] * bins
    maxs = [-1.0] * bins

    # ffmpeg decode command: PCM s16le mono
    cmd = [
        "ffmpeg", "-v", "error",
        "-i", audio_path,
        "-ac", "1",
        "-ar", str(sr),
        "-f", "s16le",
        "pipe:1"
    ]

    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)

    # Read in chunks of bytes; 2 bytes per sample for s16le
    chunk_bytes = 64 * 1024  # 64KB
    sample_index = 0
    last_update = 0.0

    try:
        while True:
            data = p.stdout.read(chunk_bytes)
            if not data:
                break

            # Convert bytes -> array('h') without numpy
            a = array('h')
            a.frombytes(data)

            for s in a:
                # Map sample to bin
                b = sample_index // spb
                if b >= bins:
                    break
                x = s / 32768.0
                if x < mins[b]:
                    mins[b] = x
                if x > maxs[b]:
                    maxs[b] = x
                sample_index += 1

            now = time.time()
            if status_cb and (now - last_update) > 0.10:
                # progress estimate
                prog = min(1.0, sample_index / max(1, total_samples))
                status_cb(prog, sample_index, total_samples)
                last_update = now

        ret = p.wait()
        if ret != 0:
            raise RuntimeError("ffmpeg falló al decodificar el audio.")
    finally:
        try:
            if p.stdout:
                p.stdout.close()
        except Exception:
            pass

    # Fix bins that might remain untouched (very short audios)
    for i in range(bins):
        if mins[i] > maxs[i]:
            mins[i] = 0.0
            maxs[i] = 0.0

    return mins, maxs, dur

def save_cache(path, audio_path, sr, bins, mins, maxs, dur):
    payload = {
        "audio_path": os.path.abspath(audio_path),
        "sr": sr,
        "bins": bins,
        "duration": dur,
        "mins": mins,
        "maxs": maxs,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)

def load_cache(path, audio_path, sr, bins):
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if payload.get("audio_path") != os.path.abspath(audio_path):
            return None
        if payload.get("sr") != sr or payload.get("bins") != bins:
            return None
        return payload["mins"], payload["maxs"], payload.get("duration")
    except Exception:
        return None

def draw_wave(stdscr, mins, maxs, dur, cursor_col=None, title="Wave (envelope)"):
    stdscr.erase()
    h, w = stdscr.getmaxyx()

    # Layout
    top = 2
    bottom = h - 3
    wave_h = max(1, bottom - top + 1)
    mid = top + wave_h // 2

    # Header
    stdscr.addstr(0, 0, (title[:w-1] if w > 1 else ""))
    info = f"duración: {dur/3600:.2f}h | ancho: {len(mins)} bins | q salir | r recalcular | +/- sr"
    stdscr.addstr(1, 0, info[:w-1])

    # Wave drawing per column
    # Use only up to w columns
    cols = min(w, len(mins))
    for x in range(cols):
        mn = mins[x]
        mx = maxs[x]

        # Map amplitude [-1,1] to rows
        y_min = mid - int(mn * (wave_h / 2))
        y_max = mid - int(mx * (wave_h / 2))

        y1 = max(top, min(bottom, min(y_min, y_max)))
        y2 = max(top, min(bottom, max(y_min, y_max)))

        # Draw a vertical segment for min..max
        for y in range(y1, y2 + 1):
            try:
                stdscr.addch(y, x, ord('|'))
            except curses.error:
                pass

    # Center line
    for x in range(cols):
        try:
            stdscr.addch(mid, x, ord('-'))
        except curses.error:
            pass

    # Cursor
    if cursor_col is not None and 0 <= cursor_col < cols:
        for y in range(top, bottom + 1):
            try:
                stdscr.addch(y, cursor_col, ord('#'))
            except curses.error:
                pass

    # Footer
    stdscr.addstr(h - 2, 0, "Flechas ← → mover cursor. Enter muestra tiempo aprox."[:w-1])
    stdscr.addstr(h - 1, 0, "Tip: la 1ra vez tarda; luego usa cache .env_*.json"[:w-1])
    stdscr.refresh()

def ui(stdscr, audio_path):
    curses.curs_set(0)
    stdscr.nodelay(False)
    stdscr.keypad(True)

    # Default params (rápido)
    sr = 8000

    cursor = 0
    mins = maxs = None
    dur = None

    def status_cb(prog, si, total):
        h, w = stdscr.getmaxyx()
        msg = f"Decodificando+calculando envelope... {prog*100:5.1f}%  ({si}/{total} samples)"
        stdscr.erase()
        stdscr.addstr(0, 0, msg[:w-1])
        stdscr.addstr(1, 0, "Esto es 1 sola pasada (streaming). Luego quedará cacheado."[:w-1])
        stdscr.refresh()

    while True:
        h, w = stdscr.getmaxyx()
        bins = max(10, w)  # 1 bin por columna (aprox)
        cpath = cache_path(audio_path, sr, bins)

        cached = load_cache(cpath, audio_path, sr, bins)
        if cached:
            mins, maxs, dur = cached
        else:
            mins, maxs, dur = compute_envelope_streaming(audio_path, sr, bins, status_cb=status_cb)
            try:
                save_cache(cpath, audio_path, sr, bins, mins, maxs, dur)
            except Exception:
                pass

        cursor = max(0, min(len(mins)-1, cursor))
        draw_wave(stdscr, mins, maxs, dur, cursor_col=cursor,
                  title=f"Envelope rápido | sr={sr} Hz | archivo: {os.path.basename(audio_path)}")

        k = stdscr.getch()
        if k in (ord('q'), ord('Q')):
            return
        elif k in (ord('r'), ord('R')):
            # Force recompute by deleting cache
            try:
                os.remove(cpath)
            except Exception:
                pass
            continue
        elif k == curses.KEY_LEFT:
            cursor = max(0, cursor - 1)
        elif k == curses.KEY_RIGHT:
            cursor = min(len(mins)-1, cursor + 1)
        elif k in (ord('+'), ord('=')):
            # Increase sample rate (more detail, slower)
            sr = min(44100, sr * 2)
            continue
        elif k in (ord('-'), ord('_')):
            sr = max(2000, sr // 2)
            continue
        elif k in (10, 13):  # Enter
            # Show approximate time at cursor
            t = (cursor / max(1, len(mins)-1)) * dur
            hh = int(t // 3600)
            mm = int((t % 3600) // 60)
            ss = int(t % 60)
            msg = f"Cursor ~ {hh:02d}:{mm:02d}:{ss:02d}"
            h, w = stdscr.getmaxyx()
            stdscr.addstr(0, 0, msg[:w-1])
            stdscr.refresh()
            time.sleep(0.6)

def main():
    if len(sys.argv) < 2:
        print("Uso: python wave_curses.py /ruta/al/audio.mp3")
        print("Tip: en Termux, usa rutas tipo: /sdcard/Music/mi_audio.mp3")
        sys.exit(1)

    audio_path = sys.argv[1]
    if not os.path.exists(audio_path):
        print("No existe:", audio_path)
        sys.exit(1)

    curses.wrapper(ui, audio_path)

if __name__ == "__main__":
    main()