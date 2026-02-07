#!/usr/bin/env python3
"""
ChibiBooru First-Run Setup Wizard

Interactive CLI wizard for configuring ChibiBooru on first installation.
Handles secret generation, directory creation, and optional model downloads.
"""

import getpass
import os
import sys
import secrets
import urllib.request
from pathlib import Path
from typing import Optional, Tuple, List

# Project root
PROJECT_ROOT = Path(__file__).parent


def print_banner():
    """Print welcome banner."""
    print()
    print("=" * 60)
    print("  🎨 ChibiBooru Setup Wizard")
    print("=" * 60)
    print()
    print("  Welcome! This wizard will help you configure ChibiBooru.")
    print("  Press Enter to accept defaults shown in [brackets].")
    print()


def print_section(title: str):
    """Print section header."""
    print()
    print(f"─── {title} " + "─" * (55 - len(title)))
    print()


def generate_secret() -> str:
    """Generate a secure random secret."""
    return secrets.token_urlsafe(32)


def prompt(message: str, default: Optional[str] = None, password: bool = False) -> str:
    """Prompt user for input with optional default."""
    if default:
        display = "*" * 8 if password and default else default
        prompt_text = f"  {message} [{display}]: "
    else:
        prompt_text = f"  {message}: "
    
    try:
        value = input(prompt_text).strip()
        return value if value else (default or "")
    except (EOFError, KeyboardInterrupt):
        print("\n  Cancelled.")
        sys.exit(1)


def prompt_yes_no(message: str, default: bool = True) -> bool:
    """Prompt for yes/no answer."""
    default_str = "Y/n" if default else "y/N"
    try:
        value = input(f"  {message} [{default_str}]: ").strip().lower()
        if not value:
            return default
        return value in ('y', 'yes')
    except (EOFError, KeyboardInterrupt):
        print("\n  Cancelled.")
        sys.exit(1)


def prompt_password(message: str) -> str:
    """Prompt for input without echoing (for passwords)."""
    try:
        return getpass.getpass(f"  {message}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  Cancelled.")
        sys.exit(1)


def read_env_file() -> dict:
    """Read existing .env file."""
    env_path = PROJECT_ROOT / ".env"
    env_vars = {}
    
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
    
    return env_vars


def write_env_file(env_vars: dict):
    """Write .env file preserving comments and order."""
    env_path = PROJECT_ROOT / ".env"
    lines = []
    written_keys = set()
    
    # Preserve existing file structure if it exists
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith('#') and '=' in stripped:
                    key = stripped.split('=', 1)[0].strip()
                    if key in env_vars:
                        lines.append(f"{key}={env_vars[key]}\n")
                        written_keys.add(key)
                    else:
                        lines.append(line)
                else:
                    lines.append(line)
    
    # Add any new keys
    for key, value in env_vars.items():
        if key not in written_keys:
            lines.append(f"{key}={value}\n")
    
    # Write file
    with open(env_path, 'w') as f:
        f.writelines(lines)


def is_default_secret(value: str, key: str) -> bool:
    """Check if a secret is still the default value."""
    defaults = {
        'SECRET_KEY': 'dev-secret-key-change-for-production',
        'SYSTEM_API_SECRET': 'change-this-secret',
        'APP_PASSWORD': 'default-password',
    }
    return value == defaults.get(key, '')


def setup_secrets() -> dict:
    """Configure security secrets."""
    print_section("🔐 Security Configuration")
    
    env_vars = read_env_file()
    changes = {}
    
    # SECRET_KEY (Flask sessions)
    current = env_vars.get('SECRET_KEY', '')
    if not current or is_default_secret(current, 'SECRET_KEY'):
        generated = generate_secret()
        changes['SECRET_KEY'] = generated
        print(f"  ✓ Generated SECRET_KEY: {generated}")
    else:
        print("  ✓ SECRET_KEY already configured")
    
    # SYSTEM_API_SECRET (API authentication)
    current = env_vars.get('SYSTEM_API_SECRET', '')
    if not current or is_default_secret(current, 'SYSTEM_API_SECRET'):
        generated = generate_secret()
        changes['SYSTEM_API_SECRET'] = generated
        print(f"  ✓ Generated SYSTEM_API_SECRET: {generated}")
    else:
        print("  ✓ SYSTEM_API_SECRET already configured")
    
    # APP_PASSWORD (web UI login)
    current = env_vars.get('APP_PASSWORD', '')
    if not current or is_default_secret(current, 'APP_PASSWORD'):
        print("\n  APP_PASSWORD is used for web UI login.")
        value = prompt_password("Enter APP_PASSWORD (web UI login)")
        if value:
            changes['APP_PASSWORD'] = value
            print("  ✓ Set APP_PASSWORD")
        else:
            print("  ⚠ No password set - using default (change this!)")
    else:
        print("  ✓ APP_PASSWORD already configured")
    
    return changes


def setup_optional_api_keys() -> dict:
    """Ask for optional API keys (e.g. SauceNao)."""
    print_section("🔑 Optional API Keys")
    
    env_vars = read_env_file()
    changes = {}
    
    saucenao_key = env_vars.get("SAUCENAO_API_KEY", "").strip()
    if saucenao_key:
        print("  ✓ SAUCENAO_API_KEY already configured")
    else:
        print("  SauceNao API key enables reverse image search (find source of an image).")
        print("  Get a key at: https://saucenao.com/user.php")
        print()
        if prompt_yes_no("Do you have a SauceNao API key to add now?", default=False):
            value = prompt("Paste your SAUCENAO_API_KEY")
            if value:
                changes["SAUCENAO_API_KEY"] = value.strip()
                print("  ✓ SAUCENAO_API_KEY will be saved to .env")
        else:
            print("  You can add SAUCENAO_API_KEY to your .env file later for reverse image search.")
    
    return changes


def setup_directories():
    """Create required directories."""
    print_section("📁 Directory Setup")
    
    directories = [
        ("./static/images", "Image storage"),
        ("./static/thumbnails", "Thumbnail cache"),
        ("./static/upscaled", "Upscaled images"),
        ("./ingest", "File ingest folder"),
        ("./models/Tagger", "Tagger model"),
        ("./models/Similarity", "Similarity model (legacy)"),
        ("./models/SigLIP", "SigLIP similarity model"),
        ("./models/Upscaler", "Upscaler models"),
        ("./data", "Database"),
    ]
    
    for path, description in directories:
        full_path = PROJECT_ROOT / path
        if not full_path.exists():
            full_path.mkdir(parents=True, exist_ok=True)
            print(f"  ✓ Created {path} ({description})")
        else:
            print(f"  ✓ {path} exists")


def download_file(
    url: str,
    destination: Path,
    description: str,
    label: Optional[str] = None,
) -> bool:
    """Download a file with progress reporting. Optional label for parallel downloads."""
    prefix = f"  [{label}] " if label else "  "
    print(f"\n{prefix}Downloading {description}...")
    print(f"{prefix}  From: {url}")
    
    try:
        def progress_hook(block_num, block_size, total_size):
            if total_size > 0:
                downloaded = block_num * block_size
                percent = min(100, downloaded * 100 / total_size)
                mb_downloaded = downloaded / (1024 * 1024)
                mb_total = total_size / (1024 * 1024)
                print(f"\r{prefix}Progress: {percent:.1f}% ({mb_downloaded:.1f} MB / {mb_total:.1f} MB)", end="")
        
        urllib.request.urlretrieve(url, destination, progress_hook)
        print()
        print(f"{prefix}✓ Downloaded {description}")
        return True
    
    except Exception as e:
        print(f"\n{prefix}✗ Failed to download: {e}")
        return False


def _download_task(args: Tuple[str, Path, str, Optional[str]]) -> bool:
    """Run a single download (for use with ThreadPoolExecutor)."""
    url, destination, description, label = args
    return download_file(url, destination, description, label=label)


def setup_models():
    """Offer to download AI models. Asks all questions first, then runs downloads in parallel."""
    print_section("🤖 AI Model Downloads (Optional)")
    
    print("  ChibiBooru can use AI models for tagging, similarity, and upscaling.")
    print("  These are optional but recommended for full functionality.")
    print()
    
    # Collect choices first (no downloads yet)
    tasks: List[Tuple[str, Path, str, Optional[str]]] = []  # (url, destination, description, label)
    
    # Tagger
    tagger_path = PROJECT_ROOT / "models" / "Tagger" / "model.onnx"
    tagger_dir = tagger_path.parent
    if not tagger_path.exists():
        print("  📌 Tagger Model (Camie Tagger v2) - ~800 MB")
        print("     Used for automatic AI tagging of images")
        download_tagger = prompt_yes_no("Download tagger model?", default=True)
        if download_tagger:
            tasks.append((
                "https://huggingface.co/Camais03/camie-tagger-v2/resolve/main/camie-tagger-v2.onnx",
                tagger_path,
                "tagger model",
                "Tagger",
            ))
            tasks.append((
                "https://huggingface.co/Camais03/camie-tagger-v2/resolve/main/camie-tagger-v2-metadata.json",
                tagger_dir / "metadata.json",
                "tagger metadata",
                "Tagger",
            ))
    else:
        print("  ✓ Tagger model already installed")
    
    print()
    
    # Similarity (SigLIP 2)
    siglip_path = PROJECT_ROOT / "models" / "SigLIP" / "model.onnx"
    siglip_dir = siglip_path.parent
    siglip_dir.mkdir(parents=True, exist_ok=True)
    
    if not siglip_path.exists():
        print("  📌 Similarity Model (SigLIP 2) - ~4.5 GB download, ~1.8 GB ONNX")
        print("     Used for finding visually similar images (state-of-the-art)")
        print("     Requires: transformers, torch (will be installed if missing)")
        download_siglip = prompt_yes_no("Download and export SigLIP model?", default=True)
        if download_siglip:
            print()
            print("  Exporting SigLIP 2 model (this may take a few minutes)...")
            try:
                # Import and run the export script
                import subprocess
                result = subprocess.run(
                    [sys.executable, str(PROJECT_ROOT / "scripts" / "export_siglip.py")],
                    cwd=str(PROJECT_ROOT),
                    capture_output=False,
                )
                if result.returncode == 0:
                    print("  ✓ SigLIP model exported successfully")
                else:
                    print("  ⚠ SigLIP export failed - you can run 'python scripts/export_siglip.py' later")
            except Exception as e:
                print(f"  ⚠ SigLIP export failed: {e}")
                print("    You can run 'python scripts/export_siglip.py' later")
    else:
        print("  ✓ Similarity model (SigLIP) already installed")
    
    print()
    
    # Upscaler
    upscaler_dir = PROJECT_ROOT / "models" / "Upscaler"
    upscaler_general = upscaler_dir / "RealESRGAN_x4plus.pth"
    upscaler_anime = upscaler_dir / "RealESRGAN_x4plus_anime.pth"
    if not upscaler_general.exists() or not upscaler_anime.exists():
        print("  📌 Upscaler Models (RealESRGAN) - ~17-67 MB each")
        print("     Used for AI-powered image upscaling")
        download_upscaler = prompt_yes_no("Download upscaler models?", default=False)
        if download_upscaler:
            if not upscaler_general.exists():
                tasks.append((
                    "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
                    upscaler_general,
                    "RealESRGAN_x4plus (general)",
                    "Upscaler",
                ))
            if not upscaler_anime.exists():
                tasks.append((
                    "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth",
                    upscaler_anime,
                    "RealESRGAN_x4plus_anime",
                    "Upscaler",
                ))
    else:
        print("  ✓ Upscaler models already installed")
    
    # Run all chosen downloads one at a time (clean progress output)
    if tasks:
        print()
        print("  Downloading selected models...")
        for task in tasks:
            _download_task(task)
        print()
        print("  ✓ All downloads finished")


def is_first_run() -> bool:
    """Check if this is a fresh installation needing setup."""
    env_vars = read_env_file()
    
    # Check for default secrets
    checks = [
        ('SECRET_KEY', 'dev-secret-key-change-for-production'),
        ('SYSTEM_API_SECRET', 'change-this-secret'),
        ('APP_PASSWORD', 'default-password'),
    ]
    
    for key, default in checks:
        value = env_vars.get(key, default)
        if value == default:
            return True
    
    # Check if .env doesn't exist
    if not (PROJECT_ROOT / ".env").exists():
        return True
    
    return False


def print_summary(env_changes: dict):
    """Print setup completion summary."""
    print_section("✅ Setup Complete")
    
    if env_changes:
        print("  Configuration saved to .env")
        for key in env_changes:
            print(f"    • {key} configured")
    
    print()
    print("  Next steps:")
    print("    1. Review .env file if needed")
    print("    2. Start ChibiBooru: ./start_booru.sh")
    print("    3. Open http://localhost:5000 in your browser")
    print()
    print("=" * 60)
    print()


def main():
    """Main entry point."""
    # Check for non-interactive mode
    if os.environ.get('NON_INTERACTIVE') == '1':
        print("Non-interactive mode - skipping setup wizard")
        return 0
    
    # Check if setup is needed
    if not is_first_run() and '--force' not in sys.argv:
        print("ChibiBooru is already configured. Use --force to re-run setup.")
        return 0
    
    print_banner()
    
    # Security configuration
    env_changes = setup_secrets()
    
    # Optional API keys (e.g. SauceNao)
    optional_changes = setup_optional_api_keys()
    env_changes.update(optional_changes)
    
    # Apply env changes
    if env_changes:
        current_env = read_env_file()
        current_env.update(env_changes)
        write_env_file(current_env)
    
    # Directory setup
    setup_directories()
    
    # Model downloads
    setup_models()
    
    # Summary
    print_summary(env_changes)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
