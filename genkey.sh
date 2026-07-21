#!/usr/bin/env bash

# ============================================================================
# SSH KEY GENERATOR
# ============================================================================
#
# Syntax
# ----------------------------------------------------------------------------
#
#   ./genkey.sh EMAIL [PLATFORM] [HOSTNAME] [PROFILE]
#
#
# Arguments
# ----------------------------------------------------------------------------
#
# EMAIL
#   Mandatory SSH key comment.
#
#   Typically:
#
#       user@domain.tld
#
#   This email identifies the account associated with the SSH key.
#
#
# PLATFORM
#   Optional target platform.
#
#   Supported values:
#
#       github
#       gitlab
#
#   If omitted, a generic SSH key is generated.
#
#
# HOSTNAME
#   Optional machine identifier.
#
#   Recommended:
#
#       use the physical or logical machine name
#
#   Examples:
#
#       workstation
#       laptop
#       server
#
#
# PROFILE
#   Optional identity/profile discriminator.
#
#   Examples:
#
#       perso
#       pro
#       admin
#       research
#
#
# Examples
# ----------------------------------------------------------------------------
#
# Generate a professional GitHub SSH key:
#
#   ./genkey.sh user@domain.tld github workstation pro
#
#
# Generate a personal GitHub SSH key:
#
#   ./genkey.sh user@domain.tld github laptop perso
#
#
# Generate a GitLab administrator SSH key:
#
#   ./genkey.sh admin@domain.tld gitlab server admin
#
#
# Generate a generic SSH key:
#
#   ./genkey.sh user@domain.tld
#
#
# Generated Key Names
# ----------------------------------------------------------------------------
#
# Inputs:
#
#   PLATFORM = github
#   HOSTNAME = workstation
#   PROFILE  = pro
#
# Result:
#
#   ~/.ssh/id_ed25519_github_workstation_pro
#
#
# Inputs:
#
#   PLATFORM = gitlab
#   HOSTNAME = server
#   PROFILE  = admin
#
# Result:
#
#   ~/.ssh/id_ed25519_gitlab_server_admin
#
#
# Inputs:
#
#   PLATFORM = <empty>
#   HOSTNAME = <empty>
#   PROFILE  = <empty>
#
# Result:
#
#   ~/.ssh/id_ed25519
#
#
# Script Behaviour
# ----------------------------------------------------------------------------
#
# The script automatically:
#
#   - creates ~/.ssh if required
#   - generates an ED25519 SSH keypair
#   - starts ssh-agent if needed
#   - adds the key to ssh-agent
#   - applies secure filesystem permissions
#   - prints the public key
#   - proposes an SSH config snippet
#
#
# Registration URLs
# ----------------------------------------------------------------------------
#
# GitHub:
#   https://github.com/settings/keys
#
# GitLab:
#   https://gitlab.com/-/user_settings/ssh_keys
#
# ============================================================================

set -e

EMAIL="${1:-}"
PLATFORM="${2:-}"
HOSTNAME_ARG="${3:-}"
PROFILE="${4:-}"

# ----------------------------------------------------------------------------
# Validate EMAIL
# ----------------------------------------------------------------------------

if [[ -z "$EMAIL" ]]; then

    echo ""
    echo "ERROR: EMAIL argument is mandatory."
    echo ""
    echo "Syntax:"
    echo "  ./genkey.sh EMAIL [PLATFORM] [HOSTNAME] [PROFILE]"
    echo ""
    exit 1

fi

# ----------------------------------------------------------------------------
# Normalize platform
# ----------------------------------------------------------------------------

PLATFORM=$(echo "$PLATFORM" | tr '[:upper:]' '[:lower:]')

# ----------------------------------------------------------------------------
# Validate platform
# ----------------------------------------------------------------------------

if [[ "$PLATFORM" != "github" && "$PLATFORM" != "codeberg" && "$PLATFORM" != "gitlab" && -n "$PLATFORM" ]]; then

    echo ""
    echo "ERROR: unsupported PLATFORM."
    echo ""
    echo "Supported values:"
    echo "  github"
    echo "  gitlab"
    echo "  codeberg"
    echo ""
    exit 1

fi

# ----------------------------------------------------------------------------
# Build SSH key filename
# ----------------------------------------------------------------------------

SUFFIX=""

if [[ -n "$PLATFORM" ]]; then
    SUFFIX="${SUFFIX}_${PLATFORM}"
fi

if [[ -n "$HOSTNAME_ARG" ]]; then
    SUFFIX="${SUFFIX}_${HOSTNAME_ARG}"
fi

if [[ -n "$PROFILE" ]]; then
    SUFFIX="${SUFFIX}_${PROFILE}"
fi

KEY_NAME="id_ed25519${SUFFIX}"
KEY_PATH="$HOME/.ssh/$KEY_NAME"

# ----------------------------------------------------------------------------
# Display configuration
# ----------------------------------------------------------------------------

echo ""
echo "========================================================"
echo "SSH KEY GENERATION"
echo "========================================================"
echo ""

echo "EMAIL    : $EMAIL"
echo "PLATFORM : ${PLATFORM:-<empty>}"
echo "HOSTNAME : ${HOSTNAME_ARG:-<empty>}"
echo "PROFILE  : ${PROFILE:-<empty>}"
echo ""

echo "KEY PATH : $KEY_PATH"
echo ""

# ----------------------------------------------------------------------------
# Create ~/.ssh directory
# ----------------------------------------------------------------------------

mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"

# ----------------------------------------------------------------------------
# Prevent overwrite
# ----------------------------------------------------------------------------

if [[ -f "$KEY_PATH" || -f "${KEY_PATH}.pub" ]]; then

    echo "ERROR: SSH key already exists:"
    echo "  $KEY_PATH"
    echo ""
    exit 1

fi

# ----------------------------------------------------------------------------
# Generate SSH key
# ----------------------------------------------------------------------------

ssh-keygen -t ed25519 -C "$EMAIL" -f "$KEY_PATH"

# ----------------------------------------------------------------------------
# Start ssh-agent if required
# ----------------------------------------------------------------------------

if [[ -z "${SSH_AUTH_SOCK:-}" ]]; then

    echo ""
    echo "Starting ssh-agent..."
    eval "$(ssh-agent -s)"

fi

# ----------------------------------------------------------------------------
# Add SSH key to agent
# ----------------------------------------------------------------------------

echo ""
echo "Adding SSH key to ssh-agent..."
ssh-add "$KEY_PATH"

# ----------------------------------------------------------------------------
# Secure permissions
# ----------------------------------------------------------------------------

chmod 600 "$KEY_PATH"
chmod 644 "${KEY_PATH}.pub"

# ----------------------------------------------------------------------------
# Display public key
# ----------------------------------------------------------------------------

echo ""
echo "========================================================"
echo "PUBLIC KEY"
echo "========================================================"
echo ""

cat "${KEY_PATH}.pub"

# ----------------------------------------------------------------------------
# SSH config snippet
# ----------------------------------------------------------------------------

echo ""
echo "========================================================"
echo "SSH CONFIG SNIPPET"
echo "========================================================"
echo ""

if [[ "$PLATFORM" == "github" ]]; then

cat <<EOF
Host github.com
    HostName github.com
    User git
    IdentityFile $KEY_PATH
    IdentitiesOnly yes
EOF

elif [[ "$PLATFORM" == "gitlab" ]]; then

cat <<EOF
Host gitlab.com
    HostName gitlab.com
    User git
    IdentityFile $KEY_PATH
    IdentitiesOnly yes
EOF

else

cat <<EOF
# Generic SSH configuration example
Host myserver
    HostName example.org
    User myuser
    IdentityFile $KEY_PATH
    IdentitiesOnly yes
EOF

fi

# ----------------------------------------------------------------------------
# Registration instructions
# ----------------------------------------------------------------------------

echo ""
echo "========================================================"
echo "NEXT STEPS"
echo "========================================================"
echo ""

if [[ "$PLATFORM" == "github" ]]; then

    echo "Register the public key on:"
    echo "https://github.com/settings/keys"
    echo ""
    echo "Test command:"
    echo "  ssh -T git@github.com"

elif [[ "$PLATFORM" == "gitlab" ]]; then

    echo "Register the public key on:"
    echo "https://gitlab.com/-/user_settings/ssh_keys"
    echo ""
    echo "Test command:"
    echo "  ssh -T git@gitlab.com"

else

    echo "Register the public key on the target infrastructure."

fi

echo ""
echo "Done."
echo ""
