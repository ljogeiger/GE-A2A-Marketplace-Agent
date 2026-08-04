#!/bin/bash


echo "This script will upload secrets from .env to Google Secret Manager."
read -p "Do you want to continue? [Y/n] " confirm
confirm=${confirm:-Y}

if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
  echo "Aborting."
  exit 0
fi

# Check if .env file exists
if [ ! -f .env ]; then
  echo "Error: .env file not found in current directory."
  exit 1
fi

# Read .env file line by line
# IFS='=' splits the line into key and value
while IFS='=' read -r key value || [ -n "$key" ]; do
  # Skip empty lines and comments (starting with #)
  if [[ -z "$key" || "$key" =~ ^# ]]; then
    continue
  fi

  # Remove leading/trailing whitespace from key and value
  key=$(echo "$key" | xargs)
  value=$(echo "$value" | xargs)

  # Remove potential quotes surrounding the value
  value=$(echo "$value" | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")

  if [ -n "$key" ]; then
    echo "Processing secret: $key"
    # Create the secret and upload the value
    # --data-file=- reads the value from stdin
    echo -n "$value" | gcloud secrets create "$key" --data-file=-
  fi
done < .env
