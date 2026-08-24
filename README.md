# Infinia Labour Tool - Web Backend

## Deploying to Render (free, no credit card needed)

1. Go to https://render.com and sign up (GitHub login is fastest)
2. Create a new GitHub repository and upload everything in this folder to it
   (github.com > New repository > upload these files)
3. In Render: **New > Blueprint**
4. Connect the GitHub repo you just created
5. Render will read `render.yaml` automatically and set up:
   - The web service (the API)
   - A free PostgreSQL database, already linked to it
6. Click **Apply** - first deploy takes a few minutes
7. Once it's live, Render gives you a URL like:
   `https://infinia-labour-tool-api.onrender.com`

That URL is a real, working backend, reachable from any browser -
already logged in as `admin` / `changeme123` (change this password
immediately after your first login), with your real 74 employees, sites,
and engineers already loaded in automatically on first startup.

## Important limits of Render's free tier

- The free database **expires after 30 days**. This is fine for testing
  and demoing to staff, but not for real production data - once you're
  ready to go live for real, this is exactly when to move to the BigRock
  VPS discussed separately.
- The web service **sleeps after 15 minutes of no traffic**, and takes
  ~30-60 seconds to wake back up on the next request. Normal for a free
  tier, not something to worry about during testing.
- **Change the admin password immediately** - this URL will be public on
  the internet, even without a custom domain pointed at it yet.

## What's included here

- `app/` - the FastAPI backend (auth, employees, daily attendance,
  salary adjustments, all reusing the desktop app's exact payroll
  formula)
- `app/master_data.json` - your real 74 employees, sites, and engineers,
  auto-imported the first time the app starts
- `render.yaml` - tells Render how to build and run everything, and to
  provision a linked free database automatically
- `requirements.txt` - the exact Python packages needed

## Local development

```
pip install -r requirements.txt
# requires a running PostgreSQL instance
export DATABASE_URL="postgresql://user:password@localhost:5432/infinia_labour"
cd app
uvicorn main:app --reload
```
