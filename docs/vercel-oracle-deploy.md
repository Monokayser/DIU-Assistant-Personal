# Vercel Frontend + Oracle Backend

This is the closest deployment path to local development without paying for a VPS:

- `frontend/` deploys to Vercel as a static Vite app
- `backend/main.py` runs on an Oracle Cloud Free VM in Docker
- runtime folders under `tmp/` stay writable and persistent on the Oracle VM

## What stays close to localhost

- the Python API remains a normal long-running server
- uploaded document context still writes to `tmp/uploaded_contexts/`
- canvas artifacts still write to `tmp/canvas_artifacts/`
- backend logs still write to `tmp/logs/`

The main difference from localhost is that the frontend and backend live on separate HTTPS domains.

## Frontend on Vercel

Use `frontend/` as the Vercel project root.

Set this environment variable in Vercel:

```bash
VITE_API_URL=https://api.your-domain.com
```

Then deploy from the `frontend/` directory:

```bash
vercel
```

Or for production:

```bash
vercel --prod
```

## Backend on Oracle

Use an Oracle Cloud Free Ubuntu VM and point a DNS record like `api.your-domain.com` to that VM.

### 1. Install Docker on the VM

From the repo root on the VM:

```bash
bash scripts/oracle-bootstrap.sh
```

Open Oracle networking for:

- `22/tcp` for SSH
- `80/tcp` for HTTP
- `443/tcp` for HTTPS

### 2. Prepare backend environment

Start from the included template:

```bash
cp .env.oracle.example .env
```

Then fill in the real values. At minimum, set:

```bash
GEMINI_API_KEY=your_key_here
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here
SUPABASE_ANON_KEY=your_anon_key_here
SUPABASE_SESSION_ID=default
SUPABASE_DOCUMENT_TABLE=document_chunks
SUPABASE_MATCH_RPC=match_document_chunks
APP_DOMAIN=api.your-domain.com
ALLOWED_ORIGINS=https://your-frontend.vercel.app,https://your-custom-frontend-domain.com
API_HOST=0.0.0.0
API_PORT=8765
```

You can keep the rest aligned with `.env.example`.

### 3. Start the backend stack

```bash
bash scripts/oracle-deploy.sh
```

### 4. Verify health

```bash
curl -I https://api.your-domain.com/api/health
```

To inspect containers:

```bash
docker compose -f docker-compose.oracle.yml ps
docker compose -f docker-compose.oracle.yml logs --tail=100
```

## Everyday updates

On the Oracle VM:

```bash
git pull
docker compose -f docker-compose.oracle.yml up -d --build
```

On Vercel:

- push to the connected branch, or
- run `vercel --prod` from `frontend/`

## Notes

- Oracle free compute is good for personal or low-traffic usage, but not for heavy concurrent uploads.
- Vercel will feel fast on the frontend, but Gemini response time still depends on the model call itself.
- This path is much closer to localhost than putting the backend on a serverless platform.
