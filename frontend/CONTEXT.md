# Frontend Context Summary

## Stack
- **Framework:** Next.js 14.2 (App Router)
- **Language:** TypeScript
- **Styling:** Tailwind CSS
- **Data Fetching:** SWR (stale-while-revalidate) + native `fetch`
- **Backend URL:** `http://localhost:8000` (hardcoded)

## Project Structure
```
app/
  layout.tsx        — Root layout (Inter font, neutral-200 bg)
  globals.css       — Tailwind imports + custom scrollbar styles
  page.tsx          — Home page: chat list + create chat
  [chatId]/
    page.tsx        — Individual chat page: message display + input
utils/
  fetcher.ts        — SWR fetcher wrapper for GET requests
```

## Key Files

### `utils/fetcher.ts`
- Wraps `fetch` for use with SWR
- Accepts `{ url: string }`, prepends `http://localhost:8000/`
- Throws `RequestError` with `info` and `status` on non-OK responses

### `app/page.tsx` — Home / Chat List
- **GET chats:** `useSWR({ url: 'chat' }, fetcher)` → renders table of chats (id, created_at)
- **Create chat:** `POST http://localhost:8000/chat` with empty body → navigates to `/${json.id}`
- Each chat row is a `<Link>` to `/{chatId}`

### `app/[chatId]/page.tsx` — Chat Window (Main interaction page)
- **State:** `input` (text input), `messages` (array of OpenAI-format messages)
- **Load chat:** `useSWR({ url: 'chat/{chatId}' }, fetcher)` → sets `messages` from `data.messages` via `useEffect`
- **Send message (`generateResponse`):**
  1. Appends user message to local state
  2. `PUT http://localhost:8000/chat/{chatId}` with `{ messages: [...] }`
  3. On success, updates `messages` from response

#### Message Display Components
| Component | Renders |
|---|---|
| `OpenAIConversationDisplay` | Maps over messages array, delegates by role |
| User messages (`role: "user"`) | Red-950 bg bubble, left-aligned |
| Assistant messages (`role: "assistant"`) | Blue-950 bg bubble, right-aligned |
| `ToolCallComponent` | Shows function name + arguments (for `tool_calls` in assistant msg) |
| `ToolResponseComponent` | Shows tool response content (for `role: "tool"`) |

### `app/layout.tsx`
- Root HTML layout, Inter font, `bg-neutral-200 text-black` on body

## ⚠️ Current Gap (Task 1 Target)
- **No form submission display:** Chat page only shows messages, no UI for form submissions
- **No API call** to fetch form submissions for a chat
- Will need: fetch form submissions for the chat and display them alongside the chat window
