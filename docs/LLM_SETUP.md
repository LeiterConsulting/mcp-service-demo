# Connect the demo to an LLM

The LLM is optional. **Setup → Agent & LLM** supports OpenAI and compatible Responses API
endpoints while Guided mode remains available as a deterministic fallback.

For OpenAI, use:

- API endpoint: `https://api.openai.com/v1`
- Model: a Responses API model available to the supplied API key
- TLS verification: enabled

The browser connection test and every agent request use the same endpoint, model, API key, Docker
routing, timeout, and TLS trust configuration. A successful test therefore validates the path the
demo itself will use.

## Certificate verification on Docker for Mac

An error containing `CERTIFICATE_VERIFY_FAILED` and `unable to get local issuer certificate` means
the demo container cannot build a trusted chain for the certificate it received. A common cause is
a company security product or proxy issuing a replacement certificate whose root is trusted by the
macOS Keychain but is not present inside Docker's Linux container.

The preferred fix preserves certificate verification:

1. Export the issuing company root and any required intermediate certificates from **Keychain
   Access** as PEM certificate data. Do not export a private key.
2. Save the bundle in this repository, for example `certs/company-root.pem`. The `certs/` contents
   are ignored by Git and mounted read-only at `/app/certs` by Docker Compose.
3. Open **Setup → Agent & LLM**.
4. Keep **Verify TLS certificate** selected and enter `/app/certs/company-root.pem` in **Custom CA
   bundle**.
5. Choose **Test model**, then save the settings.

For a controlled local demo only, clearing **Verify TLS certificate** bypasses server-certificate
validation. This is useful as a short-term diagnostic or rehearsal workaround, not as the default
for customer or production networks.

The equivalent environment settings are:

```dotenv
OPENAI_VERIFY_SSL=true
OPENAI_CA_BUNDLE=/app/certs/company-root.pem
```

Custom LLM CA bundles are included in encrypted `.mcpdemo` settings exports, just like Splunk CA
bundles, so a configured presentation profile can be transferred without depending on its original
filesystem path.

## Network diagnostic

This credential-free request exercises the container's DNS, network, and TLS path:

```bash
docker compose exec demo python -c "import httpx; print(httpx.get('https://api.openai.com/v1/models', timeout=15).status_code)"
```

An HTTP `401` is expected without a key and proves the HTTPS path is valid. A certificate exception
confirms that the trust configuration—not the API key or model—is preventing the connection.
