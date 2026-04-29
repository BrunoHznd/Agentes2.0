import os
import json
import time
import subprocess
import platform
import socket
import threading
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import requests

DEFAULT_INTERVAL = 60

@dataclass
class SpeedTestResult:
    download_mbps: float
    upload_mbps: float
    timestamp: str

@dataclass
class PingResult:
    ip: str
    reachable: bool
    avg_latency_ms: Optional[float]
    packet_loss: Optional[float]
    timestamp: str

# Variáveis globais
last_speed_test: Optional[SpeedTestResult] = None
last_ping_results: List[PingResult] = []


def load_agent_config() -> Dict[str, Any]:
    cfg_path = Path(__file__).parent / "agent.json"
    cfg: Dict[str, Any] = {}
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Erro ao carregar configuração: {e}")
            cfg = {}
    
    # Configurações básicas
    site = os.getenv("AGENT_SITE", cfg.get("site", "default"))
    server = os.getenv("AGENT_SERVER", cfg.get("server", "http://85.31.63.53:5656"))
    token = os.getenv("AGENT_TOKEN", cfg.get("token", ""))
    agent_name = os.getenv("AGENT_NAME", cfg.get("agent_name", socket.gethostname()))
    
    # Configurações de intervalo e loop
    interval_sec = int(os.getenv("AGENT_INTERVAL_SEC", str(cfg.get("interval_sec", DEFAULT_INTERVAL))))
    loop = os.getenv("AGENT_LOOP", str(cfg.get("loop", "true"))).lower() in ("1", "true", "yes")
    command_check_interval = int(os.getenv("AGENT_COMMAND_CHECK_INTERVAL", str(cfg.get("command_check_interval", 5))))
    
    # Configurações de câmeras e alvos de ping
    cameras = cfg.get("cameras") if isinstance(cfg.get("cameras"), list) else []
    ping_targets = cfg.get("ping_targets") if isinstance(cfg.get("ping_targets"), list) else []
    
    # Configurações de teste de velocidade
    speed_enabled = os.getenv("AGENT_SPEEDTEST", str(cfg.get("speedtest", "1"))).lower() in ("1", "true", "yes")
    try:
        speed_dl = int(os.getenv("AGENT_SPEEDTEST_DOWNLOAD_BYTES", str(cfg.get("speed_download_bytes", 100 * 1024 * 1024))))
    except Exception:
        speed_dl = 100 * 1024 * 1024
    try:
        speed_ul = int(os.getenv("AGENT_SPEEDTEST_UPLOAD_BYTES", str(cfg.get("speed_upload_bytes", 50 * 1024 * 1024))))
    except Exception:
        speed_ul = 50 * 1024 * 1024
    return {
        "site": site,
        "agent_name": agent_name,
        "server": server.rstrip("/"),
        "token": token,
        "interval_sec": interval_sec,
        "loop": loop,
        "command_check_interval": command_check_interval,
        "cameras": cameras,
        "ping_targets": ping_targets,
        "speedtest": speed_enabled,
        "speed_download_bytes": speed_dl,
        "speed_upload_bytes": speed_ul,
    }


def ping_ip(ip: str, count: int = 2, timeout_ms: int = 800) -> Tuple[bool, Optional[float], Optional[float], str]:
    """
    Retorna: (reachable, avg_latency_ms, packet_loss_percent, raw_output_tail)
    """
    is_windows = platform.system().lower().startswith("win")
    if is_windows:
        cmd = ["ping", "-n", str(count), "-w", str(timeout_ms), ip]
    else:
        # -W 1 (segundos no Linux), -c count
        cmd = ["ping", "-c", str(count), "-W", "1", ip]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=max(3, count * 2))
        output = (proc.stdout or "") + (proc.stderr or "")
        reachable = proc.returncode == 0
        avg_ms: Optional[float] = None
        loss_pct: Optional[float] = None
        if is_windows:
            # Ex.: Média = 4ms
            for line in output.splitlines():
                line = line.strip()
                if "Média" in line or "Average" in line:
                    # pegar último número antes de 'ms'
                    import re as _re
                    m = _re.search(r"(\d+)ms", line)
                    if m:
                        avg_ms = float(m.group(1))
            # Perda: Lost = X (Y% loss)
            for line in output.splitlines():
                if "perdidos" in line.lower() or "lost" in line.lower():
                    import re as _re
                    m = _re.search(r"\((\d+)%", line)
                    if m:
                        loss_pct = float(m.group(1))
        else:
            # Linux/mac output: rtt min/avg/max/mdev = 0.345/0.456/...
            for line in output.splitlines():
                if "rtt min/avg/max" in line or "round-trip min/avg/max" in line:
                    try:
                        part = line.split("=")[-1].strip().split("/")
                        avg_ms = float(part[1])
                    except Exception:
                        pass
            for line in output.splitlines():
                if "% packet loss" in line:
                    try:
                        loss_pct = float(line.split("% packet loss")[0].split(" ")[-1])
                    except Exception:
                        pass
        return reachable, avg_ms, loss_pct, output[-500:]
    except Exception as e:
        return False, None, None, f"ping error: {e}"

def get_agent_info(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Retorna informações do agente"""
    return {
        "agent_name": cfg.get("agent_name", "unnamed-agent"),
        "hostname": socket.gethostname(),
        "platform": platform.system(),
        "python_version": platform.python_version(),
        "ip_address": socket.gethostbyname(socket.gethostname()),
        "site": cfg.get("site", "default"),
        "version": "1.0.0"
    }

def run_network_test(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Executa todos os testes de rede e retorna os resultados"""
    global last_speed_test, last_ping_results
    
    print("Iniciando teste de rede...")
    
    # Executar teste de velocidade se configurado
    speed_result = None
    if cfg.get("speedtest", True):
        try:
            print("Executando teste de velocidade...")
            speed = speedtest(
                cfg["server"],
                cfg.get("speed_download_bytes", 1024*1024),
                cfg.get("speed_upload_bytes", 512*1024),
                cfg.get("token")
            )
            speed_result = SpeedTestResult(
                download_mbps=speed.get("download_mbps", 0),
                upload_mbps=speed.get("upload_mbps", 0),
                timestamp=datetime.now(timezone.utc).isoformat()
            )
            last_speed_test = speed_result
            print(f"Teste de velocidade concluído: {speed_result.download_mbps:.2f} Mbps down, {speed_result.upload_mbps:.2f} Mbps up")
        except Exception as e:
            print(f"Erro no teste de velocidade: {e}")

    # Executar ping nos alvos configurados
    ping_targets = list(set(cfg.get("ping_targets", []) + cfg.get("cameras", [])))
    ping_results = []
    
    for target in ping_targets:
        if not target or not isinstance(target, str) or not target.strip():
            continue
            
        target = target.strip()
        print(f"Testando ping para {target}...")
        
        try:
            reachable, avg_ms, loss_pct, _ = ping_ip(target)
            ping_result = PingResult(
                ip=target,
                reachable=reachable,
                avg_latency_ms=avg_ms,
                packet_loss=loss_pct,
                timestamp=datetime.now(timezone.utc).isoformat()
            )
            ping_results.append(ping_result)
            status = "OK" if reachable else "FALHA"
            print(f"  {target}: {status} (latência: {avg_ms or 'N/A'}ms, perda: {loss_pct or 'N/A'}%)")
        except Exception as e:
            print(f"  Erro ao testar {target}: {e}")
    
    last_ping_results = ping_results
    
    # Preparar resultado final
    result = {
        "agent_info": get_agent_info(cfg),
        "speed_test": asdict(speed_result) if speed_result else None,
        "ping_results": [asdict(r) for r in ping_results],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    return result

def check_for_commands(cfg: Dict[str, Any]) -> None:
    """Verifica se há comandos pendentes no servidor"""
    if not cfg.get("server"):
        return
        
    try:
        headers = {}
        if cfg.get("token"):
            headers["Authorization"] = f"Bearer {cfg['token']}"
        
        response = requests.get(
            f"{cfg['server']}/api/agent/commands",
            headers=headers,
            params={"agent_name": cfg.get("agent_name")},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            commands = data.get("commands", [])
            
            for cmd in commands:
                if cmd.get("type") == "run_network_test":
                    print("\n=== Comando recebido: Executar teste de rede ===")
                    result = run_network_test(cfg)
                    
                    # Enviar resultados de volta para o servidor
                    try:
                        post_url = f"{cfg['server']}/api/agent/test_results"
                        requests.post(
                            post_url,
                            json=result,
                            headers=headers,
                            timeout=30
                        )
                        print("Resultados enviados para o servidor com sucesso!")
                    except Exception as e:
                        print(f"Erro ao enviar resultados: {e}")
                
                elif cmd.get("type") == "update_ping_targets":
                    print("\n=== Atualizando alvos de ping ===")
                    new_targets = cmd.get("targets", [])
                    if isinstance(new_targets, list):
                        # Atualizar configuração local
                        cfg["ping_targets"] = new_targets
                        
                        # Salvar no arquivo de configuração
                        try:
                            cfg_path = Path(__file__).parent / "agent.json"
                            current_cfg = {}
                            if cfg_path.exists():
                                current_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                            
                            current_cfg["ping_targets"] = new_targets
                            cfg_path.write_text(json.dumps(current_cfg, indent=2), encoding="utf-8")
                            print(f"Alvos de ping atualizados: {', '.join(new_targets) if new_targets else 'Nenhum'}")
                        except Exception as e:
                            print(f"Erro ao salvar alvos de ping: {e}")
    
    except requests.exceptions.RequestException as e:
        print(f"Erro ao verificar comandos: {e}")
    except Exception as e:
        print(f"Erro inesperado ao verificar comandos: {e}")

def run_command_loop(cfg: Dict[str, Any]) -> None:
    """Loop principal de verificação de comandos"""
    print(f"\nIniciando loop de verificação de comandos (intervalo: {cfg.get('command_check_interval', 5)}s)")
    
    while True:
        try:
            check_for_commands(cfg)
        except Exception as e:
            print(f"Erro no loop de comandos: {e}")
        
        time.sleep(cfg.get("command_check_interval", 5))

def speedtest(server: str, download_bytes: int, upload_bytes: int, token: Optional[str] = None) -> Dict[str, float]:
    """Measure download/upload throughput using API endpoints provided by the server.
    Returns: { download_mbps, upload_mbps }
    """
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    # Teste de download
    download_speed = 0.0
    start_dl = time.time()
    try:
        print("  Iniciando teste de download...")
        dl_resp = requests.get(
            f"{server}/api/speedtest/download?size_bytes={download_bytes}",
            headers=headers,
            timeout=60,
            stream=True
        )
        dl_resp.raise_for_status()
        
        # Ler todos os dados para medir a velocidade
        total_bytes = 0
        for chunk in dl_resp.iter_content(chunk_size=1024*1024):  # 1MB chunks
            if not chunk:
                break
            total_bytes += len(chunk)
            
        dl_time = time.time() - start_dl
        if dl_time > 0:
            download_speed = total_bytes * 8 / dl_time / 1_000_000  # Mbps
            print(f"  Download: {download_speed:.2f} Mbps ({total_bytes / 1024 / 1024:.1f} MB em {dl_time:.2f}s)")
    except Exception as e:
        print(f"  Erro no teste de download: {e}")
    
    # Pequena pausa entre os testes
    time.sleep(1)
    
    # Teste de upload
    upload_speed = 0.0
    start_ul = time.time()
    try:
        print("  Iniciando teste de upload...")
        # Gerar dados para upload (zeros são mais rápidos)
        upload_data = b"\x00" * upload_bytes
        
        ul_resp = requests.post(
            f"{server}/api/speedtest/upload",
            headers=headers,
            data=upload_data,
            timeout=60
        )
        ul_resp.raise_for_status()
        
        upload_time = time.time() - start_ul
        if upload_time > 0:
            upload_speed = len(upload_data) * 8 / upload_time / 1_000_000  # Mbps
            print(f"  Upload: {upload_speed:.2f} Mbps ({len(upload_data) / 1024 / 1024:.1f} MB em {upload_time:.2f}s)")
    except Exception as e:
        print(f"  Erro no teste de upload: {e}")
    
    return {
        "download_mbps": round(download_speed, 2),
        "upload_mbps": round(upload_speed, 2)
    }

def post_report(server: str, site: str, token: Optional[str], payload: Dict[str, Any]) -> bool:
    """Send report to the server"""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    try:
        response = requests.post(
            f"{server}/api/agents/{site}/report",
            json=payload,
            headers=headers,
            timeout=10
        )
        if response.status_code != 200:
            print(f"Erro ao enviar relatório: {response.status_code} - {response.text}")
            return False
        return True
    except Exception as e:
        print(f"Erro ao enviar relatório: {e}")
        return False

def run_once(cfg: Dict[str, Any]) -> None:
    """Run one monitoring cycle"""
    print(f"\n=== Iniciando monitoramento ===")
    print(f"Site: {cfg.get('site', 'N/A')}")
    print(f"Agente: {cfg.get('agent_name', 'N/A')}")
    print(f"Servidor: {cfg.get('server', 'N/A')}")
    
    # Executar teste de rede
    result = run_network_test(cfg)
    
    # Enviar relatório para o servidor, se configurado
    if cfg.get("server"):
        print("\nEnviando relatório para o servidor...")
        success = post_report(
            cfg["server"], 
            cfg["site"], 
            cfg.get("token"), 
            result
        )
        if success:
            print("Relatório enviado com sucesso!")
        else:
            print("Falha ao enviar relatório")

if __name__ == "__main__":
    config = load_agent_config()
    if config.get("loop"):
        interval = int(config.get("interval_sec", DEFAULT_INTERVAL))
        while True:
            try:
                run_once(config)
            except Exception as e:
                print(f"[agent] error: {e}")
            time.sleep(interval)
    else:
        run_once(config)
