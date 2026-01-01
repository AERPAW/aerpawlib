#!/usr/bin/env bash
# Bash script to clone, install prerequisites, and build ArduPilot for SITL.
# Creates a dedicated Python venv for ArduPilot to avoid polluting the system.
# Usage: ./install_ardupilot.sh [--dir /path/to/ardupilot] [--branch BRANCH]
#        [--vehicle copter|plane|rover|sub] [--no-deps] [--mavproxy] [--jobs N]
set -euo pipefail

# Get the directory where this script is located (aerpawlib folder)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Project root is one level up from aerpawlib
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"

# Defaults - install to /ardupilot in the project root
INSTALL_DIR="${PROJECT_ROOT}/ardupilot"
VENV_DIR="${PROJECT_ROOT}/.venv"
BRANCH="master"
VEHICLE="copter"
INSTALL_DEPS=true
INSTALL_MAVPROXY=false
JOBS=""
declare -a EXTRA_ARGS=()

show_usage() {
    cat <<EOF
Usage: $0 [options]

Installs ArduPilot SITL for use with aerpawlib.
Creates a dedicated Python virtual environment for ArduPilot dependencies.

Options:
  --dir DIR           Path to clone ArduPilot (default: ${INSTALL_DIR})
  --venv DIR          Path to create Python venv (default: ${VENV_DIR})
  --branch BRANCH     Git branch or tag to checkout (default: ${BRANCH})
  --vehicle NAME      Vehicle to build: copter, plane, rover, sub (default: ${VEHICLE})
  --no-deps           Skip running ArduPilot platform prereq installer
  --mavproxy          Install MAVProxy (useful for console/map)
  --jobs N            Parallel build jobs (defaults to CPU count)
  --help              Show this help

Examples:
  # Install with defaults (copter, in project /ardupilot folder)
  ./install_ardupilot.sh

  # Install rover instead
  ./install_ardupilot.sh --vehicle rover

  # Install to custom location
  ./install_ardupilot.sh --dir ~/my-ardupilot --venv ~/my-ardupilot-venv

  # Install with MAVProxy for console/map support
  ./install_ardupilot.sh --mavproxy
EOF
}

# parse args (simple)
while [ $# -gt 0 ]; do
    case "$1" in
        --dir) INSTALL_DIR="$2"; shift 2;;
        --venv) VENV_DIR="$2"; shift 2;;
        --branch) BRANCH="$2"; shift 2;;
        --vehicle) VEHICLE="$2"; shift 2;;
        --no-deps) INSTALL_DEPS=false; shift;;
        --mavproxy) INSTALL_MAVPROXY=true; shift;;
        --jobs) JOBS="$2"; shift 2;;
        --help) show_usage; exit 0;;
        *) EXTRA_ARGS+=("$1"); shift;;
    esac
done

log() { printf "[install-ardupilot] %s\n" "$*"; }

# detect platform
OS="$(uname -s)"
case "$OS" in
    Darwin) PLATFORM="macos";;
    Linux) PLATFORM="linux";;
    *) PLATFORM="unknown";;
esac

# determine CPU count if not provided
if [ -z "${JOBS}" ]; then
    if [ "$PLATFORM" = "macos" ]; then
        JOBS="$(sysctl -n hw.ncpu || echo 4)"
    else
        JOBS="$(nproc 2>/dev/null || echo 4)"
    fi
fi

log "========================================"
log "ArduPilot SITL Installer for aerpawlib"
log "========================================"
log "Platform detected: ${PLATFORM}"
log "Install dir: ${INSTALL_DIR}"
log "Venv dir: ${VENV_DIR}"
log "Branch: ${BRANCH}"
log "Vehicle: ${VEHICLE}"
log "Install deps: ${INSTALL_DEPS}"
log "Install MAVProxy: ${INSTALL_MAVPROXY}"
log "Build jobs: ${JOBS}"
log ""

# ============================================================================
# Create Python virtual environment for ArduPilot
# ============================================================================
log "Setting up Python virtual environment..."

if [ -d "${VENV_DIR}" ]; then
    log "Venv already exists at ${VENV_DIR}"
else
    log "Creating venv at ${VENV_DIR}..."
    python3 -m venv "${VENV_DIR}"
fi

# Activate the venv
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

log "Upgrading pip in venv..."
pip install --upgrade pip wheel setuptools

# ============================================================================
# Clone or update ArduPilot repository
# ============================================================================
if [ -d "${INSTALL_DIR}/.git" ]; then
    log "ArduPilot repository exists. Fetching updates..."
    git -C "${INSTALL_DIR}" fetch --all --tags --prune
else
    log "Cloning ArduPilot into ${INSTALL_DIR}..."
    git clone --depth 1 --branch "${BRANCH}" https://github.com/ArduPilot/ardupilot.git "${INSTALL_DIR}"
fi

cd "${INSTALL_DIR}"

log "Checking out branch ${BRANCH}..."
git checkout "${BRANCH}" 2>/dev/null || git checkout -b "${BRANCH}" origin/"${BRANCH}" 2>/dev/null || true
git pull --ff-only 2>/dev/null || true

log "Initializing submodules (this may take a while)..."
git submodule update --init --recursive

# ============================================================================
# Install system dependencies (optional)
# ============================================================================
if [ "${INSTALL_DEPS}" = true ]; then
    log ""
    log "Installing system prerequisites..."
    if [ "${PLATFORM}" = "macos" ]; then
        if [ -f "Tools/environment_install/install-prereqs-mac.sh" ]; then
            log "Running macOS prereq installer (may prompt for password)..."
            # Run prereq installer but don't fail if it has issues
            Tools/environment_install/install-prereqs-mac.sh -y || {
                log "WARNING: System prereq installer had issues. Continuing with venv setup..."
            }
        else
            log "macOS prereq installer not found. You may need to install some system deps:"
            log "  brew install gcc-arm-none-eabi"
        fi
    elif [ "${PLATFORM}" = "linux" ]; then
        if [ -f "Tools/environment_install/install-prereqs-ubuntu.sh" ]; then
            log "Running Ubuntu prereq installer (will prompt for sudo)..."
            Tools/environment_install/install-prereqs-ubuntu.sh -y || {
                log "WARNING: System prereq installer had issues. Continuing with venv setup..."
            }
        else
            log "Ubuntu prereq installer not found. You may need to install some system deps."
        fi
    else
        log "Unknown platform. Skipping system prerequisite installation."
    fi
fi

# ============================================================================
# Install Python dependencies into the venv
# ============================================================================
log ""
log "Installing Python dependencies into venv..."

# Core ArduPilot build dependencies
pip3 install setuptools future lxml matplotlib pymavlink MAVProxy pexpect geocoder flake8 junitparser empy==3.3.4 dronecan


# Install from ArduPilot's requirements if available
if [ -f "Tools/autotest/requirements.txt" ]; then
    log "Installing from Tools/autotest/requirements.txt..."
    pip install -r Tools/autotest/requirements.txt || {
        log "WARNING: Some requirements failed to install. Continuing..."
    }
fi

if [ -f "Tools/environment_install/requirements.txt" ]; then
    log "Installing from Tools/environment_install/requirements.txt..."
    pip install -r Tools/environment_install/requirements.txt || {
        log "WARNING: Some requirements failed to install. Continuing..."
    }
fi

# Optional MAVProxy install
if [ "${INSTALL_MAVPROXY}" = true ]; then
    log ""
    log "Installing MAVProxy into venv..."
    pip install MAVProxy || {
        log "WARNING: MAVProxy installation failed."
    }
fi

# ============================================================================
# Build ArduPilot for SITL
# ============================================================================

# ensure waf is present
if [ ! -f "./waf" ]; then
    log "ERROR: waf build tool not found. Submodule initialization may have failed."
    exit 1
fi

# configure and build
log ""
log "Configuring for SITL..."
./waf configure --board sitl

log ""
log "Building ${VEHICLE} (this can take several minutes)..."
./waf "${VEHICLE}" -j "${JOBS}"

# Determine vehicle binary name for instructions
case "${VEHICLE}" in
    copter) ARDUPILOT_VNAME="ArduCopter";;
    plane) ARDUPILOT_VNAME="ArduPlane";;
    rover) ARDUPILOT_VNAME="Rover";;
    sub) ARDUPILOT_VNAME="ArduSub";;
    *) ARDUPILOT_VNAME="ArduCopter";;
esac

# ============================================================================
# Create activation helper script
# ============================================================================
ACTIVATE_SCRIPT="${PROJECT_ROOT}/activate-ardupilot.sh"
cat > "${ACTIVATE_SCRIPT}" <<EOFSCRIPT
#!/usr/bin/env bash
# Source this script to activate the ArduPilot venv
# Usage: source ./activate-ardupilot.sh

export ARDUPILOT_HOME="${INSTALL_DIR}"
source "${VENV_DIR}/bin/activate"

echo "ArduPilot environment activated."
echo "  ARDUPILOT_HOME=\${ARDUPILOT_HOME}"
echo "  Python: \$(which python)"
echo ""
echo "To run SITL manually:"
echo "  cd \${ARDUPILOT_HOME}"
echo "  Tools/autotest/sim_vehicle.py -v ${ARDUPILOT_VNAME} --console --map"
EOFSCRIPT
chmod +x "${ACTIVATE_SCRIPT}"

# ============================================================================
# Done!
# ============================================================================
log ""
log "========================================"
log "Installation complete!"
log "========================================"
log ""
log "ArduPilot installed to: ${INSTALL_DIR}"
log "Python venv created at: ${VENV_DIR}"
log ""
log "To run SITL manually (activates venv automatically):"
log ""
log "  source ${ACTIVATE_SCRIPT}"
log "  cd ${INSTALL_DIR}"
log "  Tools/autotest/sim_vehicle.py -v ${ARDUPILOT_VNAME} --console --map"
log ""
log "To use with aerpawlib (SITL auto-starts with correct venv):"
log ""
log "  python -m aerpawlib --api-version v2 --script your_script --vehicle drone --sitl"
log ""
log "QGroundControl connection:"
log "  Type: TCP"
log "  Host: localhost"
log "  Port: 5760"
log ""

# Deactivate venv
deactivate

exit 0
