#!/bin/bash
# Rigorous exit on error
set -e

# --- Configuration ---
ENV_TEMPLATE_FILE=".env.template"
ENV_FILE=".env"
REQUIRED_DIRS=("media_root/authentik/media" "configs/authentik/certs")

# --- Helper Functions ---
generate_secret() {
    openssl rand -hex 32
}

# --- Main Logic ---
echo "Visify Story Studio - Deployment Initializer"
echo "------------------------------------------------"

if [ ! -f "$ENV_TEMPLATE_FILE" ]; then
    echo "Error: Template file '$ENV_TEMPLATE_FILE' not found."
    exit 1
fi

if [ -f "$ENV_FILE" ]; then
    read -p "Warning: '$ENV_FILE' already exists. Do you want to overwrite it? [y/N]: " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo "Aborted."
        exit 0
    fi
fi

echo "Generating new '$ENV_FILE' from template..."
cp "$ENV_TEMPLATE_FILE" "$ENV_FILE"

echo "Generating secure keys..."
DJANGO_SECRET_KEY=$(generate_secret)
POSTGRES_PASSWORD=$(generate_secret)
AUTHENTIK_SECRET_KEY=$(generate_secret)
AUTHENTIK_BOOTSTRAP_PASSWORD=$(generate_secret)

sed -i.bak "s|DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}|" "$ENV_FILE"
sed -i.bak "s|POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${POSTGRES_PASSWORD}|" "$ENV_FILE"
sed -i.bak "s|AUTHENTIK_SECRET_KEY=.*|AUTHENTIK_SECRET_KEY=${AUTHENTIK_SECRET_KEY}|" "$ENV_FILE"
sed -i.bak "s|AUTHENTIK_BOOTSTRAP_PASSWORD=.*|AUTHENTIK_BOOTSTRAP_PASSWORD=${AUTHENTIK_BOOTSTRAP_PASSWORD}|" "$ENV_FILE"

echo "Please provide initial settings for the instance:"
read -p "Enter the initial Django superuser email: " DJANGO_SUPERUSER_EMAIL
read -s -p "Enter the initial Django superuser password: " DJANGO_SUPERUSER_PASSWORD
echo
read -p "Enter the Label Studio Access Token (from the LS UI): " LABEL_STUDIO_ACCESS_TOKEN
read -p "Enter the Authentik API Token (create this in the Authentik UI): " AUTHENTIK_API_TOKEN
read -p "Enter comma-separated emails for auto-superuser access: " AUTHORIZED_SUPERUSER_EMAILS
DEFAULT_ALLOWED_HOSTS="localhost,127.0.0.1"
read -p "Enter comma-separated Allowed Hosts [${DEFAULT_ALLOWED_HOSTS}]: " DJANGO_ALLOWED_HOSTS
# Correct way to handle default value after the read command
DJANGO_ALLOWED_HOSTS=${DJANGO_ALLOWED_HOSTS:-$DEFAULT_ALLOWED_HOSTS}

# Use sed to replace placeholders, wrapping values in quotes for safety
sed -i.bak "s|DJANGO_SUPERUSER_EMAIL=.*|DJANGO_SUPERUSER_EMAIL=\"${DJANGO_SUPERUSER_EMAIL}\"|" "$ENV_FILE"
sed -i.bak "s|DJANGO_SUPERUSER_PASSWORD=.*|DJANGO_SUPERUSER_PASSWORD=\"${DJANGO_SUPERUSER_PASSWORD}\"|" "$ENV_FILE"
sed -i.bak "s|LABEL_STUDIO_ACCESS_TOKEN=.*|LABEL_STUDIO_ACCESS_TOKEN=\"${LABEL_STUDIO_ACCESS_TOKEN}\"|" "$ENV_FILE"
sed -i.bak "s|AUTHENTIK_API_TOKEN=.*|AUTHENTIK_API_TOKEN=\"${AUTHENTIK_API_TOKEN}\"|" "$ENV_FILE"
sed -i.bak "s|AUTHORIZED_SUPERUSER_EMAILS=.*|AUTHORIZED_SUPERUSER_EMAILS=\"${AUTHORIZED_SUPERUSER_EMAILS}\"|" "$ENV_FILE"
sed -i.bak "s|DJANGO_ALLOWED_HOSTS=.*|DJANGO_ALLOWED_HOSTS=\"${DJANGO_ALLOWED_HOSTS}\"|" "$ENV_FILE"

rm -f "${ENV_FILE}.bak"
chmod 600 "$ENV_FILE"

echo "Creating necessary directories..."
for dir in "${REQUIRED_DIRS[@]}"; do
    mkdir -p "$dir"
done

echo "------------------------------------------------"
echo "✅ Initialization complete!"
echo "The '$ENV_FILE' has been created successfully."
echo
echo "Next steps:"
echo "1. Run 'docker-compose up -d' to start all services."
echo "2. Run 'docker-compose exec web python manage.py migrate'"
echo "3. Run 'docker-compose exec web python manage.py setup_instance'"