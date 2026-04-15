#!/usr/bin/env python3
"""
AI Smart PDF Editor - Launcher Script
Starts both frontend and backend servers
"""

import subprocess
import sys
import os
import time
from pathlib import Path
from dotenv import load_dotenv


def load_env():
    """Load environment variables from .env file"""
    if Path(".env").exists():
        load_dotenv()
        return True
    else:
        print("⚠️  Warning: .env file not found!")
        print("📋 Creating from .env.example...")
        if Path(".env.example").exists():
            with open(".env.example", "r") as src:
                with open(".env", "w") as dst:
                    dst.write(src.read())
            print("✅ .env file created. Please update with your API keys.")
            return False
        return False


def check_requirements():
    """Check if required dependencies are installed"""
    required_packages = [
        "fastapi", "uvicorn", "streamlit", "pydantic",
        "dotenv", "fitz", "pytesseract", "groq"
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package.replace("-", "_"))
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"⚠️  Missing packages: {', '.join(missing_packages)}")
        print("Run: pip install -r requirements.txt")
        return False
    return True


def run_command(command, cwd=None, name="Process"):
    """Run a command in a subprocess."""
    try:
        print(f"🔄 Running: {command}")
        process = subprocess.Popen(
            command,
            shell=True,
            cwd=cwd or os.getcwd()
        )
        return process
    except Exception as e:
        print(f"❌ Error running '{name}': {e}")
        return None


def get_pid_on_port(port):
    """Find process ID using a specific port on Windows"""
    try:
        if sys.platform == "win32":
            output = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True, text=True)
            for line in output.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    return int(line.strip().split()[-1])
    except:
        pass
    return None

def kill_process(pid):
    """Kill process by PID"""
    try:
        if sys.platform == "win32":
            subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.kill(pid, 9)
    except Exception:
        pass

def check_ports():
    """Check if required ports are available and kill zombie processes"""
    import socket
    ports = {
        8000: "Backend API",
        8501: "Frontend (Streamlit)"
    }
    
    print("\n🔌 Clearing and binding ports...")
    time.sleep(1)
    
    for port, service in ports.items():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) == 0:
                print(f"⚠️  Port {port} is busy. Attempting to kill ghost process...")
                pid = get_pid_on_port(port)
                if pid:
                    kill_process(pid)
                    time.sleep(2)  # Give OS time to clear port
                
                # Check again
                if s.connect_ex(('127.0.0.1', port)) == 0:
                    print(f"❌ Failed to free port {port}.")
                    return False
    return True


def wait_for_server(url, timeout=10):
    """Wait for server to start"""
    import requests
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(url, timeout=1)
            if response.status_code == 200 or response.status_code == 404:
                return True
        except:
            time.sleep(0.5)
    return False


def main():
    print("=" * 60)
    print("🚀 AI Smart PDF Editor - Startup")
    print("=" * 60)
    
    # Load environment
    print("\n📋 Loading environment variables...")
    if not load_env():
        print("\n⚠️  Please update your .env file with API keys before running!")
    
    # Check requirements
    print("\n✅ Checking dependencies...")
    if not check_requirements():
        print("\n❌ Missing required packages. Install them first:")
        print("   pip install -r requirements.txt")
        return
    
    # Check ports
    print("\n🔌 Checking port availability...")
    if not check_ports():
        return
    
    # Create required directories
    print("\n📁 Creating required directories...")
    for directory in ["uploads", "outputs", "temp"]:
        Path(directory).mkdir(exist_ok=True)
        print(f"   ✓ {directory}/")
    
    # Get backend port from environment
    backend_port = os.getenv("BACKEND_PORT", "8000")
    backend_host = os.getenv("BACKEND_HOST", "127.0.0.1")
    frontend_port = os.getenv("FRONTEND_PORT", "8501")
    
    print(f"\n📡 Backend will run on: http://{backend_host}:{backend_port}")
    print(f"🖥️  Frontend will run on: http://127.0.0.1:{frontend_port}")
    
    # Start backend server
    print("\n" + "=" * 60)
    print("Starting Backend Server...")
    print("=" * 60)
    backend_command = f"uvicorn backend.main:app --workers 4 --host {backend_host} --port {backend_port}"
    backend_process = run_command(backend_command, name="Backend")
    
    if not backend_process:
        print("❌ Failed to start backend server")
        return
    
    print("⏳ Waiting for backend to start...")
    time.sleep(3)
    
    # Start frontend
    print("\n" + "=" * 60)
    print("Starting Frontend Server...")
    print("=" * 60)
    frontend_command = f"streamlit run frontend/app.py --server.port {frontend_port} --logger.level=info"
    frontend_process = run_command(frontend_command, name="Frontend")
    
    if not frontend_process:
        print("❌ Failed to start frontend")
        backend_process.terminate()
        return
    
    print("⏳ Waiting for frontend to start...")
    time.sleep(2)
    
    # Display startup info
    print("\n" + "=" * 60)
    print("✅ ALL SERVERS STARTED SUCCESSFULLY!")
    print("=" * 60)
    print(f"\n📱 Frontend URL: http://127.0.0.1:{frontend_port}")
    print(f"🔧 Backend API: http://{backend_host}:{backend_port}")
    print(f"📚 API Docs: http://{backend_host}:{backend_port}/docs")
    print(f"🔍 API Redoc: http://{backend_host}:{backend_port}/redoc")
    print("\n💡 Tips:")
    print("   • Open the frontend URL in your browser")
    print("   • Check API documentation at /docs endpoint")
    print("   • Logs appear below")
    print("\n⏹️  Press Ctrl+C to stop all servers\n")
    print("=" * 60)
    
    try:
        # Keep processes running
        while True:
            if backend_process.poll() is not None:
                print("\n⚠️  Backend process stopped!")
                break
            if frontend_process.poll() is not None:
                print("\n⚠️  Frontend process stopped!")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down...")
        print("⏳ Stopping backend server...")
        backend_process.terminate()
        print("⏳ Stopping frontend server...")
        frontend_process.terminate()
        
        time.sleep(1)
        print("✅ All servers stopped")
        print("👋 Goodbye!")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
