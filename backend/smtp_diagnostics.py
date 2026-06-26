# -*- coding: utf-8 -*-
import sys, io
# Forzar UTF-8 en stdout para Windows (cp1252 no soporta todos los símbolos)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf_8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

"""
smtp_diagnostics.py
===================
Diagnóstico completo del relay SMTP bancario.

Prueba:
  1. Conectividad TCP a los puertos 25, 587 y 465
  2. TLS implícito (SMTPS, puerto 465)
  3. STARTTLS disponible (puerto 587/25)
  4. Si se requiere usuario/contraseña (AUTH)
  5. Si la IP del servidor está autorizada (sin rechazo 550/554)
  6. Si puede enviarse a destinatarios externos
  7. From permitido: noreply@banco.com

Uso:
  python smtp_diagnostics.py
  python smtp_diagnostics.py --host smtp-relay.banco.local --from noreply@banco.com --ext-to usuario@gmail.com

Requiere solo la stdlib de Python (≥ 3.8).
"""

import argparse
import smtplib
import socket
import ssl
import sys
import textwrap
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# ─── Colores ANSI ────────────────────────────────────────────────────────────
try:
    import colorama; colorama.init()
    GREEN  = "\033[92m"
    RED    = "\033[91m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"
except ImportError:
    GREEN = RED = YELLOW = CYAN = BOLD = RESET = ""

OK   = f"{GREEN}[SI]{RESET}"
FAIL = f"{RED}[NO]{RESET}"
WARN = f"{YELLOW}[PARCIAL]{RESET}"
UNK  = f"{YELLOW}[?]{RESET}"


# ─── Resultado de cada prueba ─────────────────────────────────────────────────
@dataclass
class Result:
    label: str
    value: str          # OK / FAIL / WARN / UNK
    detail: str = ""


@dataclass
class DiagReport:
    host: str
    from_addr: str
    ext_to: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    results: list = field(default_factory=list)

    def add(self, label: str, value: str, detail: str = ""):
        self.results.append(Result(label, value, detail))

    def print(self):
        width = 72
        sep = "=" * width
        print(f"\n{BOLD}{sep}{RESET}")
        print(f"{BOLD}  DIAGNOSTICO SMTP -- {self.host}{RESET}")
        print(f"  Fecha/Hora : {self.timestamp}")
        print(f"  From       : {self.from_addr}")
        print(f"  Ext-To     : {self.ext_to or '(no especificado)'}")
        print(f"{BOLD}{sep}{RESET}\n")

        col_label = 45
        for r in self.results:
            label_str = r.label.ljust(col_label)
            print(f"  {label_str} {r.value}")
            if r.detail:
                for line in textwrap.wrap(r.detail, width=width - 4):
                    print(f"    {CYAN}>> {line}{RESET}")

        print(f"\n{BOLD}{'=' * width}{RESET}\n")


# ─── Helpers ──────────────────────────────────────────────────────────────────
TIMEOUT = 10  # segundos


def tcp_open(host: str, port: int) -> tuple[bool, str]:
    """Comprueba si el puerto TCP está abierto."""
    try:
        with socket.create_connection((host, port), timeout=TIMEOUT):
            return True, f"Puerto {port} accesible"
    except socket.timeout:
        return False, f"Timeout al conectar a {host}:{port}"
    except ConnectionRefusedError:
        return False, f"Conexión rechazada en {host}:{port}"
    except OSError as e:
        return False, f"Error de red: {e}"


def probe_plain(host: str, port: int, from_addr: str, ext_to: str) -> dict:
    """
    Conecta sin TLS (SMTP plano o STARTTLS).
    Devuelve un dict con claves:
      connected, starttls, auth_required, from_ok, ext_ok, banner, error
    """
    r = dict(connected=False, starttls=False, auth_required=None,
             from_ok=None, ext_ok=None, banner="", error="")
    try:
        with smtplib.SMTP(host, port, timeout=TIMEOUT) as s:
            s.set_debuglevel(0)
            code, msg = s.ehlo()
            r["connected"] = True
            r["banner"] = msg.decode(errors="replace") if isinstance(msg, bytes) else str(msg)

            caps = s.esmtp_features
            r["starttls"] = "starttls" in caps

            # Intentar STARTTLS si está disponible
            tls_active = False
            if r["starttls"]:
                try:
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    s.starttls(context=ctx)
                    s.ehlo()
                    tls_active = True
                    caps = s.esmtp_features
                except smtplib.SMTPException as e:
                    r["error"] += f"STARTTLS fallido: {e}; "

            # ¿Requiere AUTH?
            r["auth_required"] = "auth" in caps

            # Probar MAIL FROM
            try:
                code2, _ = s.mail(from_addr)
                r["from_ok"] = (code2 == 250)
            except smtplib.SMTPSenderRefused as e:
                r["from_ok"] = False
                r["error"] += f"MAIL FROM rechazado ({e.smtp_code}): {e.smtp_error}; "
            except smtplib.SMTPException as e:
                r["from_ok"] = False
                r["error"] += f"MAIL FROM error: {e}; "

            # Probar RCPT TO externo (si from_ok y ext_to provisto)
            if r["from_ok"] and ext_to:
                try:
                    code3, _ = s.rcpt(ext_to)
                    r["ext_ok"] = (code3 == 250)
                except smtplib.SMTPRecipientsRefused as e:
                    r["ext_ok"] = False
                    r["error"] += f"RCPT externo rechazado: {e}; "
                except smtplib.SMTPException as e:
                    r["ext_ok"] = False
                    r["error"] += f"RCPT externo error: {e}; "

    except smtplib.SMTPConnectError as e:
        r["error"] = f"No se pudo conectar: {e}"
    except smtplib.SMTPException as e:
        r["error"] = f"Error SMTP: {e}"
    except OSError as e:
        r["error"] = f"Error de red: {e}"

    return r


def probe_tls(host: str, port: int, from_addr: str, ext_to: str) -> dict:
    """
    Conecta con TLS implícito (SMTPS, normalmente puerto 465).
    """
    r = dict(connected=False, starttls=False, auth_required=None,
             from_ok=None, ext_ok=None, banner="", error="")
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=TIMEOUT) as s:
            code, msg = s.ehlo()
            r["connected"] = True
            r["banner"] = msg.decode(errors="replace") if isinstance(msg, bytes) else str(msg)
            caps = s.esmtp_features
            r["auth_required"] = "auth" in caps

            try:
                code2, _ = s.mail(from_addr)
                r["from_ok"] = (code2 == 250)
            except smtplib.SMTPSenderRefused as e:
                r["from_ok"] = False
                r["error"] += f"MAIL FROM rechazado ({e.smtp_code}): {e.smtp_error}; "
            except smtplib.SMTPException as e:
                r["from_ok"] = False
                r["error"] += f"MAIL FROM error: {e}; "

            if r["from_ok"] and ext_to:
                try:
                    code3, _ = s.rcpt(ext_to)
                    r["ext_ok"] = (code3 == 250)
                except smtplib.SMTPRecipientsRefused as e:
                    r["ext_ok"] = False
                    r["error"] += f"RCPT externo rechazado: {e}; "
                except smtplib.SMTPException as e:
                    r["ext_ok"] = False
                    r["error"] += f"RCPT externo error: {e}; "

    except ssl.SSLError as e:
        r["error"] = f"Error SSL: {e}"
    except smtplib.SMTPConnectError as e:
        r["error"] = f"No se pudo conectar: {e}"
    except smtplib.SMTPException as e:
        r["error"] = f"Error SMTP: {e}"
    except OSError as e:
        r["error"] = f"Error de red: {e}"

    return r


# ─── Motor principal ──────────────────────────────────────────────────────────
def run_diagnostics(host: str, from_addr: str, ext_to: str) -> DiagReport:
    report = DiagReport(host=host, from_addr=from_addr, ext_to=ext_to)

    ports = {
        25:  ("plain/STARTTLS", probe_plain),
        587: ("STARTTLS",       probe_plain),
        465: ("TLS implícito",  probe_tls),
    }

    # Guardar los resultados por puerto para respuestas consolidadas
    port_probes = {}
    best: Optional[dict] = None          # primer puerto que conectó exitosamente

    print(f"\n{CYAN}Iniciando diagnóstico SMTP hacia {host}...{RESET}\n")

    for port, (proto_name, probe_fn) in ports.items():
        # 1. TCP
        tcp_ok, tcp_detail = tcp_open(host, port)
        report.add(
            f"Puerto {port} ({proto_name}) — TCP abierto",
            OK if tcp_ok else FAIL,
            tcp_detail,
        )
        if not tcp_ok:
            port_probes[port] = None
            continue

        # 2. Handshake SMTP
        print(f"  {CYAN}Probando SMTP en puerto {port} ({proto_name})...{RESET}")
        probe = probe_fn(host, port, from_addr, ext_to)
        port_probes[port] = probe

        report.add(
            f"Puerto {port} — Handshake SMTP exitoso",
            OK if probe["connected"] else FAIL,
            probe["error"] if not probe["connected"] else f"Banner: {probe['banner'][:120]}",
        )

        if probe["connected"] and best is None:
            best = {"port": port, "proto": proto_name, **probe}

    # ─── Preguntas globales ───────────────────────────────────────────────────
    print(f"\n  {CYAN}Consolidando respuestas...{RESET}\n")

    # TLS requerido (algún puerto con TLS disponible conectó)
    tls_ports_ok = [p for p, pr in port_probes.items() if pr and pr["connected"] and p in (465, 587)]
    if tls_ports_ok:
        report.add(
            "¿TLS disponible/requerido?",
            OK,
            f"Conexión TLS exitosa en puerto(s): {', '.join(str(p) for p in tls_ports_ok)}",
        )
    else:
        p25 = port_probes.get(25)
        if p25 and p25["connected"]:
            report.add(
                "¿TLS disponible/requerido?",
                WARN,
                "Solo el puerto 25 (sin TLS) respondió. Se recomienda habilitar TLS.",
            )
        else:
            report.add("¿TLS disponible/requerido?", UNK, "Ningún puerto respondió correctamente.")

    # STARTTLS
    starttls_ports = [p for p, pr in port_probes.items() if pr and pr.get("starttls")]
    if starttls_ports:
        report.add(
            "¿STARTTLS disponible?",
            OK,
            f"Anunciado en puerto(s): {', '.join(str(p) for p in starttls_ports)}",
        )
    else:
        connected_ports = [p for p, pr in port_probes.items() if pr and pr["connected"] and p != 465]
        if connected_ports:
            report.add(
                "¿STARTTLS disponible?",
                FAIL,
                f"No anunciado en puerto(s): {', '.join(str(p) for p in connected_ports)}",
            )
        else:
            report.add("¿STARTTLS disponible?", UNK, "No hubo puertos planos conectados para verificar.")

    # AUTH requerido
    if best:
        if best["auth_required"]:
            report.add(
                "¿Requiere usuario/contraseña (AUTH)?",
                OK,
                f"AUTH anunciado en el banner del puerto {best['port']}",
            )
        else:
            report.add(
                "¿Requiere usuario/contraseña (AUTH)?",
                FAIL,
                f"AUTH NO anunciado en puerto {best['port']} — el relay acepta conexiones anónimas (open relay o autenticación por IP)",
            )
    else:
        report.add("¿Requiere usuario/contraseña (AUTH)?", UNK, "No se pudo conectar a ningún puerto.")

    # IP autorizada (inferido de from_ok)
    if best and best["from_ok"] is not None:
        if best["from_ok"]:
            report.add(
                "¿Tu IP está autorizada?",
                OK,
                f"MAIL FROM aceptado en puerto {best['port']} — la IP local no fue rechazada",
            )
        else:
            report.add(
                "¿Tu IP está autorizada?",
                FAIL,
                f"MAIL FROM rechazado en puerto {best['port']}. Puede indicar que la IP no está en la lista blanca del relay. Detalles: {best.get('error','')}",
            )
    elif best and best["connected"]:
        report.add(
            "¿Tu IP está autorizada?",
            WARN,
            "Conectó pero no fue posible verificar MAIL FROM",
        )
    else:
        report.add("¿Tu IP está autorizada?", UNK, "No se pudo conectar.")

    # From permitido
    if best and best["from_ok"] is not None:
        report.add(
            f"¿From '{from_addr}' permitido?",
            OK if best["from_ok"] else FAIL,
            f"MAIL FROM {'aceptado' if best['from_ok'] else 'rechazado'} en puerto {best['port']}",
        )
    else:
        report.add(f"¿From '{from_addr}' permitido?", UNK, "No se pudo probar MAIL FROM.")

    # Envío a externos
    if ext_to:
        if best and best["ext_ok"] is not None:
            if best["ext_ok"]:
                report.add(
                    f"¿Puede enviar a externos ({ext_to})?",
                    OK,
                    f"RCPT TO aceptado en puerto {best['port']}",
                )
            else:
                report.add(
                    f"¿Puede enviar a externos ({ext_to})?",
                    FAIL,
                    f"RCPT TO rechazado — el relay posiblemente restringe el envío externo. Detalles: {best.get('error','')}",
                )
        else:
            report.add(
                f"¿Puede enviar a externos ({ext_to})?",
                UNK,
                "MAIL FROM falló antes de poder probar RCPT TO externo.",
            )
    else:
        report.add(
            "¿Puede enviar a externos?",
            UNK,
            "No se especificó dirección externa (--ext-to). Usa --ext-to usuario@dominio.com para probar.",
        )

    return report


# ─── CLI ─────────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Diagnóstico SMTP para relay bancario",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Ejemplos:
              python smtp_diagnostics.py
              python smtp_diagnostics.py --host smtp-relay.banco.local --from noreply@banco.com
              python smtp_diagnostics.py --host 192.168.1.10 --ext-to externo@gmail.com
        """),
    )
    p.add_argument("--host",    default="smtp-relay.banco.local",
                   help="SMTP relay host (default: smtp-relay.banco.local)")
    p.add_argument("--from",    dest="from_addr", default="noreply@banco.com",
                   help="Dirección From a probar (default: noreply@banco.com)")
    p.add_argument("--ext-to",  dest="ext_to", default="",
                   help="Dirección externa para probar relay (ej: usuario@gmail.com)")
    return p.parse_args()


def main():
    args = parse_args()
    report = run_diagnostics(
        host=args.host,
        from_addr=args.from_addr,
        ext_to=args.ext_to,
    )
    report.print()

    # Código de salida: 0 si al menos un puerto conectó, 1 si ninguno
    any_connected = any(
        r.value == OK for r in report.results if "TCP abierto" in r.label
    )
    sys.exit(0 if any_connected else 1)


if __name__ == "__main__":
    main()
