# TLS Certificates

Place certificate files used by Nginx in this directory.

Expected filenames:

- `cert.pem`
- `key.pem`

## Development (self-signed)

```bash
openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365
```

## Production

Use valid certificates (for example Let's Encrypt) and keep the same filenames so `docker/nginx.conf` can load them.
