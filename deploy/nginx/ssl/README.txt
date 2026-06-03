Place your TLS certificate and key here:
- cert.pem : Full certificate chain (server cert + intermediate)
- key.pem  : Private key (no passphrase)

To generate a self-signed certificate for testing:
  openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout key.pem -out cert.pem -subj "/CN=pygbsentry.local"

For production, use Let's Encrypt or your CA:
  See deploy/scripts/backup.sh and backend/app/services/ssl_certbot/
