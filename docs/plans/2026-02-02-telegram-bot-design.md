# Telegram Bot Design

## Overview

A Telegram bot that provides full HR-Breaker functionality within Telegram. Users can send job URLs, select CVs, and receive optimized resumes as PDFs directly in chat.

## Architecture

```
┌─────────────────────────────────────────────┐
│            Telegram Bot Service             │
│         (Standalone Python + aiogram)       │
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │  Handlers: /start, /upload_cv, etc  │   │
│  │  Inline keyboards for CV selection   │   │
│  │  Payment handlers (Telegram Payments)│   │
│  │  Background task polling             │   │
│  └─────────────────────────────────────┘   │
└──────────────────┬──────────────────────────┘
                   │ HTTP calls
                   ▼
┌──────────────────────────────────────────────┐
│          Existing FastAPI Backend            │
│  (Extended with bot-specific endpoints)      │
└──────────────────────────────────────────────┘
```

**Key decisions:**
- Bot is a separate Python service with its own entry point
- Communicates with FastAPI backend via HTTP (reuses existing endpoints + new ones)
- Uses aiogram 3.x for async Telegram interaction
- Bot stores minimal state (Telegram user ID ↔ backend user mapping)
- Optimization runs in the existing backend; bot polls for completion and sends result

**Dependencies:**
- `aiogram>=3.0` — async Telegram bot framework
- `httpx` — async HTTP client (already in project)
- `pydantic-settings` — configuration management

## Authentication Flow

All users must have a Google account from the web app first. No standalone Telegram accounts.

**Linking flow:**

1. User creates account on web app via Google OAuth (existing flow)
2. User goes to web app → Settings → "Link Telegram"
3. Web app shows a unique 6-digit code (expires in 10 min)
4. User sends `/start` or `/link <code>` to bot
5. Bot verifies code via backend, links Telegram ID to existing account
6. User now has full access to their CVs and subscription

**Unlinked user experience:**
- If user messages bot without linking, bot replies: "Please link your account first" with a button to open the web app

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message + prompt to link account if not linked |
| `/link <code>` | Link Telegram to web account using 6-digit code |
| `/my_cvs` | List all uploaded CVs with inline buttons |
| `/upload_cv` | Instructions to send a file (PDF, TXT, DOCX, etc.) |
| `/delete_cv` | Shows CV list with delete buttons |
| `/history` | List past optimization runs with download buttons |
| `/status` | Show subscription status, requests remaining |
| `/subscribe` | Start subscription payment flow |
| `/buy_credits` | Buy add-on request pack |
| `/help` | List all commands |

**Inline keyboards used for:**
- CV selection after sending job URL
- Confirming CV deletion
- Re-downloading past PDFs from history

**File handling:**
- When user sends a document (outside of any command), bot asks: "Save this as a new CV?"
- When user sends a URL, bot detects it and starts optimization flow

## Optimization Flow

**Step-by-step interaction:**

```
User: https://linkedin.com/jobs/view/12345

Bot:  🔍 Job URL detected! Select a CV to optimize:
      [📄 Software_Engineer_CV.pdf]
      [📄 Backend_Developer.txt]
      [📄 General_Resume.pdf]

User: (taps "Software_Engineer_CV.pdf")

Bot:  ⏳ Starting optimization for "Software_Engineer_CV.pdf"
      I'll send you the result when it's ready.

      (User can continue chatting or leave)

Bot:  ✅ Your optimized resume is ready!
      📄 (sends PDF file)

      Requests remaining: 47/50
```

**Behind the scenes:**
1. Bot calls `POST /api/optimize` with CV ID and job URL
2. Backend returns `run_id` immediately
3. Bot spawns async task to poll `GET /api/optimize/{run_id}` every 3-5 seconds
4. When status is `completed`, bot fetches PDF via `GET /api/optimize/{run_id}/pdf`
5. Bot sends PDF to user with file caption

## Telegram Payments Integration

Telegram has built-in payment system with Stripe as provider. Users pay without leaving the app.

**Subscribe (€20/month):**
```
User: /subscribe

Bot:  📦 Monthly Subscription - €20/month
      • 50 optimization requests per month
      • Priority support

      (Telegram payment button appears)

User: (completes payment in Telegram)

Bot:  ✅ Subscription activated! You now have 50 requests.
```

**Buy add-on (€5 for 10 requests):**
```
User: /buy_credits

Bot:  ➕ Request Pack - €5
      • +10 optimization requests
      • Never expires

      (Telegram payment button appears)

User: (completes payment)

Bot:  ✅ Added 10 requests! Total remaining: 57
```

**Configuration:**
- `TELEGRAM_PAYMENT_PROVIDER_TOKEN` — Stripe token for Telegram Payments

## Backend API Extensions

**New endpoints:**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/api/auth/telegram/link-code` | Generate 6-digit linking code |
| `POST` | `/api/auth/telegram/verify` | Verify code, link Telegram ID |
| `GET` | `/api/auth/telegram/user` | Get user by Telegram ID |
| `POST` | `/api/subscription/telegram-payment` | Record Telegram payment |

**Bot authentication:**
- New middleware to validate `X-Bot-Api-Key` header
- When present, look up user by `X-Telegram-User-Id` header instead of JWT
- Reject if Telegram ID not linked to any account

**Database migration:**
- Add `telegram_id BIGINT UNIQUE` to `profiles` table
- Add `telegram_link_code VARCHAR(6)` and `telegram_link_expires_at TIMESTAMP` for linking flow

## Bot Project Structure

```
telegram_bot/
├── bot/
│   ├── __init__.py
│   ├── main.py              # Entry point, bot startup
│   ├── config.py            # Settings (tokens, API URL)
│   │
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── start.py         # /start, /link, /help
│   │   ├── cvs.py           # /my_cvs, /upload_cv, /delete_cv
│   │   ├── optimize.py      # URL detection, CV selection, polling
│   │   ├── history.py       # /history
│   │   ├── subscription.py  # /status, /subscribe, /buy_credits
│   │   └── payments.py      # Telegram payment callbacks
│   │
│   ├── keyboards/
│   │   ├── __init__.py
│   │   └── inline.py        # CV selection, confirmation buttons
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── api_client.py    # httpx client for backend calls
│   │   └── polling.py       # Async optimization status polling
│   │
│   ├── middlewares/
│   │   ├── __init__.py
│   │   └── auth.py          # Check if user is linked
│   │
│   └── utils/
│       ├── __init__.py
│       └── messages.py      # Message templates
│
├── pyproject.toml           # Dependencies (aiogram, httpx, pydantic-settings)
├── Dockerfile
└── .env.example
```

## Error Handling

**Authentication errors:**
- Unlinked user tries any command → "Please link your account first. Visit {web_app_url}/settings to get a code."
- Invalid/expired link code → "This code is invalid or expired. Please generate a new one."

**Paywall errors:**
- No requests remaining → "You're out of requests! /subscribe for monthly plan or /buy_credits for a quick top-up."
- Payment fails → "Payment could not be processed. Please try again or use the web app."

**Optimization errors:**
- Job URL unreachable → "Couldn't fetch that job posting. Try pasting the job description as text instead."
- Optimization times out (>5 min) → "Optimization is taking longer than expected. Check /history later for results."
- All iterations failed → "Couldn't generate a valid resume for this job. Try a different CV or job posting."

**File handling errors:**
- Unsupported file format → "Please send a PDF, TXT, DOCX, or Markdown file."
- File too large (>10MB) → "File is too large. Maximum size is 10MB."
- CV upload fails → "Couldn't save your CV. Please try again."

**Rate limiting:**
- Bot respects backend rate limits
- If 429 received → "Too many requests. Please wait a moment."

## Testing Strategy

**Unit tests:**
- Handler logic (mocked API responses)
- Keyboard builders
- Message formatting
- URL detection regex

**Integration tests:**
- API client against real backend (test environment)
- Full optimization flow with test CV and job posting
- Payment flow with Stripe test mode

**Manual testing checklist:**
- [ ] Link account flow works
- [ ] CV upload via file attachment
- [ ] CV selection keyboard appears
- [ ] Optimization completes and PDF is delivered
- [ ] Subscription payment via Telegram
- [ ] Add-on purchase via Telegram
- [ ] Error messages display correctly
- [ ] Unlinked user gets helpful error

**Test tooling:**
- `pytest` + `pytest-asyncio` for async tests
- `aiogram`'s built-in test utilities for mocking updates
