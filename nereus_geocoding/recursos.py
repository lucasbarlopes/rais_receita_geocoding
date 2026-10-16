"""Limitação de CPU/memória — portado do script Python original.

Fornece:
- :func:`baixar_prioridade`    processo em prioridade "abaixo do normal";
- :func:`aplicar_tetos_windows` teto RÍGIDO de memória e CPU via Job Object;
- :func:`iniciar_medicao`      zera a medição de CPU do processo;
- :func:`esperar_folga`        espera enquanto a máquina estiver ocupada;
- :func:`uso_proprio`          string com memória/CPU só deste processo.

Tudo degrada graciosamente se ``psutil`` não estiver instalado (sem pausa
automática) e fora do Windows (sem Job Object).
"""

from __future__ import annotations

import sys
import time
from datetime import datetime

from . import config

try:
    import psutil
except ImportError:  # psutil é opcional
    psutil = None


def _log(*partes) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S}  " + " ".join(str(p) for p in partes), flush=True)


def baixar_prioridade() -> None:
    """Coloca o processo (e threads) em prioridade 'abaixo do normal' no Windows."""
    if not config.PRIORIDADE_BAIXA:
        return
    try:
        if psutil:
            psutil.Process().nice(
                psutil.BELOW_NORMAL_PRIORITY_CLASS if sys.platform == "win32" else 10
            )
        elif sys.platform == "win32":
            import ctypes
            k32 = ctypes.windll.kernel32
            k32.SetPriorityClass(k32.GetCurrentProcess(), 0x4000)  # BELOW_NORMAL
        _log("prioridade do processo: abaixo do normal")
    except Exception as e:  # noqa: BLE001
        _log(f"AVISO: não consegui baixar a prioridade ({e})")


def aplicar_tetos_windows() -> None:
    """Coloca o processo num Job Object com teto de memória e de CPU (hard cap).

    Os tetos valem para o processo e tudo que ele criar, inclusive o DuckDB
    interno do geocodebr, que não tem opção própria de limite de memória.
    """
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes as wt

    class BASIC(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wt.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wt.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wt.DWORD),
                    ("SchedulingClass", wt.DWORD)]

    class IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in
                    ("ReadOp", "WriteOp", "OtherOp", "ReadBytes", "WriteBytes", "OtherBytes")]

    class EXTENDED(ctypes.Structure):
        _fields_ = [("Basic", BASIC), ("Io", IO),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    class CPU_RATE(ctypes.Structure):
        _fields_ = [("ControlFlags", wt.DWORD), ("CpuRate", wt.DWORD)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wt.HANDLE
    k32.GetCurrentProcess.restype = wt.HANDLE
    k32.SetInformationJobObject.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD]
    k32.AssignProcessToJobObject.argtypes = [wt.HANDLE, wt.HANDLE]
    job = k32.CreateJobObjectW(None, None)
    if not job:
        _log(f"AVISO: não consegui criar o Job Object (erro {ctypes.get_last_error()})")
        return

    ext = EXTENDED()
    ext.Basic.LimitFlags = 0x200                       # JOB_OBJECT_LIMIT_JOB_MEMORY
    ext.JobMemoryLimit = config.TETO_MEMORIA_GB * 2**30
    ok_mem = k32.SetInformationJobObject(job, 9, ctypes.byref(ext), ctypes.sizeof(ext))

    cpu = CPU_RATE(ControlFlags=0x1 | 0x4,             # ENABLE | HARD_CAP
                   CpuRate=int(config.TETO_CPU_PCT * 100))  # em centésimos de %
    ok_cpu = k32.SetInformationJobObject(job, 15, ctypes.byref(cpu), ctypes.sizeof(cpu))

    if not k32.AssignProcessToJobObject(job, k32.GetCurrentProcess()):
        _log(f"AVISO: tetos do Windows não aplicados (erro {ctypes.get_last_error()}) — "
             "valem só os limites do DuckDB e a pausa automática")
        return
    _log(f"teto do Windows: memória {config.TETO_MEMORIA_GB} GB {'ok' if ok_mem else 'FALHOU'} | "
         f"CPU {config.TETO_CPU_PCT}% {'ok' if ok_cpu else 'FALHOU'}")


def iniciar_medicao() -> None:
    """Zera a medição de CPU deste processo (chamar uma vez no início)."""
    if psutil:
        psutil.Process().cpu_percent(None)
    else:
        _log("AVISO: psutil não instalado — sem pausa automática quando a máquina "
             "estiver ocupada (python -m pip install psutil)")


def esperar_folga() -> None:
    """Antes de cada geocodificação: espera a máquina ter CPU e memória livres."""
    if psutil is None:
        return
    avisou = False
    while True:
        cpu = psutil.cpu_percent(interval=3)
        livre_gb = psutil.virtual_memory().available / 2**30
        if cpu <= config.PAUSA_CPU_PCT and livre_gb >= config.PAUSA_MEM_LIVRE:
            if avisou:
                _log("   máquina liberada, continuando")
            return
        if not avisou:
            _log(f"   máquina ocupada (CPU {cpu:.0f}%, {livre_gb:.0f} GB livres) — aguardando...")
            avisou = True
        time.sleep(config.PAUSA_CHECAR_S)


def uso_proprio() -> str:
    """Memória e CPU (média desde a chamada anterior) só deste processo."""
    if psutil is None:
        return ""
    p = psutil.Process()
    mem = p.memory_info().rss / 2**30
    cpu = p.cpu_percent(None) / psutil.cpu_count()
    return f" | este processo: {mem:.1f} GB, CPU {cpu:.0f}% da máquina"


def memoria_duckdb() -> str:
    """Limite de memória do DuckDB: abaixo do teto do Windows, para ele usar disco
    antes de o Windows negar memória (senão: Allocation failure)."""
    mem_gb = min(int(config.MEMORIA.upper().rstrip("GB")), int(config.TETO_MEMORIA_GB * 0.6))
    return f"{mem_gb}GB"
