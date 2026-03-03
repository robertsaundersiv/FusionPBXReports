# SSL Certificates (self-signed for development)
# For production, use proper certificates from Let's Encrypt or similar

# Generate self-signed cert for development:
# openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365
