import socket
import time
from collections import deque

import numpy as np
from scipy import signal

UDP_IP = "0.0.0.0"
UDP_PORT = 5005

BYTES_USAR = 128           # 64 subportadoras (LLTF) x 2 bytes; si el paquete es más largo se ignora el resto
IMAG_PRIMERO = True        # ESP-IDF entrega [imag, real]. Si no, ponelo en False
ORDEN_LLTF = True          # True: el paquete viene como 0..31, -32..-1 -> se reordena a -32..31

FS = 20.0                  # Hz de la grilla uniforme
VENTANA_SEG = 60           # ventana de análisis (ver nota abajo)
ACTUALIZAR_SEG = 1.0       # cada cuánto se recalcula
BANDA_HZ = (0.15, 0.5)     # respiración: 9 a 30 rpm
HP_HZ = 0.07               # pasa-altos Butterworth (quita deriva)
BORDE_SEG = 5              # se recortan los extremos de la señal filtrada (transitorio del filtro)
N_PCS = 3                  # componentes principales que se prueban

ALFA = 1e-3                # p-valor máximo para "posible respiración"
CONFIRMAR_N = 3            # ventanas SIN solape que tienen que coincidir para confirmar
TOL_RPM = 3.0

# Nota sobre la ventana: una respiración dura entre 2 s (30 rpm) y 7 s (9 rpm). Con 2 s no entra
# ni un ciclo. Se actualiza seguido, pero cada cálculo necesita decenas de segundos de historia.


# ---------------- Paquete -> CSI complejo ----------------
def parse_csi_payload(data):
    crudo = np.frombuffer(data[:BYTES_USAR], dtype=np.int8).astype(np.float32)
    if IMAG_PRIMERO:
        imag, real = crudo[0::2], crudo[1::2]
    else:
        real, imag = crudo[0::2], crudo[1::2]
    z = real + 1j * imag
    return np.fft.fftshift(z) if ORDEN_LLTF else z     # [0..31,-32..-1] -> [-32..31]


# ---------------- Señal por subportadora ----------------
def preparar(csi, t, modo):
    amp = np.abs(csi)
    media = amp.mean(axis=0)
    validas = media > 0.3 * np.median(media)           # descarta subportadoras nulas (guardas / DC)
    if validas.sum() < 10:
        return None
    k = np.flatnonzero(validas).astype(float)
    z = csi[:, validas]

    if modo == "fase":
        fase = np.unwrap(np.angle(z), axis=1)           # unwrap entre subportadoras
        X = np.column_stack([np.ones_like(k), k - k.mean()])
        coef = np.linalg.lstsq(X, fase.T, rcond=None)[0]
        datos = np.unwrap(fase - (X @ coef).T, axis=0)  # sin offset/pendiente; unwrap en el tiempo
    else:
        datos = np.abs(z)

    t0 = t - t[0]
    grilla = np.arange(0.0, t0[-1], 1.0 / FS)
    return np.column_stack([np.interp(grilla, t0, datos[:, j]) for j in range(datos.shape[1])])


# ---------------- Espectro y decisión ----------------
def pico_cfar(x):
    """Pico de la banda comparado con el promedio de sus frecuencias vecinas (ruido local).
    Sin pico real, pico/vecinas ~ F(2,2m) y p = (1 + r/m)^-m."""
    n = len(x)
    pot = np.abs(np.fft.rfft(x)) ** 2
    f = np.fft.rfftfreq(n, 1.0 / FS)
    banda = np.flatnonzero((f >= BANDA_HZ[0]) & (f <= BANDA_HZ[1]))
    zona = (f >= 0.09) & (f <= 1.2)

    mejor = None
    for i, j in enumerate(banda):
        v = np.arange(j - 15, j + 16)
        v = v[(np.abs(v - j) > 3) & (v >= 1) & (v < len(pot))]   # sin el lóbulo del propio pico
        v = v[zona[v]]
        if len(v) < 8:
            continue
        m = len(v)
        r = pot[j] / (pot[v].mean() + 1e-20)
        logp = -m * np.log1p(r / m)
        if mejor is None or logp < mejor[0]:
            mejor = (logp, j, i)
    if mejor is None:
        return None

    logp, j, i = mejor
    delta = 0.0                                          # afinado parabólico de la frecuencia
    if 1 <= j < len(pot) - 1:
        a, b, c = np.log(pot[j - 1:j + 2] + 1e-20)
        if a - 2 * b + c != 0:
            delta = float(np.clip(0.5 * (a - c) / (a - 2 * b + c), -0.5, 0.5))
    return dict(logp=float(logp), rpm=(j + delta) * (FS / n) * 60.0,
                n_banda=len(banda), en_borde=bool(i in (0, len(banda) - 1)))


def analizar(csi, t, modo):
    d = preparar(csi, t, modo)
    if d is None:
        return None
    d = signal.detrend(d, axis=0)

    x = (d - d.mean(axis=0)) / (d.std(axis=0) + 1e-9)    # PCA: combina las subportadoras
    U, S, _ = np.linalg.svd(x, full_matrices=False)
    k = min(N_PCS, len(S))
    pcs = U[:, :k] * S[:k]

    sos = signal.butter(2, HP_HZ, btype="highpass", fs=FS, output="sos")
    filt = signal.sosfiltfilt(sos, pcs, axis=0)
    b = int(BORDE_SEG * FS)
    filt = filt[b:-b] * np.hanning(len(filt) - 2 * b)[:, None]

    mejor = None
    for c in range(k):
        r = pico_cfar(filt[:, c])
        if r is not None and (mejor is None or r["logp"] < mejor["logp"]):
            mejor = r
    if mejor is None:
        return None
    mejor["p"] = float(min(1.0, mejor["n_banda"] * k * np.exp(mejor["logp"])))  # corrige por mirar muchas
    return mejor


def confirmar(hist):
    """Toma estimaciones separadas >= VENTANA_SEG (ventanas sin solape) y exige que coincidan."""
    sel = []
    for t, r in reversed(hist):
        if not sel or sel[-1][0] - t >= VENTANA_SEG:
            sel.append((t, r))
        if len(sel) == CONFIRMAR_N:
            break
    if len(sel) < CONFIRMAR_N or any(r is None for _, r in sel):
        return None
    rs = [r for _, r in sel]
    return float(np.mean(rs)) if max(rs) - min(rs) <= TOL_RPM else None


# ---------------- Programa principal ----------------
def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
    sock.bind((UDP_IP, UDP_PORT))
    sock.settimeout(2.0)
    print(f"Escuchando CSI en UDP {UDP_PORT}...")

    buf, tiempos, hist = deque(), deque(), deque()
    ultimo = time.monotonic()
    try:
        while True:
            try:
                data, _ = sock.recvfrom(4096)
            except socket.timeout:
                print("(no llegan paquetes")
                continue
            if len(data) < BYTES_USAR:
                continue

            ahora = time.monotonic()
            buf.append(parse_csi_payload(data))
            tiempos.append(ahora)
            while ahora - tiempos[0] > VENTANA_SEG:
                tiempos.popleft()
                buf.popleft()

            if ahora - ultimo < ACTUALIZAR_SEG:
                continue
            ultimo = ahora

            dur = tiempos[-1] - tiempos[0]
            if dur < VENTANA_SEG * 0.95:
                print(f"Llenando buffer {dur:.0f}/{VENTANA_SEG} s")
                continue

            t = np.array(tiempos)
            fs_raw = (len(t) - 1) / dur
            if fs_raw < 10 or np.max(np.diff(t)) > 1.0:
                print(f"Ventana descartada: {fs_raw:.0f} paquetes/s, hueco máx. {np.max(np.diff(t)):.1f} s "
                      f"(el ESP32 tiene que recibir tráfico constante, p. ej. ping al router)")
                continue

            csi = np.array(buf)
            res = {m: analizar(csi, t, m) for m in ("fase", "amplitud")}
            res = {m: r for m, r in res.items() if r is not None}
            if not res:
                print("muy pocas subportadoras válidas")
                continue

            texto = " | ".join(f"{m}: {r['rpm']:.1f} rpm (p={r['p']:.0e}{', borde' if r['en_borde'] else ''})"
                               for m, r in res.items())
            m_mejor = min(res, key=lambda m: res[m]["p"])
            r = res[m_mejor]
            candidato = min(1.0, 2 * r["p"]) < ALFA and not r["en_borde"]   # x2: se miraron dos métodos

            hist.append((ahora, r["rpm"] if candidato else None))
            while hist and ahora - hist[0][0] > CONFIRMAR_N * VENTANA_SEG:
                hist.popleft()

            conf = confirmar(hist)
            if conf is not None:
                print(f"PRESENCIA: respiración ~{conf:.1f} rpm, confirmada   [{texto}]")
            elif candidato:
                print(f"posible respiración ~{r['rpm']:.1f} rpm (sin confirmar, método {m_mejor})   [{texto}]")
            else:
                print(f"sin presencia   [{texto}]")
    except KeyboardInterrupt:
        print("\nDeteniendo escucha UDP...")
    finally:
        sock.close()


if __name__ == "__main__":
    main()