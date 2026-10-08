# Putting CiteCheck online for free

The public demo needs no token: the "Try a sample" tab runs on the offline demo library. Add your Indian Kanoon token only when you want the "Check your draft" tab to work for visitors, and keep the daily limit low until Indian Kanoon approves non-commercial credit.

## Option A: Streamlit Community Cloud (simplest)

1. Push this repository to a **public** GitHub repo under your personal account.
2. Sign in at [share.streamlit.io](https://share.streamlit.io) with that GitHub account and choose **Create app**.
3. Pick the repo, branch `main`, main file `app.py`. Under **Advanced settings**, choose Python 3.12.
4. (Optional) Under **Secrets**, add:
   ```toml
   IK_API_TOKEN = "your-indian-kanoon-token"
   ```
   and under environment variables, `CITECHECK_DAILY_CALL_LIMIT = "50"`.
5. Deploy. You get a `*.streamlit.app` address to share.

## Option B: Hugging Face Spaces (Docker)

1. Create a new Space, choose the **Docker** SDK and the free CPU hardware.
2. Push this repository to the Space. Add these lines to the top of the Space's `README.md` (Hugging Face reads them; GitHub would show them as a table, which is why they aren't in this repo's README):
   ```yaml
   ---
   title: CiteCheck
   emoji: ⚖️
   colorFrom: blue
   colorTo: gray
   sdk: docker
   app_port: 7860
   ---
   ```
3. (Optional) Under **Settings → Variables and secrets**, add the secret `IK_API_TOKEN` and the variable `CITECHECK_DAILY_CALL_LIMIT`.

## Keeping the cost at zero

- A search costs ₹0.50 and a judgment fetch ₹0.20. A typical draft uses 10 to 30 calls.
- Everything is cached under `.cache/kanoon`, so a draft checked twice costs nothing the second time. Free hosts wipe this cache when the app restarts, which is fine.
- `CITECHECK_DAILY_CALL_LIMIT` is a hard stop. Once it is reached, items are marked "Not checked" instead of spending more.
