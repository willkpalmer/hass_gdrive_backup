# Running your own auth server

Google only lets the add-on reach your Drive after you sign in through a Google "app" (an OAuth
client). That app's client secret can't be shipped inside the add-on, so a small web service, the
**auth server**, holds it. The add-on uses the auth server for two things:

- **Sign in** (`/drive/authorize`): sends you to Google's consent screen and hands the resulting
  credentials back to your Home Assistant.
- **Token refresh** (`/drive/refresh`): turns the long-lived refresh token into short-lived access
  tokens, roughly once an hour.

It also serves the Drive folder picker, `/privacy_policy` and `/terms_of_service` (Google asks for
both when you set up the consent screen), and `/health`.

The server is the code in [`hass_gdrive_backup/backup/server`](hass_gdrive_backup/backup/server).
It stores nothing: credentials pass through it, and error reports from add-ons are only written
to its log.

Until you point the add-on at your own server, it uses the original add-on's shared server at
`habackup.io`.

## 1. Create the Google app (one time)

In the [Google Cloud console](https://console.cloud.google.com/):

1. **Create a project**, and note its **project ID** and **project number**.
2. **Enable APIs:** *Google Drive API* and *Google Picker API*.
3. **Decide your server's URL.** On Cloud Run it's predictable before you deploy:
   `https://hass-gdrive-backup-auth-<PROJECT_NUMBER>.<REGION>.run.app`. On your own host, use a
   domain you control, served over HTTPS. The steps below call this `https://AUTH_SERVER`.
4. **Configure the consent screen** (*Google Auth Platform → Branding / Audience / Data access*):
   - User type **External**. Add your app name, support email and developer contact.
   - Home page: `https://AUTH_SERVER/`. Privacy policy: `https://AUTH_SERVER/privacy_policy`.
     Terms of service: `https://AUTH_SERVER/terms_of_service`.
   - Scope: `https://www.googleapis.com/auth/drive.file` only. It lets the app see only the files
     and folders it creates or that you pick, and Google classes it as non-sensitive.
   - **Publish the app ("In production").** While an app is in *Testing*, Google expires its
     refresh tokens after 7 days, so backups would stop uploading every week. Apps that only ask
     for non-sensitive scopes don't need Google's review to publish, though Google may still ask
     you to verify the branding details.
5. **Create an OAuth client** (*Clients → Create client → Web application*):
   - Authorized JavaScript origin: `https://AUTH_SERVER`
   - Authorized redirect URI: `https://AUTH_SERVER/drive/authorize`
   - Keep the **client ID** and **client secret**.
6. **Create an API key** for the folder picker (*APIs & Services → Credentials → Create API key*).
   Restrict it to the *Google Picker API* and to websites `https://AUTH_SERVER/*`.

## 2. Run the server

The server is a container image published by the
[Auth Server workflow](.github/workflows/auth_server.yml) to
`ghcr.io/willkpalmer/hass-gdrive-backup-auth` on every change to `master`. It's configured with
environment variables:

| Variable | Required | What it is |
| --- | --- | --- |
| `DEFAULT_DRIVE_CLIENT_ID` | yes | OAuth client ID from step 1.5 |
| `DEFAULT_DRIVE_CLIENT_SECRET` | yes | OAuth client secret from step 1.5 |
| `AUTHORIZATION_HOST` | yes | The server's public URL, `https://AUTH_SERVER` (used to build the redirect URI) |
| `DRIVE_PICKER_API_KEY` | for the folder picker | API key from step 1.6 |
| `SERVER_CONTACT_EMAIL` | no | Shown on the privacy policy page |
| `PORT` | no | Port to listen on (default `8080`) |

The server refuses to start if a required variable is missing.

### Option A: Google Cloud Run (automatic deploys)

Cloud Run's free tier comfortably covers a personal server. After this one-time setup, the
workflow redeploys the server whenever its code changes on `master`.

Run these once, in [Cloud Shell](https://shell.cloud.google.com/) or anywhere with `gcloud`:

```bash
PROJECT_ID=your-project-id
REGION=us-central1
REPO=willkpalmer/hass_gdrive_backup
gcloud config set project "$PROJECT_ID"
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')

gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com iamcredentials.googleapis.com

# Where deployed images are stored (Cloud Run can't pull from ghcr.io directly)
gcloud artifacts repositories create hass-gdrive-backup --repository-format=docker --location="$REGION"

# The two secrets, readable by the service Cloud Run runs as
printf '%s' 'YOUR_CLIENT_SECRET' | gcloud secrets create drive-client-secret --data-file=-
printf '%s' 'YOUR_PICKER_API_KEY' | gcloud secrets create drive-picker-api-key --data-file=-
for secret in drive-client-secret drive-picker-api-key; do
  gcloud secrets add-iam-policy-binding "$secret" --role=roles/secretmanager.secretAccessor \
    --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
done

# A deploy account that GitHub Actions can use without a stored key (Workload Identity Federation)
gcloud iam service-accounts create github-deployer
SA="github-deployer@${PROJECT_ID}.iam.gserviceaccount.com"
for role in roles/run.admin roles/artifactregistry.writer roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SA" --role="$role"
done
gcloud iam workload-identity-pools create github --location=global
gcloud iam workload-identity-pools providers create-oidc github-actions --location=global \
  --workload-identity-pool=github --issuer-uri=https://token.actions.githubusercontent.com \
  --attribute-mapping=google.subject=assertion.sub,attribute.repository=assertion.repository \
  --attribute-condition="assertion.repository=='${REPO}'"
gcloud iam service-accounts add-iam-policy-binding "$SA" --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github/attribute.repository/${REPO}"

echo "GCP_WORKLOAD_IDENTITY_PROVIDER=projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github/providers/github-actions"
echo "GCP_SERVICE_ACCOUNT=${SA}"
echo "AUTH_SERVER_URL=https://hass-gdrive-backup-auth-${PROJECT_NUMBER}.${REGION}.run.app"
```

Then, in the GitHub repository under *Settings → Secrets and variables → Actions → Variables*,
add these **variables** (none of them are secret):

| Variable | Value |
| --- | --- |
| `GCP_PROJECT_ID` | your project ID (setting this turns the Cloud Run deploy on) |
| `GCP_REGION` | e.g. `us-central1` |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | printed by the script above |
| `GCP_SERVICE_ACCOUNT` | printed by the script above |
| `DRIVE_CLIENT_ID` | OAuth client ID from step 1.5 |
| `AUTH_SERVER_URL` | printed by the script above (or your custom domain) |
| `SERVER_CONTACT_EMAIL` | optional |

Run the *Auth Server* workflow from the Actions tab (or push to `master`), then open
`https://AUTH_SERVER/health`. It should return `{"status": "ok", ...}`.

### Option B: any Docker host

Run the image behind an HTTPS reverse proxy (Caddy, Traefik, nginx, Cloudflare Tunnel, ...) that
forwards `https://AUTH_SERVER` to port 8080:

```bash
docker run -d --restart unless-stopped -p 8080:8080 \
  -e DEFAULT_DRIVE_CLIENT_ID=... \
  -e DEFAULT_DRIVE_CLIENT_SECRET=... \
  -e DRIVE_PICKER_API_KEY=... \
  -e AUTHORIZATION_HOST=https://AUTH_SERVER \
  ghcr.io/willkpalmer/hass-gdrive-backup-auth:latest
```

Google must be able to redirect your browser to it, but it doesn't need to be reachable from the
wider internet beyond that, and your Home Assistant must be able to reach it for token refresh.

## 3. Point the add-on at it

In Home Assistant, open the add-on's **Configuration** tab and set **`auth_server_url`** to
`https://AUTH_SERVER`. Then, in the add-on's web UI, sign in to Google Drive again. Credentials
from a different server can't be refreshed by yours.

To make your server the default for every install, change `Setting.AUTHORIZATION_HOST` and
`Setting.TOKEN_SERVER_HOSTS` in
[`backup/config/settings.py`](hass_gdrive_backup/backup/config/settings.py) and release a new
version.

Signing in with your own Google credentials directly in the add-on, without any auth server, also
still works. See [LOCAL_AUTH.md](LOCAL_AUTH.md).
