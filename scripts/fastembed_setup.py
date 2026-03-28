#!/usr/bin/env python3
"""
FastEmbed Engram Setup
Complete setup for FastEmbed + Qdrant memory system
"""

import os
import sys
import subprocess
import json
import time
import requests
from pathlib import Path
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class FastEmbedSetup:
    def __init__(self, skill_dir: str = None):
        self.skill_dir = Path(skill_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.venv_path = self.skill_dir / ".venv"
        self.requirements_file = self.skill_dir / "requirements.txt"
        
    def check_python_version(self):
        """Check Python version compatibility"""
        version = sys.version_info
        logger.info(f"Python {version.major}.{version.minor}.{version.micro} - {'OK' if version >= (3, 8) else 'FAIL'}")
        if version < (3, 8):
            raise RuntimeError("Python 3.8+ required")
    
    def setup_virtual_environment(self):
        """Create and setup virtual environment"""
        logger.info("Setting up virtual environment...")
        
        if not self.venv_path.exists():
            subprocess.run([sys.executable, "-m", "venv", str(self.venv_path)], check=True)
            logger.info("Virtual environment created")
        
        # Install requirements
        pip_path = self.venv_path / "bin" / "pip"
        if not pip_path.exists():
            pip_path = self.venv_path / "Scripts" / "pip.exe"  # Windows
        
        logger.info("Installing Python requirements...")
        subprocess.run([
            str(pip_path), "install", "-r", str(self.requirements_file)
        ], check=True)
        logger.info("Requirements installed successfully")
    
    def check_qdrant_connection(self):
        """Check if Qdrant is running and accessible"""
        logger.info("Checking Qdrant connection...")
        try:
            response = requests.get("http://localhost:6333/collections", timeout=5)
            response.raise_for_status()
            logger.info("✓ Qdrant is running and accessible")
            return True
        except Exception as e:
            logger.warning(f"✗ Qdrant not accessible: {e}")
            return False
    
    def start_qdrant_docker(self):
        """Start Qdrant using Docker"""
        logger.info("Starting Qdrant with Docker...")
        try:
            # Check if container exists
            result = subprocess.run([
                "docker", "ps", "-a", "--filter", "name=engram-qdrant", "--format", "{{.Names}}"
            ], capture_output=True, text=True)
            
            if "engram-qdrant" in result.stdout:
                # Start existing container
                subprocess.run(["docker", "start", "engram-qdrant"], check=True)
                logger.info("Started existing Qdrant container")
            else:
                # Create new container
                subprocess.run([
                    "docker", "run", "-d",
                    "--name", "engram-qdrant", 
                    "-p", "6333:6333", "-p", "6334:6334",
                    "qdrant/qdrant:latest"
                ], check=True)
                logger.info("Created and started new Qdrant container")
            
            # Wait for Qdrant to be ready
            for i in range(30):
                if self.check_qdrant_connection():
                    return True
                time.sleep(1)
            
            raise RuntimeError("Qdrant failed to start properly")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to start Qdrant: {e}")
            raise
    
    def test_fastembed_service(self):
        """Test FastEmbed service"""
        logger.info("Testing FastEmbed service...")
        
        python_path = self.venv_path / "bin" / "python3"
        if not python_path.exists():
            python_path = self.venv_path / "Scripts" / "python.exe"  # Windows
        
        fastembed_script = self.skill_dir / "scripts" / "fastembed_service.py"
        
        # Start FastEmbed service in background
        import threading
        def run_service():
            subprocess.run([str(python_path), str(fastembed_script)])
        
        service_thread = threading.Thread(target=run_service, daemon=True)
        service_thread.start()
        
        # Wait for service to start
        time.sleep(5)
        
        # Test service
        try:
            response = requests.post(
                "http://localhost:8000/embeddings",
                json={"texts": ["test embedding"]},
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            
            if "embeddings" in result and len(result["embeddings"]) > 0:
                logger.info("✓ FastEmbed service working correctly")
                return True
            else:
                logger.error("✗ FastEmbed service returned invalid response")
                return False
                
        except Exception as e:
            logger.error(f"✗ FastEmbed service test failed: {e}")
            return False
    
    def test_memory_operations(self):
        """Test memory store and search operations"""
        logger.info("Testing memory operations...")
        
        python_path = self.venv_path / "bin" / "python3"
        if not python_path.exists():
            python_path = self.venv_path / "Scripts" / "python.exe"  # Windows
        
        memory_store_script = self.skill_dir / "scripts" / "memory_store.py"
        memory_search_script = self.skill_dir / "scripts" / "memory_search.py"
        
        try:
            # Test memory storage
            result = subprocess.run([
                str(python_path), str(memory_store_script),
                "Engram test memory", "test", "1.0"
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                logger.error(f"Memory store test failed: {result.stderr}")
                return False
            
            store_output = json.loads(result.stdout)
            if not store_output.get("success"):
                logger.error(f"Memory store failed: {store_output.get('error')}")
                return False
            
            memory_id = store_output["memory_id"]
            logger.info(f"✓ Memory stored successfully: {memory_id}")
            
            # Test memory search
            result = subprocess.run([
                str(python_path), str(memory_search_script),
                "Engram test", "5", "0.0"
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                logger.error(f"Memory search test failed: {result.stderr}")
                return False
            
            search_output = json.loads(result.stdout)
            if search_output.get("count", 0) == 0:
                logger.error("Memory search returned no results")
                return False
            
            logger.info(f"✓ Memory search working: {search_output['count']} results")
            return True
            
        except Exception as e:
            logger.error(f"Memory operations test failed: {e}")
            return False
    
    def create_startup_scripts(self):
        """Create convenience startup scripts"""
        logger.info("Creating startup scripts...")
        
        # Create FastEmbed service script
        service_script = self.skill_dir / "start_fastembed.sh"
        python_path = self.venv_path / "bin" / "python3"
        fastembed_script = self.skill_dir / "scripts" / "fastembed_service.py"
        
        script_content = f"""#!/bin/bash
# Start FastEmbed service for Engram
cd "{self.skill_dir}"
echo "Starting FastEmbed service..."
{python_path} {fastembed_script}
"""
        
        with open(service_script, 'w') as f:
            f.write(script_content)
        
        os.chmod(service_script, 0o755)
        logger.info(f"Created startup script: {service_script}")
    
    def run_setup(self, force_reinstall: bool = False):
        """Run complete setup process"""
        logger.info("=== Engram FastEmbed Setup ===")
        
        try:
            # Step 1: Check Python
            self.check_python_version()
            
            # Step 2: Setup virtual environment
            if force_reinstall and self.venv_path.exists():
                import shutil
                shutil.rmtree(self.venv_path)
                logger.info("Removed existing virtual environment")
            
            self.setup_virtual_environment()
            
            # Step 3: Setup Qdrant
            if not self.check_qdrant_connection():
                self.start_qdrant_docker()
            
            # Step 4: Test FastEmbed service
            if not self.test_fastembed_service():
                raise RuntimeError("FastEmbed service test failed")
            
            # Step 5: Test memory operations
            if not self.test_memory_operations():
                raise RuntimeError("Memory operations test failed")
            
            # Step 6: Create startup scripts
            self.create_startup_scripts()
            
            logger.info("🎉 Engram setup completed successfully!")
            logger.info("")
            logger.info("Next steps:")
            logger.info(f"1. Start FastEmbed service: {self.skill_dir}/start_fastembed.sh")
            logger.info("2. Use memory_store.py and memory_search.py for memory operations")
            logger.info("3. Engram is ready for OpenClaw integration!")
            
        except Exception as e:
            logger.error(f"Setup failed: {e}")
            raise

def main():
    """Main setup function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Engram FastEmbed Setup')
    parser.add_argument('--force', action='store_true', help='Force reinstall')
    parser.add_argument('--skill-dir', help='Skill directory path')
    
    args = parser.parse_args()
    
    setup = FastEmbedSetup(skill_dir=args.skill_dir)
    setup.run_setup(force_reinstall=args.force)

if __name__ == "__main__":
    main()