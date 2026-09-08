#!/usr/bin/env bash
# Cross-platform Docker installer and service manager for MCP Service Demo.

set -Eeuo pipefail

VERSION="0.9.8"
APP_NAME="MCP Service Demo"
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$INSTALL_DIR/.env"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ACTION="install"
ACTION_SET="no"
BUILD="no"
OPEN_BROWSER="no"
REMOVE_DATA="no"
FORCE_YES="no"
WAIT_SECONDS=60
WEB_PORT=""
SPLUNK_PORT=""
TICKET_PORT=""
CATALOG_PORT=""
PROJECT_NAME=""
COMPOSE=()

print_msg() {
    local color="$1"
    local message="$2"
    printf '%b%s%b\n' "$color" "$message" "$NC"
}

show_help() {
    printf '%b%s v%s%b\n\n' "$GREEN" "$APP_NAME" "$VERSION" "$NC"
    printf '%bUSAGE:%b\n' "$BLUE" "$NC"
    printf '    ./install.sh [COMMAND] [OPTIONS]\n\n'
    printf '%bCOMMANDS:%b\n' "$BLUE" "$NC"
    printf '    (no command)          Prepare, build, and start the complete demo\n'
    printf '    --start               Start existing services (build if needed)\n'
    printf '    --stop                Stop services and preserve containers/settings\n'
    printf '    --restart             Restart services\n'
    printf '    --status              Show service and health status\n'
    printf '    --logs                Follow service logs\n'
    printf '    --uninstall           Remove containers and local image; preserve data\n'
    printf '    --help, -h            Show this help message\n\n'
    printf '%bOPTIONS:%b\n' "$BLUE" "$NC"
    printf '    --build               Rebuild images with --start or --restart\n'
    printf '    --open                Open the demo in the default browser after startup\n'
    printf '    --web-port PORT       Publish the web interface on PORT (default 8100)\n'
    printf '    --splunk-port PORT    Publish Splunk MCP on PORT (default 8101)\n'
    printf '    --ticket-port PORT    Publish Ticket MCP on PORT (default 8102)\n'
    printf '    --catalog-port PORT   Publish Catalog MCP on PORT (default 8103)\n'
    printf '    --project-name NAME   Set a persistent Compose project name\n'
    printf '    --wait-seconds N      Startup health timeout (default 60)\n'
    printf '    --remove-data         With --uninstall, also remove settings and tickets\n'
    printf '    --force-yes           Skip the --remove-data confirmation\n\n'
    printf '%bEXAMPLES:%b\n' "$BLUE" "$NC"
    printf '    ./install.sh\n'
    printf '    ./install.sh --open\n'
    printf '    ./install.sh --web-port 8200 --project-name customer-demo\n'
    printf '    ./install.sh --restart --build\n'
    printf '    ./install.sh --logs\n'
    printf '    ./install.sh --uninstall\n\n'
    printf '%bNOTES:%b\n' "$BLUE" "$NC"
    printf '    Docker Engine or Docker Desktop with Compose v2 is recommended.\n'
    printf '    Port and project-name options are saved in .env. Existing .env values\n'
    printf '    and browser-saved Splunk/LLM settings are otherwise preserved.\n'
}

set_action() {
    local requested="$1"
    if [[ "$ACTION_SET" == "yes" ]]; then
        print_msg "$RED" "Choose only one command."
        exit 2
    fi
    ACTION="$requested"
    ACTION_SET="yes"
}

require_value() {
    local option="$1"
    local value="${2:-}"
    if [[ -z "$value" || "$value" == --* ]]; then
        print_msg "$RED" "$option requires a value."
        exit 2
    fi
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --help|-h)
                set_action "help"
                shift
                ;;
            --start|--stop|--restart|--status|--logs|--uninstall)
                set_action "${1#--}"
                shift
                ;;
            --build)
                BUILD="yes"
                shift
                ;;
            --open)
                OPEN_BROWSER="yes"
                shift
                ;;
            --remove-data)
                REMOVE_DATA="yes"
                shift
                ;;
            --force-yes)
                FORCE_YES="yes"
                shift
                ;;
            --web-port|--splunk-port|--ticket-port|--catalog-port|--project-name|--wait-seconds)
                require_value "$1" "${2:-}"
                case "$1" in
                    --web-port) WEB_PORT="$2" ;;
                    --splunk-port) SPLUNK_PORT="$2" ;;
                    --ticket-port) TICKET_PORT="$2" ;;
                    --catalog-port) CATALOG_PORT="$2" ;;
                    --project-name) PROJECT_NAME="$2" ;;
                    --wait-seconds) WAIT_SECONDS="$2" ;;
                esac
                shift 2
                ;;
            *)
                print_msg "$RED" "Unknown option: $1"
                printf '\n'
                show_help
                exit 2
                ;;
        esac
    done
}

validate_port() {
    local name="$1"
    local value="$2"
    [[ -z "$value" ]] && return 0
    if ! [[ "$value" =~ ^[0-9]+$ ]] || (( value < 1 || value > 65535 )); then
        print_msg "$RED" "$name must be an integer from 1 to 65535."
        exit 2
    fi
}

validate_options() {
    validate_port "--web-port" "$WEB_PORT"
    validate_port "--splunk-port" "$SPLUNK_PORT"
    validate_port "--ticket-port" "$TICKET_PORT"
    validate_port "--catalog-port" "$CATALOG_PORT"

    if ! [[ "$WAIT_SECONDS" =~ ^[0-9]+$ ]] || (( WAIT_SECONDS < 5 || WAIT_SECONDS > 300 )); then
        print_msg "$RED" "--wait-seconds must be an integer from 5 to 300."
        exit 2
    fi

    if [[ -n "$PROJECT_NAME" ]] && ! [[ "$PROJECT_NAME" =~ ^[a-z0-9][a-z0-9_-]*$ ]]; then
        print_msg "$RED" "--project-name must start with a lowercase letter or digit and contain only lowercase letters, digits, hyphens, or underscores."
        exit 2
    fi

    if [[ "$REMOVE_DATA" == "yes" && "$ACTION" != "uninstall" ]]; then
        print_msg "$RED" "--remove-data is only valid with --uninstall."
        exit 2
    fi
}

ensure_runtime_files() {
    if [[ ! -f "$ENV_FILE" ]]; then
        cp "$INSTALL_DIR/.env.example" "$ENV_FILE"
        print_msg "$GREEN" "Created .env from .env.example"
    fi
    mkdir -p "$INSTALL_DIR/certs"
}

upsert_env() {
    local key="$1"
    local value="$2"
    local temp_file
    temp_file="$(mktemp "$INSTALL_DIR/.env.tmp.XXXXXX")"

    awk -v target="$key" -v replacement="$value" '
        BEGIN { found = 0 }
        index($0, target "=") == 1 {
            print target "=" replacement
            found = 1
            next
        }
        { print }
        END {
            if (!found) print target "=" replacement
        }
    ' "$ENV_FILE" > "$temp_file"
    mv "$temp_file" "$ENV_FILE"
}

save_overrides() {
    [[ -n "$WEB_PORT" ]] && upsert_env "DEMO_WEB_PORT" "$WEB_PORT"
    [[ -n "$SPLUNK_PORT" ]] && upsert_env "SPLUNK_MCP_PORT" "$SPLUNK_PORT"
    [[ -n "$TICKET_PORT" ]] && upsert_env "TICKET_MCP_PORT" "$TICKET_PORT"
    [[ -n "$CATALOG_PORT" ]] && upsert_env "CATALOG_MCP_PORT" "$CATALOG_PORT"
    [[ -n "$PROJECT_NAME" ]] && upsert_env "COMPOSE_PROJECT_NAME" "$PROJECT_NAME"
    return 0
}

read_env_value() {
    local key="$1"
    local fallback="$2"
    local value
    value="$(awk -v target="$key" 'index($0, target "=") == 1 { value=substr($0, length(target) + 2) } END { print value }' "$ENV_FILE")"
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"
    printf '%s' "${value:-$fallback}"
}

check_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        print_msg "$RED" "Docker was not found. Install Docker Desktop or Docker Engine, then run this installer again."
        exit 1
    fi
    if ! docker info >/dev/null 2>&1; then
        print_msg "$RED" "Docker is installed but its engine is not running. Start Docker and try again."
        exit 1
    fi
    if docker compose version >/dev/null 2>&1; then
        COMPOSE=(docker compose)
    elif command -v docker-compose >/dev/null 2>&1; then
        COMPOSE=(docker-compose)
        print_msg "$YELLOW" "Using legacy docker-compose; Docker Compose v2 is recommended."
    else
        print_msg "$RED" "Docker Compose was not found. Install the Compose plugin and try again."
        exit 1
    fi
}

compose() {
    (cd "$INSTALL_DIR" && "${COMPOSE[@]}" "$@")
}

web_url() {
    printf 'http://127.0.0.1:%s' "$(read_env_value DEMO_WEB_PORT 8100)"
}

wait_for_health() {
    local container_id
    local health
    local elapsed=0
    container_id="$(compose ps -q demo)"
    if [[ -z "$container_id" ]]; then
        print_msg "$RED" "The demo container was not created."
        compose logs --tail 80 demo || true
        return 1
    fi

    while (( elapsed < WAIT_SECONDS )); do
        health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || true)"
        case "$health" in
            healthy)
                print_msg "$GREEN" "Demo is healthy."
                return 0
                ;;
            unhealthy|exited|dead)
                print_msg "$RED" "Demo entered state: $health"
                compose logs --tail 80 demo || true
                return 1
                ;;
        esac
        sleep 2
        elapsed=$((elapsed + 2))
    done

    print_msg "$RED" "Demo did not become healthy within ${WAIT_SECONDS} seconds."
    compose logs --tail 80 demo || true
    return 1
}

open_demo() {
    local url="$1"
    if command -v open >/dev/null 2>&1; then
        open "$url" >/dev/null 2>&1 || true
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$url" >/dev/null 2>&1 || true
    elif command -v cmd.exe >/dev/null 2>&1; then
        cmd.exe /c start "" "$url" >/dev/null 2>&1 || true
    else
        print_msg "$YELLOW" "Could not identify a browser launcher; open $url manually."
    fi
}

show_ready() {
    local url
    url="$(web_url)"
    printf '\n'
    print_msg "$GREEN" "$APP_NAME is ready."
    print_msg "$BLUE" "Web interface: $url"
    print_msg "$BLUE" "Setup: use the gear menu to configure Splunk, the LLM, and audience."
    print_msg "$BLUE" "Logs: ./install.sh --logs"
    [[ "$OPEN_BROWSER" == "yes" ]] && open_demo "$url"
    return 0
}

install_demo() {
    print_msg "$BLUE" "Building and starting the complete MCP demo..."
    compose up --detach --build --remove-orphans
    wait_for_health
    show_ready
}

start_demo() {
    print_msg "$BLUE" "Starting the MCP demo..."
    if [[ "$BUILD" == "yes" ]]; then
        compose up --detach --build --remove-orphans
    else
        compose up --detach --remove-orphans
    fi
    wait_for_health
    show_ready
}

stop_demo() {
    print_msg "$BLUE" "Stopping the MCP demo..."
    compose stop
    print_msg "$GREEN" "Services stopped. Settings and ticket data were preserved."
}

restart_demo() {
    print_msg "$BLUE" "Restarting the MCP demo..."
    if [[ "$BUILD" == "yes" ]]; then
        compose up --detach --build --force-recreate --remove-orphans
    else
        compose restart
    fi
    wait_for_health
    show_ready
}

status_demo() {
    compose ps
    local container_id
    local health
    container_id="$(compose ps -q demo)"
    if [[ -z "$container_id" ]]; then
        print_msg "$YELLOW" "Demo is not running."
        return 1
    fi
    health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || true)"
    if [[ "$health" == "healthy" ]]; then
        print_msg "$GREEN" "Demo is healthy: $(web_url)"
        return 0
    fi
    print_msg "$YELLOW" "Demo health: ${health:-unknown}"
    return 1
}

uninstall_demo() {
    local args=(down --remove-orphans --rmi local)
    if [[ "$REMOVE_DATA" == "yes" ]]; then
        if [[ "$FORCE_YES" != "yes" ]]; then
            print_msg "$YELLOW" "This will permanently remove this Compose project's tickets and encrypted Splunk/LLM settings."
            local confirmation
            read -r -p "Type REMOVE to continue: " confirmation
            if [[ "$confirmation" != "REMOVE" ]]; then
                print_msg "$BLUE" "Uninstall cancelled."
                return 0
            fi
        fi
        args+=(--volumes)
    fi

    compose "${args[@]}"
    if [[ "$REMOVE_DATA" == "yes" ]]; then
        print_msg "$GREEN" "Containers, local image, and this project's persistent demo data were removed."
    else
        print_msg "$GREEN" "Containers and local image were removed. Settings and ticket data were preserved."
    fi
    print_msg "$BLUE" "The cloned source and .env remain in $INSTALL_DIR"
}

main() {
    parse_args "$@"
    validate_options

    if [[ "$ACTION" == "help" ]]; then
        show_help
        return 0
    fi

    ensure_runtime_files
    save_overrides
    check_docker

    case "$ACTION" in
        install) install_demo ;;
        start) start_demo ;;
        stop) stop_demo ;;
        restart) restart_demo ;;
        status) status_demo ;;
        logs) compose logs --follow --tail 150 ;;
        uninstall) uninstall_demo ;;
    esac
}

main "$@"
