#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingTCPServer

# Set workspace root
ROOT = Path(__file__).resolve().parents[1]

class PipelineManager:
    def __init__(self):
        self.process = None
        self.logs: list[str] = []
        self.running = False
        self.exit_code = None
        self.queue = queue.Queue()
        self.thread = None
        self.project_name = ""

    def start(self, cmd: list[str], project_name: str) -> bool:
        if self.running:
            return False
        
        self.logs = []
        self.running = True
        self.exit_code = None
        self.project_name = project_name
        self.queue = queue.Queue()
        
        self.logs.append(f"$ {' '.join(cmd)}\n")
        self.logs.append("Initializing Auto Studio Autopilot Dashboard...\n")
        
        try:
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                close_fds=True,
                env=env
            )
            
            # Start background thread to read output
            def enqueue_output(out, q):
                for line in iter(out.readline, b''):
                    q.put(line.decode('utf-8', errors='replace'))
                out.close()

            self.thread = threading.Thread(
                target=enqueue_output, 
                args=(self.process.stdout, self.queue),
                daemon=True
            )
            self.thread.start()
            return True
        except Exception as e:
            self.logs.append(f"Failed to spawn pipeline script: {e}\n")
            self.running = False
            return False

    def update(self):
        # Read all currently buffered logs from the queue
        while not self.queue.empty():
            try:
                line = self.queue.get_nowait()
                self.logs.append(line)
            except queue.Empty:
                break
        
        if self.process:
            poll = self.process.poll()
            if poll is not None:
                self.exit_code = poll
                self.running = False
                
                # Consume any trailing lines in queue
                while not self.queue.empty():
                    try:
                        line = self.queue.get_nowait()
                        self.logs.append(line)
                    except queue.Empty:
                        break
                
                if poll == 0:
                    self.logs.append("\n[Pipeline finished successfully!]\n")
                else:
                    self.logs.append(f"\n[Pipeline failed with exit code: {poll}]\n")
                self.process = None

    def stop(self):
        if self.process:
            self.logs.append("\n[Aborting pipeline execution...]\n")
            try:
                self.process.terminate()
                self.process.wait(timeout=3)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.running = False
            self.process = None
            self.logs.append("[Pipeline Stopped]\n")


# Global Manager Singleton
manager = PipelineManager()

class ThreadingHTTPServer(ThreadingTCPServer, HTTPServer):
    # Enable socket re-use to prevent "Address already in use" errors during quick restarts
    allow_reuse_address = True

class DashboardHandler(BaseHTTPRequestHandler):
    def serve_file(self, file_path: Path):
        # Security check to prevent traversing outside the workspace
        try:
            file_path.resolve().relative_to(ROOT)
        except ValueError:
            self.send_error(403, "Access Denied")
            return

        if not file_path.exists() or not file_path.is_file():
            self.send_error(404, "File Not Found")
            return
        
        ext = file_path.suffix.lower()
        content_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".svg": "image/svg+xml",
            ".mp4": "video/mp4",
            ".srt": "text/plain; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".csv": "text/csv; charset=utf-8",
        }
        content_type = content_types.get(ext, "application/octet-stream")
        
        try:
            # Handle Range HTTP requests for Safari HTML5 video compatibility
            range_header = self.headers.get("Range")
            stat = file_path.stat()
            file_size = stat.st_size
            
            if range_header and range_header.startswith("bytes="):
                ranges = range_header.split("=")[1].split("-")
                start = int(ranges[0])
                end = int(ranges[1]) if ranges[1] else file_size - 1
                
                if start >= file_size or end >= file_size or start > end:
                    self.send_response(416, "Requested Range Not Satisfiable")
                    self.send_header("Content-Range", f"bytes */{file_size}")
                    self.end_headers()
                    return
                
                chunk_size = end - start + 1
                self.send_response(206)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                self.send_header("Content-Length", str(chunk_size))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                
                with open(file_path, "rb") as f:
                    f.seek(start)
                    self.wfile.write(f.read(chunk_size))
            else:
                data = file_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
        except Exception as e:
            self.send_error(500, f"Internal Server Error: {e}")

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            default_ollama = "qwen2.5vl"
            default_openai = "gpt-4.1-mini"
            try:
                settings_path = ROOT / "config" / "settings.json"
                if settings_path.exists():
                    settings_data = json.loads(settings_path.read_text(encoding="utf-8"))
                    default_ollama = settings_data.get("default_model_ollama", "qwen2.5vl")
                    default_openai = settings_data.get("default_model_openai", "gpt-4.1-mini")
            except Exception:
                pass
                
            # 1. Dynamically build Ollama dropdown options by querying local Ollama tags
            ollama_options_html = f'<option class="opt-ollama" value="{default_ollama}">默认模型 ({default_ollama})</option>'
            try:
                import ollama
                
                host = None
                cfg_path = ROOT / "config" / "tagger_config.json"
                if cfg_path.exists():
                    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                    host = cfg.get("vision_config", {}).get("api_base")
                    if host and host.endswith("/v1"):
                        host = host[:-3]
                
                client = ollama.Client(host=host) if host else ollama.Client()
                response = client.list()
                
                if hasattr(response, "models"):
                    models_list = response.models
                elif isinstance(response, dict):
                    models_list = response.get("models", [])
                else:
                    models_list = []
                
                seen_names = {default_ollama}
                for m in models_list:
                    m_name = None
                    if hasattr(m, "model"):
                        m_name = m.model
                    elif hasattr(m, "name"):
                        m_name = m.name
                    elif isinstance(m, dict):
                        m_name = m.get("model") or m.get("name")
                    else:
                        m_name = str(m)
                        
                    if m_name and m_name not in seen_names:
                        display_name = m_name
                        if ":" in m_name:
                            name_part, tag_part = m_name.split(":", 1)
                            if tag_part == "latest":
                                display_name = name_part
                        ollama_options_html += f'<option class="opt-ollama" value="{m_name}">{display_name}</option>'
                        seen_names.add(m_name)
            except Exception:
                # Local Ollama client fail fallback to static defaults
                static_ollama = ["qwen2.5vl", "qwen3.5:9b", "deepseek-r1:8b", "llama3.2:latest"]
                for m in static_ollama:
                    if m != default_ollama:
                        ollama_options_html += f'<option class="opt-ollama" value="{m}">{m}</option>'

            # 2. Build OpenAI dropdown options
            openai_options_html = f'<option class="opt-openai" value="{default_openai}" style="display:none;">默认模型 ({default_openai})</option>'
            static_openai = ["gpt-4.1-mini", "gpt-4o", "o3-mini"]
            for m in static_openai:
                if m != default_openai:
                    display = "gpt-4o-mini" if m == "gpt-4.1-mini" else m
                    openai_options_html += f'<option class="opt-openai" value="{m}" style="display:none;">{display}</option>'
                
            # Replace placeholders in HTML
            html = HTML_CONTENT.replace("{{DEFAULT_OLLAMA_MODEL}}", default_ollama).replace("{{DEFAULT_OPENAI_MODEL}}", default_openai)
            html = html.replace("{{OLLAMA_MODEL_OPTIONS}}", ollama_options_html).replace("{{OPENAI_MODEL_OPTIONS}}", openai_options_html)
            
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
            return
        
        if self.path.startswith("/api/status"):
            manager.update()
            
            screenshots = []
            if manager.project_name:
                images_dir = ROOT / "outputs" / "images" / manager.project_name
                if images_dir.exists():
                    screenshots = [
                        f.name for f in sorted(
                            images_dir.glob("page_*.png"),
                            key=lambda p: int(p.stem.split("_")[1]) if "_" in p.stem and p.stem.split("_")[1].isdigit() else 0
                        )
                    ]
            
            reports = {}
            if manager.project_name:
                reports_dir = ROOT / "outputs" / "reports"
                if reports_dir.exists():
                    for ext in ["json", "csv"]:
                        candidate = reports_dir / f"{manager.project_name}_assets.{ext}"
                        if candidate.exists():
                            reports[ext] = f"/outputs/reports/{candidate.name}"
                    candidate_md = reports_dir / f"{manager.project_name}_assets_report.md"
                    if candidate_md.exists():
                        reports["md"] = f"/outputs/reports/{candidate_md.name}"
                    
                    canva_csv = ROOT / "outputs" / "content" / f"{manager.project_name}_canva.csv"
                    if canva_csv.exists():
                        reports["canva_csv"] = f"/outputs/content/{canva_csv.name}"
                        
            video_url = ""
            if manager.project_name:
                video_path = ROOT / "outputs" / "video" / f"{manager.project_name}.mp4"
                if video_path.exists():
                    video_url = f"/outputs/video/{manager.project_name}.mp4"

            res = {
                "running": manager.running,
                "exit_code": manager.exit_code,
                "project_name": manager.project_name,
                "logs": manager.logs,
                "screenshots": screenshots,
                "reports": reports,
                "video_url": video_url
            }
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
            return

        if self.path.startswith("/outputs/"):
            # Clean query parameters
            clean_path = self.path.split("?")[0]
            rel_path = clean_path[len("/outputs/"):]
            file_path = ROOT / "outputs" / rel_path
            self.serve_file(file_path)
            return
            
        self.send_error(404, "Not Found")

    def do_POST(self):
        if self.path == "/api/start":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            params = json.loads(body.decode("utf-8"))
            
            project_name = params.get("name", "project").strip() or "project"
            
            # Map parameters to command-line args for scripts/run_pipeline.py
            cmd = [
                sys.executable,
                "-u",
                str(ROOT / "scripts" / "run_pipeline.py"),
                "--name", project_name,
                "--brand", params.get("brand", "BMW"),
                "--model", params.get("model", "i3"),
                "--series", params.get("series", "Neue Klasse"),
                "--topic", params.get("topic", "BMW Neue Klasse i3"),
                "--column", params.get("column", "新车档案"),
                "--angle", params.get("angle", "宝马终于开始真正做电动车了"),
                "--provider", params.get("provider", "ollama"),
                "--scale-factor", str(params.get("scale_factor", 2)),
            ]
            
            model_name = params.get("model_name")
            if model_name and model_name != "default":
                cmd.extend(["--llm-model", model_name])
            
            if params.get("move"):
                cmd.append("--move")
            if params.get("vision"):
                cmd.append("--vision")
            if params.get("skip_tagging"):
                cmd.append("--skip-tagging")
            if params.get("skip_generation"):
                cmd.append("--skip-generation")
            if params.get("content"):
                cmd.extend(["--content", params["content"]])
            
            success = manager.start(cmd, project_name)
            
            self.send_response(200 if success else 400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "started" if success else "already_running"}).encode("utf-8"))
            return

        if self.path == "/api/stop":
            manager.stop()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "stopped"}).encode("utf-8"))
            return

        self.send_error(404, "Not Found")


# GORGEOUS GLASSMORPHIC H5 FRONTEND UI
HTML_CONTENT = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Auto Studio — Autopilot 自动创意工作站</title>
    
    <!-- Premium Google Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&family=Outfit:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    
    <!-- FontAwesome Icons -->
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    
    <style>
        :root {
            --bg-base: #08090d;
            --card-bg: rgba(18, 22, 35, 0.65);
            --card-border: rgba(255, 255, 255, 0.08);
            --card-active-border: rgba(139, 92, 246, 0.35);
            --text-primary: #f3f4f6;
            --text-secondary: #9ca3af;
            --text-muted: #6b7280;
            --accent-purple: #8b5cf6;
            --accent-blue: #3b82f6;
            --accent-success: #10b981;
            --accent-warning: #f59e0b;
            --accent-error: #ef4444;
            --gradient-primary: linear-gradient(135deg, #8b5cf6 0%, #3b82f6 100%);
            --gradient-success: linear-gradient(135deg, #10b981 0%, #059669 100%);
            --gradient-glow: 0 0 25px rgba(139, 92, 246, 0.45);
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            background-color: var(--bg-base);
            color: var(--text-primary);
            font-family: 'Inter', sans-serif;
            min-height: 100vh;
            overflow-x: hidden;
            position: relative;
        }

        /* Futuristic Background Blobs */
        .bg-blob {
            position: absolute;
            border-radius: 50%;
            filter: blur(140px);
            z-index: -1;
            opacity: 0.45;
        }
        .blob-purple {
            width: 500px;
            height: 500px;
            background: #7c3aed;
            top: -200px;
            left: -150px;
        }
        .blob-blue {
            width: 600px;
            height: 600px;
            background: #2563eb;
            bottom: -200px;
            right: -100px;
        }
        .blob-pink {
            width: 400px;
            height: 400px;
            background: #db2777;
            top: 40%;
            left: 45%;
            opacity: 0.15;
        }

        /* Container & Structure */
        .wrapper {
            max-width: 1440px;
            margin: 0 auto;
            padding: 30px 25px;
        }

        header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 35px;
            padding-bottom: 20px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }

        .logo-section h1 {
            font-family: 'Outfit', sans-serif;
            font-size: 32px;
            font-weight: 800;
            background: linear-gradient(to right, #fff 30%, #a78bfa 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -0.5px;
            display: flex;
            align-items: center;
            gap: 12px;
        }
        
        .logo-section h1 i {
            background: var(--gradient-primary);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            filter: drop-shadow(0 0 10px rgba(139,92,246,0.5));
        }

        .logo-section p {
            color: var(--text-secondary);
            font-size: 14px;
            margin-top: 4px;
            font-weight: 400;
        }

        .system-status {
            display: flex;
            align-items: center;
            gap: 10px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.05);
            padding: 8px 16px;
            border-radius: 12px;
            font-size: 13px;
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background-color: var(--text-muted);
            box-shadow: 0 0 8px var(--text-muted);
        }
        .status-dot.active {
            background-color: var(--accent-purple);
            box-shadow: 0 0 10px var(--accent-purple);
            animation: pulse-purple 2s infinite;
        }
        .status-dot.success {
            background-color: var(--accent-success);
            box-shadow: 0 0 10px var(--accent-success);
        }

        @keyframes pulse-purple {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(139, 92, 246, 0.7); }
            70% { transform: scale(1.1); box-shadow: 0 0 0 8px rgba(139, 92, 246, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(139, 92, 246, 0); }
        }

        /* Dashboard Grid Layout */
        .dashboard-grid {
            display: grid;
            grid-template-columns: 460px 1fr;
            gap: 30px;
            align-items: start;
        }

        @media (max-width: 1024px) {
            .dashboard-grid {
                grid-template-columns: 1fr;
            }
        }

        /* Glass Cards */
        .card {
            background: var(--card-bg);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid var(--card-border);
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 12px 40px 0 rgba(0, 0, 0, 0.4);
            transition: border-color 0.3s ease, box-shadow 0.3s ease;
        }

        .card:hover {
            border-color: rgba(255, 255, 255, 0.12);
        }

        .card-title {
            font-family: 'Outfit', sans-serif;
            font-size: 20px;
            font-weight: 700;
            margin-bottom: 22px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .card-title i {
            color: var(--accent-purple);
        }

        /* Forms Elements */
        .form-group {
            margin-bottom: 18px;
        }

        .form-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
        }

        label {
            display: block;
            font-size: 13px;
            font-weight: 600;
            color: var(--text-secondary);
            margin-bottom: 8px;
            letter-spacing: 0.3px;
        }

        input[type="text"], select {
            width: 100%;
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.1);
            color: var(--text-primary);
            padding: 11px 14px;
            border-radius: 10px;
            font-family: inherit;
            font-size: 14px;
            transition: all 0.25s ease;
        }

        input[type="text"]:focus, select:focus {
            outline: none;
            border-color: var(--accent-purple);
            box-shadow: 0 0 12px rgba(139, 92, 246, 0.15);
            background: rgba(0, 0, 0, 0.45);
        }

        /* Switch Styling */
        .switch-container {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px 14px;
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            margin-bottom: 12px;
            transition: background 0.2s ease;
        }
        .switch-container:hover {
            background: rgba(255, 255, 255, 0.04);
        }

        .switch-info {
            display: flex;
            flex-direction: column;
            gap: 2px;
        }
        .switch-info span {
            font-size: 13.5px;
            font-weight: 550;
        }
        .switch-info small {
            font-size: 11px;
            color: var(--text-muted);
        }

        .switch {
            position: relative;
            display: inline-block;
            width: 44px;
            height: 24px;
        }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider {
            position: absolute;
            cursor: pointer;
            top: 0; left: 0; right: 0; bottom: 0;
            background-color: rgba(255,255,255,0.15);
            transition: .3s;
            border-radius: 34px;
        }
        .slider:before {
            position: absolute;
            content: "";
            height: 16px; width: 16px;
            left: 4px; bottom: 4px;
            background-color: white;
            transition: .3s;
            border-radius: 50%;
        }
        input:checked + .slider {
            background: var(--gradient-primary);
        }
        input:checked + .slider:before {
            transform: translateX(20px);
        }

        /* Trigger Button */
        .btn-trigger {
            width: 100%;
            background: var(--gradient-primary);
            border: none;
            color: white;
            padding: 15px;
            border-radius: 12px;
            font-family: 'Outfit', sans-serif;
            font-size: 16px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(139, 92, 246, 0.3);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            margin-top: 15px;
        }

        .btn-trigger:hover {
            transform: translateY(-2px);
            box-shadow: var(--gradient-glow);
        }

        .btn-trigger:active {
            transform: translateY(0);
        }

        .btn-trigger:disabled {
            background: rgba(255, 255, 255, 0.1);
            color: var(--text-muted);
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }

        .btn-abort {
            background: linear-gradient(135deg, var(--accent-error) 0%, #991b1b 100%) !important;
            box-shadow: 0 4px 15px rgba(239, 68, 68, 0.3) !important;
        }
        .btn-abort:hover {
            box-shadow: 0 0 25px rgba(239, 68, 68, 0.45) !important;
        }

        /* Stepper & Progress Section */
        .monitor-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        
        .progress-bar-container {
            width: 100%;
            height: 6px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 30px;
            margin-bottom: 25px;
            overflow: hidden;
            position: relative;
        }
        
        .progress-bar-fill {
            width: 0%;
            height: 100%;
            background: var(--gradient-primary);
            border-radius: 30px;
            transition: width 0.5s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 0 10px var(--accent-purple);
        }

        .stepper {
            display: flex;
            justify-content: space-between;
            position: relative;
            margin-bottom: 30px;
            padding: 0 10px;
        }
        
        .stepper::before {
            content: "";
            position: absolute;
            height: 2px;
            background: rgba(255,255,255,0.06);
            top: 15px; left: 35px; right: 35px;
            z-index: 1;
        }
        
        .step {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 10px;
            z-index: 2;
            width: 70px;
            text-align: center;
        }
        
        .step-circle {
            width: 32px;
            height: 32px;
            border-radius: 50%;
            background: #111420;
            border: 2px solid rgba(255,255,255,0.12);
            color: var(--text-muted);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            font-weight: 700;
            transition: all 0.3s ease;
        }
        
        .step-label {
            font-size: 11px;
            font-weight: 600;
            color: var(--text-muted);
            transition: all 0.3s ease;
        }
        
        /* Stepper States */
        .step.pending .step-circle {
            background: #111420;
        }
        
        .step.active .step-circle {
            border-color: var(--accent-purple);
            color: var(--accent-purple);
            background: rgba(139, 92, 246, 0.15);
            box-shadow: 0 0 15px rgba(139, 92, 246, 0.3);
            animation: pulse-border 1.5s infinite;
        }
        
        .step.active .step-label {
            color: var(--text-primary);
            font-weight: 700;
        }
        
        .step.completed .step-circle {
            border-color: var(--accent-success);
            color: white;
            background: var(--accent-success);
            box-shadow: 0 0 10px rgba(16, 185, 129, 0.2);
        }
        
        .step.completed .step-label {
            color: var(--accent-success);
        }

        @keyframes pulse-border {
            0% { border-color: rgba(139, 92, 246, 0.4); }
            50% { border-color: rgba(139, 92, 246, 1); }
            100% { border-color: rgba(139, 92, 246, 0.4); }
        }

        /* Console Terminal emulator */
        .terminal {
            background: #05070a;
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
        }
        
        .terminal-header {
            background: #0d0f14;
            padding: 10px 16px;
            display: flex;
            align-items: center;
            gap: 8px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        
        .terminal-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
        }
        .td-red { background: #ff5f56; }
        .td-yellow { background: #ffbd2e; }
        .td-green { background: #27c93f; }
        
        .terminal-title {
            color: var(--text-secondary);
            font-size: 12px;
            font-family: 'JetBrains Mono', monospace;
            margin-left: 10px;
            font-weight: 500;
        }
        
        .terminal-body {
            height: 380px;
            overflow-y: auto;
            padding: 18px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 12.5px;
            line-height: 1.5;
            color: #d1d5db;
            scroll-behavior: smooth;
        }
        
        .terminal-body::-webkit-scrollbar {
            width: 8px;
        }
        .terminal-body::-webkit-scrollbar-track {
            background: transparent;
        }
        .terminal-body::-webkit-scrollbar-thumb {
            background: rgba(255,255,255,0.1);
            border-radius: 4px;
        }
        
        .log-line {
            white-space: pre-wrap;
            margin-bottom: 4px;
        }
        .log-line.cmd { color: #818cf8; font-weight: bold; }
        .log-line.stage { color: #a78bfa; font-weight: bold; margin-top: 10px; border-left: 3px solid #8b5cf6; padding-left: 8px; }
        .log-line.success { color: #34d399; }
        .log-line.error { color: #f87171; }
        .log-line.warning { color: #fbbf24; }
        .log-line.done { color: #60a5fa; font-weight: bold; }
        
        .cursor {
            display: inline-block;
            width: 7px;
            height: 14px;
            background: #a78bfa;
            animation: cursor-blink 1s infinite;
            vertical-align: middle;
            margin-left: 4px;
        }
        @keyframes cursor-blink {
            0%, 49% { opacity: 0; }
            50%, 100% { opacity: 1; }
        }

        /* Results Area Showcase - Slide Up */
        .results-section {
            margin-top: 40px;
            display: none;
            animation: slide-up 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }

        @keyframes slide-up {
            from { opacity: 0; transform: translateY(40px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .results-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
        }

        @media (max-width: 900px) {
            .results-grid {
                grid-template-columns: 1fr;
            }
        }

        /* Video Showcase */
        .video-container {
            width: 100%;
            background: #000;
            border-radius: 12px;
            overflow: hidden;
            aspect-ratio: 3 / 4;
            border: 1px solid rgba(255,255,255,0.08);
            box-shadow: 0 8px 30px rgba(0,0,0,0.6);
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
        }

        .video-container video {
            width: 100%;
            height: 100%;
            object-fit: contain;
        }

        /* Image Showcase */
        .screenshots-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
            gap: 15px;
            max-height: 520px;
            overflow-y: auto;
            padding-right: 8px;
        }

        .screenshots-grid::-webkit-scrollbar {
            width: 6px;
        }
        .screenshots-grid::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.15);
            border-radius: 10px;
        }

        .screenshot-thumbnail {
            position: relative;
            aspect-ratio: 3 / 4;
            border-radius: 8px;
            overflow: hidden;
            border: 1px solid rgba(255,255,255,0.06);
            cursor: zoom-in;
            background: #090b0f;
            transition: transform 0.25s ease, border-color 0.25s ease;
        }

        .screenshot-thumbnail:hover {
            transform: scale(1.04);
            border-color: var(--accent-purple);
        }

        .screenshot-thumbnail img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        
        .screenshot-label {
            position: absolute;
            bottom: 0; left: 0; right: 0;
            background: linear-gradient(180deg, transparent 0%, rgba(0,0,0,0.85) 100%);
            padding: 8px;
            font-size: 11px;
            text-align: center;
            font-weight: 500;
        }

        /* Download Reports Card */
        .reports-container {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 15px;
            margin-top: 22px;
        }

        .report-download-btn {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 12px;
            padding: 16px;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 10px;
            color: var(--text-primary);
            text-decoration: none;
            font-size: 13px;
            font-weight: 600;
            transition: all 0.25s ease;
            text-align: center;
        }

        .report-download-btn i {
            font-size: 26px;
            transition: transform 0.2s ease;
        }

        .report-download-btn:hover {
            background: rgba(139, 92, 246, 0.08);
            border-color: var(--card-active-border);
            transform: translateY(-3px);
        }
        .report-download-btn:hover i {
            transform: scale(1.15);
        }

        .report-download-btn.json-file i { color: #f59e0b; }
        .report-download-btn.csv-file i { color: #10b981; }
        .report-download-btn.md-file i { color: #3b82f6; }
        .report-download-btn.canva-file i { color: #ec4899; }

        /* Fullscreen Lightbox Overlay */
        .lightbox {
            position: fixed;
            inset: 0;
            background: rgba(4, 5, 8, 0.95);
            z-index: 1000;
            display: none;
            align-items: center;
            justify-content: center;
            opacity: 0;
            transition: opacity 0.3s ease;
            backdrop-filter: blur(8px);
        }

        .lightbox.active {
            display: flex;
            opacity: 1;
        }

        .lightbox-content {
            position: relative;
            max-width: 90%;
            max-height: 90%;
            box-shadow: 0 0 40px rgba(0,0,0,0.8);
            border-radius: 12px;
            overflow: hidden;
        }

        .lightbox-content img {
            max-width: 100vw;
            max-height: 85vh;
            object-fit: contain;
            display: block;
        }

        .lightbox-close {
            position: absolute;
            top: -50px;
            right: 0;
            background: none;
            border: none;
            color: #d1d5db;
            font-size: 32px;
            cursor: pointer;
            transition: color 0.2s ease;
        }

        .lightbox-close:hover {
            color: white;
        }
    </style>
</head>
<body>

    <div class="bg-blob blob-purple"></div>
    <div class="bg-blob blob-blue"></div>
    <div class="bg-blob blob-pink"></div>

    <div class="wrapper">
        <!-- Dashboard Header -->
        <header>
            <div class="logo-section">
                <h1><i class="fa-solid fa-wand-magic-sparkles"></i> Auto Studio</h1>
                <p>Ollama & Playwright 无损竖屏视频自动化工厂</p>
            </div>
            
            <div class="system-status" id="sys-status-badge">
                <span class="status-dot" id="sys-status-dot"></span>
                <span id="sys-status-text">系统就绪，等待指令</span>
            </div>
        </header>

        <!-- Main Workspace Grid -->
        <div class="dashboard-grid">
            
            <!-- Left Side: Config Panel -->
            <section class="card">
                <h2 class="card-title"><i class="fa-solid fa-sliders"></i> 工作流参数配置</h2>
                
                <form id="config-form">
                    
                    <div class="form-row">
                        <div class="form-group">
                            <label for="provider">LLM 驱动源</label>
                            <select id="provider" onchange="toggleProviderModels()">
                                <option value="ollama">Ollama (本地私有)</option>
                                <option value="openai">OpenAI (云端 API)</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label for="model_name">大模型名称</label>
                            <select id="model_name">
                                <!-- Ollama Options -->
                                {{OLLAMA_MODEL_OPTIONS}}
                                <!-- OpenAI Options -->
                                {{OPENAI_MODEL_OPTIONS}}
                            </select>
                        </div>
                    </div>

                    <div class="form-row">
                        <div class="form-group">
                            <label for="name">项目标识符 (文件夹名)</label>
                            <input type="text" id="name" value="bmw_i3" placeholder="例如: bmw_i3" required>
                        </div>
                        <div class="form-group">
                            <label for="scale_factor">渲染分辨率</label>
                            <select id="scale_factor">
                                <option value="2" selected>Retina 2K 超清 (2160x2880, 强烈推荐)</option>
                                <option value="3">4K 极致画质 (3240x4320)</option>
                                <option value="1">1x 快速预览 (1080x1440)</option>
                            </select>
                        </div>
                    </div>

                    <div class="form-row" style="grid-template-columns: 1fr 1fr 1fr; gap: 10px;">
                        <div class="form-group">
                            <label for="brand">汽车品牌 (Brand)</label>
                            <input type="text" id="brand" value="BMW" placeholder="例如: BMW" required>
                        </div>
                        <div class="form-group">
                            <label for="model">具体车型 (Model)</label>
                            <input type="text" id="model" value="i3" placeholder="例如: i3" required>
                        </div>
                        <div class="form-group">
                            <label for="series">所属车系 (Series)</label>
                            <input type="text" id="series" value="Neue Klasse" placeholder="例如: Neue Klasse" required>
                        </div>
                    </div>

                    <div class="form-group">
                        <label for="topic">创作主题</label>
                        <input type="text" id="topic" value="BMW Neue Klasse i3" placeholder="例如: 宝马新世代i3" required>
                    </div>

                    <div class="form-group">
                        <label for="angle">创意卖点 / 痛点角度</label>
                        <input type="text" id="angle" value="宝马终于开始真正做电动车了" placeholder="例如: 百年品牌的电动逆袭">
                    </div>

                    <div class="form-group">
                        <label for="column">栏目风格样式</label>
                        <select id="column">
                            <option value="新车档案" selected>新车档案 (偏严谨科普)</option>
                            <option value="犀利车评">犀利车评 (偏吐槽主观)</option>
                            <option value="买车指南">买车指南 (偏性价比分析)</option>
                        </select>
                    </div>

                    <div class="form-group" style="margin-top: 10px;">
                        <label>打标整理参数 (Stage 1)</label>
                        
                        <div class="switch-container">
                            <div class="switch-info">
                                <span>视觉多模态识别</span>
                                <small>采用 Vision 模型自动分类 (未开启则使用文字规则)</small>
                            </div>
                            <label class="switch">
                                <input type="checkbox" id="vision" checked>
                                <span class="slider"></span>
                            </label>
                        </div>

                        <div class="switch-container">
                            <div class="switch-info">
                                <span>移动原始素材</span>
                                <small>将 raw 图片剪切到库中，否则默认为拷贝</small>
                            </div>
                            <label class="switch">
                                <input type="checkbox" id="move">
                                <span class="slider"></span>
                            </label>
                        </div>
                    </div>

                    <div class="form-group">
                        <label>旁路跳过选项 (局部测试)</label>
                        
                        <div class="switch-container">
                            <div class="switch-info">
                                <span>跳过资产分类 (Stage 1)</span>
                                <small>直接从已整理好的 library 目录读取素材</small>
                            </div>
                            <label class="switch">
                                <input type="checkbox" id="skip_tagging">
                                <span class="slider"></span>
                            </label>
                        </div>

                        <div class="switch-container">
                            <div class="switch-info">
                                <span>跳过视频渲染 (Stage 2)</span>
                                <small>只对原始图片分拣打标，不生成文案和视频</small>
                            </div>
                            <label class="switch">
                                <input type="checkbox" id="skip_generation">
                                <span class="slider"></span>
                            </label>
                        </div>
                    </div>

                    <!-- Giant Start Button -->
                    <button type="button" id="trigger-btn" class="btn-trigger" onclick="togglePipeline()">
                        <i class="fa-solid fa-play"></i> 启动全自动工作流
                    </button>
                </form>
            </section>

            <!-- Right Side: Live Console & Stepper -->
            <section class="card">
                <div class="monitor-header">
                    <h2 class="card-title"><i class="fa-solid fa-microchip"></i> 生产实况监视器</h2>
                    <span id="pipeline-timer" style="font-family: 'JetBrains Mono', monospace; font-size: 14px; color: var(--text-secondary);">00:00</span>
                </div>
                
                <!-- Linear Stepper -->
                <div class="stepper" id="stepper">
                    <div class="step pending" id="step-1">
                        <div class="step-circle">1</div>
                        <div class="step-label">图片分拣</div>
                    </div>
                    <div class="step pending" id="step-2">
                        <div class="step-circle">2</div>
                        <div class="step-label">文案创作</div>
                    </div>
                    <div class="step pending" id="step-3">
                        <div class="step-circle">3</div>
                        <div class="step-label">画面对齐</div>
                    </div>
                    <div class="step pending" id="step-4">
                        <div class="step-circle">4</div>
                        <div class="step-label">海报生成</div>
                    </div>
                    <div class="step pending" id="step-5">
                        <div class="step-circle">5</div>
                        <div class="step-label">字幕合成</div>
                    </div>
                    <div class="step pending" id="step-6">
                        <div class="step-circle">6</div>
                        <div class="step-label">MP4压缩</div>
                    </div>
                </div>

                <!-- Custom Progress Bar -->
                <div class="progress-bar-container">
                    <div class="progress-bar-fill" id="progress-bar"></div>
                </div>

                <!-- Styled Terminal Console emulator -->
                <div class="terminal">
                    <div class="terminal-header">
                        <span class="terminal-dot td-red"></span>
                        <span class="terminal-dot td-yellow"></span>
                        <span class="terminal-dot td-green"></span>
                        <span class="terminal-title">pipeline.log — auto_studio</span>
                    </div>
                    <div class="terminal-body" id="console-output">
                        <div class="log-line text-muted">工作站已就绪，请输入左侧配置并点击“启动全自动工作流”。</div>
                        <span class="cursor"></span>
                    </div>
                </div>
            </section>
        </div>

        <!-- Hidden Slide-up Results Section -->
        <section class="card results-section" id="results-section">
            <h2 class="card-title" style="margin-bottom: 25px;"><i class="fa-solid fa-square-poll-vertical"></i> 生产成果看板</h2>
            
            <div class="results-grid">
                <!-- Left: MP4 Theater Card -->
                <div>
                    <h3 style="font-size: 16px; font-weight: 600; margin-bottom: 12px; color: var(--text-secondary);">
                        <i class="fa-solid fa-film"></i> 最终超清视频 (HTML5 播放器)
                    </h3>
                    <div class="video-container">
                        <video id="output-video" controls playsinline>
                            您的浏览器不支持 HTML5 视频播放。
                        </video>
                    </div>
                </div>
                
                <!-- Right: Screenshots grid & download options -->
                <div>
                    <h3 style="font-size: 16px; font-weight: 600; margin-bottom: 12px; color: var(--text-secondary);">
                        <i class="fa-solid fa-images"></i> 视网膜无损截图分片
                    </h3>
                    <div class="screenshots-grid" id="screenshots-grid">
                        <!-- Filled by JS -->
                    </div>
                    
                    <h3 style="font-size: 16px; font-weight: 600; margin-top: 25px; margin-bottom: 12px; color: var(--text-secondary);">
                        <i class="fa-solid fa-file-invoice"></i> 生成资产报表下载
                    </h3>
                    <div class="reports-container" id="reports-container">
                        <!-- Filled by JS -->
                    </div>
                </div>
            </div>
        </section>
    </div>

    <!-- Lightbox Zoom Modal overlay -->
    <div class="lightbox" id="lightbox" onclick="closeLightbox()">
        <div class="lightbox-content" onclick="event.stopPropagation()">
            <button class="lightbox-close" onclick="closeLightbox()">&times;</button>
            <img id="lightbox-img" src="" alt="超清大图">
        </div>
    </div>

    <!-- Page Logic Script -->
    <script>
        let pollInterval = null;
        let timerInterval = null;
        let isRunning = false;
        let secondsElapsed = 0;
        let currentLogsLength = 0;

        // Dynamic model selectors toggler based on chosen LLM provider
        function toggleProviderModels() {
            const provider = document.getElementById("provider").value;
            const ollamaOpts = document.querySelectorAll(".opt-ollama");
            const openaiOpts = document.querySelectorAll(".opt-openai");
            
            if (provider === "ollama") {
                ollamaOpts.forEach(o => o.style.display = "block");
                openaiOpts.forEach(o => o.style.display = "none");
                document.getElementById("model_name").value = "{{DEFAULT_OLLAMA_MODEL}}";
            } else {
                ollamaOpts.forEach(o => o.style.display = "none");
                openaiOpts.forEach(o => o.style.display = "block");
                document.getElementById("model_name").value = "{{DEFAULT_OPENAI_MODEL}}";
            }
        }

        // Timer controller
        function startTimer() {
            clearInterval(timerInterval);
            secondsElapsed = 0;
            document.getElementById("pipeline-timer").innerText = "00:00";
            timerInterval = setInterval(() => {
                secondsElapsed++;
                const mins = String(Math.floor(secondsElapsed / 60)).padStart(2, '0');
                const secs = String(secondsElapsed % 60).padStart(2, '0');
                document.getElementById("pipeline-timer").innerText = `${mins}:${secs}`;
            }, 1000);
        }

        function stopTimer() {
            clearInterval(timerInterval);
        }

        // Stepper Stage Detector & Progress bar percentage mapper
        function updateStepperAndProgress(logs) {
            let stage = 0; 
            
            for (let line of logs) {
                if (line.includes("Stage 1: Tagging Assets...")) {
                    stage = 1;
                } else if (line.includes("Stage 2: Generating Content & Video...")) {
                    stage = 2;
                } else if (line.includes("Matching assets with content...")) {
                    stage = 3;
                } else if (line.includes("Rendering HTML files...")) {
                    stage = 4;
                } else if (line.includes("Creating subtitles (SRT)...")) {
                    stage = 5;
                } else if (line.includes("Rendering video...")) {
                    stage = 6;
                } else if (line.includes("PIPELINE EXECUTION COMPLETED")) {
                    stage = 7;
                }
            }

            // Set stepper active/completed UI states
            for (let i = 1; i <= 6; i++) {
                const stepEl = document.getElementById(`step-${i}`);
                if (!stepEl) continue;
                
                stepEl.className = "step";
                if (stage === 7) {
                    stepEl.classList.add("completed");
                } else if (i < stage) {
                    stepEl.classList.add("completed");
                } else if (i === stage) {
                    stepEl.classList.add("active");
                } else {
                    stepEl.classList.add("pending");
                }
            }

            // Map progress bar percentage
            const progressBar = document.getElementById("progress-bar");
            if (stage === 7) {
                progressBar.style.width = "100%";
            } else if (stage > 0) {
                progressBar.style.width = `${Math.round(((stage - 1) / 6) * 90)}%`;
            } else {
                progressBar.style.width = "0%";
            }
        }

        // Render console output lines in the styled retro terminal emulator
        function renderTerminalLogs(logs) {
            const consoleOutput = document.getElementById("console-output");
            // Remove previous cursor
            const cursor = consoleOutput.querySelector(".cursor");
            if (cursor) cursor.remove();

            // Only append new lines since last length for performance
            if (logs.length > currentLogsLength) {
                for (let i = currentLogsLength; i < logs.length; i++) {
                    const rawLine = logs[i];
                    const div = document.createElement("div");
                    div.className = "log-line";
                    
                    // Simple regex/substring highlighting
                    if (rawLine.startsWith("$")) {
                        div.classList.add("cmd");
                    } else if (rawLine.includes(">>> Stage") || rawLine.includes("Starting Autopilot Pipeline")) {
                        div.classList.add("stage");
                    } else if (rawLine.includes("DONE") || rawLine.includes("successfully") || rawLine.includes("COMPLETED")) {
                        div.classList.add("success");
                    } else if (rawLine.includes("Error") || rawLine.includes("failed") || rawLine.includes("Failed")) {
                        div.classList.add("error");
                    } else if (rawLine.includes("Warning") || rawLine.includes("SKIPPED")) {
                        div.classList.add("warning");
                    } else if (rawLine.includes("images:") || rawLine.includes("content:") || rawLine.includes("csv:")) {
                        div.classList.add("done");
                    }
                    
                    div.innerText = rawLine.replace(/\\n$/, "");
                    consoleOutput.appendChild(div);
                }
                currentLogsLength = logs.length;
                
                // Re-append cursor and auto-scroll to bottom
                const newCursor = document.createElement("span");
                newCursor.className = "cursor";
                consoleOutput.appendChild(newCursor);
                consoleOutput.scrollTop = consoleOutput.scrollHeight;
            }
        }

        // Main status polling loop
        async function pollStatus() {
            try {
                const response = await fetch("/api/status");
                if (!response.ok) return;
                
                const data = await response.json();
                
                // Update terminal logs
                renderTerminalLogs(data.logs);
                
                // Update stepper active states
                updateStepperAndProgress(data.logs);

                if (data.running) {
                    setSystemState("running", "工作流执行中...");
                } else {
                    stopTimer();
                    clearInterval(pollInterval);
                    isRunning = false;
                    
                    const btn = document.getElementById("trigger-btn");
                    btn.disabled = false;
                    btn.className = "btn-trigger";
                    btn.innerHTML = '<i class="fa-solid fa-play"></i> 启动全自动工作流';

                    if (data.exit_code === 0) {
                        setSystemState("completed", "执行成功！成果已生成");
                        // Reveal outputs slide-up card
                        showResults(data);
                    } else if (data.exit_code !== null) {
                        setSystemState("failed", `执行失败 (错误码: ${data.exit_code})`);
                    } else {
                        setSystemState("idle", "系统就绪，等待指令");
                    }
                }
            } catch (error) {
                console.error("Failed to poll status:", error);
            }
        }

        // Set status badge styling
        function setSystemState(state, text) {
            const badge = document.getElementById("sys-status-badge");
            const dot = document.getElementById("sys-status-dot");
            const statusTxt = document.getElementById("sys-status-text");
            
            dot.className = "status-dot";
            statusTxt.innerText = text;

            if (state === "running") {
                dot.classList.add("active");
            } else if (state === "completed") {
                dot.classList.add("success");
            } else if (state === "failed") {
                dot.classList.add("status-dot");
                dot.style.backgroundColor = "var(--accent-error)";
                dot.style.boxShadow = "0 0 10px var(--accent-error)";
            } else {
                dot.classList.add("status-dot");
            }
        }

        // Play or Stop pipeline trigger
        async function togglePipeline() {
            if (isRunning) {
                // Confirm stop
                if (!confirm("确定要强行终止当前正在执行的生产线吗？")) return;
                
                const btn = document.getElementById("trigger-btn");
                btn.disabled = true;
                btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> 正在终止...';
                
                try {
                    await fetch("/api/stop", { method: "POST" });
                } catch (e) {
                    console.error("Stop error:", e);
                }
                return;
            }

            // Gather inputs
            const params = {
                name: document.getElementById("name").value,
                brand: document.getElementById("brand").value,
                model: document.getElementById("model").value,
                series: document.getElementById("series").value,
                topic: document.getElementById("topic").value,
                angle: document.getElementById("angle").value,
                column: document.getElementById("column").value,
                model_name: document.getElementById("model_name").value,
                provider: document.getElementById("provider").value,
                scale_factor: parseInt(document.getElementById("scale_factor").value),
                vision: document.getElementById("vision").checked,
                move: document.getElementById("move").checked,
                skip_tagging: document.getElementById("skip_tagging").checked,
                skip_generation: document.getElementById("skip_generation").checked,
            };

            // Reset frontend state
            const consoleOutput = document.getElementById("console-output");
            consoleOutput.innerHTML = '<div class="log-line text-muted">工作流初始化中...</div><span class="cursor"></span>';
            currentLogsLength = 0;
            
            // Hide outputs card
            document.getElementById("results-section").style.display = "none";
            document.getElementById("output-video").src = "";
            document.getElementById("screenshots-grid").innerHTML = "";
            
            // Set Stepper pending
            for (let i = 1; i <= 6; i++) {
                const el = document.getElementById(`step-${i}`);
                if (el) el.className = "step pending";
            }
            document.getElementById("progress-bar").style.width = "0%";

            isRunning = true;
            startTimer();
            setSystemState("running", "初始化工作流...");
            
            const btn = document.getElementById("trigger-btn");
            btn.className = "btn-trigger btn-abort";
            btn.innerHTML = '<i class="fa-solid fa-stop"></i> 强行终止工作流';

            try {
                const response = await fetch("/api/start", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(params)
                });
                
                if (response.ok) {
                    // Start polling
                    pollInterval = setInterval(pollStatus, 500);
                } else {
                    alert("启动失败，生产线可能已经在后台运行中。");
                    isRunning = false;
                    btn.className = "btn-trigger";
                    btn.innerHTML = '<i class="fa-solid fa-play"></i> 启动全自动工作流';
                    stopTimer();
                    setSystemState("failed", "启动失败");
                }
            } catch (error) {
                console.error("Start error:", error);
                alert("请求失败，请确保本地后台 Python 服务正常运行中。");
                isRunning = false;
                btn.className = "btn-trigger";
                btn.innerHTML = '<i class="fa-solid fa-play"></i> 启动全自动工作流';
                stopTimer();
                setSystemState("failed", "启动失败");
            }
        }

        // Display results on successful finish
        function showResults(data) {
            const resultsSection = document.getElementById("results-section");
            resultsSection.style.display = "block";
            
            // 1. Setup Video Player with cache-busting timestamp
            const videoPlayer = document.getElementById("output-video");
            if (data.video_url) {
                videoPlayer.src = `${data.video_url}?t=${Date.now()}`;
                videoPlayer.load();
            } else {
                videoPlayer.src = "";
            }

            // 2. Render Playwright Screenshot Grid
            const screenshotsGrid = document.getElementById("screenshots-grid");
            screenshotsGrid.innerHTML = "";
            
            if (data.screenshots && data.screenshots.length > 0) {
                data.screenshots.forEach(fname => {
                    const thumb = document.createElement("div");
                    thumb.className = "screenshot-thumbnail";
                    
                    const imgUrl = `/outputs/images/${data.project_name}/${fname}?t=${Date.now()}`;
                    thumb.innerHTML = `
                        <img src="${imgUrl}" alt="${fname}" onerror="this.src='https://placehold.co/1080x1440/111420/a78bfa?text=PNG+Detail'">
                        <div class="screenshot-label">${fname}</div>
                    `;
                    thumb.onclick = () => openLightbox(imgUrl);
                    screenshotsGrid.appendChild(thumb);
                });
            } else {
                screenshotsGrid.innerHTML = '<div style="grid-column: 1/-1; padding: 30px; text-align: center; color: var(--text-muted);">暂未输出图片分片</div>';
            }

            // 3. Render Downloadable Reports list
            const reportsContainer = document.getElementById("reports-container");
            reportsContainer.innerHTML = "";
            
            const r = data.reports;
            if (r) {
                if (r.md) {
                    reportsContainer.appendChild(createReportBtn(r.md, "Tagger 报告", "md-file", "fa-file-markdown"));
                }
                if (r.csv) {
                    reportsContainer.appendChild(createReportBtn(r.csv, "打标 CSV", "csv-file", "fa-file-csv"));
                }
                if (r.json) {
                    reportsContainer.appendChild(createReportBtn(r.json, "打标 JSON", "json-file", "fa-file-code"));
                }
                if (r.canva_csv) {
                    reportsContainer.appendChild(createReportBtn(r.canva_csv, "Canva CSV", "canva-file", "fa-file-excel"));
                }
            }
            if (reportsContainer.children.length === 0) {
                reportsContainer.innerHTML = '<div style="grid-column: 1/-1; padding: 10px; text-align: center; color: var(--text-muted);">暂无生成报表</div>';
            }

            // Scroll down to the results showcase card smoothly
            setTimeout(() => {
                resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
            }, 300);
        }

        function createReportBtn(url, label, className, iconName) {
            const a = document.createElement("a");
            a.href = `${url}?t=${Date.now()}`;
            a.download = "";
            a.className = `report-download-btn ${className}`;
            a.innerHTML = `
                <i class="fa-solid ${iconName}"></i>
                <span>${label}</span>
            `;
            return a;
        }

        // Fullscreen Lightbox triggers
        function openLightbox(src) {
            const lightbox = document.getElementById("lightbox");
            const lightboxImg = document.getElementById("lightbox-img");
            lightboxImg.src = src;
            lightbox.classList.add("active");
        }

        function closeLightbox() {
            const lightbox = document.getElementById("lightbox");
            lightbox.classList.remove("active");
        }

        // Initial setup on load
        window.onload = () => {
            toggleProviderModels();
            
            // Check if pipeline is already running in background (in case of browser refresh)
            fetch("/api/status")
                .then(res => res.json())
                .then(data => {
                    if (data.running) {
                        isRunning = true;
                        currentLogsLength = 0;
                        
                        const btn = document.getElementById("trigger-btn");
                        btn.className = "btn-trigger btn-abort";
                        btn.innerHTML = '<i class="fa-solid fa-stop"></i> 强行终止工作流';
                        
                        setSystemState("running", "工作流背景执行中...");
                        startTimer();
                        pollInterval = setInterval(pollStatus, 500);
                    }
                })
                .catch(err => console.error("Initial check error:", err));
        };
    </script>
</body>
</html>
"""

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Auto Studio Autopilot Dashboard Web Server")
    parser.add_argument("--port", type=int, default=8080, help="Web server port (default: 8080)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind IP address (default: 127.0.0.1)")
    args = parser.parse_args()
    
    server_address = (args.host, args.port)
    httpd = ThreadingHTTPServer(server_address, DashboardHandler)
    
    print("=" * 60)
    print(f"AUTO STUDIO WEB DASHBOARD SERVER RUNNING")
    print(f"Local URL: http://{args.host}:{args.port}/")
    print("=" * 60)
    print("Press Ctrl+C to stop the dashboard server.")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard server...")
        manager.stop()
        httpd.server_close()
        print("Server stopped. Goodbye!")

if __name__ == "__main__":
    main()
